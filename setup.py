#!/usr/bin/env python3


import setuptools

import btleWeatherStation


with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="btleWeatherStation",
    version=btleWeatherStation.__version__,
    author="Arnaud Balmelle & Robert Franklin",
    author_email="rcf@mince.net",
    description="Scan for and get data from an Oregon Scientific BtLE weather "
                "station",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/mincebert/bleWeatherStation",
    packages=setuptools.find_packages(),
    install_requires=[
        "bluepy",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
