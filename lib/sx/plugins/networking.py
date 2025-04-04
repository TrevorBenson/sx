#!/usr/bin/env python3
"""
A class that can run analyze the storage aspect of a sosreport.

@author    :  Shane Bradley
@contact   :  sbradley@redhat.com
@version   :  2.17
@copyright :  GPLv2
"""
import sys
import os
import os.path
import logging

import sx
import sx.plugins
from sx.logwriter import LogWriter
from sx.reports.sosreport import Sosreport
from sx.reports.sysreport import Sysreport
from sx.tools import StringUtil

from sx.plugins.lib.general.distroreleaseparser import DistroReleaseParser
from sx.plugins.lib.general.distroreleaseparser import DistroRelease
from sx.plugins.lib.networking.networkdeviceparser import NetworkDeviceParser
from sx.plugins.lib.networking.networkdeviceparser import NetworkMap
from sx.plugins.lib.networking.networkdeviceparser import NetworkMaps
from sx.plugins.lib.kernel.modulesparser import ModulesParser

from sx.analysisreport import AnalysisReport
from sx.analysisreport import ARSection
from sx.analysisreport import ARSectionItem
class NetworkingData:
    def __init__(self, hostname, uptime, distroRelease, uname, networkMaps):
        """
        These are all the files that we know will be present.
        """
        self.__hostname = hostname
        self.__uptime = uptime
        self.__distroRelease = distroRelease
        self.__uname = uname
        self.__networkMaps = networkMaps

    # #######################################################################
    # Get functions
    # #######################################################################
    def getHostname(self):
        """
        Returns the hostname.

        @return: Returns the hostname.
        @rtype: String
        """
        return self.__hostname

    def getUptime(self):
        """
        Returns the uptime for the cluster node.
        @return: Returns the uptime for the cluster node.
        @rtype: String
        """
        return self.__uptime

    def getDistroRelease(self):
        """
        Returns the DistroRelease Object for this node.

        @return: Returns the DistroRelease Object for this node.
        @rtype: DistroRelease
        """
        return self.__distroRelease

    def getUname(self):
        """
        Returns the data from the uname_a file.

        @return: Returns the data from the uname_a file.
        @rtype: String
        """
        return self.__uname

    def getNetworkMaps(self):
        return self.__networkMaps

    # #######################################################################
    # Helper functions
    # #######################################################################
    def getSummary(self) :
        """
        Returns a string that contain basic information within this object.

        @return: Returns a string that contain basic information
        within this object.
        @rtype: String
        """
        unameASplit = self.getUname().split()
        unameA = ""
        for i in range (0, len(unameASplit)):
            if (i == 5) :
                unameA += "\n\t      "
            unameA += "%s " %(unameASplit[i])
            i = i + 1
        summary = ""
        summary += "Hostname:     %s" %(self.getHostname())
        summary += "\nRH Release:   %s" %(self.getDistroRelease())
        summary += "\nUptime:       %s" %(self.getUptime())
        summary += "\nUname -a:     %s" %(unameA)
        return summary

