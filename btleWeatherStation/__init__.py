# btleWeatherStation.__init__


"""Oregon Scientific BtLE weather station module.

Scan, connect and retrieve information from Oregon Scientific BtLE
(Bluetooth Low Energy) weather stations.
"""



from .station import WeatherStation
from .scan import scan



__version__ = "3.0.0"


__all__ = [
    "scan",
    "WeatherStation",
]
