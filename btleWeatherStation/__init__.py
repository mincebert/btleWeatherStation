# btleWeatherStation.__init__


"""Oregon Scientific BtLE weather station module.

Scan, connect and retrieve information from Oregon Scientific BtLE
(Bluetooth Low Energy) weather stations.
"""



from .station import WeatherStation, WeatherStationData, WeatherStationSensor
from .scan import weatherstation_scan



__version__ = "3.1.0"


__all__ = [
    "weatherstation_scan",
    "WeatherStation",
    "WeatherStationData",
    "WeatherStationSensor",
]
