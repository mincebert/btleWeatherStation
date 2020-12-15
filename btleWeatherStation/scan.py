# btleWeatherStation.scan


"""Scan for weather stations.
"""



import logging

from bluepy import btle



# WEATHERSTATION_NAMES = list
#
# A default list of names to match weather stations with, by running a
# BtLE scan looking for devices with one of these names at the GAP
# Complete Local Name field.

WEATHERSTATION_NAMES = ("IDTW211R", "IDTW213R")



class _WeatherStationScanDelegate(btle.DefaultDelegate):
    """This class handles discovery of weather station devices by
    responding to notifications from a scan of BtLE devices.  An
    instance of this class should be used with btle.Scanner().-
    withDelegate().

    After a scan being run, the names of the discovered devices can be
    retrieved with getDevices().
    """


    def __init__(self, names=WEATHERSTATION_NAMES):
        """The construction stores the list of weather station device
        names to be searched for and initialises the list of found
        weather stations to empty.

        names=WEATHERSTATION_NAMES -- a list of strings of weather
        station device names (as reported by Generic Access Profile
        [GAP] field 0x09 - Complete Local Name).  The default value for
        this is a list of known names of weather stations.
        """

        super().__init__()

        # store the list of names
        self._names = names

        # initialise the list of found devices to empty - this is a
        # dictionary with keys as the MAC addresses and values as the
        # names (GAP Complete Local Name)
        self._devices = {}


    def getDevices(self):
        """Return the list of found devices as a dictionary, with the
        device MAC addresses as the keys and the values as the names,
        as returned in the GAP Complete Local Name field.

        The returned dictionary must not be modified in place; if this
        is to be done, it must be copy()ed first.
        """

        return self._devices


    def handleDiscovery(self, dev, isNewDev, isNewData):
        """This method is callbacked when a notification is received,
        in response to a scan.

        This will check the name field (GAP Complete Local Name) and,
        if the name matches one of those in the list supplied, it will
        be added to the list of found devices to be retrieved with
        getDevices().
        """


        # get the GAP Complete Local Name field

        name = dev.getValueText(btle.ScanEntry.COMPLETE_LOCAL_NAME)


        # if the name matches one of the ones being searched for, add
        # it to the found list

        if name in self._names:
            logging.debug("discovered weather station: %s name: %s",
                          dev.addr, name)

            self._devices[dev.addr] = name

        else:
            logging.debug("ignoring unknown device: %s name: %s",
                          dev.addr, name)



def scan(names=WEATHERSTATION_NAMES, timeout=2.0):
    """This function scans for devices via BtLE, looking for weather
    stations.  These are identified by the GAP Complete Local Name
    (0x09) field in the scan notification - it must match one of the
    listed names.

    The returned value is a dictionary with the keys as the MAC
    addresses of the found weather stations and the values as the names
    (as per GAP Complete Local Name) or None, if there was a problem
    doing the scan.  This list must not be modified in place but
    copy()ed first, if it is going to be changed.

    names=WEATHERSTATION_NAMES -- the list of names in the GAP
    Complete Local Name to match.

    timeout=2.0 -- the timeout before scanning stops, in seconds.
    """


    # create a scan delegate

    scan_delegate = _WeatherStationScanDelegate(names)


    # do the scan

    logging.debug("scan starting")
    scanner = btle.Scanner().withDelegate(scan_delegate)

    try:
        scanner.scan(timeout)
    except btle.BTLEException as e:
        logging.debug("scanning failed: %s", e)
        return None

    logging.debug("scan finshed")


    # return the list of found devices

    return scan_delegate.getDevices()
def scan(names=WEATHERSTATION_NAMES, timeout=2.0):
    """This function scans for devices via BtLE, looking for weather
    stations.  These are identified by the GAP Complete Local Name
    (0x09) field in the scan notification - it must match one of the
    listed names.

    The returned value is a dictionary with the keys as the MAC
    addresses of the found weather stations and the values as the names
    (as per GAP Complete Local Name) or None, if there was a problem
    doing the scan.  This list must not be modified in place but
    copy()ed first, if it is going to be changed.

    names=WEATHERSTATION_NAMES -- the list of names in the GAP
    Complete Local Name to match.

    timeout=2.0 -- the timeout before scanning stops, in seconds.
    """


    # create a scan delegate

    scan_delegate = _WeatherStationScanDelegate(names)


    # do the scan

    logging.debug("scan starting")
    scanner = btle.Scanner().withDelegate(scan_delegate)

    try:
        scanner.scan(timeout)
    except btle.BTLEException as e:
        logging.debug("scanning failed: %s", e)
        return None

    logging.debug("scan finshed")


    # return the list of found devices

    return scan_delegate.getDevices()
