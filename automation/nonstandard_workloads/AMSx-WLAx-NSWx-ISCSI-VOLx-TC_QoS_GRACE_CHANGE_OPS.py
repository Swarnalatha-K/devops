# SMGLNSN
'''
###############################################################################################################
# Testcase Name : Ocassional of IOPS, Enable/Disable Grace on Iscsi volume                                    #               
#                                                                                                             #
# Testcase Description : This test performs the following actions :                                           #
#                        a) Create iscsi volume                                                               #
#			 b) mount lun and run IOs for certain time                                            #
#                        b) take mean of latest 4 iops value (from monitor qos)                               #
#                        c) Enable grace wait for certain time and take mean of latest 4 iops value           #
#                        d) Compare IOps values and validate                                                  #
#                                                                                                             # 
# Testcase Pre-Requisites : Pool has to be created                                                            #
#                                                                                                             #
# Testcase Creation Date : 09/05/2016                                                                         #
#                                                                                                             #
# Testcase Last Modified : 11/05/2016                                                                         #  
#                                                                                                             #  
# Modifications made : None                                                                                   #  
#                                                                                                             #
# Testcase Author : Prathima                                                                                  #
###############################################################################################################
'''
# Import necessary packages and methods
import os
import sys
import json
import time
from time import ctime
import subprocess

from cbrequest import get_url, configFile, sendrequest, resultCollection, \
    get_apikey, executeCmd, getoutput
from tsmUtils import get_tsm_info, listTSMWithIP_new, tsm_creation_flow, \
    verify_tsmIP_from_configFile, delete_tsm
from volumeUtils import get_volume_info, create_volume, addNFSclient, \
    delete_volume, listVolumeWithTSMId_new, edit_qos_grace
from utils import logAndresult, mountPointDetails, assign_iniator_gp_to_LUN, \
    iscsi_login_logout, iscsi_mount_flow, updateGlobalSettings, UMain
from vdbenchUtils import executeVdbenchFile, is_vdbench_alive, kill_process
from poolUtils import pool_creation_flow, delete_pool
import logging

#***************Initialization for Logging location****************************
tcName = sys.argv[0]
tcName = tcName.split('.py')[0]
logFile = tcName + '.log'
logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',\
                 filename='logs/'+logFile,filemode='a',level=logging.DEBUG)
#*****************************************************************************
#testcase = 'Enable/Disable Grace on Iscsi volume'
logging.info('----Start of testcase "%s"----', tcName)

#***************Check proper arguments are passed******************************
if len(sys.argv) < 2:
    print "Argument are not correct, Please provide as follows"
    print "python %s.py conf.txt" %(tcName)
    logging.debug('----Ending script because of parameter mismatch----')
    exit()
#******************************************************************************

#***************Get necessary params and value from config file****************
config = configFile(sys.argv)
api_key = get_apikey(config)
stdurl = get_url(config, api_key[1])

disk_type = config["pool_disk_type"]
pool_type = config["pool_type"]
pool_iops =  config["pool_iops"]
no_of_disk = config["num_pool_disks"]
tsmIP = config['ipVSM1']
tsmInterface = config['interfaceVSM1']
acctName = config["AccountName"]
#******************************************************************************

#***************Methods Defined for this testcase******************************

##....Method Description: Collecting Qos Details of the Volume...............##
def monitorFilesystemQoS(stdurl, volid):
    querycommand = 'command=monitorFileSystemQoS&id=%s' %(volid)
    rest_api = str(stdurl) + str(querycommand)
    logging.debug('Rest Api for Monitor FS Qos : %s', str(rest_api))
    resp_FSqos = sendrequest(stdurl, querycommand)
    data = json.loads(resp_FSqos.text)
    logging.debug('Response for  Monitor FS Qos: %s', str(data))
    if 'monitorFilesystemQoS' in str(data['monitorFileSystemResponse']):
        fs_qos = data['monitorFileSystemResponse']['monitorFilesystemQoS']
        result = ['PASSED', fs_qos]
        return result
    else:
        errormsg = str(data['monitorFileSystemResponse'].get('errortext'))
        result = ['FAILED', errormsg]
        return result

