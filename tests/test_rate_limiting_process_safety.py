from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from app import LoginRateLimiter


class TestRateLimiterProcessSafety(unittest.TestCase):
    def setUp(self):
        # Create a temporary database file for the rate limiter
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)
        self.db_path = Path(self.temp_db_path)

    def tearDown(self):
        # Clean up the temporary database file
        if self.db_path.exists():
            try:
                os.remove(self.temp_db_path)
            except Exception:
                pass

    def test_sqlite_rate_limiter_sync_across_instances(self):
        """Verify that multiple rate limiter instances sharing the same DB correctly synchronize state."""
        # Setup two independent instances pointing to the same SQLite file
        limiter1 = LoginRateLimiter(max_attempts=3, period=10, db_path=self.db_path)
        limiter2 = LoginRateLimiter(max_attempts=3, period=10, db_path=self.db_path)

        ip = "192.168.1.99"

        # Initially, neither should be rate limited
        self.assertFalse(limiter1.is_rate_limited(ip))
        self.assertFalse(limiter2.is_rate_limited(ip))

        # Record attempts using limiter1
        limiter1.record_failed_attempt(ip)
        limiter1.record_failed_attempt(ip)

        # Still not limited (only 2 failed attempts, max is 3)
        self.assertFalse(limiter1.is_rate_limited(ip))
        self.assertFalse(limiter2.is_rate_limited(ip))

        # Record 3rd attempt using limiter2 (simulates a separate worker process receiving request)
        limiter2.record_failed_attempt(ip)

        # Now BOTH should be rate limited because the state is shared via the database
        self.assertTrue(limiter1.is_rate_limited(ip))
        self.assertTrue(limiter2.is_rate_limited(ip))

    def test_sqlite_rate_limiter_concurrency(self):
        """Verify that concurrent writes/reads from multiple threads do not cause deadlocks or database corruption."""
        limiter = LoginRateLimiter(max_attempts=100, period=10, db_path=self.db_path)
        ip_base = "10.0.0."

        def worker(worker_id):
            ip = f"{ip_base}{worker_id}"
            # Record failed attempts and verify rate limiting behavior
            for _ in range(5):
                limiter.record_failed_attempt(ip)
                limiter.is_rate_limited(ip)

        # Launch concurrent threads simulating multiple active worker processes/threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, i) for i in range(10)]
            for future in futures:
                future.result()  # Ensure no exception is thrown

        # Check total recorded attempts
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM login_attempts").fetchone()
            self.assertEqual(row[0], 50, "Total attempts in DB should match the concurrent runs.")


if __name__ == "__main__":
    unittest.main()
