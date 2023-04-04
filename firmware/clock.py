import collections
import gfx
import math
import ntptime
import uasyncio as asyncio
import usocket


# Clock handles task queuing and time-keeping, but not graphics.
class Clock:
    def __init__(self, config, rtc, galactic_unicorn):
        self.config = config
        self.rtc = rtc
        self.gu = galactic_unicorn

        self.task_queue = collections.deque((), 10, 1)
        self.last_second = -1

        self.apply_config(config)
        self.update_time()

    async def main_loop(self):
        tasks = self.task_queue

        while True:
            # TODO: Look into async safety for deque.
            if tasks:
                # Run queued task.
                await tasks.popleft()()
            else:
                # Base task: render clock.
                if self.update_time():
                    gfx.draw_clock(self.gu, self)

            await asyncio.sleep(0.1)

    def apply_config(self, config):
        self.utc_offset = int(config["utc_offset"])
        self.twentyfour = bool(config["24_hour"])

    # Updates time from RTC, returns true if it has changed.
    def update_time(self):
        # Set time fields.
        (
            self.year,
            self.month,
            self.day,
            self.wd,
            self.hour,
            self.minute,
            self.second,
            _,
        ) = self.rtc.datetime()
        if self.twentyfour:
            self.hour = (self.hour + self.utc_offset) % 24
        else:
            self.hour = (self.hour + self.utc_offset) % 12

        # Has the second field changed?
        if self.second != self.last_second:
            self.last_second = self.second
            return True

        return False

    def percent_to_midday(self):
        time_through_day = (((self.hour * 60) + self.minute) * 60) + self.second
        percent_through_day = time_through_day / 86400

        return 1.0 - ((math.cos(percent_through_day * math.pi * 2) + 1) / 2)

    def text(self):
        return "{:02}:{:02}:{:02}".format(self.hour, self.minute, self.second)

    # Enqueues a task to scroll the specified message text.
    def message_task(self, text, fg_name, bg_name):
        fg_name = fg_name if fg_name in gfx.COLORS else "white"
        bg_name = bg_name if bg_name in gfx.COLORS else "black"

        async def display_message():
            await gfx.scroll_text(
                self.gu, text, fg=gfx.COLORS[fg_name], bg=gfx.COLORS[bg_name]
            )

        self.task_queue.append(display_message)

    def scroll_error(self, message):
        self.message_task(message, self.config["error_fg"], self.config["error_bg"])

    def scroll_status(self, message):
        self.message_task(message, self.config["status_fg"], self.config["status_bg"])

    # Synchronize the RTC time from NTP.
    def sync_time(self, ntp_host):
        # DNS resolution not necessary, but nice for debugging.
        host_ip = usocket.getaddrinfo(ntp_host, 123)[0][-1][0]
        print(f'NTP server "{ntp_host}" resolved to {host_ip}')

        try:
            ntptime.host = host_ip
            ntptime.settime()
            print("Time set via NTP")
            self.scroll_status("NTP synced")
        except OSError:
            print("NTP time sync failed")
            self.scroll_error("Time sync failed")
