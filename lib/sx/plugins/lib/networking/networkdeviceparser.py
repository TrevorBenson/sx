#!/usr/bin/env python3
"""
This is a collection of classes that contain data for files from a
sosreport in the directory:
sos_commands/networking/

@author    :  Shane Bradley
@contact   :  sbradley@redhat.com
@version   :  2.17
@copyright :  GPLv2
"""
import re
import logging

import sx
from sx.logwriter import LogWriter
from sx.tools import ConfigurationFileParser
from sx.tools import SimpleUtil

# Offical naming map.
BONDING_MODES_MAP = {"-1":"unknown bonding mode", "0":"balance-rr", "1":"active-backup", "2":"balance-xor",
                     "3":"broadcast", "4":"802.3ad", "5":"balance-tlb", "6":"balance-alb"}
# These are for nomes defined, for example in proc/net/bonding the
# names are different than the official names.
BONDING_MODE_NAMES_MAP = {"unknown bonding mode":"-1", "load balancing (round-robin)":"0",
                          "balance-rr":"0", "active-backup":"1", "balance-xor":"2",
                          "broadcast":"3", "802.3ad":"4", "balance-tlb":"5", "balance-alb":"6"}


class NetworkDeviceParser:
    def parseEtcHostsData(etcHostsData):
        """
        This function generates a map of all the ip to hostnames in
        the /etc/hosts file.

        The key is the ip and its value is an array of hostnames.

        @return: Returns a dictionary of the ip to hostnames in the
        file /etc/hosts.
        @rtype: Dictionary
        """
        etcHostsMap = {}
        if (etcHostsData == None):
            return etcHostsMap

        ipRegex = r"(?:[\d]{1,3})\.(?:[\d]{1,3})\.(?:[\d]{1,3})\.(?:[\d]{1,3})"
        rem = re.compile(r"(%s)\s(.*)" %(ipRegex))
        for line in etcHostsData:
            # Remove any new line garabage.
            line = line.strip()
            # Skip all the comments.
            if (line.startswith("#")):
                continue
            # Now try and do the match with clean /etc/hosts data.
            mo = rem.match(line)
            if mo:
                ipAddress = mo.group(1).strip()
                hostnames = mo.group(2).strip()

                # Strip out any comments that are on a valid line
                # because they are not hostnames.
                hostnamesNoComments = hostnames.split("#")[0]
                hostnamesNoComments = hostnamesNoComments.split()
                # If the key is already in map then just combine the arrays.
                if ipAddress in etcHostsMap:
                    etcHostsMap[ipAddress] = (etcHostsMap[ipAddress] + hostnamesNoComments)
                else:
                     etcHostsMap[ipAddress] = hostnamesNoComments
        return etcHostsMap
    parseEtcHostsData = staticmethod(parseEtcHostsData)

    def parseIPAddressData(ip_addressData):
        networkInterfaces = []
        if (ip_addressData == None):
            return networkInterfaces

        # 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 16436 qdisc noqueue
        remIface = re.compile(r"([0-9].*): (?P<interface>.*): <(?P<listOfStates>.*)> mtu (?P<mtu>[0-9]?[0-9]?[0-9]?[0-9]?[0-9]?[0-9]) (?P<otherOptions>.*)")
        remLink = re.compile(r"link/(?P<interfaceType>loopback|ether) (?P<hwAddr>[0-9a-zA-Z\:].*) brd (?P<brd>[0-9a-zA-Z\:])")
        remInet = re.compile(r"inet (?P<ipv4Address>([\d\.]*))/(?P<subnetMask>([\d\.]*)) .*")
        for index in range(0, len(ip_addressData)):
            # A counter that will increment on each regex that finds a
            # match.
            moIface = remIface.search(ip_addressData[index].strip())
            if (moIface):
                interface = moIface.group("interface")
                listOfStates = moIface.group("listOfStates").split(",")
                mtu = moIface.group("mtu")
                otherOptions = moIface.group("otherOptions").split(" ")

                hwAddr = ""
                for nextIndex in range((index + 1), len(ip_addressData)):
                    currentLine = ip_addressData[nextIndex].strip()
                    nextMoIface = remIface.search(currentLine)
                    if (nextMoIface):
                        break
                    else:
                        moLink = remLink.search(currentLine)
                        moInet = remInet.search(currentLine)
                        if (moLink):
                            hwAddr = moLink.group("hwAddr")
                        elif (moInet):
                            ipv4Addr = moInet.group("ipv4Address")
                            subnetMask = moInet.group("subnetMask")
                            networkInterfaces.append(NetworkInterface(interface, hwAddr, ipv4Addr, subnetMask, listOfStates, mtu))
        return networkInterfaces
    parseIPAddressData = staticmethod(parseIPAddressData)

    def parseIfconfigData(ifconfigData) :
        """
        This function generates a NetworkMap of all the interfaces. It
        will return an array of NetworkMap Objects. Loopback and sitX
        will not be mapped.

        Information about ifconfig output:
        http://linux-ip.net/html/tools-ifconfig.html#tools-ifconfig-output

        @return: Returns an array of NetworkMap objects.
        @rtype: Array
        """
        networkInterfaces = []
        if (ifconfigData == None):
            return networkInterfaces
        # Does english and spanish currently.
        remIface = re.compile(r"(.*)Link.*HW.*\s([0-9a-zA-Z\:].*)")
        remLoopback = re.compile(r"(.*)Link encap:(Local Loopback.*|Loopback Local.*)")
        remIPV4Addr  = re.compile(r".*(inet addr|inet end.):\s?([\d\.]*)\s.*(Mask|Masc):([\d\.]*)")

        remIPV6Addr  = re.compile(r".*inet6 addr:.*|en.*inet6:")
        remMTUMetric = re.compile(r"(?P<states>.*)  MTU:(?P<mtu>.*)  M.*:(?P<metric>.*).*")
        for index in range(0, len(ifconfigData)):
            # A counter that will increment on each regex that finds a
            # match.
            nextLineCounter = 0
            interface = ""
            hwAddr = ""

            moIface = remIface.match(ifconfigData[index + nextLineCounter].strip())
            moLoopback = remLoopback.match(ifconfigData[index + nextLineCounter].strip())
            if (moIface):
                interface = moIface.group(1).strip()
                hwAddr = moIface.group(2).strip()
                nextLineCounter = nextLineCounter + 1
            elif (moLoopback):
                interface = moLoopback.group(1).strip()
                hwAddr = ""
                nextLineCounter = nextLineCounter + 1
            # If there was an interface found.
            if (len(interface) > 0):
                # Go ahead and define these with defaults because not
                # all of these values will be found in output.
                ipv4Addr = ""
                subnetMask = ""
                listOfStates = []
                mtu = -1
                # metric = -1

                # Get the next line
                nextLine = ifconfigData[index + nextLineCounter].strip()
                moIPV4Addr  = remIPV4Addr.match(nextLine)
                if (moIPV4Addr):
                    ipv4Addr = moIPV4Addr.group(2).strip()
                    subnetMask = moIPV4Addr.group(4).strip()
                    nextLineCounter = nextLineCounter + 1
                    nextLine = ifconfigData[index + nextLineCounter].strip()
                moIPV6Addr = remIPV6Addr.match(nextLine)
                if (moIPV6Addr):
                    nextLineCounter = nextLineCounter + 1
                    nextLine = ifconfigData[index + nextLineCounter].strip()
                moMTUMetric = remMTUMetric.match(nextLine)
                if (moMTUMetric):
                    listOfStates = moMTUMetric.group("states").split()
                    mtu = int(moMTUMetric.group("mtu"))
                    #metric = int(moMTUMetric.group("metric"))

                # Add the map since we have interface for the map.
                networkInterfaces.append(NetworkInterface(interface, hwAddr, ipv4Addr, subnetMask, listOfStates, mtu))
        return networkInterfaces
    parseIfconfigData = staticmethod(parseIfconfigData)

    def parseEtcSysconfigNetworkScript(networkScriptData):
        networkScriptMap = {}
        if (networkScriptData == None):
            return networkScriptMap
        configFileParser = ConfigurationFileParser(networkScriptData, {}, enforceEmptyValues=False)
        networkScriptMap = configFileParser.getMap()
        return networkScriptMap
    parseEtcSysconfigNetworkScript = staticmethod(parseEtcSysconfigNetworkScript)

    def parseEthtoolIData(ethtoolIData):
        ethtoolIDataMap = {}
        if (ethtoolIData == None):
            return ethtoolIDataMap
        for line in ethtoolIData:
            lineSplit = line.split(":")
            if (len(lineSplit) == 2):
                ethtoolIDataMap[lineSplit[0]] = lineSplit[1].strip()
        return ethtoolIDataMap
    parseEthtoolIData = staticmethod(parseEthtoolIData)

