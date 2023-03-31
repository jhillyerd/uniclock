import gfx
import json
import machine
import math
import uasyncio as asyncio
from clock import Clock
from galactic import GalacticUnicorn
from micropython import const
from mqtt_as import MQTTClient, config as MQTT_BASE_CONFIG

# These three values control hysterisis for LED brightness.
LIGHT_SENSOR_SAMPLES = const(6)  # Higher -> slower reaction
LIGHT_RECENCY_BIAS = const(0.2)  # Higher -> faster reaction
MIN_BRIGHT_STEP = const(0.01)

# Default configuration.
config = {
    "message_fg": "blue",
    "message_bg": "black",
    "error_fg": "red",
    "error_bg": "black",
    "status_fg": "yellow",
    "status_bg": "black",
}

gu = GalacticUnicorn()
clock = Clock(config, machine.RTC(), gu)

# Light sensor outputs 0-4095, but usable range is approx 10-2000.
# These defaults are suitable for a bare Unicorn board, but are likely to be
# too dark for one in an enclosure.
#
# Converted to 0-1.0 brightness range by:
#   Taking the log of sensor output
#   Multiplyng by scale factor
#   Adding to shift value
#
# Use light_shift to set the minimum brightness, and light_scale the maximum.
light_shift = -0.3
light_scale = 0.15


# Grab network config.
try:
    from secrets import WIFI_SSID, WIFI_PASSWORD, NTP_SERVER
    from secrets import MQTT_SERVER, MQTT_PORT, MQTT_USER, MQTT_PASSWORD, MQTT_TOPIC
except ImportError:
    print("Create secrets.py with your WiFi & MQTT credentials")
    gfx.draw_text(
        gu,
        "secrets.py",
        fg=gfx.COLORS[config["error_fg"]],
        bg=gfx.COLORS[config["error_bg"]],
    )
    while True:
        pass


async def main():
    # Set reasonable startup brightness, start checking sensor.
    gu.set_brightness(0.2)
    asyncio.create_task(light_sense())

    # No scrolling here, prevents wifi startup delay.
    gfx.draw_text(
        gu,
        "Connecting",
        fg=gfx.COLORS[config["status_fg"]],
        bg=gfx.COLORS[config["status_bg"]],
    )

    # Setup network, MQTT, sync NTP.
    await setup_mqtt()
    clock.sync_time(NTP_SERVER)

    await clock.main_loop()

    print("Error: main loop exited!")


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
    config["queue_len"] = 1  # Use event interface with default queue

    MQTTClient.DEBUG = True
    return MQTTClient(config)


async def setup_mqtt():
    client = setup_mqtt_client()
    try:
        await client.connect()
    except OSError:
        print("MQTT connection failed")
        clock.scroll_error("MQTT connection failed")

    for task in (mqtt_up, mqtt_receiver):
        asyncio.create_task(task(client))


async def mqtt_up(client):
    while True:
        await client.up.wait()
        client.up.clear()
        print("Connected to MQTT broker")
        clock.scroll_status("MQTT connected")
        await client.subscribe(MQTT_TOPIC, 1)


async def mqtt_down(client):
    while True:
        await client.down.wait()
        client.down.clear()
        print("MQTT connection down")
        clock.scroll_error("MQTT connection down")


async def mqtt_receiver(client):
    # Loop over incoming messages.
    async for topic, msg, retained in client.queue:
        print(
            f'Topic: "{topic.decode()}" Message: "{msg.decode()}" Retained: {retained}'
        )

        try:
            obj = json.loads(msg.decode())
        except ValueError:
            print(f"MQTT JSON decode error on: {msg.decode()}")
            continue

        mtype = obj["type"]
        if mtype == "config":
            handle_config(obj)
        elif mtype == "message":
            handle_message(obj)
        elif mtype == "sync":
            clock.sync_time(NTP_SERVER)
        else:
            print(f"Received unknown MQTT JSON message type '{mtype}'")


def handle_config(obj):
    global light_shift, light_scale

    print(f"Reconfiguring: {obj}")
    if obj["utc_offset"]:
        offset = int(obj["utc_offset"])
        clock.utc_offset = offset
    if obj["light_shift"]:
        light_shift = float(obj["light_shift"])
    if obj["light_scale"]:
        light_scale = float(obj["light_scale"])


def handle_message(obj):
    message = obj["message"]
    if message:
        clock.message_task(
            message,
            obj.get("foreground", config["message_fg"]),
            obj.get("background", config["message_bg"]),
        )
    else:
        print(f"Empty message received: {obj}")


async def light_sense():
    prev_bias = 1.0 - LIGHT_RECENCY_BIAS
    actual_bright = gu.get_brightness()
    prev_bright = actual_bright
    lights = [gu.light()] * LIGHT_SENSOR_SAMPLES
    lights_next = 0

    while True:
        # Average recent light readings to reduce flicker.
        lights[lights_next] = gu.light()
        lights_next = (lights_next + 1) % LIGHT_SENSOR_SAMPLES
        light = sum(lights) // LIGHT_SENSOR_SAMPLES

        # Scale sensor to screen brightness, clamping range to 0 - 1.0.
        bright = (math.log(light) * light_scale) + light_shift
        bright = max(min(bright, 1.0), 0.0)

        # Weighted average of previous and current brightness.
        bright = prev_bright * prev_bias + bright * LIGHT_RECENCY_BIAS

        if abs(bright - actual_bright) > MIN_BRIGHT_STEP:
            print(f"bright {prev_bright} -> {bright} for {light}")
            gu.set_brightness(bright)
            gfx.update(gu)
            actual_bright = bright

        prev_bright = bright

        await asyncio.sleep(0.1)


try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()
