#!/usr/bin/env python
"""

This plugin is documented here:
- https://fedorahosted.org/sx/wiki/SX_clusterplugin

@author    :  Shane Bradley
@contact   :  sbradley@redhat.com
@version   :  2.11
@copyright :  GPLv2
"""
import re
import os.path
import logging
import textwrap

import sx
from sx.tools import StringUtil
from sx.logwriter import LogWriter
from sx.plugins.lib.clusterha.clusterhaconfanalyzer import ClusterHAConfAnalyzer
from sx.plugins.lib.clusterha.clusternode import ClusterStorageFilesystem

# For finding quorum disk.
from sx.plugins.lib.storage.devicemapperparser import DeviceMapperParser
from sx.plugins.lib.storage.devicemapperparser import DMSetupInfoC
from sx.plugins.lib.storage.lvm import LVM
from sx.plugins.lib.clusterha.clustercommandsparser import ClusterCommandsParser

class ClusterHAStorage():
    def __init__(self, cnc):
        self.__cnc = cnc
        # Seperator between sections:
        self.__seperator = "-------------------------------------------------------------------------------------------------"

    def getClusterNodes(self):
        return self.__cnc

    # #######################################################################
    # Evaluate Function
    # #######################################################################
    def evaluate(self):
        # Return string for evaluation.
        rString = ""
        # Nodes that are in cluster.conf, so should have report of all these
        baseClusterNode = self.__cnc.getBaseClusterNode()
        if (baseClusterNode == None):
            # Should never occur since node count should be checked first.
            return ""
        cca = ClusterHAConfAnalyzer(baseClusterNode.getPathToClusterConf())
        filename = "%s-storage_summary.txt" %(cca.getClusterName())
        # ###################################################################
        # Get the GFS/GFS2 storage summary
        # ###################################################################
        result = self.__cnc.getClusterStorageSummary()
        if (len(result) > 0):
            sectionHeader = "%s\nGFS and GFS2 Filesystem Summary\n%s" %(self.__seperator, self.__seperator)
            rString += "%s\n%s\n\n" %(sectionHeader, result)
        # ###################################################################
        # Get the fs.sh resources and write summary
        # ###################################################################
        result = ""
        fsListHeader = ["device", "mount_point", "fs_type"]
        stringUtil = StringUtil()

        fsTable = []
        filesystemResourcesList = cca.getFilesystemResourcesList()
        if (len(filesystemResourcesList) > 0):
            for clusterConfMount in filesystemResourcesList:
                currentFS = [clusterConfMount.getDeviceName(), clusterConfMount.getMountPoint(), clusterConfMount.getFSType()]
                if (not currentFS in fsTable):
                    fsTable.append(currentFS)
        if (len(fsTable) > 0):
            # Should flag for vgs with no c bit set and no lvm on device path.
            stringUtil = StringUtil()
            sectionHeader =  "%s\nFilesystem and Clustered-Filesystem cluster.conf Summary\n%s" %(self.__seperator, self.__seperator)
            tableHeader = ["device_name", "mount_point", "fs_type"]
            tableOfStrings = stringUtil.toTableString(fsTable, tableHeader)
            rString += "%s\n%s\n\n" %(sectionHeader, tableOfStrings)

        # ###################################################################
        # Write summary of status of HALVM and CLVM
        # ###################################################################
        lvmSummary = ""
        for clusternode in self.__cnc.getClusterNodes():
            devicemapperCommandsMap =  self.__cnc.getStorageData(clusternode.getClusterNodeName()).getDMCommandsMap()
            lvm = LVM(DeviceMapperParser.parseVGSVData(devicemapperCommandsMap.get("vgs_-v")),
                      DeviceMapperParser.parseLVSAODevicesData(devicemapperCommandsMap.get("lvs_-a_-o_devices")),
                      self.__cnc.getStorageData(clusternode.getClusterNodeName()).getLVMConfData())
            currentSummary =""
            lockingType = lvm.getLockingTypeValue()
            currentSummary += "  locking_type: %s\n" %(lockingType)

            volume_list = lvm.getVolumeListValues()
            volumesListValues = ""
            for item in volume_list:
               volumesListValues += "%s |" %(item)
            volumesListValues = volumesListValues.rstrip("|")
            currentSummary += "  volume_list: %s\n\n" %(volumesListValues)

            # Check to see clvmd is enabled at boot.
            serviceName = "clvmd"
            serviceStatus = ""
            for chkConfigItem in clusternode.getChkConfigList():
                if (chkConfigItem.getName() == serviceName):
                    serviceStatus = chkConfigItem.getRawStatus()
            if (len(serviceStatus) > 0):
                currentSummary += "  The service \"clvmd\" was found and the runlevel status is below:\n    %s\n" %(serviceStatus)
            else:
                currentSummary += "  The service \"clvmd\" was not found for the package \"lvm2-cluster\".\n"

            # Add current summary to lvm summary
            if (len(currentSummary) > 0):
                lvmSummary += "%s:\n%s\n" %(clusternode.getClusterNodeName(), currentSummary)
        # List the first 10 vgs and will have to search each report till all the
        # information is found on them. This means taking all the filesystems in
        # cluster.conf, finding vg informaiton on the first 10 found then add to
        # lvm summary. The goal is to print vgs and all the bit set so that you
        # will know if clustered but dont want to spam the report file.


        # Add lvm summary to return string.
        if (len(lvmSummary) > 0):
            sectionHeader = "%s\nLVM Summary\n%s" %(self.__seperator, self.__seperator)
            message = "If there are no values for some options then possible that they are commented out or the files\nfor option was not found."
            rString += "%s\n%s\n\n%s\n\n" %(sectionHeader, message, lvmSummary)
        return rString.rstrip()
