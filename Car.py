import json
import logging
import os
import queue
import signal
import smtplib
import threading
import time
from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from time import sleep

import keyboard
import pyautogui
from colorama import init as colorama_init, Fore, Style
from dotenv import load_dotenv


# -------------------- Color Logger --------------------
colorama_init(autoreset=True)


class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: Style.DIM,
        logging.INFO: Fore.CYAN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }


    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, "")
        reset = Style.RESET_ALL
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


logger = logging.getLogger("autobuy")
logger.setLevel(logging.DEBUG)
_handler = logging.StreamHandler()
_handler.setFormatter(
    ColorFormatter(fmt="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(_handler)

COMP_COLORS = {
    "CORE": Fore.WHITE + Style.BRIGHT,
    "DETECT": Fore.MAGENTA + Style.BRIGHT,
    "BUY": Fore.GREEN + Style.BRIGHT,
    "EMAIL": Fore.BLUE + Style.BRIGHT,
    "STATS": Fore.CYAN + Style.BRIGHT,
}


def clog(level, comp, msg):
    c = COMP_COLORS.get(comp, "")
    reset = Style.RESET_ALL
    logger.log(level, f"{c}[{comp}]{reset} {msg}")


# -------------------- PyAutoGUI Settings --------------------
pyautogui.FAILSAFE = True

# -------------------- Global Variables --------------------
TEMP_SCREENSHOT = None
CURRENT_SERVER = None
_CLEANED = False
_EXITING = False
_CLEAN_LOCK = threading.Lock()

# -------------------- Load Environment Variables --------------------
load_dotenv(dotenv_path=".env")
mail_user = os.getenv("MAIL_USER")
mail_password = os.getenv("MAIL_PASSWORD")
if not mail_user or not mail_password:
    raise ValueError("MAIL_USER and MAIL_PASSWORD must be set in the .env file")


# -------------------- Util: Pixel Check --------------------
def check_color(x, y, color):
    # Check if the color at a specific screen position matches the given color.
    try:
        px = pyautogui.screenshot(region=(x, y, 1, 1)).getpixel((0, 0))
        return px == color
    except OSError:
        time.sleep(0.05)
        return False


# -------------------- Async Email Notification --------------------
class EmailJob:


    def __init__(self, to_addr, subject, html_body, screenshot_path=None):
        self.to_addr = to_addr
        self.subject = subject
        self.html_body = html_body
        self.screenshot_path = screenshot_path
        self.created_at = time.time()


class EmailSender:


    def __init__(self, user, password, retry_dir="outbox", scan_interval=60, max_queue=1000):
        self.user = user
        self.password = password
        self.retry_dir = retry_dir
        self.scan_interval = scan_interval
        self.queue = queue.Queue(maxsize=max_queue)
        self.stop_event = threading.Event()
        os.makedirs(self.retry_dir, exist_ok=True)

        self.worker = threading.Thread(target=self._worker_loop, daemon=True, name="email-worker")
        self.scanner = threading.Thread(target=self._scan_loop, daemon=True, name="email-retry-scanner")


    def start(self):
        self.worker.start()
        self.scanner.start()


    def shutdown(self, wait_seconds=1.0):
        self.stop_event.set()
        try:
            self.queue.join()
        except Exception:
            pass
        t0 = time.time()
        while not self.queue.empty() and (time.time() - t0) < wait_seconds:
            time.sleep(0.05)


    def send_async(self, job: EmailJob):
        try:
            self.queue.put_nowait(job)
            clog(logging.INFO, "EMAIL",
                 f"queued: {os.path.basename(job.screenshot_path) if job.screenshot_path else '(no attachment)'}")
        except queue.Full:
            clog(logging.WARNING, "EMAIL", "queue full, fallback to cache on disk")
            self._cache_to_disk(job)


    def _worker_loop(self):
        while not self.stop_event.is_set():
            try:
                job = self.queue.get(timeout=0.2)
            except queue.Empty:
                if self.stop_event.is_set():
                    break
                continue
            try:
                self._send(job)
                if job.screenshot_path and os.path.exists(job.screenshot_path):
                    os.remove(job.screenshot_path)
                clog(logging.INFO, "EMAIL", "sent successfully")
            except Exception as e:
                clog(logging.ERROR, "EMAIL", f"send failed: {e}")
                self._cache_to_disk(job)
            finally:
                self.queue.task_done()


    def _scan_loop(self):
        while not self.stop_event.is_set():
            try:
                for name in os.listdir(self.retry_dir):
                    if not name.endswith(".json"):
                        continue
                    meta_path = os.path.join(self.retry_dir, name)
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    shot_path = meta.get("screenshot_path")
                    job = EmailJob(
                        to_addr=meta.get("to_addr"),
                        subject=meta.get("subject"),
                        html_body=meta.get("html_body"),
                        screenshot_path=shot_path if shot_path else None
                    )
                    try:
                        self.queue.put_nowait(job)
                        os.remove(meta_path)
                        clog(logging.DEBUG, "EMAIL",
                             f"re-queued cached job: {os.path.basename(shot_path) if shot_path else '(no attachment)'}")
                    except queue.Full:
                        clog(logging.WARNING, "EMAIL", "queue still full, keep cached")
            except Exception as e:
                clog(logging.ERROR, "EMAIL", f"scan failed: {e}")
            for _ in range(int(self.scan_interval * 10)):
                if self.stop_event.is_set():
                    break
                time.sleep(0.1)


    def _cache_to_disk(self, job: EmailJob):
        base = os.path.splitext(os.path.basename(job.screenshot_path))[
            0] if job.screenshot_path else f"job_{int(time.time() * 1000)}"
        meta_path = os.path.join(self.retry_dir, f"{base}.json")
        data = {
            "to_addr": job.to_addr,
            "subject": job.subject,
            "html_body": job.html_body,
            "screenshot_path": job.screenshot_path,
            "created_at": datetime.now().isoformat() + "Z"
        }
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            clog(logging.INFO, "EMAIL", f"cached job to disk: {os.path.basename(meta_path)}")
        except Exception as e:
            clog(logging.ERROR, "EMAIL", f"failed to write cache meta: {e}")


    def _send(self, job: EmailJob):
        msg = MIMEMultipart('related')
        msg['From'] = self.user
        msg['To'] = job.to_addr
        msg['Subject'] = job.subject

        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText(job.html_body, 'html'))
        msg.attach(alt)

        if job.screenshot_path and os.path.exists(job.screenshot_path):
            with open(job.screenshot_path, 'rb') as img:
                msg_image = MIMEImage(img.read())
                msg_image.add_header('Content-ID', '<screenshot>')
                msg_image.add_header('Content-Disposition', 'inline')
                msg.attach(msg_image)

        server = None
        try:
            server = smtplib.SMTP_SSL('smtp.qq.com', 465, timeout=15)
            server.login(self.user, self.password)
            server.sendmail(self.user, job.to_addr, msg.as_string())
        finally:
            try:
                if server:
                    server.quit()
            except Exception:
                pass


# -------------------- Async Stats --------------------
class Stats:


    def __init__(self, log_interval_sec=30, milestone=300, milestone_cb=None):
        self.no_sale_visits = 0
        self.purchase_attempts = 0
        self.purchase_failures = 0

        self._first_sale_count = 0
        self._first_sale_total_secs = 0.0

        self._last_enter_main_ts = None
        self._lock = threading.Lock()

        self._log_interval = log_interval_sec
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="stats-reporter")

        self._milestone = milestone
        self._milestone_cb = milestone_cb


    def start(self):
        self._thread.start()


    def stop(self):
        self._stop.set()


    def mark_enter_main(self):
        with self._lock:
            self._last_enter_main_ts = time.time()


    def mark_no_sale(self):
        snapshot_for_cb = None
        reached = False
        with self._lock:
            self.no_sale_visits += 1
            if self._milestone and self.no_sale_visits % self._milestone == 0:
                snapshot_for_cb = self._snapshot_unlocked()
                reached = True
        if reached and self._milestone_cb:
            threading.Thread(target=self._milestone_cb, args=(snapshot_for_cb,),
                             daemon=True, name="stats-milestone-cb").start()


    def mark_purchase_attempt(self):
        with self._lock:
            self.purchase_attempts += 1


    def mark_purchase_failure(self):
        with self._lock:
            self.purchase_failures += 1


    def mark_first_sale_seen(self):
        with self._lock:
            if self._last_enter_main_ts:
                delta = time.time() - self._last_enter_main_ts
                self._first_sale_total_secs += delta
                self._first_sale_count += 1
                self._last_enter_main_ts = None  # 只记录首次在售的耗时，后续不累加


    def snapshot(self):
        with self._lock:
            return self._snapshot_unlocked()


    def _snapshot_unlocked(self):
        avg_time = (self._first_sale_total_secs / self._first_sale_count) if self._first_sale_count > 0 else 0.0
        return {
            "no_sale_visits": self.no_sale_visits,
            "purchase_attempts": self.purchase_attempts,
            "purchase_failures": self.purchase_failures,
            "avg_time_to_first_sale_sec": round(avg_time, 2),
            "first_sale_samples": self._first_sale_count,
            "timestamp": datetime.now().isoformat() + "Z"
        }


    def _loop(self):
        while not self._stop.is_set():
            time.sleep(self._log_interval)
            snap = self.snapshot()
            clog(logging.INFO, "STATS",
                 f"no_sale={snap['no_sale_visits']} "
                 f"attempts={snap['purchase_attempts']} "
                 f"failures={snap['purchase_failures']} "
                 f"avg_time_to_first_sale={snap['avg_time_to_first_sale_sec']}s "
                 f"(n={snap['first_sale_samples']})"
                 )