##....Method Description: Collecting latest 4 Iops value of the volume,
##		          Taking Mean value for those value..................##
#..........Parameter details...........
#...fsqos => o/p of monitorFilesystemQoS method
def get_iops_value(fsqos):
    latest_qos = fsqos[-11:-1]
    logging.debug('latest monitor qos details are : %s', latest_qos)
    latest_iops = [x.get('iops') for x in latest_qos]
    latest_iops = [int(v) for v in latest_iops]
    logging.debug('latest iops values are : %s', latest_iops)
    timestamp = [y.get('timestamp') for y in latest_qos]
    logging.debug('latest time stamp taken are : %s', timestamp)
    logging.info('get mean value of IOPS taken')
    mean_iops = int(sum(latest_iops) / float(len(latest_iops)))
    return mean_iops
#******************************************************************************

#******************Updating Global Seeting*************************************
####-----------Changing Monitor Qos stats interval to 30s------------------####
logging.info('Updating monitor.qos.stats.interval to 30s')
mntr_glb = updateGlobalSettings('monitor.qos.stats.interval', 30, stdurl)
if mntr_glb[0] == 'FAILED':
    logging.error('%s', mntr_glb[1])
logging.debug('Successfully updated monitor.qos.stats.interval to 30s') 

#setting monitor.storage.stats.interval to 60s
updateGlobalSettings('monitor.storage.stats.interval', 60, stdurl)
time.sleep(2)
#******************************************************************************

#**************PREREQUSITES: POOL AND VSM CREATION*****************************

####-------------------------Pool creation---------------------------------####
startTime = ctime()
poolName = 'iPoolgrace'
pool_iops = int(pool_iops)
pool_paras = {'name': poolName, 'grouptype': pool_type, \
                'iops': pool_iops}
pool_create =  pool_creation_flow(stdurl, pool_paras, no_of_disk, disk_type)
endTime = ctime()
if pool_create[0] == 'FAILED':
    logAndresult(tcName, 'BLOCKED', pool_create[1], startTime, endTime)
logging.debug('Pool "%s" is created successfully', poolName)

####--------------------------Vsm creation---------------------------------####
startTime = ctime()
acctName = 'Account'

tsmIops = pool_iops - 50
if tsmIops <= 0:
    endTime = ctime()
    print 'pool iops should be more than 50, recommended for minimum value 100'
    logAndresult(tcName, 'BLOCKED', 'iops are less', startTime, endTime)

tsm_params = {'name': 'iTsmGrace', 'ipaddress': tsmIP, 'totaliops': tsmIops, \
        'tntinterface': tsmInterface}
tsm_create = tsm_creation_flow(stdurl, poolName, acctName, tsm_params)
endTime = ctime()
if tsm_create[0] == 'FAILED':
    logAndresult(tcName, 'BLOCKED', tsm_create[1], startTime, endTime)
logging.debug('%s', tsm_create[1])
#******************************************************************************

#***************Listing VSM and extracting IDs*********************************
startTime = ctime()
tsmList = listTSMWithIP_new(stdurl, tsmIP)
endTime = ctime()
if tsmList[0] == 'FAILED':
    logAndresult(tcName, 'BLOCKED', tsmList[1], startTime, endTime)

get_tsmInfo = get_tsm_info(tsmList[1])
tsmID = get_tsmInfo[0]
tsmName = get_tsmInfo[1]
datasetID = get_tsmInfo[2]
pool_id = tsmList[1][0].get('poolid')
account_id = tsmList[1][0].get('accountid')
logging.debug('tsm_name:%s, tsm_id:%s, dataset_id:%s', \
        tsmName, tsmID, datasetID)
#******************************************************************************

#***************************Volume Operations**********************************

####----------------------Volume Creation----------------------------------####
volIops = tsmIops/3

startTime = ctime()
vol = {'name': 'iscsiGrace' , 'tsmid': tsmID, 'datasetid': datasetID, \
        'protocoltype': 'ISCSI', 'iops': volIops, 'quotasize': '5G'}
