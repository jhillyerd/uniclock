import collections
import gfx
import json
import machine
import math
import ntptime
import uasyncio as asyncio
import usocket
from clock import Clock
from galactic import GalacticUnicorn
from micropython import const
from mqtt_as import MQTTClient, config as MQTT_BASE_CONFIG


# Grab network config.
try:
    from secrets import WIFI_SSID, WIFI_PASSWORD, NTP_SERVER
    from secrets import MQTT_SERVER, MQTT_PORT, MQTT_USER, MQTT_PASSWORD, MQTT_TOPIC
except ImportError:
    print("Create secrets.py with your WiFi & MQTT credentials")

LIGHT_SENSOR_AVERAGES = const(6)

gu = GalacticUnicorn()
clock = Clock(machine.RTC())
task_queue = collections.deque((), 10, 1)

# Light sensor outputs 0-4095, but usable range is approx 10-2000.
# Converted to 0-1.0 range by:
#   Taking the log
#   Dividing by scale factor
#   Adding to shift value
light_shift = -0.3
light_scale = 6.0

# Status/error message colors.
error_fg = "red"
error_bg = "black"
status_fg = "yellow"
status_bg = "black"

# Default configuration.
config = {
    "message_fg": "blue",
    "message_bg": "black",
}


async def main():
    # Set reasonable default brightness, start checking sensor.
    gu.set_brightness(0.4)
    asyncio.create_task(light_sense())

    # No scrolling here, prevents startup delay.
    gfx.draw_text(gu, "Starting", fg=gfx.COLORS[status_fg], bg=gfx.COLORS[status_bg])

    # Setup network, MQTT, sync NTP.
    await setup_mqtt()
    sync_time()

    asyncio.create_task(brightness())

    tasks = task_queue
    cl = clock

    while True:
        # TODO: Look into async safety for deque.
        if tasks:
            # Run queued task.
            await tasks.popleft()()
        else:
            # Base task: render clock.
            cl.update_time()
            if cl.has_changed():
                gfx.draw_clock(gu, cl)

        await asyncio.sleep(0.1)


# Constructs a task for the requested message text.
def message_task(text, foreground, background):
    async def display_message():
        await gfx.scroll_text(
            gu, text, fg=gfx.COLORS[foreground], bg=gfx.COLORS[background]
        )

    return display_message


# Synchronize the RTC time from NTP.
def sync_time():
    # DNS resolution not necessary, but nice for debugging.
    host_ip = usocket.getaddrinfo(NTP_SERVER, 123)[0][-1][0]
    print(f'NTP server "{NTP_SERVER}" resolved to {host_ip}')

    try:
        ntptime.host = host_ip
        ntptime.settime()
        print("Time set via NTP")
        scroll_status("Got NTP")
    except OSError:
        print("Time sync failed")
        scroll_error("Time sync failed")


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
        scroll_error("MQTT connection failed")

    for task in (mqtt_up, mqtt_receiver):
        asyncio.create_task(task(client))


async def mqtt_up(client):
    while True:
        await client.up.wait()
        client.up.clear()
        print("Connected to MQTT broker")
        scroll_status("MQTT connected")
        await client.subscribe(MQTT_TOPIC, 1)


async def mqtt_down(client):
    while True:
        await client.down.wait()
        client.down.clear()
        print("MQTT connection down")
        task_queue.append(message_task("MQTT connection down", status_fg, status_bg))


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
            sync_time()
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
        task_queue.append(
            message_task(
                message,
                obj.get("foreground", config["message_fg"]),
                obj.get("background", config["message_bg"]),
            )
        )
    else:
        print(f"Empty message received: {obj}")


async def brightness():
    while True:
        if gu.is_pressed(GalacticUnicorn.SWITCH_BRIGHTNESS_UP):
            gu.adjust_brightness(+0.01)
            gfx.update(gu)
        if gu.is_pressed(GalacticUnicorn.SWITCH_BRIGHTNESS_DOWN):
            gu.adjust_brightness(-0.01)
            gfx.update(gu)

        await asyncio.sleep(0.02)


async def light_sense():
    prev_bright = gu.get_brightness()
    lights = [gu.light()] * LIGHT_SENSOR_AVERAGES
    lights_next = 0

    while True:
        # Average recent light readings to reduce flicker.
        lights[lights_next] = gu.light()
        lights_next = (lights_next + 1) % LIGHT_SENSOR_AVERAGES
        light = sum(lights) // LIGHT_SENSOR_AVERAGES

        # Scale sensor to screen brightness (0-1.0)
        bright = (math.log(light) / light_scale) + light_shift
        bright = max(min(bright, 1.0), 0.0)

        if abs(bright - prev_bright) > 0.03:
            print(f"bright {prev_bright} -> {bright} for {light}")
            prev_bright = bright
            gu.set_brightness(bright)
            gfx.update(gu)

        await asyncio.sleep(0.1)


def scroll_error(message):
    task_queue.append(message_task(message, error_fg, error_bg))


def scroll_status(message):
    task_queue.append(message_task(message, status_fg, status_bg))


try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()
