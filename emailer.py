import json
import logging
import os
import queue
import smtplib
import threading
import time
from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import MAIL_PASSWORD, MAIL_USER, EMAIL_SCAN_INTERVAL, OUTBOX_DIR
from logutil import clog


class EmailJob:


    def __init__(self, to_addr, subject, html_body, screenshot_path=None):
        self.to_addr = to_addr
        self.subject = subject
        self.html_body = html_body
        self.screenshot_path = screenshot_path
        self.created_at = time.time()


class EmailSender:


    def __init__(self, user=MAIL_USER, password=MAIL_PASSWORD, retry_dir=OUTBOX_DIR, scan_interval=EMAIL_SCAN_INTERVAL,
                 max_queue=1000):
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


    def shutdown(self, wait_seconds=5.0):
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
            fname = os.path.basename(job.screenshot_path) if job.screenshot_path else "(no attachment)"
            clog(logging.INFO, "EMAIL", f"queued: {fname}")
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
