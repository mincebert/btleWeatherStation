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



# --- functions ---



def _default(s, default="--"):
    """Returns the supplied string 's' if it is not None.  If 's' is
    None, the 'default' value is returned.

    It's typically used for debugging messages, to show undefined or
    unavailable values.
    """

    if s is None:
        return default

    return s



# --- classes ---



class WeatherStationSensor(object):
    """This class represents a measured status for a sensor on the
    weather station.  It is typically used by the WeatherStationData
    class.

    Attributes contain the various measured values:

    temp_current, temp_min, temp_max -- the current, minimum and
    maximum temperatures in celcius

    humidity_current, humidity_min, humidity_max -- the current, minimum
    and maximum humidities as a percentage (0-100)

    low_battery -- a boolean indicating if the sensor has a low battery
    state
    """

    def __init__(
            self, temp_current=None, temp_min=None, temp_max=None,
            humidity_current=None, humidity_min=None, humidity_max=None,
            low_battery=None):

        "The constructor just stores the supplied values."

        super().__init__()

        self.temp_current = temp_current
        self.temp_min = temp_min
        self.temp_max = temp_max

        self.humidity_current = humidity_current
        self.humidity_min = humidity_min
        self.humidity_max = humidity_max

        self.low_battery = low_battery


    def __str__(self):
        """Returns a simple string representation of the sensor data,
        primarily for debugging purposes and the format should not be
        relied upon.
        """

        return (
            "TEMP ('C): "
            f"min: { _default(self.temp_min) }, "
            f"current: { _default(self.temp_current) }, "
            f"max: { _default(self.temp_max) }; "
            "HUMIDITY (%): "
            f"min: { _default(self.humidity_min) }, "
            f"current: { _default(self.humidity_current) }, "
            f"max: { _default(self.humidity_max) }, "
            f"BATTERY: { 'low' if self.low_battery else 'ok' }")



