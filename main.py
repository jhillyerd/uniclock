import gfx
import machine
import ntptime
import uasyncio as asyncio
import usocket
from clock import Clock
from galactic import GalacticUnicorn
from mqtt_as import MQTTClient, config as MQTT_BASE_CONFIG

from secrets import MQTT_SERVER, MQTT_PORT, MQTT_USER, MQTT_PASSWORD, MQTT_TOPIC

# Grab network config.
try:
    from secrets import WIFI_SSID, WIFI_PASSWORD, NTP_SERVER
    wifi_available = True
except ImportError:
    print("Create secrets.py with your WiFi credentials to get time from NTP")
    wifi_available = False

gu = GalacticUnicorn()
clock = Clock(machine.RTC())


async def main():
    gu.set_brightness(0.5)

    # MQTT setup.
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

        clock.update_time()
        if clock.has_changed():
            gfx.draw_clock(gu, clock)

        await asyncio.sleep(0.05)


# Synchronize the RTC time from NTP.
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
