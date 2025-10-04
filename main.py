import logging
import os
import time
from time import sleep

import pyautogui

from config import MAIL_USER, OUTBOX_DIR, STATS_LOG_INTERVAL, STATS_MILESTONE
from emailer import EmailJob, EmailSender
from logutil import clog
from shutddown import inject_refs, register_hotkeys_and_signals, _cleanup_and_exit
from stats import Stats
from vision import check_color


pyautogui.FAILSAFE = True


def send_stats_email_async(email_sender, snapshot: dict):
    html = f"""
    <h3>AutoBuy Stats Milestone</h3>
    <p>Reached <b>{snapshot['no_sale_visits']}</b> no-sale visits.</p>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
      <tr><th align="left">Timestamp</th><td>{snapshot['timestamp']}</td></tr>
      <tr><th align="left">No-sale visits (total)</th><td>{snapshot['no_sale_visits']}</td></tr>
      <tr><th align="left">Purchase attempts</th><td>{snapshot['purchase_attempts']}</td></tr>
      <tr><th align="left">Purchase failures</th><td>{snapshot['purchase_failures']}</td></tr>
      <tr><th align="left">Time to FIRST sale from start (s)</th><td>{snapshot['time_to_first_sale_from_start_sec']}</td></tr>
      <tr><th align="left">No-sale before FIRST sale</th><td>{snapshot['no_sale_before_first_sale']}</td></tr>
      <tr><th align="left">Avg sale interval (s)</th><td>{snapshot['avg_sale_interval_sec']}</td></tr>
      <tr><th align="left">Sale occurrences</th><td>{snapshot['sale_occurrences']}</td></tr>
      <tr><th align="left">First sale seen?</th><td>{snapshot['first_sale_seen']}</td></tr>
    </table>
    """
    job = EmailJob(
        to_addr=MAIL_USER,
        subject=f"AutoBuy Stats — No-sale={snapshot['no_sale_visits']}",
        html_body=html,
        screenshot_path=None,
    )
    email_sender.send_async(job)


def send_success_email_with_shot(email_sender, snapshot):
    os.makedirs(OUTBOX_DIR, exist_ok=True)
    screenshot_file = os.path.join(OUTBOX_DIR, f"screenshot_{int(time.time() * 1000)}.png")
    pyautogui.screenshot(screenshot_file)

    stats_html = f"""
    <h3>AutoBuy Stats (at success)</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
      <tr><th align="left">Timestamp</th><td>{snapshot['timestamp']}</td></tr>
      <tr><th align="left">No-sale visits (total)</th><td>{snapshot['no_sale_visits']}</td></tr>
      <tr><th align="left">Purchase attempts</th><td>{snapshot['purchase_attempts']}</td></tr>
      <tr><th align="left">Purchase failures</th><td>{snapshot['purchase_failures']}</td></tr>
      <tr><th align="left">Time to FIRST sale from start (s)</th><td>{snapshot['time_to_first_sale_from_start_sec']}</td></tr>
      <tr><th align="left">No-sale before FIRST sale</th><td>{snapshot['no_sale_before_first_sale']}</td></tr>
      <tr><th align="left">Avg sale interval (s)</th><td>{snapshot['avg_sale_interval_sec']}</td></tr>
      <tr><th align="left">Sale occurrences</th><td>{snapshot['sale_occurrences']}</td></tr>
      <tr><th align="left">First sale seen?</th><td>{snapshot['first_sale_seen']}</td></tr>
    </table>
    """

    html = (
            '<p>The car purchase was <b>successful</b>. See the screenshot below:</p>'
            '<img src="cid:screenshot"><br><br>' + stats_html
    )

    email_sender.send_async(EmailJob(
        to_addr=MAIL_USER,
        subject='Car Purchase Successful',
        html_body=html,
        screenshot_path=screenshot_file
    ))


