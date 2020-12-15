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

from bluepy import btle
from . import __version__, WeatherStation, scan



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
    default=3,
    help="interval in seconds between retries of measure")

parser.add_argument(
    "-t", "--timeout",
    type=int,
    help="total timeout for repeated retries of measure")

parser.add_argument(
    "-s", "--scan",
    action="store_true",
    help="scan for weather stations in range (requires root privilege)")

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
    print("error: one (and only one) of -m and -s can be specified", file=sys.stderr)
    exit(1)


# if the debug option is used, enable debugging

if args.debug:
    logging.basicConfig(format=r"%(asctime)s %(message)s", level=logging.DEBUG)



# --- process options ---



# if scan mode is selected, so a scan for weather stations in range

if args.scan:
    # try the scan, printing an error if it fails

    stations = scan()

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
    if not args.timeout:
        station.measure()
    else:
        station.measure_retry(args.timeout, args.interval)

except Exception as e:
    print("error:", e, file=sys.stderr)
    exit(1)



# data retrieved - print current temperatures from any present sensors

print("current sensor temperatures / humidities:")

for num in range(0, 6):
    if station.sensor_present(num):
        print("%d = %5.1f'C / %d%%"
                  % (num, station.get_temp(num)["current"],
                     station.get_humidity(num)["current"]))
