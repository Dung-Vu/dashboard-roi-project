from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from cache import PersistentCache
from dashboard_service import DashboardService
from odoo_client import OdooAPI


class TestCacheProcessLock(unittest.TestCase):
    def setUp(self):
        # Create a temporary database file for the cache lock test
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)
        self.db_path = Path(self.temp_db_path)
        self.cache = PersistentCache(db_path=self.db_path)

    def tearDown(self):
        # Clean up the temporary database file
        if self.db_path.exists():
            try:
                os.remove(self.temp_db_path)
            except Exception:
                pass

    def test_acquire_and_release_warmer_lock(self):
        """Verify that acquire_warmer_lock and release_warmer_lock provide mutual exclusion."""
        lock_key = "test_warmer_lock"

        # 1. First attempt to acquire lock should succeed
        acquired1 = self.cache.acquire_warmer_lock(lock_key, lock_ttl=10)
        self.assertTrue(acquired1)

        # 2. Second attempt (from same/another instance simulating concurrent process) should fail
        acquired2 = self.cache.acquire_warmer_lock(lock_key, lock_ttl=10)
        self.assertFalse(acquired2)

        # 3. Release the lock
        self.cache.release_warmer_lock(lock_key)

        # 4. Attempting to acquire again after release should succeed
        acquired3 = self.cache.acquire_warmer_lock(lock_key, lock_ttl=10)
        self.assertTrue(acquired3)

    def test_lock_ttl_expiration(self):
        """Verify that an expired lock gets cleaned up and can be acquired again."""
        lock_key = "test_expired_lock"

        # 1. Acquire lock with a very short TTL of 1 second
        acquired1 = self.cache.acquire_warmer_lock(lock_key, lock_ttl=1)
        self.assertTrue(acquired1)

        # 2. Immediate attempt to acquire should fail
        self.assertFalse(self.cache.acquire_warmer_lock(lock_key, lock_ttl=1))

        # 3. Wait for TTL to expire
        time.sleep(1.1)

        # 4. Attempt to acquire should succeed because the expired lock is cleaned up
        acquired2 = self.cache.acquire_warmer_lock(lock_key, lock_ttl=1)
        self.assertTrue(acquired2)

    def test_background_warmer_concurrency_skips_when_recent(self):
        """Verify that the background warmer skips execution if it ran recently."""
        client_mock = MagicMock(spec=OdooAPI)
        service = DashboardService(client_mock)
        service._db_cache = self.cache

        # Set warmer_last_run in DB cache to current time (simulating recent execution)
        now = time.time()
        self.cache.set("warmer_last_run", {"timestamp": now})

        # Mock build_projects_dashboard
        with patch.object(service, "build_projects_dashboard") as mock_build:
            target_fn = None
            def mock_thread_start(thread_obj):
                nonlocal target_fn
                target_fn = thread_obj._target

            with patch("threading.Thread.start", mock_thread_start):
                service.start_background_warmer(interval_seconds=60)
            
            self.assertIsNotNone(target_fn)
            
            # Setup wait mock to execute loop once and then exit
            wait_calls = []
            original_wait = service._warmer_stop_event.wait
            def mock_wait(timeout=None):
                wait_calls.append(timeout)
                if len(wait_calls) == 1:
                    return False
                service._warmer_stop_event.set()
                return True
                
            with patch.object(service._warmer_stop_event, "wait", mock_wait):
                target_fn()
            
            # Since warmer_last_run was set to current time, build_projects_dashboard should NOT have been called
            mock_build.assert_not_called()

    def test_background_warmer_concurrency_runs_when_needed(self):
        """Verify that background warmer runs and updates the last run timestamp if needed."""
        client_mock = MagicMock(spec=OdooAPI)
        service = DashboardService(client_mock)
        service._db_cache = self.cache

        # Set warmer_last_run to a long time ago (e.g. 1000s ago)
        self.cache.set("warmer_last_run", {"timestamp": time.time() - 1000})

        # Mock build_projects_dashboard
        with patch.object(service, "build_projects_dashboard") as mock_build:
            mock_build.side_effect = lambda *args, **kwargs: service._warmer_stop_event.set()
            
            target_fn = None
            def mock_thread_start(thread_obj):
                nonlocal target_fn
                target_fn = thread_obj._target

            with patch("threading.Thread.start", mock_thread_start):
                service.start_background_warmer(interval_seconds=60)
            
            wait_calls = []
            original_wait = service._warmer_stop_event.wait
            def mock_wait(timeout=None):
                wait_calls.append(timeout)
                if len(wait_calls) == 1:
                    return False
                return original_wait(timeout)
                
            with patch.object(service._warmer_stop_event, "wait", mock_wait):
                target_fn()
            
            # build_projects_dashboard should be called since interval has elapsed
            mock_build.assert_called_once_with(date_from="2026-01-01", company="all", refresh=True)
            
            # warmer_last_run should be updated in cache
            last_run = self.cache.get("warmer_last_run")
            self.assertIsNotNone(last_run)
            self.assertGreater(last_run["timestamp"], time.time() - 5)


if __name__ == "__main__":
    unittest.main()
