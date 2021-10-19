# btleWeatherStation.station


"""Connect and retrieve data from weather stations.
"""



from datetime import datetime
import logging

from binascii import b2a_hex
from bluepy import btle
from time import sleep



# --- constants ---



# _<type>_HANDLE = (16-bit int)
#
# These are the handles giving the types of notifications received from
# the weather station, identifying the different data.

SENSORS_HANDLE = 0x0017
CLOCK_HANDLE = 0x001d
STATUS_HANDLE = 0x000e



# --- exceptions ---



class WeatherStationError(Exception):
    "Base class for exceptions in this module."


class WeatherStationNoDataError(WeatherStationError):
    "Exception raised when no data was received from a weather station."

    def __init__(self, message):
        self.message = message



# --- classes ---



class WeatherStation(object):
    """This class models a weather station and has methods to connect
    and retrieve data from it.
    """


    def __init__(self, mac):
        """The constructor takes the MAC address of a weather station
        and initialises the object, with the received data to 'not
        known yet'.
        """

        super().__init__()

        # the MAC address of the weather station we're connecting to
        self._mac = mac

        # the btle.Peripheral object for the station, set by a call to
        # _connect()
        self._station = None

        # the station clock and weather data binary blobs, if received
        # (or blank if none) - these are filled in by measure()
        self._clock = None
        self._sensors = {}


    def _connect(self):
        """This method connects to the weather station.

        If the weather station is already connected, it will be
        disconnected (to avoid jamming up a station's Bluetooth stack)
        and a btle.BTLEDisconnectError exception raised.
        """


        # if the station is already connected, disconnect and raise exception

        if self._station:
            self._disconnect()

            raise btle.BTLEDisconnectError(
                      "already connected to weather station: %s" % self._mac)


        # connect to the station

        logging.debug("connecting to weather station: %s", self._mac)

        try:
            self._station = btle.Peripheral(self._mac, btle.ADDR_TYPE_RANDOM)

        except btle.BTLEDisconnectError:
            logging.debug("error connecting to weather station")
            raise


        # set up the notification delegate

        try:
            self._station.withDelegate(_WeatherStationDelegate())

        except btle.BTLEDisconnectError:
            self._disconnect()

            logging.debug("error setting notification delegate for station")
            raise


        logging.debug("connected to weather station: %s", self._mac)


    def _disconnect(self):
        """Disconnect from the weather station.  If we are not already
        connected, raise a btle.BTLEDisconnectError exception.

        This method is called by most other methods if an exception is
        caught, whilst they're doing anything, to avoid jamming the
        Bluetooth stack on the weather station.
        """

        if not self._station:
            raise btle.BTLEDisconnectError(
                      "already disconnected from weather station")

        self._station.disconnect()
        self._station = None

        logging.debug("disconnected from weather station: %s", self._mac)


    def _enable_notifications(self):
        """Enable notifications (messages) from the weather station
        which give details of the current measurements and information
        about the weather station itself (such as the clock).

        The notifications will be received by the _WeatherStation-
        Delegate object attached in _connect().
        """

        # list of notifications to enable

        _characteristics = [
            (0x000c, b"\x02\x00"),
            (0x000f, b"\x02\x00"),
            (0x0012, b"\x02\x00"),
            (0x0015, b"\x01\x00"),
            (0x0018, b"\x02\x00"),
            (0x001b, b"\x02\x00"),
            (0x001e, b"\x02\x00"),
            (0x0021, b"\x02\x00"),
            (0x0032, b"\x01\x00"),
        ]


        # try to enable all the listed notifications - if this fails,
        # disconnect and re-raise the exception

        try:
            for handle, val in _characteristics:
                self._station.writeCharacteristic(handle, val)

        except btle.BTLEException:
            logging.debug("error whilst enabling notifications")
            self._disconnect()
            raise


        logging.debug("notifications enabled")


    def _decode_temp(self, b, o):
        """Decode temperature data from sensors notification bytes and
        return it as a float.

        Temperatures are stored as two bytes, little-endian order,
        signed and multiplied by 10 (so a single decimal point).

        If the data is missing, return None.

        b -- the sensors notification data as a block of bytes

        o -- the offset into the block, of the first byte
        """

        # missing temperatures have 0x7f in the most significant byte
        if b[o + 1] == 0x7f:
            return None

        return int.from_bytes(b[o : o+2], "little", signed=True) / 10


    def _decode_humidity(self, b, o):
        """Decode humidity data from sensors notification bytes and
        return it as an integer percentage.

        If the data is missing, return None.

        b -- the sensors notification data as a block of bytes

        o -- the offset into the block, of the byte
        """

        # missing data has a percentage greater than 100%
        if b[o] > 100:
            return None

        return b[o]


    def _decode_clock(self, b):
        """Decode the weather station clock from the supplied
        clock notification data.

        The bytes at the positions below have the following meaning:

        00    = clock: year - 2000
        01    = clock: month
        02    = clock: day of month
        03    = clock: hour
        04    = clock: minute
        05    = clock: second
        06    = unknown (always seems to be 0xff)
        07-10 = unknown (vary)
        11-18 = unknown (always seem to be 0xff)

        Note: there is always a clock time present - it's just
        incorrect, if not set.

        b -- the clock notification data as a block of bytes
        """

        return datetime(
                   year=2000 + b[0], month=b[1], day=b[2],
                   hour=b[3], minute=b[4], second=b[5])


    def _decode_sensors_present(self, b):
        """Return a set of the numbers of the sensors which are
        present.  Sensor 0 (internal) is always assumed to be
        present, for convenience (you can't detect this, but it's
        clearly the case!).

        b -- the status notification data as a block of bytes
        """

        # the 'sensor present' data is a bitfield in the second byte of
        # the status notification data
        return { 0 }.union(
                   { s for s in range(1, 4) if b[1] & (1 << (s - 1)) })


    def _decode_low_battery(self, b):
        """Return a set of the numbers of the sensors which currently
        have the 'low battery' alarm.  This includes sensor 0 - the
        display.

        b -- the status notification data as a block of bytes
        """

        # the display's low battery is the MSB of the first byte; each
        # sensor's low battery state is a bitfield in the sixth byte
        return { 0 } if b[0] & 0x80 else set().union(
                   { s for s in range(1, 4) if b[5] & (1 << (s - 1)) })


    def _decode_sensors(self, d):
        """Decode the data from the sensors from the supplied
        notification dictionary.

        The bytes at the positions below have the following meaning:

        00-01 = sensor 0 (internal): temperature - current
        02-03 = sensor 1: temperature - current
        04-05 = sensor 1: temperature - current
        06-07 = sensor 1: temperature - current
        08    = sensor 0: humidity - current
        09    = sensor 1: humidity - current
        10    = sensor 2: humidity - current
        11    = sensor 3: humidity - current
        12-13 = unknown: always seem to be 0xff
        14    = sensor 0: humidity - maximum
        15    = sensor 0: humidity - minimum
        16    = sensor 1: humidity - maximum
        17    = sensor 1: humidity - minimum
        18    = sensor 2: humidity - maximum (seems to be 0xff)
        19    = sensor 2: humidity - minimum
        20    = sensor 3: humidity - maximum
        21    = sensor 3: humidity - minimum
        22-23 = sensor 0: temperature - maximum
        24-25 = sensor 0: temperature - minimum
        26-27 = sensor 1: temperature - maxumum
        28-29 = sensor 1: temperature - minimum
        30-31 = sensor 2: temperature - maxumum
        32-33 = sensor 2: temperature - minimum
        34-35 = sensor 3: temperature - maxumum
        36-37 = sensor 3: temperature - minimum

        d -- notification dictionary (as returned by get_raw_data())
        """

        sensors = {}

        # get the sensors notification data
        s = d[SENSORS_HANDLE]

        # get the sensors present and which have low battery
        sensors_present = self._decode_sensors_present(d[STATUS_HANDLE])
        low_battery = self._decode_low_battery(d[STATUS_HANDLE])

        # go through the set of sensors which are present, getting
        # their data
        for n in sorted(sensors_present):
            sensor = {
                "temp": {
                    "current": self._decode_temp(s, n*2),
                    "min"    : self._decode_temp(s, 24 + n*4),
                    "max"    : self._decode_temp(s, 22 + n*4), },

                "humidity": {
                    "current": self._decode_humidity(s, 8 + n),
                    "min"    : self._decode_humidity(s, 15 + n*2),
                    "max"    : self._decode_humidity(s, 14 + n*2), },

                "low_battery": n in low_battery,
            }

            sensors[n] = sensor


            # if we're in debug mode, we log the decoded sensor data

            logging.debug("decoded sensor data: %s "
                          "temp: %s < %s < %s, "
                          "humidity: %s < %s < %s, "
                          "low battery?: %s"
                              % (n,
                                 sensor["temp"]["min"] or "?",
                                 sensor["temp"]["current"] or "?",
                                 sensor["temp"]["max"] or "?",
                                 sensor["humidity"]["min"] or "?",
                                 sensor["humidity"]["current"] or "?",
                                 sensor["humidity"]["max"] or "?",
                                 sensor["low_battery"]))

        return sensors


    def get_raw_data(self):
        """This method connects, gets the current data from the weather
        station, disconnects and returns it as a dictionary keyed on
        the handle of the data packets (e.g. sensor data is in
        data[SENSORS_HANDLE]) with bytes objects as values.
        """

        # connect and enable notifications

        self._connect()
        self._enable_notifications()


        # loop, waiting for and handling notifications, with a 1.0s
        # timeout - if no notification is received in that time, we
        # assume we're done

        while self._station.waitForNotifications(1.0):
            # _WeatherStationDelegate.handleNotification() will be
            # callbacked here, as they come come in
            continue


        logging.debug("notifications complete or timed out")


        # get the data retrieved via the notifications and disconnect

        data = self._station.delegate.getData()
        self._disconnect()


        return data


    def measure(self):
        """Connect to the weather station, retrieve the current weather
        sensor data, disconnect and decode it, storing it in the
        object.

        Data includes the temperature and humidity of all the sensors,
        included stored minima and maxima, as well as the current clock
        time.

        If no data was received, an WeatherStationNoDataError exception
        is raised.
        """


        # connect to the weather station, read the current data and
        # disconnect

        data = self.get_raw_data()


        # decode and store the date and time using the system data

        self._clock = (self._decode_clock(data[CLOCK_HANDLE])
                           if CLOCK_HANDLE in data
                           else None)

        if self._clock:
            logging.debug("decoded clock data: %s", self._clock)


        # if the sensor data was missing, blank it out and stop with
        # failure

        if SENSORS_HANDLE not in data:
            self._sensors = {}
            raise WeatherStationNoDataError("no data received from station")

        self._sensors = self._decode_sensors(data)


    def measure_retry(self, timeout=30, interval=3):
        """This method repeatedly retries measure() until it returns a
        successful result, up until the maximum time specifed,
        sleep()ing for the interval, between each retry.

        This is useful because sometimes the weather station connection
        fails and it's necessary to retry it a few times to get data.
        """

        total = 0

        while True:
            try:
                self.measure()
                break

            except (btle.BTLEException, WeatherStationNoDataError):
                # stop if we've waited at least the maximum time

                if total >= timeout:
                    logging.debug(
                        "info: stopping measure after: %ds timeout: %ds",
                        total, timeout)

                    raise


            # wait for the interval time

            logging.debug(
                "info: waited so far: %ds timeout: %ds: retrying in: %ds",
                total, timeout, interval)

            sleep(interval)
            total += interval


    def sensor_present(self, n):
        """This method returns if there is data for a particular sensor
        present, after calling measure().

        The presence can also be tested for by using get_sensors() and
        testing if the sensor's number is present in the returned
        dictionary.
        """

        return n in self._sensors


    def get_sensors(self):
        """This method returns a dictionary, keyed on the sensor number
        and then on the type of data measured ("temp" and "humidity")
        and then the value ("current", "min" and "max"); there is also
        a "low_battery" key with a flag showing if that alarm is set.

        A sensor's presence can be explicitly tested for with the
        sensor_present() method or by checking if its key is in this
        dictionary.

        The returned value must not be changed: if it is to be
        modified, it must be deepcopy()ed first.
        """

        return self._sensors


    def get_clock(self):
        """This method returns the clock time returned by the weather
        station.

        If the clock has not been measured or was not available, None
        will be returned.
        """

        return self._clock


    def get_temp(self, n=0):
        """This method returns the temperature data from the numbered
        sensor (with 0 being the weather station's internal sensor).
        Temperatures are returned as floats.

        The returned value is a dictionary, keyed on the "current",
        "min" and "max" values.

        If any particular sensor value is unavailable, None will be
        returned for that.
        """

        return self._sensors[n].get("temp")


    def get_humidity(self, n=0):
        """This method returns the humidity data from the numbered
        sensor (with 0 being the weather station's internal sensor).
        Humidities are returned as an integer, giving the percentage.

        The returned value is a dictionary, keyed on the "current",
        "min" and "max" values.

        If any particular sensor value is unavailable, None will be
        returned for that.
        """

        return self._sensors[n].get("humidity")


    def get_low_battery(self, n=0):
        """This method returns the low battery alarm from the numbered
        sensor (with 0 being the weather station's battery).

        The return value is a boolean.  If the status is unavailable,
        None will be returned.
        """

        return self._sensors[n].get("low_battery")


