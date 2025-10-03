import os
import signal
import smtplib
import threading
import time
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import keyboard
import pyautogui
from dotenv import load_dotenv


TEMP_SCREENSHOT = None
CURRENT_SERVER = None
_CLEANED = False
_CLEAN_LOCK = threading.Lock()

load_dotenv(dotenv_path=".env")
mail_user = os.getenv("MAIL_USER")
mail_password = os.getenv("MAIL_PASSWORD")


def _cleanup():
    global TEMP_SCREENSHOT, CURRENT_SERVER, _CLEANED
    with _CLEAN_LOCK:
        if _CLEANED:
            return
        print(">>> Cleaning up before exit...")

        # Remove temporary screenshot file if it exists
        if TEMP_SCREENSHOT and os.path.exists(TEMP_SCREENSHOT):
            try:
                os.remove(TEMP_SCREENSHOT)
                print(f">>> Removed temporary file: {TEMP_SCREENSHOT}")
            except Exception as e:
                print(f">>> Failed to remove temporary file: {e}")
            TEMP_SCREENSHOT = None

        # Close SMTP server connection if open
        if CURRENT_SERVER:
            try:
                CURRENT_SERVER.quit()
                print(">>> Closed SMTP server connection.")
            except Exception as e:
                pass
            CURRENT_SERVER = None
        _CLEANED = True


def _shutdown_now():
    try:
        keyboard.unhook_all()
    except Exception:
        pass
    _cleanup()
    print(">>> Exiting now...")
    os._exit(0)


def hard_kill():
    print("F12 detected — stopping script immediately.")
    t = threading.Thread(target=_shutdown_now, daemon=True)
    t.start()


keyboard.add_hotkey('f12', hard_kill, suppress=True)


def _sig_handler(signum, frame):
    print(f"Signal {signum} received — stopping script.")
    _shutdown_now()


try:
    signal.signal(signal.SIGINT, _sig_handler)  # Ctrl+C
except Exception:
    pass
try:
    signal.signal(signal.SIGTERM, _sig_handler)  # 终止信号
except Exception:
    pass


def send_email():
    global TEMP_SCREENSHOT, CURRENT_SERVER

    to = '737641891@qq.com'
    subject = 'Check running result'
    body = 'Running ends, check result.'
    screenshot_file = "screenshot.png"

    TEMP_SCREENSHOT = screenshot_file
    pyautogui.screenshot(screenshot_file)

    msg = MIMEMultipart('related')
    msg['From'] = mail_user
    msg['To'] = to
    msg['Subject'] = subject

    msg_alternative = MIMEMultipart('alternative')
    msg.attach(msg_alternative)
    msg_text = MIMEText(body, 'html')
    msg_alternative.attach(msg_text)

    with open(screenshot_file, 'rb') as img:
        msg_image = MIMEImage(img.read())
        msg_image.add_header('Content-Disposition', 'attachment', filename=os.path.basename(screenshot_file))
        msg.attach(msg_image)

    try:
        CURRENT_SERVER = smtplib.SMTP('smtp.qq.com', 587)
        CURRENT_SERVER.starttls()
        CURRENT_SERVER.login(mail_user, mail_password)
        CURRENT_SERVER.sendmail(mail_user, to, msg.as_string())
        print('mail sent')
    except Exception as e:
        print(f'mail sent fail: {e}')
    finally:
        if CURRENT_SERVER:
            try:
                CURRENT_SERVER.quit()
            except Exception:
                pass
            CURRENT_SERVER = None
        if TEMP_SCREENSHOT and os.path.exists(TEMP_SCREENSHOT):
            try:
                os.remove(TEMP_SCREENSHOT)
                print("Temp screenshot deleted.")
            except Exception as e:
                print(f"Failed to delete screenshot: {e}")
        TEMP_SCREENSHOT = None


def check_color(x, y, color):
    # Check if the color at a specific screen position matches the given color.
    screen_color = pyautogui.screenshot().getpixel((x, y))
    return screen_color == color


def main_script():
    while True:
        # Loop until the main screen is detected
        while not check_color(1900, 420, (247, 247, 247)):
            time.sleep(0.5)  # Wait a bit before rechecking

        # On the main screen, press Enter twice
        time.sleep(1)
        pyautogui.press('enter', presses=2, interval=0.5)

        # Loop until no lag is detected
        while not (check_color(1678, 701, (255, 255, 255)) or check_color(2360, 476, (247, 247, 247))):
            time.sleep(0.5)  # Wait a bit before rechecking

        # Check if car is on sale
        if check_color(1000, 325, (247, 247, 247)):
            # If available, keep pressing Y until enter the buying screen
            while check_color(700, 1330, (21, 9, 21)):
                pyautogui.press('y')
                time.sleep(0.5)

            # Try to buy
            if not check_color(1700, 885, (247, 247, 247)):
                print("Car not available any more, returning to main screen...")
                pyautogui.press('esc', presses=2, interval=0.5)
                continue

            pyautogui.press('down')
            time.sleep(0.2)
            pyautogui.press('enter', presses=2, interval=0.2)

            # Wait to see if buying is successful
            time.sleep(10)

            # Notify by email
            send_email()

            # Failed buying, exit to main screen and try again
            if not check_color(1559, 772, (247, 247, 247)):
                print("Buying failed, retrying...")
                pyautogui.press('enter')
                time.sleep(0.5)
                pyautogui.press('esc', presses=2, interval=0.5)
            else:
                print("Buying successful, exiting script.")
                pyautogui.press('enter')
                time.sleep(0.5)
                pyautogui.press('esc', presses=2, interval=0.5)
                time.sleep(1)
                pyautogui.press('right')
                time.sleep(0.5)
                pyautogui.press('down')
                time.sleep(0.5)
                pyautogui.press('enter')
                _shutdown_now()

        # If no car is on sale, press Esc to return to the main screen
        else:
            pyautogui.press('esc')


# Run the script
if __name__ == "__main__":
    print("Press F12 at any time to stop the script.")
    try:
        main_script()
    except KeyboardInterrupt:
        _shutdown_now()
