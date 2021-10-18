# btleWeatherStation.station


"""Connect and retrieve data from weather stations.
"""



from datetime import datetime
import logging

from binascii import b2a_hex
from bluepy import btle
from time import sleep



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


    def _decode_temp(self, d, o):
        """Decode temperature data from the binary blob, received in a
        notification, and return it as a float.

        Temperatures are stored as two bytes, little-endian order,
        signed and multiplied by 10 (so a single decimal point).

        If the data is missing, return None.

        d -- the data as a block of bytes

        o -- the offset into the block, of the first byte
        """

        # missing temperatures have 0x7f in the most significant byte
        if d[o + 1] == 0x7f:
            return None

        return int.from_bytes(d[o : o+2], "little", signed=True) / 10


    def _decode_humidity(self, d, o):
        """Decode humidity data from the binary blob, received in a
        notification, and return it as an integer percentage.

        If the data is missing, return None.

        d -- the data as a block of bytes

        o -- the offset into the block, of the byte
        """

        # missing data has a percentage greater than 100%
        if d[o] > 100:
            return None

        return d[o]


    def _decode_clock(self, d):
        """Decode the weather station clock from the system data.

        There is always a clock time present - it's just incorrect, if
        not set.

        d -- the system data block
        """


        return datetime(
                   year=2000 + d[1], month=d[2], day=d[3],
                   hour=d[4], minute=d[5], second=d[6])


    def _get_data(self):
        """This method gets the current data from the weather station,
        disconnects and returns it as a tuple of (system_data,
        sensor_data).

        If there was a problem retrieving part of the data, that part
        will be returned as None; if both parts are unavailable, a
        tuple of (None, None) will be returned.
        """

        # try to connect and enable notifications

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

        system_data = self._station.delegate.getSystemData()
        sensor_data = self._station.delegate.getSensorData()

        self._disconnect()

        return system_data, sensor_data


    def get_raw_system_data(self):
        """Connect to the weather station, read the current data and
        disconnect.  Then return the raw sensor data block as an array
        of bytes.

        The bytes at the positions below have the stated meaning:

        00    = unknown
        01    = clock: year - 2000
        02    = clock: month
        03    = clock: day of month
        04    = clock: hour
        05    = clock: minute
        06    = clock: second
        07    = unknown (always seems to be 0xff)
        08-11 = unknown (vary)
        12-19 = unknown (always seem to be 0xff)
        """

        return self._get_data()[0]


    def get_raw_sensor_data(self):
        """Connect to the weather station, read the current data and
        disconnect.  Then return the raw sensor data block as an array
        of bytes.

        The bytes at the positions below have the stated meaning:

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
        """

        return self._get_data()[1]


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

        system_data, sensor_data = self._get_data()


        # decode and store the date and time using the system data

        self._clock = self._decode_clock(system_data) if system_data else None

        if self._clock:
            logging.debug("decoded clock data: %s", self._clock)


        # if the sensor data was missing, blank it out and stop with
        # failure

        if sensor_data is None:
            self._sensors = {}
            raise WeatherStationNoDataError("no data received from station")


        # decode the data from each of the sensors, storing it in the
        # sensor data dictionary

        for n in range(0, 4):
            sensor = {
                "temp": {
                    "current": self._decode_temp(sensor_data, n*2),
                    "min"    : self._decode_temp(sensor_data, 24 + n*4),
                    "max"    : self._decode_temp(sensor_data, 22 + n*4), },

                "humidity": {
                    "current": self._decode_humidity(sensor_data, 8 + n),
                    "min"    : self._decode_humidity(sensor_data, 15 + n*2),
                    "max"    : self._decode_humidity(sensor_data, 14 + n*2), },
            }

            self._sensors[n] = sensor


            # if we're in debug mode, we log the decoded sensor data

            logging.debug("decoded sensor data: %s "
                          "temp: %s < %s < %s "
                          "humidity: %s < %s < %s"
                              % (n,
                                 sensor["temp"]["min"] or "?",
                                 sensor["temp"]["current"] or "?",
                                 sensor["temp"]["max"] or "?",
                                 sensor["humidity"]["min"] or "?",
                                 sensor["humidity"]["current"] or "?",
                                 sensor["humidity"]["max"] or "?"))


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


    def sensor_present(self, n=0):
        """This method returns if there is data for a particular sensor
        present, after calling measure().
        """

        return n in self._sensors


    def get_sensors(self):
        """This method returns a dictionary, keyed on the sensor number
        and then on the type of data measured ("temp" and "humidity")
        and then the value ("current", "min" and "max").

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

        self._sensordata = {}
        self._systemdata = None


    def handleNotification(self, cHandle, data):
        "Handle a notification received from the weather station."

        # the characteristic handle indicates the type of notification
        # packet received

        if cHandle == 0x0017:
            # weather sensor data packet


            # the weather data is made up of two parts - the high bit of
            # the first byte tells us which we have

            part = (data[0] & 0x80) // 0x80


            logging.debug("received notification: sensor data part: %d: %s",
                          part, b2a_hex(data))


            # store the received data, dropping the first byte (the part
            # number) because that lets us join everything together and
            # more easily extract data algorithmically

            self._sensordata[part] = data[1:]


        elif cHandle == 0x001d:
            # system data packet (containing the date and time, and
            # probably some other things)

            logging.debug("received notification: system data: %s",
                          b2a_hex(data))

            self._systemdata = data


        else:
            # skip other types of packet

            logging.debug("received notification: unknown data: %x: %s",
                          cHandle, b2a_hex(data))


    def getSensorData(self):
        """Return the received weather sensor data as a sequence of
        bytes.

        If a complete set of weather data was not received (one or both
        of parts 0 and 1 missing) then None is returned.
        """

        if not ((0 in self._sensordata) and (1 in self._sensordata)):
            return None

        return self._sensordata[0] + self._sensordata[1]


    def getSystemData(self):
        """Return the received system data as a sequence of bytes.

        If it was not received, None is returned.
        """

        return self._systemdata