# ###########################################################################
# Network Objects
# ###########################################################################
class NetworkInterface:
    """
    Container for network information for network information.
    """
    def __init__(self, interface, hwAddr, ipv4Addr, subnetMask, listOfStates, mtu):
        """
        @param interface: The network interface.
        @type interface: String
        @param hwAddr: The hardware address
        @type hwAddr: String
        @param ipv4Addr: The ip address.
        @type ipv4Addr: String
        @param subnetMask: The subnet mask.
        @type subnetMask: String
        @param listOfStates: The list of states for
        interface.
        @type listOfStates: Array
        @param mtu: The mtu for the interface.
        @type mtu: Int
        """
        self.__interface = interface
        self.__hwAddr = hwAddr
        self.__ipv4Addr = ipv4Addr
        if ((not subnetMask.find(".") > 0) and (len(subnetMask) > 0)):
            self.__subnetMask = self.__convertCIDRToDotDecimal(subnetMask)
        else:
            self.__subnetMask = subnetMask
        self.__listOfStates = listOfStates
        self.__mtu = mtu

    def __str__(self):
        ip = self.getIPv4Address()
        smask = self.getSubnetMask()
        rString = "%s" %(self.getInterface())
        if (len(ip) > 0):
            rString += ": %s" %(ip)
            if (len(smask) > 0):
                rString += "/%s" %(smask)
        return rString

    def __convertCIDRToDotDecimal(self, subnetMask):
        subnetMask = SimpleUtil.castInt(subnetMask)
        if (not subnetMask == None):
            bits = 0
            for i in xrange(32-subnetMask,32):
                bits |= (1 << i)
            return "%d.%d.%d.%d" % ((bits & 0xff000000) >> 24, (bits & 0xff0000) >> 16, (bits & 0xff00) >> 8 , (bits & 0xff))
        return ""

    def getInterface(self):
        """
        Returns the network interface.

        @return: Returns the network interface.
        @rtype: String
        """
        return self.__interface

    def getHardwareAddress(self) :
        """
        Returns the Hardware address of this interface.

        @return: Returns the Hardware address of this interface.
        @rtype: String
        """
        return self.__hwAddr

    def getIPv4Address(self):
        """
        Returns the IPv4 address of this interface.

        @return: Returns the IPv4 address of this interface.
        @rtype: String
        """
        return self.__ipv4Addr

    def getSubnetMask(self) :
        """
        Returns the subnet mask of this interface.

        @return: Returns the subnet mask of this interface.
        @rtype: String
        """
        return self.__subnetMask

    def getListOfStates(self) :
        """
        Returns an array of all the states assoicated with this
        interface.

        @return: Returns an array of all the states assoicated with
        this interface.
        @rtype: Array
        """
        return self.__listOfStates

    def getMTU(self) :
        """
        Returns an int for mty for this interface. A -1 will mean an
        mtu was not found.

        @return: Returns an int for the mtu.
        @rtype: Int
        """
        return self.__mtu