# -------------------- Cleanup and Shutdown --------------------
def _cleanup():
    global TEMP_SCREENSHOT, CURRENT_SERVER, _CLEANED
    with _CLEAN_LOCK:
        if _CLEANED:
            return
        logger.debug(">>> Cleaning up before exit...")

        # Close SMTP server connection if open
        if CURRENT_SERVER:
            try:
                CURRENT_SERVER.quit()
                logger.debug(">>> Closed SMTP server connection.")
            except Exception as e:
                pass
            CURRENT_SERVER = None

        # Remove temporary screenshot file if it exists
        if TEMP_SCREENSHOT and os.path.exists(TEMP_SCREENSHOT):
            try:
                os.remove(TEMP_SCREENSHOT)
                logger.debug(f">>> Removed temporary file: {TEMP_SCREENSHOT}")
            except Exception as e:
                logger.warning(f">>> Failed to remove temporary file: {e}")
            TEMP_SCREENSHOT = None

        _CLEANED = True


def _shutdown_now():
    global _EXITING
    if _EXITING:
        return
    _EXITING = True
    try:
        keyboard.unhook_all()
    except Exception:
        pass

    try:
        stats.stop()
    except Exception:
        pass
    try:
        email_sender.shutdown(wait_seconds=5.0)
    except Exception:
        pass

    _cleanup()
    clog(logging.INFO, "CORE", ">>> Exiting now...")
    try:
        time.sleep(1)
    except Exception:
        pass
    os._exit(0)


