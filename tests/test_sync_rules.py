"""Behavioral unit tests for Cache Sync, Delta Updates, Security & Prod Guard (F-01..F-04, SEC-02)."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cache import PersistentCache
from config import Settings
from dashboard_service import DashboardService
from odoo_client import OdooAPI, OdooAPIError
from tests.fixtures.synthetic_data import (
    SYNTHETIC_CUSTOMER_ALPHA,
    SYNTHETIC_CUSTOMER_BETA,
    SYNTHETIC_VENDOR_GAMMA,
    SyntheticOdooClient,
    build_base_synthetic_records,
)


class SyncAndSecurityRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_fd, self.temp_db_path = tempfile.mkstemp(prefix="roi_test_sync_", suffix=".db")
        os.close(self.temp_fd)
        self.db_path = Path(self.temp_db_path)

    def tearDown(self) -> None:
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except OSError:
                pass

    def _make_service(self, client: SyntheticOdooClient) -> DashboardService:
        with patch("cache.CACHE_DB_PATH", self.db_path):
            service = DashboardService(client)
            service._db_cache = PersistentCache(db_path=self.db_path, ttl=86400)
            service._profitability_cache = PersistentCache(db_path=self.db_path, ttl=1800)
            return service

    def test_f01_refresh_clears_profitability_cache_before_fetch_and_retains_new(self) -> None:
        """F-01: build_projects_dashboard(refresh=True) clears profitability:* BEFORE fetching so get_panel_data is called fresh, and retains the newly fetched profitability:* in cache."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-F01-001",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-04-01 09:00:00",
                "amount_untaxed": 100_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            }
        ]
        records["project.project"] = [
            {
                "id": 100,
                "name": "DA F01 Refresh",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-F01-001"],
                "account_id": [101, "AA-101"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            }
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={
                100: {
                    "profitability_items": {
                        "costs": {"data": [{"id": "cost", "billed": -80_000_000, "to_bill": 0}]}
                    }
                }
            },
        )
        service = self._make_service(client)

        # Pre-seed stale profitability cache with 50M
        service._profitability_cache.set(
            "profitability:100",
            {
                "billed_cost_total": "50000000",
                "open_commitment_total": "0",
                "expected_cost_total": "50000000",
                "breakdown": {},
                "items": [{"id": "cost", "label": "cost", "type": None, "billed": "50000000", "open_commitment": "0", "expected": "50000000"}],
            },
        )

        payload = service.build_projects_dashboard("2026-01-01", refresh=True)
        row = payload["projects"][0]

        # Must have fetched fresh 80M from get_panel_data, NOT used stale 50M
        self.assertEqual(row["native_expected_cost"], 80_000_000.0)

        # And the new profitability:100 entry must remain in cache after refresh=True completes
        cached_prof = service._profitability_cache.get("profitability:100")
        self.assertIsNotNone(cached_prof, "New profitability:100 cache entry must be retained after refresh=True")
        self.assertEqual(str(cached_prof.get("expected_cost_total")), "80000000")

    def test_f02_odoo_429_error_preserves_valid_cache_and_marks_data_stale(self) -> None:
        """F-02: When Odoo raises OdooAPIError (e.g. HTTP 429) in get_panel_data or _fetch_shipping_costs, do NOT overwrite cache with 0; preserve prior cache and mark summary['data_stale'] = True."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-F02-001",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-04-01 09:00:00",
                "amount_untaxed": 100_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            }
        ]
        records["project.project"] = [
            {
                "id": 100,
                "name": "DA F02 RateLimit",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-F02-001"],
                "account_id": [101, "AA-101"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            }
        ]
        records["account.move.line"] = [
            {
                "id": 501,
                "date": "2026-04-05",
                "name": f"Ship - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [901, "BILL/001"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 5_000_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            }
        ]
        records["account.analytic.line"] = [
            {
                "id": 1,
                "date": "2026-04-05",
                "name": "Ship",
                "amount": -5_000_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [501, "BILL/001"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            }
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={
                100: {
                    "profitability_items": {
                        "costs": {"data": [{"id": "cost", "billed": -60_000_000, "to_bill": 0}]}
                    }
                }
            },
        )
        service = self._make_service(client)

        # 1. Initial successful load caches 60M cost and 5M shipping
        initial_payload = service.build_projects_dashboard("2026-01-01", refresh=True)
        self.assertEqual(initial_payload["projects"][0]["native_expected_cost"], 60_000_000.0)
        self.assertEqual(initial_payload["projects"][0]["shipping_cost"], 5_000_000.0)
        self.assertFalse(initial_payload["summary"].get("data_stale", False))

        # 2. Clear profitability cache and simulate HTTP 429 on get_panel_data
        service._profitability_cache.clear("profitability:")
        client.simulate_429("project.project", "get_panel_data")

        # Refresh should either return the preserved cached payload with summary["data_stale"] = True
        # or raise OdooAPIError without overwriting the cache with zeros.
        try:
            fallback_payload = service.build_projects_dashboard("2026-01-01", refresh=True)
            self.assertEqual(
                fallback_payload["projects"][0]["native_expected_cost"],
                60_000_000.0,
                "Must not overwrite native_expected_cost with 0 on HTTP 429!",
            )
            self.assertTrue(
                fallback_payload["summary"].get("data_stale"),
                "summary['data_stale'] must be True when serving fallback cache after OdooAPIError",
            )
        except OdooAPIError:
            # Verify SQLite cache still holds the valid 60M cost and was not overwritten with 0
            db_cached = service._db_cache.get("dashboard_payload:all:2026-01-01")
            self.assertIsNotNone(db_cached)
            self.assertEqual(db_cached["projects"][0]["native_expected_cost"], 60_000_000.0)

    def test_f03_f04_delta_updates_filtering_aal_detection_and_cross_company_tag_buckets(self) -> None:
        """F-03 & F-04: get_delta_updates includes date_order, filters excluded salesperson / non-target tags / pre-date_from, detects new AAL/Bills, and preserves cross-company tag_buckets."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-BON-001",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-03-10 09:00:00",
                "write_date": "2026-05-01 10:00:00",
                "amount_untaxed": 120_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "user_id": [2, "Salesperson Valid"],
                "company_id": [1, "Bonario Synthetic"],
            },
            {
                "id": 11,
                "name": "SO-ORD-002",
                "state": "sale",
                "partner_id": [2, SYNTHETIC_CUSTOMER_BETA],
                "date_order": "2026-03-15 09:00:00",
                "write_date": "2026-04-01 10:00:00",
                "amount_untaxed": 250_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "user_id": [2, "Salesperson Valid"],
                "company_id": [2, "Ordinaire Synthetic"],
            },
            {
                "id": 12,
                "name": "SO-EXCLUDED-USER",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-03-20 09:00:00",
                "write_date": "2026-05-01 10:05:00",
                "amount_untaxed": 90_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "user_id": [208, "Đỗ Thị Hải Yến"],
                "company_id": [1, "Bonario Synthetic"],
            },
            {
                "id": 13,
                "name": "SO-OLD-2025",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2025-06-01 09:00:00",
                "write_date": "2026-05-01 10:05:00",
                "amount_untaxed": 80_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "user_id": [2, "Salesperson Valid"],
                "company_id": [1, "Bonario Synthetic"],
            },
        ]
        records["project.project"] = [
            {
                "id": 100,
                "name": "P Bonario 100",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-BON-001"],
                "account_id": [101, "AA-101"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
                "write_date": "2026-04-01 10:00:00",
            },
            {
                "id": 101,
                "name": "P Ordinaire 101",
                "partner_id": [2, SYNTHETIC_CUSTOMER_BETA],
                "sale_order_id": [11, "SO-ORD-002"],
                "account_id": [102, "AA-102"],
                "company_id": [2, "Ordinaire Synthetic"],
                "active": True,
                "write_date": "2026-04-01 10:00:00",
            },
            {
                "id": 102,
                "name": "P Excluded User",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [12, "SO-EXCLUDED-USER"],
                "account_id": [103, "AA-103"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
                "write_date": "2026-05-01 10:05:00",
            },
            {
                "id": 103,
                "name": "P Old 2025",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [13, "SO-OLD-2025"],
                "account_id": [104, "AA-104"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
                "write_date": "2026-05-01 10:05:00",
            },
        ]
        # New AAL created after last_sync for project 100 (even though project 100 write_date is older)
        records["account.move.line"] = [
            {
                "id": 601,
                "date": "2026-05-01",
                "write_date": "2026-05-01 10:10:00",
                "name": f"New Ship Bill - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [901, "BILL/001"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 3_000_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            }
        ]
        records["account.analytic.line"] = [
            {
                "id": 701,
                "date": "2026-05-01",
                "write_date": "2026-05-01 10:10:00",
                "create_date": "2026-05-01 10:10:00",
                "name": "New Ship AAL",
                "amount": -3_000_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [601, "BILL/001"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            }
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={
                100: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -60_000_000, "to_bill": 0}]}}},
                101: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -100_000_000, "to_bill": 0}]}}},
            },
        )
        service = self._make_service(client)

        # Warm initial cache for "bonario" and "all"
        service.build_projects_dashboard("2026-01-01", company="all", refresh=True)
        bon_initial = service.build_projects_dashboard("2026-01-01", company="bonario", refresh=True)
        self.assertEqual(bon_initial["tag_buckets"]["Nội thất rời"][">200tr"]["count"], 1)

        # Run delta update for company="bonario" since 2026-05-01T09:50:00Z
        delta = service.get_delta_updates(
            "2026-05-01T09:50:00Z",
            company_key="bonario",
            date_from="2026-01-01",
        )
        self.assertTrue(delta["ok"])
        updated_by_id = {p["project_id"]: p for p in delta["updated_projects"]}

        # Project 100 must be updated and include date_order
        self.assertIn(100, updated_by_id)
        self.assertEqual(updated_by_id[100].get("date_order"), "2026-03-10 09:00:00")

        # Excluded salesperson (102) and pre-date_from SO (103) must NOT be in updated_projects
        self.assertNotIn(102, updated_by_id, "Excluded salesperson project must be filtered out in get_delta_updates")
        self.assertNotIn(103, updated_by_id, "Project with SO before date_from must be filtered out in get_delta_updates")

        # F-04: Ordinaire's >200tr bucket must NOT be lost when bonario cache is updated
        self.assertEqual(
            delta.get("tag_buckets", {}).get("Nội thất rời", {}).get(">200tr", {}).get("count"),
            1,
            "Updating bonario cache must not wipe out ordinaire data in cross-company tag_buckets!",
        )

    def test_sec02_unauthorized_request_returns_401_when_testing_is_false(self) -> None:
        """SEC-02: Calling /api/projects-dashboard when app.config['TESTING'] = False returns HTTP 401."""
        mock_settings = Settings(
            odoo_url="https://erp.example.com",
            odoo_db="synthetic_db",
            odoo_user_id=1,
            odoo_api_key="synthetic_key",
            default_project_id=100,
            port=5056,
            debug=False,
            dashboard_username="admin",
            dashboard_password="secret_password",
            secret_key="test_secret_key",
        )
        with patch("app.get_settings", return_value=mock_settings), patch("config.get_settings", return_value=mock_settings), patch("app.OdooAPI", return_value=SyntheticOdooClient()):
            from app import create_app

            app = create_app()
            app.config["TESTING"] = False
            app.testing = False
            client = app.test_client()

            resp = client.get("/api/projects-dashboard")
            self.assertEqual(
                resp.status_code,
                401,
                "Unauthenticated request to /api/projects-dashboard must return 401 when app.config['TESTING'] is False!",
            )

    def test_prod_guard_blocks_bonario_vietnam_odoo_com(self) -> None:
        """Prod Guard: Initializing or calling OdooAPI with bonario-vietnam.odoo.com when ODOO_BLOCK_PROD=1 raises SystemExit('PROD BLOCKED')."""
        with patch.dict(os.environ, {"ODOO_BLOCK_PROD": "1"}):
            with self.assertRaises(SystemExit) as ctx:
                api = OdooAPI(
                    url="https://bonario-vietnam.odoo.com",
                    db="bonario-vietnam",
                    user_id=1,
                    api_key="dummy_key",
                )
                api.call_method("res.users", "search_read")
            self.assertIn("PROD BLOCKED", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