volname = vol['name']
result = create_volume(vol, stdurl)
endTime = ctime()
if result[0] == 'FAILED':
    logAndresult(tcName, 'FAILED', result[1], startTime, endTime)
logging.debug('"%s" was created successfully',volname)

####-----------Listing Volume and getting required details-----------------####
volList = listVolumeWithTSMId_new(stdurl, tsmID)
endTime = ctime()
if volList[0] == 'FAILED':
    logAndresult(tcName, 'BLOCKED', volList[1], startTime, endTime)

get_volInfo = get_volume_info(volList[1], volname)
volid, vol_mntPoint, vol_iqn = get_volInfo[2], get_volInfo[3], get_volInfo[4]
vol_grp_id = get_volInfo[5]
logging.debug('volname: %s, volid: %s, vol_mntPoint: %s, vol_Iqn: %s',\
        volname, volid, vol_mntPoint, vol_iqn)
logging.debug('vol_grp_id: %s', vol_grp_id)

####------------Setting InitiatorGroup to All------------------------------####
startTime = ctime()
init_grp = assign_iniator_gp_to_LUN(stdurl, volid, account_id, 'ALL')
endTime = ctime()
if init_grp[0] == 'FAILED':
    logAndresult(tcName, 'BLOCKED', init_grp[1], startTime, endTime)
logging.debug('Iscsi Initiator group is set to "ALL" for the volume')

####------------Mounting Iscsi volume--------------------------------------####
volume = {'TSMIPAddress' : tsmIP, 'mountPoint': volname, 'name' : volname}
mnt_iscsi = iscsi_mount_flow(volname, tsmIP, vol_iqn, vol_mntPoint, 'ext3')
endTime = ctime()
if mnt_iscsi[0] == 'FAILED':
    logAndresult(tcName, 'BLOCKED', mnt_iscsi[1], startTime, endTime)
logging.debug('%s', mnt_iscsi[1])
device, iqn = mnt_iscsi[3], mnt_iscsi[2]
#******************************************************************************

logging.info('Iops details of pool and Volume is as follows:')
logging.info('Pool iops : %s, volume iops : %s, remaining pool iops : %s', \
        pool_iops, volIops, (pool_iops - volIops))
		
#***************Operations during Vdbench Execution****************************

####----------------Vdbench Exection---------------------------------------####
executeVdbenchFile(volume, 'filesystem_iscsi')
check_vdbench = is_vdbench_alive(volname)
time.sleep(1)
startTime = ctime()
#####--------Running Vdbench for certain time before enabling Grace--------####
logging.info('Running vdbench for certain time....')
for x in range(1, 4):
    time.sleep(60)
    check_vdbench = is_vdbench_alive(volname)
    if not check_vdbench:
        endTime = ctime()
        msg = 'Vdbench has stopped, hence cannot validate Grace feature'
        logAndresult(tcName, 'BLOCKED', msg, startTime, endTime)
x1 = x * 60
time.sleep(30)
x1 = x1 + 30
logging.info('After waiting for %s seconds, taking iops value', x1)

#####-----Taking monitor qos values of the volume before enabling Grace----####
startTime = ctime()
fsqos = monitorFilesystemQoS(stdurl, volid)
if fsqos[0] == 'FAILED':
    endTime = ctime()
    logAndresult(tcName, 'BLOCKED', fsqos[1], startTime, endTime)

####------Getting Mean value of volume iops before enabling grace----------#### 
before_grace_iops = get_iops_value(fsqos[1])
logging.debug('Before enabling grace, the iops value is: %s',before_grace_iops)

####------While Ios are running Enabling Grace for the volume--------------####
logging.info('Enabling grace....')
startTime = ctime()
grace_enable = edit_qos_grace(vol_grp_id, 'true', stdurl)
if grace_enable[0] == 'FAILED': 
    endTime = ctime()
    logAndresult(tcName, 'FAILED', grace_enable[1], startTime, endTime)

####----------Verifying Ios are running after enabling Grace---------------####
logging.info('Running vdbench for certain time....')
logging.info('Verify IOs are running after enabling grace')
check_vdbench = is_vdbench_alive(volname)
if not check_vdbench:
    endTime = ctime()
    msg = 'Vdbench has stopped after enabling grace'
    logAndresult(tcName, 'FAILED', msg, startTime, endTime)