def hard_kill():
    if _EXITING:
        return
    clog(logging.WARNING, "CORE", "F12 detected — stopping script immediately.")
    t = threading.Thread(target=_shutdown_now, daemon=True, name="hard_kill")
    t.start()


keyboard.add_hotkey('f12', hard_kill, suppress=True)


def _sig_handler(signum, frame):
    clog(logging.WARNING, "CORE", f"Signal {signum} received — stopping script.")
    _shutdown_now()


try:
    signal.signal(signal.SIGINT, _sig_handler)  # Ctrl+C
except Exception:
    pass
try:
    signal.signal(signal.SIGTERM, _sig_handler)  # End Signal
except Exception:
    pass

# -------------------- Email sender & Stats instances --------------------
email_sender = EmailSender(user=mail_user, password=mail_password, retry_dir="outbox", scan_interval=60)
email_sender.start()


def send_stats_email_async(snapshot: dict):
    html = f"""
    <h3>AutoBuy Stats Milestone</h3>
    <p>Reached <b>{snapshot['no_sale_visits']}</b> no-sale visits.</p>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
      <tr><th align="left">Timestamp (UTC)</th><td>{snapshot['timestamp']}</td></tr>
      <tr><th align="left">No-sale visits</th><td>{snapshot['no_sale_visits']}</td></tr>
      <tr><th align="left">Purchase attempts</th><td>{snapshot['purchase_attempts']}</td></tr>
      <tr><th align="left">Purchase failures</th><td>{snapshot['purchase_failures']}</td></tr>
      <tr><th align="left">Avg time to first sale (s)</th><td>{snapshot['avg_time_to_first_sale_sec']}</td></tr>
      <tr><th align="left">First-sale samples</th><td>{snapshot['first_sale_samples']}</td></tr>
    </table>
    """
    job = EmailJob(
        to_addr=mail_user,
        subject=f"AutoBuy Stats — No-sale={snapshot['no_sale_visits']}",
        html_body=html,
        screenshot_path=None,
    )
    clog(logging.INFO, "EMAIL", f"sending milestone stats email for no_sale={snapshot['no_sale_visits']}")
    email_sender.send_async(job)


