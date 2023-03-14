# Clock example with NTP synchronization
#
# Create a secrets.py with your Wifi details to be able to get the time
#
# Clock synchronizes time on start, and resynchronizes if you press the A button

import time
import math
import machine
import network
import ntptime
import uasyncio as asyncio
import usocket
from galactic import GalacticUnicorn
from mqtt_as import MQTTClient, config as MQTT_BASE_CONFIG
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN as DISPLAY

from secrets import MQTT_SERVER, MQTT_PORT, MQTT_USER, MQTT_PASSWORD, MQTT_TOPIC

# Constants for controlling the background colour throughout the day.
MIDDAY_HUE = 1.1
MIDNIGHT_HUE = 0.8
HUE_OFFSET = -0.1

MIDDAY_SATURATION = 1.0
MIDNIGHT_SATURATION = 1.0

MIDDAY_VALUE = 0.8
MIDNIGHT_VALUE = 0.3

# Grab network config.
try:
    from secrets import WIFI_SSID, WIFI_PASSWORD, NTP_SERVER
    wifi_available = True
except ImportError:
    print("Create secrets.py with your WiFi credentials to get time from NTP")
    wifi_available = False

# Create galactic object and graphics surface for drawing.
gu = GalacticUnicorn()
graphics = PicoGraphics(DISPLAY)
width = GalacticUnicorn.WIDTH
height = GalacticUnicorn.HEIGHT

# Set up some pens to use later.
WHITE = graphics.create_pen(255, 255, 255)
BLACK = graphics.create_pen(0, 0, 0)

# Time keeping globals.
rtc = machine.RTC()
utc_offset = 0
year, month, day, wd, hour, minute, second, _ = rtc.datetime()
last_second = -1

async def main():
    setup_timezone_buttons()
    gu.set_brightness(0.5)

    # MQTT setup.
    print("MQTT setup")
    client = setup_mqtt_client()
    try:
        await client.connect()
    except OSError:
        print("MQTT connection failed.")

    for task in (mqtt_up, mqtt_receiver):
        asyncio.create_task(task(client))

    sync_time()

    print("Entering async loop")
    while True:
        if gu.is_pressed(GalacticUnicorn.SWITCH_BRIGHTNESS_UP):
            gu.adjust_brightness(+0.01)

        if gu.is_pressed(GalacticUnicorn.SWITCH_BRIGHTNESS_DOWN):
            gu.adjust_brightness(-0.01)

        redraw_display_if_reqd()
        gu.update(graphics)

        await asyncio.sleep(0.05)


@micropython.native  # noqa: F821
def from_hsv(h, s, v):
    i = math.floor(h * 6.0)
    f = h * 6.0 - i
    v *= 255.0
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)

    i = int(i) % 6
    if i == 0:
        return int(v), int(t), int(p)
    if i == 1:
        return int(q), int(v), int(p)
    if i == 2:
        return int(p), int(v), int(t)
    if i == 3:
        return int(p), int(q), int(v)
    if i == 4:
        return int(t), int(p), int(v)
    if i == 5:
        return int(v), int(p), int(q)


# function for drawing a gradient background
def gradient_background(start_hue, start_sat, start_val, end_hue, end_sat, end_val):
    half_width = width // 2
    for x in range(0, half_width):
        hue = ((end_hue - start_hue) * (x / half_width)) + start_hue
        sat = ((end_sat - start_sat) * (x / half_width)) + start_sat
        val = ((end_val - start_val) * (x / half_width)) + start_val
        colour = from_hsv(hue, sat, val)
        graphics.set_pen(graphics.create_pen(int(colour[0]), int(colour[1]), int(colour[2])))
        for y in range(0, height):
            graphics.pixel(x, y)
            graphics.pixel(width - x - 1, y)

    colour = from_hsv(end_hue, end_sat, end_val)
    graphics.set_pen(graphics.create_pen(int(colour[0]), int(colour[1]), int(colour[2])))
    for y in range(0, height):
        graphics.pixel(half_width, y)


