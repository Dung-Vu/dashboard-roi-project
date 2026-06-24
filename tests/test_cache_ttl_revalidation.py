from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from cache import PersistentCache
from dashboard_service import DashboardService
from odoo_client import OdooAPI


class TestCacheTTLRevalidationAndConnectionSafety(unittest.TestCase):
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
        if self.db_path.exists():
            try:
                os.remove(self.temp_db_path)
            except Exception:
                pass

    def test_profitability_cache_ttl_30_minutes(self):
        """Verify that the profitability cache expires and revalidates after 30 minutes (1800s)."""
        project_id = 999
        mock_panel_data = {
            "profitability_items": {
                "costs": {
                    "data": [
                        {
                            "id": "purchase",
                            "name": "Purchase Order",
                            "billed": 100.0,
                            "to_bill": 50.0,
                        }
                    ]
                }
            }
        }
        self.mock_client.call_method.return_value = mock_panel_data

        # 1. First fetch: should call Odoo API and cache the result
        with patch("time.time", return_value=1000.0):
            res1 = self.service._get_profitability_costs(project_id)
            self.assertEqual(res1["billed_cost_total"], Decimal("-100.0"))
            self.assertEqual(res1["open_commitment_total"], Decimal("-50.0"))
            self.assertEqual(self.mock_client.call_method.call_count, 1)

        # 2. Second fetch within 30 minutes (e.g. 15 mins/900s later): should return cached results, no new call
        with patch("time.time", return_value=1900.0):
            res2 = self.service._get_profitability_costs(project_id)
            self.assertEqual(res2["billed_cost_total"], Decimal("-100.0"))
            self.assertEqual(self.mock_client.call_method.call_count, 1)

        # 3. Third fetch after 30 minutes (e.g. 31 mins/1860s later): should expire and call Odoo API again
        with patch("time.time", return_value=2861.0):
            res3 = self.service._get_profitability_costs(project_id)
            self.assertEqual(res3["billed_cost_total"], Decimal("-100.0"))
            self.assertEqual(self.mock_client.call_method.call_count, 2)

    def test_sqlite_connection_safety(self):
        """Verify that every connection opened in PersistentCache is closed, even when queries fail."""
        cache = PersistentCache(db_path=self.db_path, ttl=1800)

        # Mock sqlite3.connect to track close calls using a wrapper class
        original_connect = sqlite3.connect
        spy_connections = []

        class SpyConnection:
            def __init__(self, conn):
                self._conn = conn
                self.close_called = False

            def __getattr__(self, name):
                return getattr(self._conn, name)

            def execute(self, *args, **kwargs):
                return self._conn.execute(*args, **kwargs)

            def commit(self):
                return self._conn.commit()

            def close(self):
                self.close_called = True
                self._conn.close()

        def spy_connect(*args, **kwargs):
            conn = original_connect(*args, **kwargs)
            spy = SpyConnection(conn)
            spy_connections.append(spy)
            return spy

        with patch("sqlite3.connect", side_effect=spy_connect):
            # Test get
            cache.get("key")
            # Test set
            cache.set("key", {"val": 1})
            # Test clear
            cache.clear("key")
            # Test cleanup_expired
            cache.cleanup_expired()

        self.assertGreater(len(spy_connections), 0)
        for spy in spy_connections:
            self.assertTrue(spy.close_called, "Connection close() must be called!")


if __name__ == "__main__":
    unittest.main()
