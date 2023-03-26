import math


# Clock handles time-keeping, but not graphics.
class Clock:
    def __init__(self, rtc):
        self.rtc = rtc
        self.utc_offset = 0
        self.last_second = -1

        self.update_time()

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
        self.hour = (self.hour + self.utc_offset) % 24

        # Has the second field changed?
        self.changed = self.second != self.last_second
        self.last_second = self.second

    # Has the time changed since last update?
    def has_changed(self):
        return self.changed

    def percent_to_midday(self):
        time_through_day = (((self.hour * 60) + self.minute) * 60) + self.second
        percent_through_day = time_through_day / 86400

        return 1.0 - ((math.cos(percent_through_day * math.pi * 2) + 1) / 2)

    def text(self):
        return "{:02}:{:02}:{:02}".format(self.hour, self.minute, self.second)