class _WeatherStationDelegate(btle.DefaultDelegate):
    """This class handles notifications from a BtLE weather station and
    stores them for retrieval and processing by the caller..

    Notifications contain information about the current weather data.
    """


    def __init__(self):
        """The constructor initialises the received data fields to 'not
        received' status.
        """

        super().__init__()

        self._notification_data = {}


    def handleNotification(self, cHandle, payload):
        """Handle a notification received from the weather station.

        cHandle -- the characteristic handle (the type of notification
        packet)

        payload -- the data portion of the packet
        """

        logging.debug("received notification: handle: %04x payload: %s",
                      cHandle, b2a_hex(payload))

        # we assume that the high bit of the first byte in the payload
        # is a flag indicating if this packet continues from the
        # previous one, so we use it to select a 'part' (0 = first, 1 =
        # second); it's unclear if there are packets >2 parts but we
        # assume not
        part = (payload[0] & 0x80) // 0x80

        # store the payload data (minus the first byte, which seems to
        # only usefully contain the part flag)
        #
        # we sort out checking the parts are complete and concatenating
        # them at the end
        self._notification_data.setdefault(cHandle, {})
        self._notification_data[cHandle][part] = payload[1:]


    def getData(self):
        """Get the data received from the notifications.  This method
        should be called after receiving has timed out.

        The data across packets giving different parts with the same
        handle will be concatenated./

        The return value is a dictionary keyed on the handle, with each
        value being the bytes in the payload, minus the first byte in
        each packet (indication the packet number).
        """

        # initial return dictionary
        data = {}

        # go through the handles of received notifications
        for handle in self._notification_data:
            handle_dict = self._notification_data[handle]

            # concatenate the bytes from each packet
            data[handle] = bytes()
            for part in range(0, max(handle_dict) + 1):
                data[handle] += handle_dict[part]

        return data