def main_loop():
    email_sender = EmailSender()
    email_sender.start()

    stats = Stats(log_interval_sec=STATS_LOG_INTERVAL,
                  milestone=STATS_MILESTONE,
                  milestone_cb=lambda snap: send_stats_email_async(email_sender, snap))
    stats.start()

    inject_refs(stats, email_sender)
    register_hotkeys_and_signals()

    clog(logging.INFO, "CORE", "Press F12 at any time to stop the script.")

    while True:
        stats.mark_enter_main()
        clog(logging.DEBUG, "DETECT", "Waiting for MAIN screen...")

        # Loop until the main screen is detected
        while not check_color(1900, 420, (247, 247, 247)):
            time.sleep(0.5)

        # On the main screen, press Enter twice
        clog(logging.INFO, "DETECT", "MAIN screen detected.")
        time.sleep(1)
        pyautogui.press('enter', presses=2, interval=0.5)

        # Loop until no lag is detected
        clog(logging.DEBUG, "DETECT", "Waiting for NO-LAG state...")
        while not (check_color(1678, 701, (255, 255, 255)) or check_color(2360, 476, (247, 247, 247))):
            time.sleep(0.5)
        clog(logging.INFO, "DETECT", "NO-LAG state detected.")

        # Check if car is on sale
        if check_color(1000, 325, (247, 247, 247)):
            clog(logging.INFO, "DETECT", "CAR ON SALE detected.")
            stats.mark_first_sale_seen()

            # If available, keep pressing Y until enter the buying screen
            while check_color(700, 1330, (21, 9, 21)):
                pyautogui.press('y')
                time.sleep(0.5)

            # Try to buy
            if not check_color(1700, 885, (247, 247, 247)):
                clog(logging.WARNING, "BUY", "Car unavailable, back to MAIN.")
                pyautogui.press('esc', presses=2, interval=0.5)
                stats.mark_purchase_attempt()
                stats.mark_purchase_failure()
                continue

            stats.mark_purchase_attempt()
            clog(logging.INFO, "BUY", "Proceeding to BUY: navigating and confirming...")
            pyautogui.press('down')
            time.sleep(0.2)
            pyautogui.press('enter', presses=2, interval=0.2)

            # Wait to see if buying is successful
            clog(logging.DEBUG, "BUY", "Waiting for purchase result...")
            time.sleep(10)

            # Failed buying, exit to main screen and try again
            if not check_color(1559, 772, (247, 247, 247)):
                clog(logging.WARNING, "BUY", "Buying failed. Back to MAIN...")
                stats.mark_purchase_failure()
                pyautogui.press('enter')
                time.sleep(0.5)
                pyautogui.press('esc', presses=2, interval=0.5)
            else:
                clog(logging.INFO, "BUY", "Buying SUCCESS. Doing final navigation and notification...")
                pyautogui.press('enter')
                time.sleep(0.5)
                pyautogui.press('esc', presses=2, interval=0.5)
                time.sleep(1)
                pyautogui.press('right')
                time.sleep(0.5)
                pyautogui.press('down')
                time.sleep(0.5)
                pyautogui.press('enter')
                sleep(8)

                snap = stats.snapshot()
                clog(logging.INFO, "STATS",
                     f"SUCCESS snapshot: time_to_first_sale_from_start={snap['time_to_first_sale_from_start_sec']}s, "
                     f"no_sale_before_first_sale={snap['no_sale_before_first_sale']}, "
                     f"avg_sale_interval={snap['avg_sale_interval_sec']}s "
                     f"(occurrences={snap['sale_occurrences']})")
                # Notify by email
                send_success_email_with_shot(email_sender, snap)
                _cleanup_and_exit()

        # If no car is on sale, press Esc to return to the main screen
        else:
            stats.mark_no_sale()
            clog(logging.INFO, "DETECT", "No car on sale. Returning to MAIN (Esc).")
            pyautogui.press('esc')


# -------------------- Entry Point --------------------
if __name__ == "__main__":
    try:
        main_loop()
    except pyautogui.FailSafeException:
        clog(logging.WARNING, "CORE", "PyAutoGUI FailSafe triggered — stopping.")
        _cleanup_and_exit()
    except KeyboardInterrupt:
        _cleanup_and_exit()
