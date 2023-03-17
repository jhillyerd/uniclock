import gfx
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


# Tracks the current state of the clock, allowing future states to be queued.
# If the queue is empty, the base state will be used. States are repsented as
# async functions.
class State:
    def __init__(self, base_state):
        self.base = base_state
        self.queue = []

    def set_base(self, state):
        self.base = state

    def enqueue(self, state):
        self.queue.append(state)

    def next(self):
        if len(self.queue):
            return self.queue.pop(0)()
        else:
            return self.base()


async def main():
    global state

    # Set reasonable default brightness.
    gu.set_brightness(0.5)

    state = State(message_state("Net Init"))
    await state.next()

    # Setup network, MQTT, sync NTP.
    await setup_mqtt()
    sync_time()
    state.set_base(time_state)

    asyncio.create_task(brightness())

    while True:
        await state.next()
        await asyncio.sleep(0.1)


# Typically the base state of the clock, it checks the current time and redraws
# the screen if needed.
async def time_state():
    clock.update_time()
    if clock.has_changed():
        gfx.draw_clock(gu, clock)


# Constructs a state for the requested message text.
def message_state(text):
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
    config["queue_len"] = 1  # Use event interface with default queue

    MQTTClient.DEBUG = True
    return MQTTClient(config)


async def setup_mqtt():
    client = setup_mqtt_client()
    try:
        await client.connect()
    except OSError:
        print("MQTT connection failed.")

    for task in (mqtt_up, mqtt_receiver):
        asyncio.create_task(task(client))


async def mqtt_up(client):
    while True:
        await client.up.wait()
        client.up.clear()
        print("Connected to MQTT broker.")
        await client.subscribe(MQTT_TOPIC, 1)


async def mqtt_receiver(client):
    # Loop over incoming messages.
    async for topic, msg, retained in client.queue:
        print(
            f'Topic: "{topic.decode()}" Message: "{msg.decode()}" Retained: {retained}'
        )
        state.enqueue(message_state(msg.decode()))


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