class NetworkMap(NetworkInterface):
    """
    Container for network information for network information.
    """
    def __init__(self, interface, hwAddr, ipv4Addr, subnetMask, listOfStates, mtu,
                 etcHostsMap, networkScriptMap, modprobeConfCommands, procNetMap,
                 networkingCommandsMap):
        # If interface is not found, but sysconfig file has data then search it.
        if (not len(ipv4Addr) > 0):
            if "IPADDR" in networkScriptMap:
                if (len(networkScriptMap.get("IPADDR")) > 0):
                    ipv4Addr = networkScriptMap.get("IPADDR")
        if (not len(subnetMask) > 0):
            if "NETMASK" in networkScriptMap:
                if (len(networkScriptMap.get("NETMASK")) > 0):
                    subnetMask = networkScriptMap.get("NETMASK")
        if (not len(hwAddr) > 0):
            if "HWADDR" in networkScriptMap:
                if (len(networkScriptMap.get("HWADDR")) > 0):
                    hwAddr = networkScriptMap.get("HWADDR")

        NetworkInterface.__init__(self, interface, hwAddr, ipv4Addr,
                                  subnetMask, listOfStates, mtu)
        self.__etcHostsMap = etcHostsMap
        # What if there is quotes in the values. that is a problem on
        # compares.
        self.__networkScriptMap = networkScriptMap
        self.__modprobeConfCommands = modprobeConfCommands
        self.__procNetMap = procNetMap
        self.__networkingCommandsMap = networkingCommandsMap
        self.__hostnames = []
        if self.getIPv4Address() in self.__etcHostsMap:
            self.__hostnames = self.__etcHostsMap.get(self.getIPv4Address())
        # Bonded options
        self.__bondedModeNumber = None
        self.__listOfBondedSlaveInterfaces = []
        # Parent alias network map
        self.__parentAliasNetworkMap = None
        # Bridging
        self.__virtualBridgedNetworkMap = None

    def __str__(self) :
        """
        This function returns a string reprenstation of the object.

        @return: Returns a string reprenstation of the object.
        @rtype: String
        """
        returnString = ""
        returnString += "interface:         %s\n" % (self.getInterface())
        if (len(self.getNetworkInterfaceModule()) > 0):
            returnString += "module:            %s\n" % (self.getNetworkInterfaceModule())
        if (len(self.getHardwareAddress()) > 0):
            returnString += "hw address:        %s\n" % (self.getHardwareAddress())
        if (len(self.getIPv4Address()) > 0):
            returnString += "ipv4 address:      %s\n" % (self.getIPv4Address())
        return returnString


    # ###########################################################################
    # Helper functions
    # ###########################################################################
    def __getEthToolIMap(self):
        ethtoolIMap = {}
        networkingCommandsMap = self.getNetworkingCommandsMap()
        for key in networkingCommandsMap.keys():
            if (key.startswith("ethtool_-i_")):
                newKey = key.replace("ethtool_-i_", "")
                newValue = NetworkDeviceParser.parseEthtoolIData(networkingCommandsMap.get(key))
                ethtoolIMap[newKey] = newValue
        return ethtoolIMap

    def __getEthToolIDeviceMap(self, interface):
        ethtoolIMap = self.__getEthToolIMap()
        if interface in ethtoolIMap:
            return ethtoolIMap.get(interface)
        return {}

    # ###########################################################################
    # Is functions
    # ###########################################################################
    def hasHostnameMapped(self, hostname) :
        # Returns True if a particular hostname is in the /etc/hosts
        # file. The hostname does not have to be associated with this
        # particular interface.
        for key in self.getEtcHostsMap().keys():
            if (hostname in self.getEtcHostsMap().get(key)):
                return True
        return False

    def isOnBootEnabled(self):
        if "ONBOOT" in self.getNetworkScriptMap():
            if self.getNetworkScriptMap().get("ONBOOT") == "yes":
                return True
        return False
        
    # ###########################################################################
    # Get functions
    # ###########################################################################
    def getEtcHostsMap(self):
        """
        This returns a map of all the entries in /etc/hosts. The key
        is the ip and value is list of hostnames.

        @return: Returns a dictionary of all the entries in
        /etc/hosts.
        @rtype: Dictionary
        """
        return self.__etcHostsMap

    def getHostnames(self) :
        """
        Returns an array of all the hostnames assoicated with this
        interface.

        @return: Returns an array of all the hostnames assoicated with
        this interface.
        @rtype: Array
        """
        return self.__hostnames

    def getNetworkScriptMap(self):
        return self.__networkScriptMap

    def getModprobeConfCommands(self):
        return self.__modprobeConfCommands

    def getProcNetMap(self):
        return self.__procNetMap

    def getNetworkingCommandsMap(self):
        return self.__networkingCommandsMap

    def getBootProtocal(self):
        bootProtocal = ""
        if "BOOTPROTO" in self.getNetworkScriptMap():
            bootProtocal = self.getNetworkScriptMap().get("BOOTPROTO")
            if (bootProtocal.lower() == "none"):
                # If bootproto is none and they have set IPADDR then
                # they are using static ip addressing.
                if "IPADDR" in self.getNetworkScriptMap():
                    if (len(self.getNetworkScriptMap().get("IPADDR")) > 0):
                        bootProtocal = "static"
        return bootProtocal

    def getNetworkInterfaceModule(self):
        for modprobeCommand in self.getModprobeConfCommands():
            # Example: alias eth3 be2net
            if ((modprobeCommand.getCommand() == "alias") and
                (modprobeCommand.getWildCard() == self.getInterface())):
                return modprobeCommand.getModuleName()

        ethtoolIDeviceMap = self.__getEthToolIDeviceMap(self.getInterface())
        if "driver" in ethtoolIDeviceMap:
            return ethtoolIDeviceMap.get("driver")
        # There is no module loaded for the loopback interface and I have
        # verified this.
        # if ((self.getInterface() == "lo") and (self.getIPv4Address() == "127.0.0.1")):
        #    return "Loopback"
        return ""
    # ###########################################################################
    # Bonded functions
    # ###########################################################################
    def isBondedMasterInterface(self):
        # In RHEL 6 we have changing how modprobe.conf works and I
        # dont think sosreport is currently collecting that dir
        # modprobe.conf.d. As work around for detection then only
        # require there is bonding mode.
        return ((self.getNetworkInterfaceModule().lower() == "bonding") or
                (int(self.getBondedModeNumber()) >= 0))

    def isBondedSlaveInterface(self):
        print(self.getNetworkScriptMap().keys())
        if "SLAVE" in self.getNetworkScriptMap():
            return ((self.getNetworkScriptMap().get("SLAVE").lower() == "yes") and
                    (len(self.getBondedMasterInterface()) > 0))
        return False

    def addBondedSlaveInterfaces(self, slaveInterface):
        for currentSI in self.__listOfBondedSlaveInterfaces:
            if (slaveInterface.getInterface() == currentSI.getInterface()):
                return
        self.__listOfBondedSlaveInterfaces.append(slaveInterface)

    def getBondedMasterInterface(self):
        if "MASTER" in self.getNetworkScriptMap():
            return self.getNetworkScriptMap().get("MASTER")
        return ""

    def getBondedSlaveInterfaces(self):
        return self.__listOfBondedSlaveInterfaces

    def getBondedOptions(self):
        interfaceAlias = ""
        for modprobeCommand in self.getModprobeConfCommands():
            if (modprobeCommand.getCommand().lower() == "alias"):
                if (modprobeCommand.getWildCard().lower() == self.getInterface().lower()):
                    interfaceAlias = modprobeCommand.getModuleName()

        bondingOptions = ""
        if "BONDING_OPTS" in self.getNetworkScriptMap():
            bondingOptions = self.getNetworkScriptMap().get("BONDING_OPTS")
        for modprobeCommand in self.getModprobeConfCommands():
            if (modprobeCommand.getCommand().lower() == "options"):
                if ((modprobeCommand.getModuleName().lower() == self.getInterface().lower()) or
                    (modprobeCommand.getModuleName().lower() == interfaceAlias)):
                    for option in modprobeCommand.getModuleOptions():
                        bondingOptions += " %s" %(option)
        return bondingOptions.strip()

    def getBondedModeNumber(self):
        if (self.__bondedModeNumber == None):
            self.__bondedModeNumber = "-1"
            bondingOptions = self.getBondedOptions()
            bondingOptionsSplit = bondingOptions.split()
            for option in bondingOptionsSplit:
                optionSplit = option.split("=")
                if (len(optionSplit) == 2):
                    if (optionSplit[0].lower() == "mode"):
                        bondingMode = optionSplit[1]
                        for key in BONDING_MODES_MAP.keys():
                            value = BONDING_MODES_MAP.get(key)
                            if (bondingMode == key or bondingMode == value):
                                # Set number
                                self.__bondedModeNumber = key
                                return self.__bondedModeNumber
            if int(self.__bondedModeNumber) <= 0 and self.getInterface() in self.__procNetMap:
                bondingData = self.__procNetMap.get(self.getInterface())
                for line in bondingData:
                    lineSplit = line.split(":")
                    if ((len(lineSplit) >= 2) and lineSplit[0].startswith("Bonding Mode")):
                        bondingModeName = lineSplit[1].strip().rstrip("\n")
                        if bondingModeName in BONDING_MODE_NAMES_MAP:
                            self.__bondedModeNumber = BONDING_MODE_NAMES_MAP.get(bondingModeName)
        return self.__bondedModeNumber

    def getBondedModeName(self):
        bondedModeNumber = self.getBondedModeNumber()
        if bondedModeNumber in BONDING_MODES_MAP:
            return BONDING_MODES_MAP[bondedModeNumber]
        return ""

    # ###########################################################################
    # Alias functions
    # ###########################################################################
    def getParentAliasNetworkMap(self):
        return self.__parentAliasNetworkMap

    def setParentAliasNetworkMap(self, networkMap):
        self.__parentAliasNetworkMap = networkMap

    # ###########################################################################
    # Bridge functions
    # ###########################################################################
    def isBridgedInterface(self):
        if "BRIDGE" in self.getNetworkScriptMap():
            return (len(self.getNetworkScriptMap().get("BRIDGE").lower()) > 0)
        return False

    def isVirtualBridgedInterface(self):
        if "TYPE" in self.getNetworkScriptMap():
            return (self.getNetworkScriptMap().get("TYPE").lower() == "bridge")
        return False

    def getVirtualBridgedInterface(self):
        if "BRIDGE" in self.getNetworkScriptMap():
            return self.getNetworkScriptMap().get("BRIDGE")
        return ""

    def getVirtualBridgedNetworkMap(self):
        return self.__virtualBridgedNetworkMap

    def setVirtualBridgedNetworkMap(self, networkMap):
        self.__virtualBridgedNetworkMap = networkMap