class WeatherStationData(object):
    """Snapshot of all measured data from a WeatherStation, as returned
    by WeatherStation.measure() (and measure_retry()).

    There are two attributes:

    clock -- a datetime object containing the time set in the station

    sensors -- a dictionary, keyed on the sensor number, containing
    WeatherStationSensor objects giving data for that sensor
    """

    def __init__(self, clock=None, sensors=None):
        """The constructor just stores the supplied clock and sensor
        data.
        """

        super().__init__()

        self.clock = clock
        self.sensors = sensors


    def __str__(self):
        """Print the station data as a multiline string.  This is
        primarily used for debugging and the format should not be
        relied upon.
        """

        s = "clock: " + str(self.clock)
        for sensor in sorted(self.sensors):
            s += "\n" + f"sensor[{ sensor }]: { self.sensors[sensor] }"
        return s



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


    def _decode_clock(self, c):
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

        c -- the clock notification data as a block of bytes
        """

        return datetime(year=2000 + c[0], month=c[1], day=c[2],
                        hour=c[3], minute=c[4], second=c[5])


    def _decode_low_battery(self, t):
        """Return a set of the numbers of the sensors which currently
        have the 'low battery' alarm.  This includes sensor 0 - the
        display.

        t -- the status notification data as a block of bytes
        """

        # the display's low battery is the MSB of the first byte; each
        # sensor's low battery state is a bitfield in the sixth byte
        return ({ 0 } if t[0] & 0x80
                    else set().union({ sensor for sensor in range(1, 4)
                                           if t[5] & (1 << (sensor - 1)) }))


    def _decode_sensors_present(self, t):
        """Return a set of the numbers of the sensors which are
        present.  Sensor 0 (internal) is always assumed to be
        present, for convenience (you can't detect this, but it's
        clearly the case!).

        t -- the status notification data as a block of bytes
        """

        # the 'sensor present' data is a bitfield in the second byte of
        # the status notification data
        return { 0 }.union({ sensor for sensor in range(1, 4)
                                 if t[1] & (1 << (sensor - 1)) })


    def _decode_sensors_data(self, r):
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

        r -- notification dictionary (as returned by get_raw_data())
        """

        # get the sensors notification packet data
        sensor_data = r[SENSORS_HANDLE]

        # get the sensors present and which have low battery
        sensors_present = self._decode_sensors_present(r[STATUS_HANDLE])
        low_battery = self._decode_low_battery(r[STATUS_HANDLE])

        # initialise a dictionary of decoded sensor data - this will be
        # return
        sensors = {}

        for sensor in sorted(sensors_present):
            # decode the sensor values from the raw data
            temp_current = self._decode_temp(sensor_data, sensor*2)
            temp_min = self._decode_temp(sensor_data, 24 + sensor*4)
            temp_max = self._decode_temp(sensor_data, 22 + sensor*4)
            humidity_current = self._decode_humidity(sensor_data, 8 + sensor)
            humidity_min = self._decode_humidity(sensor_data, 15 + sensor*2)
            humidity_max = self._decode_humidity(sensor_data, 14 + sensor*2)

            # store this sensor's data in a WeatherStationSensor object
            # in the 'sensors' dictionary
            sensors[sensor] = WeatherStationSensor(
                temp_current=temp_current,
                temp_min=temp_min,
                temp_max=temp_max,
                humidity_current=humidity_current,
                humidity_min=humidity_min,
                humidity_max=humidity_max,
                low_battery=sensor in low_battery)

            # if we're in debug mode, we log the decoded sensor data
            logging.debug("decoded sensor: %s data:"
                          " temp: %s <= %s <= %s,"
                          " humidity: %s <= %s <= %s,"
                          " low battery?: %s"
                              % (sensor,
                                 _default(temp_min),
                                 _default(temp_current),
                                 _default(temp_max),
                                 _default(humidity_min),
                                 _default(humidity_current),
                                 _default(humidity_max),
                                 sensor in low_battery))

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


    def measure_once(self):
        """Connect to the weather station, retrieve the current weather
        sensor data, disconnect and decode it and store it in a
        WeatherStationData object, which is returned.

        If no data was received, an WeatherStationNoDataError exception
        is raised.

        This is only attempted once and can fail fairly regulary.  Using
        measure() (which can handle retries) is recommended.
        """


        # connect to the weather station, read the current data and
        # disconnect

        raw_data = self.get_raw_data()


        # decode and store the date and time using the system data

        if CLOCK_HANDLE not in raw_data:
            raise WeatherStationNoDataError(
                      "no clock data received from station")

        clock = self._decode_clock(raw_data[CLOCK_HANDLE])

        if clock:
            logging.debug("decoded clock data: %s", clock)


        # if the sensor data was missing, blank it out and stop with
        # failure

        if SENSORS_HANDLE not in raw_data:
            raise WeatherStationNoDataError(
                      "no sensor data received from station")

        sensors = self._decode_sensors_data(raw_data)


        # build a WeatherStationData object and return it

        return WeatherStationData(clock=clock, sensors=sensors)


    def measure(self, max_tries=5, interval=3):
        """This method repeatedly retries measure() until it returns a
        successful result, up until the maximum time specifed,
        sleep()ing for the interval, between each retry.

        This is useful because sometimes the weather station connection
        fails and it's necessary to retry it a few times to get data.

        As with measure(), a WeatherStationData object will be returned,
        or an exception raised.
        """

        tries = 0

        while tries < max_tries:
            tries += 1

            try:
                return self.measure_once()
                break

            except (btle.BTLEException, WeatherStationNoDataError):
                # if we have more tries left, wait for the interval time

                if tries >= max_tries:
                    logging.debug(
                        f"info: maximum number of tries {tries} reached -"
                        " aborting")

                    raise


            # we have more tries left, so wait and then retry

            logging.debug(
                f"info: try {tries} failed, {max_tries - tries} left; waiting "
                f"{interval} seconds before retry")

            sleep(interval)




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
