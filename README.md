# uniclock

[Galactic Unicorn] MQTT & NTP clock.


## Features

- [X] Refactored version of Pimoroni's [example clock.py]
- [X] Scrolls messages sent via an MQTT topic
- [X] Adjusts display brightness with built-in light sensor
- [X] 3D printed wall-mountable case with diffuser support
- [X] 12 & 24 hour display modes
- [ ] Reconfigurable via MQTT message; physical access not required
- [ ] Updated configuration stored on device
- [ ] Installation guide and assembly tips ;)


## Installation

My Unicorn is running this version of Pirate Python:
https://github.com/pimoroni/pimoroni-pico/releases/tag/v1.19.16

Included in this project is @peterhinch mqtt_as.py version from Jan 2, 2023:
[permalink](https://github.com/peterhinch/micropython-mqtt/blob/94b97f57c7bc4d56fe5edb3106f6ea06c84080ac/mqtt_as/mqtt_as.py)


[example clock.py]: https://github.com/pimoroni/pimoroni-pico/blob/1da44729266b895ff937b986c61937cd6adad0c7/micropython/examples/galactic_unicorn/clock.py 
[Galactic Unicorn]: https://shop.pimoroni.com/en-us/products/galactic-unicorn
