import pyautogui
import time
import keyboard
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

def send_email():
    to='meta0000ff@gmail.com'
    subject='Check running result'
    body='Running ends, check result.<br><br><img src="cid:screenshot">'
    screenshot_file="screenshot.png"
    pyautogui.screenshot(screenshot_file)
    msg=MIMEMultipart('related')
    msg['From']=gmail_user
    msg['To']=to
    msg['Subject']=subject
    msg_alternative=MIMEMultipart('alternative')
    msg.attach(msg_alternative)
    msg_text=MIMEText(body,'html')
    msg_alternative.attach(msg_text)

    with open(screenshot_file,'rb') as img:
        msg_image=MIMEImage(img.read())
        msg_image.add_header('Content_ID','<screenshot>')
        msg.attach(msg_image)

    try:
        server=smtplib.SMTP('smtp.gmail.com',587)
        server.starttls()
        server.login(gmail_user,gmail_password)
        text=msg.as_string()
        server.sendmail(gmail_user,to,text)
        server.quit()
        print('mail sent')
    except Exception as e:
        print(f'mail sent fail: {e}')
    os.remove(screenshot_file)

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
        time.sleep(1)
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
            time.sleep(10)
            # Failed buying, try again
            send_email()
        else:
            # If not available, press Esc to return to the main screen
            pyautogui.press('esc')


# Run the script
main_script()
