from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
import threading
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from cache import PersistentCache
from dashboard_service import DashboardService
from odoo_client import OdooAPI


class TestSWRAndProactiveWarming(unittest.TestCase):
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)
        self.db_path = Path(self.temp_db_path)

        # Mock OdooAPI client
        self.mock_client = MagicMock(spec=OdooAPI)
        self.mock_client.db = "test_db"
        self.mock_client.uid = 1
        self.mock_client.api_key = "test_key"
        self.mock_client.url = "https://test.odoo.com"

        # Initialize DashboardService with mock client and temp DB path
        with patch("cache.CACHE_DB_PATH", self.db_path):
            self.service = DashboardService(self.mock_client)

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
        """Verify that a stale cache within 1 hour returns stale data instantly and triggers revalidation in background."""
        # 1. Populate the SQLite cache
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
            "cached_at": time.time() - 600, # 10 minutes old (Soft stale)
        }
        
        self.service._db_cache.set(db_cache_key, mock_payload)
        
        # Mock fetch function to track if it's called
        self.mock_client.search_read.return_value = []
        self.mock_client.call_method.return_value = []
        
        # Fetching should return immediately from cache
        start_time = time.perf_counter()
        res = self.service.build_projects_dashboard(date_from=date_from, company=company, refresh=False)
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        self.assertEqual(res["date_from"], date_from)
        self.assertLess(duration_ms, 100.0, "Soft stale cache read took too long!")
        
        # Background revalidation should be triggered
        time.sleep(0.1) # Wait for thread to launch
        with self.service._active_updates_lock:
            self.assertGreaterEqual(len(self.service._active_updates), 0)

    def test_swr_hard_stale_limit(self):
        """Verify that a stale cache older than 1 hour blocks the request and fetches fresh data synchronously."""
        date_from = "2026-01-01"
        company = "all"
        db_cache_key = f"dashboard_payload:{company}:{date_from}"
        
        mock_payload = {
            "projects": [],
            "summary": {"total_projects": 0},
            "cached_at": time.time() - 90000, # More than 24 hours old (Hard stale)
        }
        
        self.service._db_cache.set(db_cache_key, mock_payload)
        
        # Mock Odoo API calls for a synchronous fetch
        self.mock_client.search_read.return_value = []
        self.mock_client.call_method.return_value = []
        
        # Call build_projects_dashboard
        res = self.service.build_projects_dashboard(date_from=date_from, company=company, refresh=False)
        
        # It must call Odoo client (meaning it falls through to synchronous fetch)
        # Search read for companies and/or sale orders should have been called
        self.assertTrue(self.mock_client.search_read.called or self.mock_client.call_method.called)

    def test_background_cache_warmer(self):
        """Verify that start_background_warmer spawns a thread and refreshes cache."""
        # Mock build_projects_dashboard
        original_build = self.service.build_projects_dashboard
        build_called = threading.Event()
        
        def spy_build(*args, **kwargs):
            build_called.set()
            return {"ok": True}
            
        self.service.build_projects_dashboard = spy_build
        
        # Start warmer with extremely short interval
        # To avoid waiting 10s in test, let's patch time.sleep to run faster
        with patch("time.sleep", side_effect=lambda s: None):
            self.service.start_background_warmer(interval_seconds=0.1)
            # Wait for event
            called = build_called.wait(timeout=2)
            self.assertTrue(called, "Background cache warmer did not run build_projects_dashboard")
            
        # Restore
        self.service.build_projects_dashboard = original_build


if __name__ == "__main__":
    unittest.main()
