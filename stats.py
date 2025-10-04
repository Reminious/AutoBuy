import logging
import threading
import time
from datetime import datetime

from logutil import clog


class Stats:


    def __init__(self, log_interval_sec=30, milestone=300, milestone_cb=None):
        self.no_sale_visits = 0
        self.purchase_attempts = 0
        self.purchase_failures = 0

        self._program_start_ts = time.time()
        self._first_sale_ts = None
        self._time_to_first_sale_from_start_sec = None
        self._no_sale_before_first_sale = 0

        self._sale_occurrences = 0
        self._last_sale_ts = None

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
        pass


    def mark_no_sale(self):
        snapshot_for_cb = None
        reached = False
        with self._lock:
            self.no_sale_visits += 1

            if self._first_sale_ts is None:
                self._no_sale_before_first_sale += 1

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
        now = time.time()
        with self._lock:
            if self._first_sale_ts is None:
                self._first_sale_ts = now
                self._time_to_first_sale_from_start_sec = now - self._program_start_ts

            self._sale_occurrences += 1
            self._last_sale_ts = now


    def snapshot(self):
        with self._lock:
            return self._snapshot_unlocked()


    def _snapshot_unlocked(self):

        if self._sale_occurrences >= 1 and self._first_sale_ts is not None and self._last_sale_ts is not None:
            avg_sale_interval = (self._last_sale_ts - self._first_sale_ts) / self._sale_occurrences
        else:
            avg_sale_interval = 0.0

        return {
            "no_sale_visits": self.no_sale_visits,
            "purchase_attempts": self.purchase_attempts,
            "purchase_failures": self.purchase_failures,
            "time_to_first_sale_from_start_sec": round(self._time_to_first_sale_from_start_sec or 0.0, 2),
            "no_sale_before_first_sale": int(self._no_sale_before_first_sale),
            "avg_sale_interval_sec": round(avg_sale_interval, 2),
            "sale_occurrences": self._sale_occurrences,
            "first_sale_seen": self._first_sale_ts is not None,
            "timestamp": datetime.now().isoformat()
        }


    def _loop(self):
        while not self._stop.is_set():
            time.sleep(self._log_interval)
            snap = self.snapshot()
            clog(logging.INFO, "STATS",
                 f"no_sale={snap['no_sale_visits']} "
                 f"attempts={snap['purchase_attempts']} "
                 f"failures={snap['purchase_failures']} "
                 f"time_to_first_sale_from_start={snap['time_to_first_sale_from_start_sec']}s "
                 f"no_sale_before_first_sale={snap['no_sale_before_first_sale']} "
                 f"avg_sale_interval={snap['avg_sale_interval_sec']}s "
                 f"(occurrences={snap['sale_occurrences']}, first_sale_seen={snap['first_sale_seen']})"
                 )
