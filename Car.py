import pyautogui
import time
import keyboard


def check_color(x, y, color):
    """Check if the color at a specific screen position matches the given color."""
    screen_color = pyautogui.screenshot().getpixel((x, y))
    return screen_color == color


def main_script():
    while True:
        # Check if F12 is pressed to stop the script
        if keyboard.is_pressed('f12'):
            print("F12 pressed, stopping the script.")
            break

        # Loop until the main screen is detected
        while not check_color(1900, 420, (247, 247, 247)):
            time.sleep(0.5)  # Wait a bit before rechecking
            if keyboard.is_pressed('f12'):
                print("F12 pressed, stopping the script.")
                return

        # On the main screen, press Enter twice
        pyautogui.press('enter', presses=2, interval=0.5)

        # Loop until no lag is detected
        while not (check_color(1678, 701, (255, 255, 255)) or check_color(2360, 476, (247, 247, 247))):
            time.sleep(0.5)  # Wait a bit before rechecking
            if keyboard.is_pressed('f12'):
                print("F12 pressed, stopping the script.")
                return

        # Check for availability
        if check_color(750, 350, (247, 247, 247)):
            # If available, keep pressing Enter until a specific condition is met
            while not check_color(450, 750, (247, 247, 247)):
                pyautogui.press('enter')
                time.sleep(0.5)
                if keyboard.is_pressed('f12'):
                    print("F12 pressed, stopping the script.")
                    return
            # Final sequence of key presses
            pyautogui.press('down')  # Press down arrow key
            time.sleep(0.5)
            pyautogui.press('enter', presses=2, interval=0.5)  # Press Enter twice
            break
        else:
            # If not available, press Esc to return to the main screen
            pyautogui.press('esc')


# Run the script
main_script()
