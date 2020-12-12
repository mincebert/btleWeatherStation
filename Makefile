all: btleWeatherStation

remake: clean all

.PHONY: btleWeatherStation
btleWeatherStation:
	./setup.py sdist bdist_wheel

upload:
	python3 -I -m twine upload dist/*

clean:
	rm -rf build dist btleWeatherStation.egg-info
