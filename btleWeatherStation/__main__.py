# btleWeatherStation.__main__



# Connect to Oregon Scientific BLE Weather Station
# Copyright (C) 2016 Arnaud Balmelle
# Reworked 2020 by Robert Franklin <rcf@mince.net>
#
# This script will connect to Oregon Scientific BtLE Weather Station
# and retrieve the temperature of the base and sensors attached to it.
#
# Supported Oregon Scientific weather stations: EMR211 and RAR218HG (and
# probably BAR218HG).
#
# License: Released under an MIT license: http://opensource.org/licenses/MIT



import argparse
import logging
import sys

from . import __version__, WeatherStation, scan



# --- constants ---



# DEFAULT_<?> = (various)
#
# Default values for various command line options.

DEFAULT_INTERVAL = 3
DEFAULT_TRIES = 5



# <?>_FMT = (string)
#
# strings giving the format for the weather data output

DETAIL_FMT = "%6s :: %8s < %8s < %8s :: %4s < %4s < %4s%s"
DISPLAY_FMT = "%6s :: %8s : %8s"



# --- functions ---



def default(s, default=" -- ", fmt=None):
    """Returns the supplied string 's', if it is not None.  If 'fmt' is
    not None, the string is formatted using that '%' specification.

    If 's' is None, the 'default' value is returned, unformatted.
    """

    if s is None:
        return default

    if fmt is None:
        return s

    return fmt % s



# --- parse arguments ---



parser = argparse.ArgumentParser(
    # override the program name as running this as a __main__ inside a module
    # directory will use '__main__' by default - this name isn't necessarily
    # correct, but it looks better than that
    prog="btleWeatherStation",

    # we want the epilog help output to be printed as it and not reformatted or
    # line wrapped
    formatter_class=argparse.RawDescriptionHelpFormatter)

parser.add_argument(
    "-m", "--mac",
    help="MAC address of weather station to connect to")

parser.add_argument(
    "-i", "--interval",
    type=int,
    default=DEFAULT_INTERVAL,
    help="interval in seconds between retries of measure (default:"
         f" {DEFAULT_INTERVAL})")

parser.add_argument(
    "-t", "--tries",
    type=int,
    default=DEFAULT_TRIES,
    help="maximum number of tries for measure or scan (default:"
         f" {DEFAULT_TRIES})")

parser.add_argument(
    "-s", "--scan",
    action="store_true",
    help="scan for weather stations in range (requires root privilege)")

parser.add_argument(
    "-l", "--detail",
    action="store_true",
    help="report more detail in displayed data (min+max and low battery"
         "alarm status)")

parser.add_argument(
    "-d", "--debug",
    action="store_true",
    help="print debug messages")

parser.add_argument(
    "-v", "--version",
    action="version",
    version=__version__)


args = parser.parse_args()



# perform some validity checks on the arguments

if ((1 if args.scan else 0) + (1 if args.mac else 0)) != 1:
    print("error: one (and only one) of -m and -s must be specified",
          file=sys.stderr)

    exit(1)


# if the debug option is used, enable debugging

if args.debug:
    logging.basicConfig(format=r"%(asctime)s %(message)s", level=logging.DEBUG)



# --- process options ---



# if scan mode is selected, so a scan for weather stations in range

if args.scan:
    # try the scan, printing an error if it fails

    stations = scan(timeout=args.timeout or 2)

    if stations is None:
        print("error: unable to scan for weather stations (are you root?)",
              file=sys.stderr)

        exit(1)


    # scan complete - print results

    if stations:
        print("found %d weather station(s):" % len(stations))
        for mac in stations:
            print("%s (%s)" % (mac, stations[mac]))

    else:
        print("no weather stations(s) found")

    exit(0)



# retrieve weather data

station = WeatherStation(args.mac)


try:
    station_data = station.measure(
                       max_tries=args.tries, interval=args.interval)

except Exception as e:
    print("error:", e, file=sys.stderr)
    exit(1)


# data retrieved - print current temperatures from any present sensors

if args.detail:
    print("""\
          -------- temperature ---------    ---- humidity ----
sensor :: min      : currrent : max      :: min  : curr : max
""")

    for sensor in sorted(station_data.sensors):
        sensor_data = station_data.sensors[sensor]
        print(DETAIL_FMT
                  % (sensor,
                     default(sensor_data.temp_min, fmt="%6.1f'C"),
                     default(sensor_data.temp_current, fmt="%6.1f'C"),
                     default(sensor_data.temp_max, fmt="%6.1f'C"),
                     default(sensor_data.humidity_min, fmt="%3d%%"),
                     default(sensor_data.humidity_current, fmt="%3d%%"),
                     default(sensor_data.humidity_max, fmt="%3d%%"),
                     " : !! low battery" if sensor_data.low_battery else ""))

    exit(0)



# no special option supplied - just display the station data

print(DISPLAY_FMT % ("sensor", "temp", "humidity"))

for sensor in station_data.sensors:
    sensor_data = station_data.sensors[sensor]
    print(DISPLAY_FMT % (sensor,
                         default(sensor_data.temp_current, fmt="%4.1f'C"),
                         default(sensor_data.humidity_current, fmt="%4d%%")))