logging.debug('Vdbench is running even after enabling grace')

#####------Running Vdbench for certain time after enabling Grace-----------####
for x in range(1, 4):
    time.sleep(60)
    check_vdbench = is_vdbench_alive(volname)
    if not check_vdbench:
        endTime = ctime()
        msg = 'Vdbench has stopped, hence cannot validate Grace feature'
        logAndresult(tcName, 'BLOCKED', msg, startTime, endTime)

x1 = x * 60
time.sleep(30)
x1 = x1 + 30
logging.info('After waiting for %s seconds, taking iops value', x1)

#####-----Taking monitor qos values of the volume after enabling Grace-----####
startTime = ctime()
fsqos = monitorFilesystemQoS(stdurl, volid)
if fsqos[0] == 'FAILED':
    endTime = ctime()
    logAndresult(tcName, 'BLOCKED', fsqos[1], startTime, endTime)

####------Getting Mean value of volume iops after enabling grace-----------####
after_grace_iops = get_iops_value(fsqos[1])
logging.debug('After enabling grace, the iops value is: %s',after_grace_iops)

####-------------------Killing the vdbench process-------------------------####
kill_process(volname)
logging.info('waiting for 10s')
time.sleep(10)
#******************************************************************************


#***************Clear Configurations*******************************************

####--------------------------Unmount lun----------------------------------####
mount_point =  getoutput('mount | grep %s | awk \'{print $3}\'' \
                     %(volume['name']))
mount_point = mount_point[0].strip('\n')
umount_other = UMain(mount_point)

umount_output = executeCmd('umount /dev/%s1' %(device))
if umount_output[0] == 'FAILED':
    logging.error('Not able to umount %s, still go ahead and delete '\
        'the Iscsi volume', volname)
else:
    logging.debug('Iscsi volume %s umounted successfully', volname)
	
####---------------------Logout from session-------------------------------####
logout_result = iscsi_login_logout(iqn, tsmIP, 'logout')
if logout_result[0] == 'FAILED':
    logging.error('%s', logout_result[1])
logging.debug('%s', logout_result[1])

####------------Setting InitiatorGroup to None-----------------------------####
logging.info('Setting initiator group to "None"')
setNone = assign_iniator_gp_to_LUN(stdurl, volid, account_id, 'None')
if setNone[0] == 'FAILED':
    logging.error('Not able to set initiator group to None, do not delete volume')
    exit()
else:
    logging.debug('Initiator group is set to "none"')

####--------------------------Volume Deletion------------------------------####
delete_result = delete_volume(volid, stdurl)
endTime = ctime()
if delete_result[0] == 'FAILED':
    logging.error('%s',delete_result[1])
    logging.error('Volume deletion failed')
    exit()
logging.debug('Volume "%s" deleted successfully', volname)

####--------------------------Vsm Deletion---------------------------------####
del_tsm = delete_tsm(tsmID, stdurl)
if del_tsm[0] == 'FAILED':
    logging.error('%s', del_tsm[1])
    logging.error('Tsm deletion failed, hence not deleting pool')
    exit()
logging.debug('%s', del_tsm[1])

####--------------------------Pool Deletion--------------------------------####
del_pool = delete_pool(pool_id, stdurl)
if del_pool[0] == 'FAILED':
    logging.error('%s', del_pool[1])
logging.debug('%s', del_pool[1])

#******************************************************************************

####----------Comparing before and after enabling grace values-------------####
if int(after_grace_iops) > int(before_grace_iops):
    logging.debug('Validated Grace, remainning Iops of pool has be used')
    endTime = ctime()
    resultCollection('%s, testcase is' %tcName, ['PASSED',' '], startTime, endTime)
else:
    #kill_process(volname)
    endTime = ctime()
    msg = 'Pool iops are not utilized even after enabling grace'
    logAndresult(tcName, 'FAILED', msg, startTime, endTime)

logging.info('----End of testcase "%s"----', tcName)

####***********************************END*********************************####
