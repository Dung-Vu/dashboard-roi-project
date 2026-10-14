from __future__ import annotations

import os
import tempfile
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cache import PersistentCache
from dashboard_service import DashboardService
from odoo_client import OdooAPI


class TestSWRAndProactiveWarming(unittest.TestCase):
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(prefix="roi_test_swr_", suffix=".db")
        os.close(self.temp_db_fd)
        self.db_path = Path(self.temp_db_path)

        # Mock OdooAPI client
        self.mock_client = MagicMock(spec=OdooAPI)
        self.mock_client.db = "test_db"
        self.mock_client.uid = 1
        self.mock_client.api_key = "test_key"
        self.mock_client.url = "https://erp.example.com"

        # Initialize DashboardService with mock client and temp DB path
        with patch("cache.CACHE_DB_PATH", self.db_path):
            self.service = DashboardService(self.mock_client)
            self.service._db_cache = PersistentCache(db_path=self.db_path, ttl=86400 * 30)
            self.service._profitability_cache = PersistentCache(db_path=self.db_path, ttl=1800)

    def tearDown(self):
        # Stop background warmer if running
        if hasattr(self, "service") and self.service:
            self.service._warmer_stop_event.set()
        if self.db_path.exists():
            try:
                os.remove(self.temp_db_path)
            except Exception:
                pass

    def test_swr_soft_stale_limit(self):
        """Verify that a stale cache within 24 hours returns stale data instantly and triggers revalidation in background."""
        date_from = "2026-01-01"
        company = "all"
        cache_key = f"{company}:{date_from}"
        db_cache_key = f"dashboard_payload:{company}:{date_from}"

        mock_payload = {
            "projects": [],
            "summary": {
                "total_projects": 0,
                "valid_project_count": 0,
                "total_bg_untaxed": 0,
                "total_native_expected_cost": 0,
                "total_adjusted_expected_cost": 0,
                "total_cost_adjustment_amount": 0,
                "total_gp_amount": 0,
                "weighted_gp_percent": 0,
            },
            "tag_buckets": {},
            "tag_gp_ranks": {},
            "meta": {},
            "date_from": date_from,
            "company": {"key": company, "label": "Tất cả công ty"},
            "fetched_at": "2026-06-24T00:00:00Z",
            "cached_at": time.time() - 600,  # 10 minutes old (Soft stale: > 300s, < 86400s)
        }

        self.service._db_cache.set(db_cache_key, mock_payload)

        revalidation_started = threading.Event()
        allow_finish = threading.Event()
        revalidation_completed = threading.Event()

        def controlled_fetch(d_from: str, c_key: str):
            revalidation_started.set()
            allow_finish.wait(timeout=2.0)
            return {
                **mock_payload,
                "fetched_at": "2026-06-24T01:00:00Z",
            }

        orig_async = self.service._async_update_projects_dashboard

        def wrapped_async(*args, **kwargs):
            try:
                return orig_async(*args, **kwargs)
            finally:
                revalidation_completed.set()

        with (
            patch.object(self.service, "_fetch_projects_dashboard_from_odoo", side_effect=controlled_fetch),
            patch.object(self.service, "_async_update_projects_dashboard", side_effect=wrapped_async),
        ):
            start_time = time.perf_counter()
            res = self.service.build_projects_dashboard(date_from=date_from, company=company, refresh=False)
            duration_ms = (time.perf_counter() - start_time) * 1000

            self.assertEqual(res["date_from"], date_from)
            self.assertEqual(res["fetched_at"], "2026-06-24T00:00:00Z")
            self.assertLess(duration_ms, 200.0, "Soft stale cache read took too long!")

            # Deterministically wait for the background thread to enter _fetch_projects_dashboard_from_odoo
            self.assertTrue(revalidation_started.wait(timeout=2.0), "Background revalidation thread did not start!")
            with self.service._active_updates_lock:
                self.assertIn(cache_key, self.service._active_updates, "cache_key must be tracked in _active_updates during background revalidation")

            allow_finish.set()
            self.assertTrue(revalidation_completed.wait(timeout=2.0), "Background revalidation thread did not complete!")

        # Verify cache was updated with new fetched_at and _active_updates was cleaned up
        with self.service._active_updates_lock:
            self.assertNotIn(cache_key, self.service._active_updates)
        updated_db = self.service._db_cache.get(db_cache_key)
        self.assertIsNotNone(updated_db)
        self.assertEqual(updated_db["fetched_at"], "2026-06-24T01:00:00Z")

    def test_swr_hard_stale_limit(self):
        """Verify that a stale cache older than 24 hours blocks the request and fetches fresh data synchronously."""
        date_from = "2026-01-01"
        company = "all"
        db_cache_key = f"dashboard_payload:{company}:{date_from}"

        mock_payload = {
            "projects": [],
            "summary": {"total_projects": 0},
            "cached_at": time.time() - 90000,  # More than 24 hours old (Hard stale)
        }

        self.service._db_cache.set(db_cache_key, mock_payload)

        # Mock Odoo API calls for a synchronous fetch
        self.mock_client.search_read.return_value = []
        self.mock_client.call_method.return_value = []

        # Call build_projects_dashboard
        res = self.service.build_projects_dashboard(date_from=date_from, company=company, refresh=False)

        # It must call Odoo client (meaning it falls through to synchronous fetch)
        self.assertTrue(self.mock_client.search_read.called or self.mock_client.call_method.called)
        self.assertEqual(res["date_from"], date_from)

    def test_background_cache_warmer(self):
        """Verify that start_background_warmer spawns a thread, acquires lock, and refreshes cache."""
        build_called = threading.Event()

        def spy_build(*args, **kwargs):
            build_called.set()
            self.service._warmer_stop_event.set()
            return {"ok": True}

        with patch.object(self.service, "build_projects_dashboard", side_effect=spy_build):
            self.service.start_background_warmer(interval_seconds=0.05)
            called = build_called.wait(timeout=2.0)
            self.assertTrue(called, "Background cache warmer did not run build_projects_dashboard")


if __name__ == "__main__":
    unittest.main()
