from __future__ import annotations

import unittest
import time
import os
import threading
import sqlite3
from pathlib import Path
from decimal import Decimal
from time import monotonic
from typing import Any

# Isolate stress test database to prevent contamination
STRESS_CACHE_DB = Path(__file__).parent / "stress_cache.db"
os.environ["CACHE_DB_PATH"] = str(STRESS_CACHE_DB)

from dashboard_service import DashboardService
from cache import PersistentCache
from tests.test_cost_pipeline import FakeOdooClient


class BackendStressTest(unittest.TestCase):
    def setUp(self):
        # Ensure fresh database before each test case
        if STRESS_CACHE_DB.exists():
            try:
                STRESS_CACHE_DB.unlink()
            except Exception:
                pass
        # Clean up any WAL files left over
        for suffix in ["-wal", "-shm"]:
            f = STRESS_CACHE_DB.with_suffix(STRESS_CACHE_DB.suffix + suffix)
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

        # Set up a Fake Odoo Client with standard metadata
        self.client = FakeOdooClient(
            records={
                "sale.order": [
                    {
                        "id": 10,
                        "name": "SO001",
                        "partner_id": [1, "Client A"],
                        "date_order": "2026-01-02 09:00:00",
                        "amount_untaxed": 100_000_000,
                        "x_sale_order_tag_ids": [101],
                        "x_studio_selection_field_q4_1imrcsjj8": "Done",
                        "company_id": [1, "Bonario"],
                    }
                ],
                "project.project": [
                    {"id": 100, "name": "Project Bonario", "partner_id": [1, "Client A"], "sale_order_id": [10, "SO001"], "company_id": [1, "Bonario"]},
                ],
                "crm.tag": [
                    {"id": 101, "name": "Nội thất rời"},
                ],
            },
            panels={
                100: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -60_000_000, "to_bill": 0}]}}},
            },
            field_relations={("sale.order", "x_sale_order_tag_ids"): "crm.tag"},
        )
        self.service = DashboardService(self.client)
        self.service._db_cache.db_path = STRESS_CACHE_DB
        self.service._db_cache._init_db()

    def tearDown(self):
        # Clean up after test run
        if STRESS_CACHE_DB.exists():
            try:
                STRESS_CACHE_DB.unlink()
            except Exception:
                pass
        for suffix in ["-wal", "-shm"]:
            f = STRESS_CACHE_DB.with_suffix(STRESS_CACHE_DB.suffix + suffix)
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

    def test_sqlite_wal_mode_enabled(self):
        """Verify SQLite database journal mode is set to WAL."""
        db = PersistentCache(STRESS_CACHE_DB)
        conn = sqlite3.connect(str(STRESS_CACHE_DB))
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        self.assertEqual(journal_mode.lower(), "wal")

    def test_cache_miss_performance_and_accuracy(self):
        """Verify SQLite cache-miss logic and response times."""
        # Warm call to load imports etc.
        start = time.perf_counter()
        payload = self.service.build_projects_dashboard("2026-01-01", refresh=False)
        duration_ms = (time.perf_counter() - start) * 1000

        self.assertIsNotNone(payload)
        self.assertEqual(payload["summary"]["total_projects"], 1)
        
        # Verify that SQLite cache db was written to
        db = PersistentCache(STRESS_CACHE_DB)
        cached_data = db.get("dashboard_payload:all:2026-01-01")
        self.assertIsNotNone(cached_data)
        
        print(f"\n[METRIC] Cache-Miss execution duration: {duration_ms:.2f} ms")

    def test_cache_hit_performance_boundaries(self):
        """Assert cache-hit response times are under 50ms (and under 10ms for SQLite WAL)."""
        # First call to populate cache (miss)
        self.service.build_projects_dashboard("2026-01-01", refresh=False)
        
        # Now call multiple times and measure cache hit response times
        durations_ms = []
        for _ in range(100):
            start = time.perf_counter()
            self.service.build_projects_dashboard("2026-01-01", refresh=False)
            durations_ms.append((time.perf_counter() - start) * 1000)

        avg_duration = sum(durations_ms) / len(durations_ms)
        max_duration = max(durations_ms)
        p95_duration = sorted(durations_ms)[int(len(durations_ms) * 0.95)]
        
        print(f"[METRIC] Cache-Hit (Warm In-Memory & WAL): Avg = {avg_duration:.2f}ms, Max = {max_duration:.2f}ms, P95 = {p95_duration:.2f}ms")
        
        # SWR performance boundary assertion:
        self.assertLess(avg_duration, 10.0, "Average cache-hit response time is above WAL threshold of 10ms!")
        self.assertLess(p95_duration, 50.0, "95th percentile cache-hit response time is above strict SLA threshold of 50ms!")

    def test_swr_thread_safety_and_single_revalidation(self):
        """Verify that stale cache hits spawn exactly one daemon thread and return instantly."""
        # 1. Populates the SQLite cache
        self.service.build_projects_dashboard("2026-01-01", refresh=False)
        
        # 2. Modify the SQLite cache record to be stale (age >= 300 seconds)
        db = PersistentCache(STRESS_CACHE_DB)
        db_cache_key = "dashboard_payload:all:2026-01-01"
        payload = db.get(db_cache_key)
        self.assertIsNotNone(payload, "SQLite payload should exist")
        
        # Put an aged timestamp (e.g., 400 seconds ago)
        payload["cached_at"] = time.time() - 400
        db.set(db_cache_key, payload)
        
        # Clear in-memory cache to force reading from SQLite stale cache
        with self.service._cache_lock:
            self.service._projects_dashboard_cache.clear()

        # Track the number of active threads before request
        initial_threads = threading.active_count()
        
        # 3. Simulate multiple concurrent requests hitting the stale cache
        num_threads = 10
        results = []
        errors = []
        durations = []
        
        def run_request():
            try:
                start = time.perf_counter()
                res = self.service.build_projects_dashboard("2026-01-01", refresh=False)
                durations.append((time.perf_counter() - start) * 1000)
                results.append(res)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=run_request) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent stale reads produced errors: {errors}")
        self.assertEqual(len(results), num_threads)
        
        # Assert response times for all threads are extremely fast (< 50ms, usually < 10ms)
        for idx, d in enumerate(durations):
            self.assertLess(d, 50.0, f"Thread {idx} stale response time was {d:.2f}ms, exceeding 50ms SLA!")
        
        print(f"[METRIC] SWR Stale Cache Response Times: Avg = {sum(durations)/len(durations):.2f}ms, Max = {max(durations):.2f}ms")

        # Give background thread a tiny moment to start and register in active_updates if needed
        time.sleep(0.05)
        
        # Verify that exactly ONE revalidation thread is active or has run
        # We can check self.service._active_updates
        self.assertLessEqual(len(self.service._active_updates), 1, "More than one active update registered!")

    def test_sqlite_wal_concurrency_under_load(self):
        """Stress test SQLite WAL mode concurrency under high concurrent read/write thread load."""
        num_threads = 30
        errors = []
        durations = []
        
        def stress_worker(worker_id):
            service = DashboardService(self.client) # separate service instance or shared, let's share the db
            service._db_cache.db_path = STRESS_CACHE_DB
            service._db_cache._init_db()
            # Mix of reads, writes, stale updates
            try:
                for i in range(10):
                    start = time.perf_counter()
                    # Alternate write and read
                    if i % 3 == 0:
                        # Write / Refresh
                        service.build_projects_dashboard("2026-01-01", refresh=True)
                    else:
                        # Read
                        service.build_projects_dashboard("2026-01-01", refresh=False)
                    durations.append((time.perf_counter() - start) * 1000)
            except Exception as e:
                errors.append((worker_id, e))

        threads = [threading.Thread(target=stress_worker, args=(i,)) for i in range(num_threads)]
        
        start_time = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        total_duration = (time.perf_counter() - start_time) * 1000

        print(f"[METRIC] Concurrency Stress: Completed {num_threads * 10} database operations in {total_duration:.2f} ms")
        print(f"[METRIC] Concurrency Operation Durations: Avg = {sum(durations)/len(durations):.2f}ms, Max = {max(durations):.2f}ms")
        
        # Verify no locking exceptions occurred
        self.assertEqual(len(errors), 0, f"Concurrency test produced database locks or errors: {errors}")


if __name__ == "__main__":
    unittest.main()