class Networking(sx.plugins.PluginBase):
    """
    A class that can run analyze the networking aspect of a sosreport/sysreport.
    """
    def __init__(self, pathToPluginReportDir="") :
        """
        This init takes the root path to where the reports will be
        written. The parent class will then create the correct
        directory structure for the plugin.

        This is going to be a sosreport only plugin. There is to many
        dependencies for sos_commands/* files.

        @param pathToPluginReportDir: This is the root path to where
        the report files will be written.
        @type pathToPluginReportDir: String
        """
        sx.plugins.PluginBase.__init__(self, "Networking",
                                       "This plugin analyzes the networking data colleted from sosreports/sysreports.",
                                       ["Sosreport"], True, True, {}, pathToPluginReportDir)

        # This will contain a list of NetworkingData objects that
        # contains information found in sosreports.
        self.__listOfNetworkingData = []

    # ###########################################################################
    # Overwriting function of parent
    # ###########################################################################
    def setup(self, reports) :
        """
        This function will setup data structure to hold any data/path
        to files that are needed to use in this plugin.

        @param reports: This is the list of Report Objects.
        @type reports: Array
        """
        message = "Running setup for plugin: %s" %(self.getName())
        logging.getLogger(sx.MAIN_LOGGER_NAME).status(message)
        for report in reports:
            message = "Getting the files for the report for report with  hostname of: %s." %(report.getHostname())
            logging.getLogger(sx.MAIN_LOGGER_NAME).debug(message)

            if (self.isValidReportType(report)) :
                distroRelease = DistroReleaseParser.parseEtcRedHatReleaseRedhatReleaseData(report.getDataFromFile("etc/redhat-release"))
                # Create the network maps

                ifconfigData = report.getDataFromFile("sos_commands/networking/ifconfig_-a")
                if (ifconfigData == None):
                    ifconfigData = report.getDataFromFile("ifconfig")
                networkInterfaces = NetworkDeviceParser.parseIfconfigData(ifconfigData)
                etcHostsMap = NetworkDeviceParser.parseEtcHostsData(report.getDataFromFile("etc/hosts"))
                # Appears this is not collect on rhel6
                # modprobeConfdList = report.getDataFromDir("etc/modprobe.conf.d")
                modprobeConfCommands = ModulesParser.parseEtcModprobeConf(report.getDataFromFile("etc/modprobe.conf"))

                # Build networkmaps from all the network related information.
                networkScriptsDataMap = {}
                for networkInterface in networkInterfaces:
                    networkScriptData = report.getDataFromFile("etc/sysconfig/network-scripts/ifcfg-%s" %(networkInterface.getInterface()))
                    if (networkScriptData == None):
                        networkScriptData = None
                    networkScriptsDataMap[networkInterface.getInterface()] = networkScriptData

                # Get all the data from proc/net including the bonding data.
                procNetMap = report.getDataFromDir("proc/net")
                bondingMap = report.getDataFromDir("proc/net/bonding")
                procNetMap = {**procNetMap, **bondingMap}

                # Get all the data in the sos_commands/networking directory.
                networkingCommandsMap = report.getDataFromDir("sos_commands/networking")
                networkMaps = NetworkMaps(networkInterfaces, etcHostsMap, networkScriptsDataMap, modprobeConfCommands, procNetMap, networkingCommandsMap)
                networkingData = NetworkingData(report.getHostname(),
                                                report.getUptime(),
                                                distroRelease,
                                                report.getUname(),
                                                networkMaps)
                # Add network data for this report to the list
                self.__listOfNetworkingData.append(networkingData)

    def report(self) :
        """
        This function will write the data that was analyzed to a file.
        """
        message = "Generating report for plugin: %s" %(self.getName())
        logging.getLogger(sx.MAIN_LOGGER_NAME).status(message)

        stringUtil = StringUtil()
        if (len(self.__listOfNetworkingData) > 0):
            # Since we are going to run the plugin and create files in
            # the plugins report directory then we will first remove
            # all the existing files.
            self.clean()

        for networkingData in self.__listOfNetworkingData:
            message = "Writing the network report for: %s." %(networkingData.getHostname())
            logging.getLogger(sx.MAIN_LOGGER_NAME).debug(message)

            # could be a problem if they are all using localhost.
            ar = AnalysisReport("networking_summary-%s" %(networkingData.getHostname()), "Network Summary")
            self.addAnalysisReport(ar)
            arSectionSystemSummary = ARSection("networking-system_summary", "System Summary")
            ar.add(arSectionSystemSummary)
            arSectionSystemSummary.add(ARSectionItem(networkingData.getHostname(), networkingData.getSummary()))

            # Get all the network maps that were built.
            networkMaps = networkingData.getNetworkMaps()
            # Bonded Interface Summary
            bondedInterfaceList = networkMaps.getListOfBondedNetworkMaps()
            bondedInterfaceTable = []
            for bondedInterface in bondedInterfaceList:
                bondingNumber = bondedInterface.getBondedModeNumber()
                bondingName = bondedInterface.getBondedModeName()
                slaveInterfaces = ""
                for slaveInterface in bondedInterface.getBondedSlaveInterfaces():
                    slaveInterfaces += " %s(%s) |" %(slaveInterface.getInterface(), slaveInterface.getNetworkInterfaceModule())
                slaveInterfaces = slaveInterfaces.rstrip("|")
                bondedInterfaceTable.append([bondedInterface.getInterface(),
                                             bondingNumber, bondingName, slaveInterfaces, bondedInterface.getIPv4Address()])
            if (len(bondedInterfaceTable) > 0):
                tableHeader = ["device", "mode_#", "mode_name", "slave_interfaces", "ipv4_address"]
                arSectionBondedSummary = ARSection("networking-bonding_summary", "Bonding Summary")
                ar.add(arSectionBondedSummary)
                arSectionBondedSummary.add(ARSectionItem(networkingData.getHostname(), stringUtil.toTableString(bondedInterfaceTable, tableHeader)))

            # Bridged Inteface Summary
            bridgedInterfaceTable = []
            for networkMap in networkMaps.getListOfBridgedNetworkMaps():
                virtualBridgeNetworkMap = networkMap.getVirtualBridgedNetworkMap()
                if (not virtualBridgeNetworkMap == None):
                    bridgedInterfaceTable.append([networkMap.getInterface(), virtualBridgeNetworkMap.getInterface(),
                                                  virtualBridgeNetworkMap.getIPv4Address()])
            if (len(bridgedInterfaceTable) > 0):
                tableHeader = ["bridge_device", "virtual_bridge_device", "ipv4_addr"]
                arSectionBridgedInterfacesSummary = ARSection("networking-bridged_interfaces_summary", "Bridged Interfaces Summary")
                ar.add(arSectionBridgedInterfacesSummary)
                arSectionBridgedInterfacesSummary.add(ARSectionItem(networkingData.getHostname(), stringUtil.toTableString(bridgedInterfaceTable, tableHeader)))

            # Aliases Interface Summary
            aliasesInterfaceTable = []
            networkInterfaceAliasMap = networkMaps.getNetworkInterfaceAliasMap()
            for key in networkInterfaceAliasMap.keys():
                for key in networkInterfaceAliasMap.keys():
                    aliasInterfacesString =  ""
                    for networkMap in networkInterfaceAliasMap[key]:
                        aliasInterfacesString += " %s |" %(networkMap.getInterface())
                    aliasInterfacesString = aliasInterfacesString.rstrip("|")
                    aliasesInterfaceTable.append([key, aliasInterfacesString])

            if (len(aliasesInterfaceTable) > 0):
                tableHeader = ["device", "alias_interfaces"]
                arSectionNetworkingAliasesSummary = ARSection("networking-networking_aliases_summary", "Networking Aliases Summary")
                ar.add(arSectionNetworkingAliasesSummary)
                arSectionNetworkingAliasesSummary.add(ARSectionItem(networkingData.getHostname(), stringUtil.toTableString(aliasesInterfaceTable, tableHeader)))

            # Network Summary
            networkInterfaceTable = []
            for networkMap in networkMaps.getListOfNetworkMaps():
                networkInterfaceTable.append([networkMap.getInterface(), networkMap.getNetworkInterfaceModule(),
                                              networkMap.getHardwareAddress(), networkMap.getIPv4Address()])
            if (len(networkInterfaceTable) > 0):
                tableHeader = ["device", "module", "hw_addr", "ipv4_addr"]
                arSectionNetworkingSummary = ARSection("networking-networking_summary", "Networking Summary")
                ar.add(arSectionNetworkingSummary)
                arSectionNetworkingSummary.add(ARSectionItem(networkingData.getHostname(), stringUtil.toTableString(networkInterfaceTable, tableHeader)))
            # Wrtite the output to a file.
            self.write("%s.txt" %(ar.getName()), "%s\n" %(str(ar)))


