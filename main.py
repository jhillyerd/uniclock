import collections
import gfx
import json
import machine
import ntptime
import uasyncio as asyncio
import usocket
from clock import Clock
from galactic import GalacticUnicorn
from mqtt_as import MQTTClient, config as MQTT_BASE_CONFIG


# Grab network config.
try:
    from secrets import WIFI_SSID, WIFI_PASSWORD, NTP_SERVER
    from secrets import MQTT_SERVER, MQTT_PORT, MQTT_USER, MQTT_PASSWORD, MQTT_TOPIC
except ImportError:
    print("Create secrets.py with your WiFi & MQTT credentials")

gu = GalacticUnicorn()
clock = Clock(machine.RTC())
task_queue = collections.deque((), 10, 1)


async def main():
    # Set reasonable default brightness.
    gu.set_brightness(0.5)
    gfx.draw_text(gu, "Starting")

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
            # Base state: render clock.
            cl.update_time()
            if cl.has_changed():
                gfx.draw_clock(gu, cl)

        await asyncio.sleep(0.1)


# Constructs a task for the requested message text.
def message_task(text):
    async def display_message():
        gfx.draw_text(gu, text)
        await asyncio.sleep(5)

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
    except OSError:
        print("Time sync failed")


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

    for task in (mqtt_up, mqtt_receiver):
        asyncio.create_task(task(client))


async def mqtt_up(client):
    while True:
        await client.up.wait()
        client.up.clear()
        print("Connected to MQTT broker")
        await client.subscribe(MQTT_TOPIC, 1)


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
    print("Reconfiguring")
    if obj["utc_offset"]:
        offset = int(obj["utc_offset"])
        clock.utc_offset = offset


def handle_message(obj):
    message = obj["message"]
    if message:
        task_queue.append(message_task(message))
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


try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()
