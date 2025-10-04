import time

import pyautogui


def check_color(x, y, color):
    # Check if the color at a specific screen position matches the given color.
    try:
        px = pyautogui.screenshot(region=(x, y, 1, 1)).getpixel((0, 0))
        return px == color
    except OSError:
        time.sleep(0.05)
        return False