# function for drawing outlined text
def outline_text(text, x, y):
    graphics.set_pen(BLACK)
    graphics.text(text, x - 1, y - 1, -1, 1)
    graphics.text(text, x, y - 1, -1, 1)
    graphics.text(text, x + 1, y - 1, -1, 1)
    graphics.text(text, x - 1, y, -1, 1)
    graphics.text(text, x + 1, y, -1, 1)
    graphics.text(text, x - 1, y + 1, -1, 1)
    graphics.text(text, x, y + 1, -1, 1)
    graphics.text(text, x + 1, y + 1, -1, 1)

    graphics.set_pen(WHITE)
    graphics.text(text, x, y, -1, 1)


# Connect to wifi and synchronize the RTC time from NTP
def sync_time():
    # DNS resolution not necessary, but nice for debugging.
    host_ip = usocket.getaddrinfo(NTP_SERVER, 123)[0][-1][0]
    print(f"NTP server \"{NTP_SERVER}\" resolved to {host_ip}")

    try:
        ntptime.host = host_ip
        ntptime.settime()
        print("Time set via NTP")
    except OSError:
        pass


# NTP synchronizes the time to UTC, this allows you to adjust the displayed time
# by one hour increments from UTC by pressing the volume up/down buttons
def setup_timezone_buttons():
    # We use the IRQ method to detect the button presses to avoid incrementing/decrementing
    # multiple times when the button is held.
    up_button = machine.Pin(GalacticUnicorn.SWITCH_VOLUME_UP, machine.Pin.IN, machine.Pin.PULL_UP)
    down_button = machine.Pin(GalacticUnicorn.SWITCH_VOLUME_DOWN, machine.Pin.IN, machine.Pin.PULL_UP)

    def adjust_utc_offset(pin):
        global utc_offset
        if pin == up_button:
            utc_offset += 1
        if pin == down_button:
            utc_offset -= 1

    up_button.irq(trigger=machine.Pin.IRQ_FALLING, handler=adjust_utc_offset)
    down_button.irq(trigger=machine.Pin.IRQ_FALLING, handler=adjust_utc_offset)


# Check whether the RTC time has changed and if so redraw the display
def redraw_display_if_reqd():
    global year, month, day, wd, hour, minute, second, last_second

    year, month, day, wd, hour, minute, second, _ = rtc.datetime()
    if second != last_second:
        hour += utc_offset
        time_through_day = (((hour * 60) + minute) * 60) + second
        percent_through_day = time_through_day / 86400
        percent_to_midday = 1.0 - ((math.cos(percent_through_day * math.pi * 2) + 1) / 2)
        # print(percent_to_midday)

        hue = ((MIDDAY_HUE - MIDNIGHT_HUE) * percent_to_midday) + MIDNIGHT_HUE
        sat = ((MIDDAY_SATURATION - MIDNIGHT_SATURATION) * percent_to_midday) + MIDNIGHT_SATURATION
        val = ((MIDDAY_VALUE - MIDNIGHT_VALUE) * percent_to_midday) + MIDNIGHT_VALUE

        gradient_background(hue, sat, val,
                            hue + HUE_OFFSET, sat, val)

        clock = "{:02}:{:02}:{:02}".format(hour, minute, second)

        # set the font
        graphics.set_font("bitmap8")

        # calculate text position so that it is centred
        w = graphics.measure_text(clock, 1)
        x = int(width / 2 - w / 2 + 1)
        y = 2

        outline_text(clock, x, y)

        last_second = second


def setup_mqtt_client():
    config = MQTT_BASE_CONFIG

    # Wifi
    config["ssid"] = WIFI_SSID
    config["wifi_pw"] = WIFI_PASSWORD

    # MQTT
    config["server"] = MQTT_SERVER
    config["port"] = MQTT_PORT
    config["user"] = MQTT_USER
    config["password"] = MQTT_PASSWORD
    config["queue_len"] = 1 # Use event interface with default queue

    MQTTClient.DEBUG = True
    return MQTTClient(config)


async def mqtt_up(client):
    while True:
        await client.up.wait()
        client.up.clear()
        print("Connected to MQTT broker.")
        await client.subscribe(MQTT_TOPIC, 1)


async def mqtt_receiver(client):
    # Loop over incoming messages.
    async for topic, msg, retained in client.queue:
        print(f'Topic: "{topic.decode()}" Message: "{msg.decode()}" Retained: {retained}')
        # spawns async task from this message
        #asyncio.create_task(pulse())


try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()
