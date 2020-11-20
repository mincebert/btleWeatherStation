#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Connect to Oregon Scientific BLE Weather Station
# Copyright (c) 2016 Arnaud Balmelle
#
# This script will connect to Oregon Scientific BLE Weather Station
# and retrieve the temperature of the base and sensors attached to it.
# If no mac-address is passed as argument, it will scan for an Oregon Scientific BLE Weather Station.
#
# Supported Oregon Scientific Weather Station: EMR211 and RAR218HG (and probably BAR218HG)
#
# Usage: python bleWeatherStation.py [mac-address]
#
# Dependencies:
# - Bluetooth 4.1 and bluez installed
# - bluepy library (https://github.com/IanHarvey/bluepy)
#
# License: Released under an MIT license: http://opensource.org/licenses/MIT

import sys
import logging
import time
import binascii
import bluepy.btle

# uncomment the following line to get debug information
logging.basicConfig(format='%(asctime)s: %(message)s', level=logging.DEBUG)

#WEATHERSTATION_NAME = "IDTW211R" # IDTW211R for EMR211
WEATHERSTATION_NAME = "IDTW213R" # IDTW213R for RAR218HG

class WeatherStation:
    def __init__(self, mac):
        self._data = {}
        try:
            self.p = bluepy.btle.Peripheral(mac, bluepy.btle.ADDR_TYPE_RANDOM)
            self.p.withDelegate(NotificationDelegate())
            logging.debug('WeatherStation connected !')
        except bluepy.btle.BTLEDisconnectError:
            self.p = 0
            logging.debug('Connection to WeatherStation failed !')
            raise

    def _enableNotification(self):
        try:
            # Enable all notification or indication
            self.p.writeCharacteristic(0x000c, b"\x02\x00")
            self.p.writeCharacteristic(0x000f, b"\x02\x00")
            self.p.writeCharacteristic(0x0012, b"\x02\x00")
            self.p.writeCharacteristic(0x0015, b"\x01\x00")
            self.p.writeCharacteristic(0x0018, b"\x02\x00")
            self.p.writeCharacteristic(0x001b, b"\x02\x00")
            self.p.writeCharacteristic(0x001e, b"\x02\x00")
            self.p.writeCharacteristic(0x0021, b"\x02\x00")
            self.p.writeCharacteristic(0x0032, b"\x01\x00")
            logging.debug('Notifications enabled')

        except bluepy.btle.BTLEException as err:
            logging.debug('Notification exception')
            print(err)
            self.p.disconnect()

    def monitorWeatherStation(self):
        try:
            # Enable notification
            self._enableNotification()
            # Wait for notifications
            while self.p.waitForNotifications(1.0):
                # handleNotification() was called
                continue
            logging.debug('Notification timeout')
        except bluepy.btle.BTLEDisconnectError:
            logging.debug('Error waiting for notifications from Weather Station')
            return None

        # a lot of the data is two bytes, little-endian, signed, multiplied
        # by 10 (to eliminate the need for a decimal point) so we have a
        # function to do this repeatedly
        def cvt(d, o):
            return int.from_bytes(d[o:o+2], 'little', signed=True) / 10

        regs = self.p.delegate.getData()

        # bug from weather station: humidity 2 max is always 0xff
        if regs is not None:
            for s in range(0, 4):
                self._data[s] = {
                    "temperature": cvt(regs, s*2),
                    "temperature_min": cvt(regs, 18 + 6 + s*4),
                    "temperature_max": cvt(regs, 18 + 4 + s*4),
                    "humidity": regs[8 + s],
                    "humidity_min": regs[15 + s*2],
                    "humidity_max": regs[14 + s*2],
                }

            return True
        else:
            return None

    def getIndoorTemp(self):
        if 0 in self._data:
            temp = self._data[0]["temperature"]
            min = self._data[0]["temperature_min"]
            max = self._data[0]["temperature_max"]
            logging.debug('Indoor temp : %.1f°C, max : %.1f°C, min : %.1f°C', temp, max, min)
            return temp
        else:
            return None

    def getOutdoorTemp(self, num=1):
        if num in self._data:
            temp = self._data[num]["temperature"]
            min = self._data[num]["temperature_min"]
            max = self._data[num]["temperature_max"]
            logging.debug('Outdoor temp %d : %.1f°C, max : %.1f°C, min : %.1f°C', num, temp, max, min)
            return temp
        else:
            return None

    def disconnect(self):
        self.p.disconnect()

class NotificationDelegate(bluepy.btle.DefaultDelegate):
    def __init__(self):
        super().__init__()
        self._indoorAndOutdoorTemp_type0 = None
        self._indoorAndOutdoorTemp_type1 = None

    def handleNotification(self, cHandle, data):
        if cHandle == 0x0017:
            # indoorAndOutdoorTemp indication received
            if data[0] & 0x80 == 0x00:
                # Type0 data packet received
                self._indoorAndOutdoorTemp_type0 = data[1:]
                logging.debug('indoorAndOutdoorTemp_type0 = %s', binascii.b2a_hex(data))
            elif data[0] & 0x80 == 0x80:
                # Type1 data packet received
                self._indoorAndOutdoorTemp_type1 = data[1:]
                logging.debug('indoorAndOutdoorTemp_type1 = %s', binascii.b2a_hex(data))
            else:
                logging.debug('got an unknown cHandle 0x0017 packet')
        else:
            # skip other indications/notifications
            logging.debug('handle %x = %s', cHandle, binascii.b2a_hex(data))

    def getData(self):
            if self._indoorAndOutdoorTemp_type0 is not None:
                # return sensors data
                return self._indoorAndOutdoorTemp_type0 + self._indoorAndOutdoorTemp_type1
            else:
                return None

class ScanDelegate(bluepy.btle.DefaultDelegate):
    def __init__(self):
        super().__init__()

    def handleDiscovery(self, dev, isNewDev, isNewData):
        global weatherStationMacAddr
        if dev.getValueText(9) == WEATHERSTATION_NAME:
            # Weather Station in range, saving Mac address for future connection
            logging.debug('WeatherStation found: %s' % dev.addr)
            weatherStationMacAddr = dev.addr

if __name__=="__main__":

    weatherStationMacAddr = None

    if len(sys.argv) < 2:
        # No MAC address passed as argument
        try:
            # Scanning to see if Weather Station in range
            scanner = bluepy.btle.Scanner().withDelegate(ScanDelegate())
            devices = scanner.scan(2.0)
        except bluepy.btle.BTLEException as err:
            print(err)
            print('Scanning requires root privilege, so do not forget to run the script with sudo.')
    else:
        # Weather Station MAC address passed as argument, will attempt to connect with this address
        weatherStationMacAddr = sys.argv[1]

    if weatherStationMacAddr is None:
        logging.debug('No WeatherStation in range !')
    else:
        try:
            # Attempting to connect to device with MAC address "weatherStationMacAddr"
            weatherStation = WeatherStation(weatherStationMacAddr)

        except bluepy.btle.BTLEDisconnectError:
            logging.debug('Abort')
            exit(0)

        try:
            if weatherStation.monitorWeatherStation() is not None:
                # WeatherStation data received
                indoor = weatherStation.getIndoorTemp()
                for num in range(1, 4):
                    outdoor = weatherStation.getOutdoorTemp(num)
            else:
                logging.debug('No data received from WeatherStation')
        except Exception as e:
            logging.debug("There was an exception --", e)

        # always disconnect otherwise the station Bluetooth locks up
        weatherStation.disconnect()
        logging.debug('Disconnected from Weather Station - DONE.')