class NetworkMaps:
    def __init__(self, networkInterfaces, etcHostsMap, networkScriptsDataMap, modprobeConfCommands, procNetMap, networkingCommandsMap):
        self.__networkInterfaces = networkInterfaces
        self.__etcHostsMap = etcHostsMap
        self.__modprobeConfCommands = modprobeConfCommands
        self.__networkScriptsDataMap = networkScriptsDataMap
        self.__procNetMap = procNetMap
        self.__networkCommandsMap = networkingCommandsMap
        # Map and list of all the network maps. Keep the map around
        # for now cause might be useful later.
        self.__mapOfNetworkMaps = self.__buildNetworkMaps()

    def __str__(self):
        rstring  = ""
        for networkMap in self.getListOfNetworkMaps():
            rstring += "%s\n" %(str(networkMap))
        return rstring

    def __buildNetworkMaps(self):
        mapOfNetworkMaps = {}
        for networkInterface in self.__networkInterfaces:
            #print networkInterface.getInterface()
            networkScriptMap = NetworkDeviceParser.parseEtcSysconfigNetworkScript(self.__networkScriptsDataMap.get(networkInterface.getInterface()))
            if networkInterface.getInterface() not in mapOfNetworkMaps:
                networkMap = NetworkMap(networkInterface.getInterface(),
                                        networkInterface.getHardwareAddress(),
                                        networkInterface.getIPv4Address(),
                                        networkInterface.getSubnetMask(),
                                        networkInterface.getListOfStates(),
                                        networkInterface.getMTU(),
                                        self.__etcHostsMap,
                                        networkScriptMap,
                                        self.__modprobeConfCommands,
                                        self.__procNetMap,
                                        self.__networkCommandsMap)
                mapOfNetworkMaps[networkInterface.getInterface()] = networkMap
        # After Maps are created then set the bonding interface for any of them.
        # print "CHECK THAT USE CASE FOR WHEN NETWORKING HAS NO IPS. Problem is ifconfig data does not contain the bond0 that is not up."
        for key in mapOfNetworkMaps.keys():
            masterBondedInterface = mapOfNetworkMaps[key].getBondedMasterInterface().replace("\"", "")
            if masterBondedInterface in mapOfNetworkMaps:
                mapOfNetworkMaps[masterBondedInterface].addBondedSlaveInterfaces(mapOfNetworkMaps[key])

        # Set all the parent aliases if there is one.
        for key in mapOfNetworkMaps.keys():
            currentNetworkMap = mapOfNetworkMaps[key]
            interfaceNameSplit = currentNetworkMap.getInterface().split(".")
            if len(interfaceNameSplit) == 2 and interfaceNameSplit[0] in mapOfNetworkMaps:
                currentNetworkMap.setParentAliasNetworkMap(mapOfNetworkMaps.get(interfaceNameSplit[0]))
            else:
                interfaceNameSplit = currentNetworkMap.getInterface().split(":")
                if len(interfaceNameSplit) == 2 and interfaceNameSplit[0] in mapOfNetworkMaps:
                    currentNetworkMap.setParentAliasNetworkMap(mapOfNetworkMaps.get(interfaceNameSplit[0]))

        # Add any virtual bridge devices to any bridge interfaces.
        for key in mapOfNetworkMaps.keys():
            virtualBridgeInterface = mapOfNetworkMaps[key].getVirtualBridgedInterface()
            if virtualBridgeInterface in mapOfNetworkMaps:
                mapOfNetworkMaps[key].setVirtualBridgedNetworkMap(mapOfNetworkMaps[virtualBridgeInterface])
        return mapOfNetworkMaps

    def getListOfNetworkMaps(self):
        # Assuming self.networkMaps is the dictionary of network maps
        listOfNetworkMaps = list(self.__mapOfNetworkMaps.values())
        listOfNetworkMaps.sort(key=lambda m: m.getInterface())
        return listOfNetworkMaps

    def getListOfBondedNetworkMaps(self):
        listOfBondedNetworkMaps = []
        for networkMap in self.getListOfNetworkMaps():
            if (networkMap.isBondedMasterInterface()):
                listOfBondedNetworkMaps.append(networkMap)
        listOfBondedNetworkMaps.sort(key=lambda m: m.getInterface())
        # print "MAP: ", map(lambda m: m.getInterface(), listOfBondedNetworkMaps)
        return listOfBondedNetworkMaps

    def getListOfBridgedNetworkMaps(self):
        listOfBridgedNetworkMaps = []
        for networkMap in self.getListOfNetworkMaps():
            if (networkMap.isBridgedInterface()):
                listOfBridgedNetworkMaps.append(networkMap)
        listOfBridgedNetworkMaps.sort(key=lambda m: m.getInterface())
        return listOfBridgedNetworkMaps

    def getNetworkInterfaceAliasMap(self):
        networkInterfaceAliasMap = {}
        for networkMap in self.getListOfNetworkMaps():
            parentAliasNetworkMap = networkMap.getParentAliasNetworkMap()
            if (not parentAliasNetworkMap == None):
                currentInterface = parentAliasNetworkMap.getInterface()
                if (currentInterface in networkInterfaceAliasMap.keys()):
                    networkInterfaceAliasMap[currentInterface].append(networkMap)
                else:
                    networkInterfaceAliasMap[currentInterface] = [networkMap]
        return networkInterfaceAliasMap