stats = Stats(log_interval_sec=30, milestone=300, milestone_cb=send_stats_email_async)
stats.start()


# -------------------- Main Script Logic --------------------
def send_email_async_with_shot():
    screenshot_file = os.path.join("outbox", f"screenshot_{int(time.time() * 1000)}.png")
    os.makedirs("outbox", exist_ok=True)
    pyautogui.screenshot(screenshot_file)

    job = EmailJob(
        to_addr=mail_user,
        subject='Car Purchase Successful',
        html_body='<p>The car purchase was successful. See the screenshot below:</p>'
                  '<img src="cid:screenshot">',
        screenshot_path=screenshot_file
    )
    email_sender.send_async(job)


def main_script():
    while True:
        stats.mark_enter_main()
        clog(logging.DEBUG, "DETECT", "Waiting for MAIN screen...")

        # Loop until the main screen is detected
        while not check_color(1900, 420, (247, 247, 247)):
            time.sleep(0.5)  # Wait a bit before rechecking

        # On the main screen, press Enter twice
        clog(logging.INFO, "DETECT", "MAIN screen detected.")
        time.sleep(1)
        pyautogui.press('enter', presses=2, interval=0.5)

        # Loop until no lag is detected
        clog(logging.DEBUG, "DETECT", "Waiting for NO-LAG state...")
        while not (check_color(1678, 701, (255, 255, 255)) or check_color(2360, 476, (247, 247, 247))):
            time.sleep(0.5)  # Wait a bit before rechecking
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
                # Notify by email
                send_email_async_with_shot()
                _shutdown_now()

        # If no car is on sale, press Esc to return to the main screen
        else:
            stats.mark_no_sale()
            clog(logging.INFO, "DETECT", "No car on sale. Returning to MAIN (Esc).")
            pyautogui.press('esc')


# -------------------- Entry Point --------------------
if __name__ == "__main__":
    clog(logging.INFO, "CORE", "Press F12 at any time to stop the script.")
    try:
        main_script()
    except pyautogui.FailSafeException:
        clog(logging.WARNING, "CORE", "PyAutoGUI FailSafe triggered — stopping.")
        _shutdown_now()
    except KeyboardInterrupt:
        _shutdown_now()
