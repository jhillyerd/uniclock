import math
import uasyncio as asyncio
from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN as DISPLAY

# Constants for controlling the background colour throughout the day.
MIDDAY_HUE = 1.1
MIDNIGHT_HUE = 0.8
HUE_OFFSET = -0.1
MIDDAY_SATURATION = 1.0
MIDNIGHT_SATURATION = 1.0
MIDDAY_VALUE = 0.8
MIDNIGHT_VALUE = 0.3

# Create galactic object and graphics surface for drawing.
graphics = PicoGraphics(DISPLAY)
width = GalacticUnicorn.WIDTH
height = GalacticUnicorn.HEIGHT

# Set up some pens to use later.
WHITE = graphics.create_pen(255, 255, 255)
BLACK = graphics.create_pen(0, 0, 0)

COLORS = {
    "black": graphics.create_pen(0, 0, 0),
    "white": graphics.create_pen(255, 255, 255),
    "red": graphics.create_pen(255, 0, 0),
    "green": graphics.create_pen(0, 255, 0),
    "blue": graphics.create_pen(0, 0, 255),
    "yellow": graphics.create_pen(255, 255, 0),
    "purple": graphics.create_pen(255, 0, 255),
    "cyan": graphics.create_pen(0, 255, 255),
    "orange": graphics.create_pen(255, 127, 0),
}


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


# Draws a gradient background.
def gradient_background(start_hue, start_sat, start_val, end_hue, end_sat, end_val):
    half_width = width // 2
    for x in range(0, half_width):
        hue = ((end_hue - start_hue) * (x / half_width)) + start_hue
        sat = ((end_sat - start_sat) * (x / half_width)) + start_sat
        val = ((end_val - start_val) * (x / half_width)) + start_val
        colour = from_hsv(hue, sat, val)
        graphics.set_pen(
            graphics.create_pen(int(colour[0]), int(colour[1]), int(colour[2]))
        )
        for y in range(0, height):
            graphics.pixel(x, y)
            graphics.pixel(width - x - 1, y)

    colour = from_hsv(end_hue, end_sat, end_val)
    graphics.set_pen(
        graphics.create_pen(int(colour[0]), int(colour[1]), int(colour[2]))
    )
    for y in range(0, height):
        graphics.pixel(half_width, y)


# Draws outlined text.
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


def draw_gradient_for_time(clock):
    percent_to_midday = clock.percent_to_midday()

    hue = ((MIDDAY_HUE - MIDNIGHT_HUE) * percent_to_midday) + MIDNIGHT_HUE
    sat = (
        (MIDDAY_SATURATION - MIDNIGHT_SATURATION) * percent_to_midday
    ) + MIDNIGHT_SATURATION
    val = ((MIDDAY_VALUE - MIDNIGHT_VALUE) * percent_to_midday) + MIDNIGHT_VALUE

    gradient_background(hue, sat, val, hue + HUE_OFFSET, sat, val)


# Draw the clock display with background.
def draw_clock(gu, clock):
    # Calculate text position so that it is centered.
    graphics.set_font("bitmap8")
    text = clock.text()
    w = graphics.measure_text(text, 1)
    x = int(width / 2 - w / 2 + 1)
    y = 2

    draw_gradient_for_time(clock)
    outline_text(text, x, y)
    gu.update(graphics)


# Draw a centered text message.
def draw_text(gu, text, fg=COLORS["white"], bg=COLORS["black"]):
    x_margin, y_margin = use_message_font()

    # Calculate text position so that it is centered.
    w = graphics.measure_text(text, 1)
    x = int(width / 2 - w / 2 + 1)

    graphics.set_pen(bg)
    graphics.clear()
    graphics.set_pen(fg)
    graphics.text(text, x, y_margin, -1, 1)

    gu.update(graphics)


# Scroll a text message across the screen.
async def scroll_text(gu, text, fg=COLORS["white"], bg=COLORS["black"]):
    x_margin, y_margin = use_message_font()
    tw = graphics.measure_text(text, 1)
    x = x_margin
    off_screen = tw - width

    def draw():
        graphics.set_pen(bg)
        graphics.clear()
        graphics.set_pen(fg)
        graphics.text(text, x, y_margin, -1, 1)
        gu.update(graphics)

    if off_screen < 1:
        # Fits on screen, draw centered and sleep.
        x = int(width / 2 - tw / 2 + 1)
        draw()
        await asyncio.sleep(3.0)
        return

    draw()
    await asyncio.sleep(1.0)

    min_x = 0 - off_screen - x_margin
    while x > min_x:
        draw()
        x -= 1
        await asyncio.sleep(0.05)

    await asyncio.sleep(1.0)


# Update display without drawing, ie for brightness change.
def update(gu):
    gu.update(graphics)


# Sets the font for messages, returns X and Y margins.
def use_message_font():
    graphics.set_font("bitmap8")
    return 2, 2
