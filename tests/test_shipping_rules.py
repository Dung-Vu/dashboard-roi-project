"""Behavioral unit tests for Shipping Cost Rules (S1–S9) and Data Contract."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cache import PersistentCache
from dashboard_service import DashboardService
from tests.fixtures.synthetic_data import (
    SYNTHETIC_CUSTOMER_ALPHA,
    SYNTHETIC_CUSTOMER_BETA,
    SYNTHETIC_VENDOR_GAMMA,
    SyntheticOdooClient,
    build_base_synthetic_records,
)


class ShippingRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_fd, self.temp_db_path = tempfile.mkstemp(prefix="roi_test_ship_", suffix=".db")
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

    def test_s1_archived_518_1237_and_bd_506_1427_discovered_with_active_test_false(self) -> None:
        """S1: Archived accounts 518, 1237 and BD accounts 506, 1427 + keywords ('giao hàng', 'cước') are discovered with active_test=False."""
        records = build_base_synthetic_records()
        # Add an archived custom shipping account with keyword 'cước' on a non-SC plan
        records["account.analytic.account"].append(
            {
                "id": 1999,
                "name": "Cước giao hàng nội thành (Archived)",
                "plan_id": [7, "Vận hành"],
                "active": False,
            }
        )
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-S1-001",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-03-01 08:00:00",
                "amount_untaxed": 100_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            }
        ]
        records["project.project"] = [
            {
                "id": 100,
                "name": "DA Alpha S1",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-S1-001"],
                "account_id": [101, "AA-DA-101"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            }
        ]
        records["account.move.line"] = [
            {
                "id": 501,
                "date": "2026-03-05",
                "name": f"Bill 518 - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [901, "BILL/2026/001"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 1_000_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,518": 100},
            },
            {
                "id": 502,
                "date": "2026-03-06",
                "name": f"Bill 1237 - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [902, "BILL/2026/002"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 2_000_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1237": 100},
            },
            {
                "id": 503,
                "date": "2026-03-07",
                "name": f"Bill BD 506 - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [903, "BILL/2026/003"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 1_500_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,506": 100},
            },
            {
                "id": 504,
                "date": "2026-03-08",
                "name": f"Bill BD 1427 - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [904, "BILL/2026/004"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 2_500_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1427": 100},
            },
            {
                "id": 505,
                "date": "2026-03-09",
                "name": f"Bill Dynamic 1999 - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [905, "BILL/2026/005"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 500_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1999": 100},
            },
        ]
        records["account.analytic.line"] = [
            {
                "id": 1,
                "date": "2026-03-05",
                "name": "Ship 518",
                "amount": -1_000_000,
                "account_id": [101, "AA-DA-101"],
                "x_plan5_id": [518, "[ARCHIVED] Logistics 518"],
                "move_line_id": [501, "BILL/2026/001"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
            {
                "id": 2,
                "date": "2026-03-06",
                "name": "Ship 1237",
                "amount": -2_000_000,
                "account_id": [101, "AA-DA-101"],
                "x_plan5_id": [1237, "[ARCHIVED] Ship 1237"],
                "move_line_id": [502, "BILL/2026/002"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
            {
                "id": 3,
                "date": "2026-03-07",
                "name": "Ship 506",
                "amount": -1_500_000,
                "account_id": [101, "AA-DA-101"],
                "x_plan5_id": [506, "BD - Vận chuyển 506"],
                "move_line_id": [503, "BILL/2026/003"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
            {
                "id": 4,
                "date": "2026-03-08",
                "name": "Ship 1427",
                "amount": -2_500_000,
                "account_id": [101, "AA-DA-101"],
                "x_plan5_id": [1427, "[ORD] BD - Giao hàng 1427"],
                "move_line_id": [504, "BILL/2026/004"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
            {
                "id": 5,
                "date": "2026-03-09",
                "name": "Ship 1999",
                "amount": -500_000,
                "account_id": [101, "AA-DA-101"],
                "x_plan5_id": [1999, "Cước giao hàng nội thành (Archived)"],
                "move_line_id": [505, "BILL/2026/005"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={
                100: {
                    "profitability_items": {
                        "costs": {"data": [{"id": "other", "billed": -7_500_000, "to_bill": 0}]}
                    }
                }
            },
        )
        service = self._make_service(client)

        shipping_ids = service._get_shipping_account_ids()
        expected_base = {518, 1237, 566, 1239, 1270, 1271, 1518, 1519, 1522, 1523, 506, 1427, 1999}
        self.assertTrue(
            expected_base.issubset(shipping_ids),
            f"Missing shipping IDs: {expected_base - shipping_ids}",
        )

        # Verify discovery called account.analytic.account with active_test=False
        aa_calls = [
            c for c in client.calls
            if c[0] == "search_read" and c[1] == "account.analytic.account"
        ]
        self.assertTrue(aa_calls, "Expected search_read on account.analytic.account")
        self.assertTrue(
            any(isinstance(c[4], dict) and c[4].get("active_test") is False for c in aa_calls),
            "account.analytic.account discovery must pass context={'active_test': False}",
        )

        payload = service.build_projects_dashboard("2026-01-01", refresh=True)
        row = payload["projects"][0]
        self.assertEqual(row["shipping_cost"], 7_500_000.0)

    def test_s1_env_override_shipping_analytic_ids(self) -> None:
        """S1: SHIPPING_ANALYTIC_IDS environment variable overrides/extends shipping account IDs."""
        client = SyntheticOdooClient(records=build_base_synthetic_records())
        service = self._make_service(client)

        with patch.dict(os.environ, {"SHIPPING_ANALYTIC_IDS": "8801, 8802"}):
            service._shipping_account_ids = None
            service._shipping_account_ids_refresh_at = 0.0
            ids = service._get_shipping_account_ids()
            self.assertIn(8801, ids)
            self.assertIn(8802, ids)

    def test_s2_d01_percentage_allocation_across_projects(self) -> None:
        """S2 / D-01: A 9,000,000 line distributed {"101,1519": 50, "102,1519": 30, "103": 20} allocates 4.5M to P101, 2.7M to P102, and 0 to P103."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-101",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-04-01 09:00:00",
                "amount_untaxed": 50_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            },
            {
                "id": 11,
                "name": "SO-102",
                "state": "sale",
                "partner_id": [2, SYNTHETIC_CUSTOMER_BETA],
                "date_order": "2026-04-02 09:00:00",
                "amount_untaxed": 40_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            },
            {
                "id": 12,
                "name": "SO-103",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-04-03 09:00:00",
                "amount_untaxed": 30_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            },
        ]
        records["project.project"] = [
            {
                "id": 1001,
                "name": "Dự án P101 (Synthetic)",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-101"],
                "account_id": [101, "AA-P101"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            },
            {
                "id": 1002,
                "name": "Dự án P102 (Synthetic)",
                "partner_id": [2, SYNTHETIC_CUSTOMER_BETA],
                "sale_order_id": [11, "SO-102"],
                "account_id": [102, "AA-P102"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            },
            {
                "id": 1003,
                "name": "Dự án P103 (Synthetic)",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [12, "SO-103"],
                "account_id": [103, "AA-P103"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            },
        ]
        records["account.move.line"] = [
            {
                "id": 600,
                "date": "2026-04-10",
                "name": f"Vận chuyển ghép chuyến - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [950, "BILL/2026/050"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 9_000_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 50, "102,1519": 30, "103": 20},
            }
        ]
        records["account.analytic.line"] = [
            {
                "id": 10,
                "date": "2026-04-10",
                "name": "Vận chuyển ghép chuyến (50%)",
                "amount": -4_500_000,
                "account_id": [101, "AA-P101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [600, "BILL/2026/050"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
            {
                "id": 11,
                "date": "2026-04-10",
                "name": "Vận chuyển ghép chuyến (30%)",
                "amount": -2_700_000,
                "account_id": [102, "AA-P102"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [600, "BILL/2026/050"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
            {
                "id": 12,
                "date": "2026-04-10",
                "name": "Chi phí không phải ship (20%)",
                "amount": -1_800_000,
                "account_id": [103, "AA-P103"],
                "x_plan5_id": False,
                "move_line_id": [600, "BILL/2026/050"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={
                1001: {"profitability_items": {"costs": {"data": [{"id": "other", "billed": -4_500_000, "to_bill": 0}]}}},
                1002: {"profitability_items": {"costs": {"data": [{"id": "other", "billed": -2_700_000, "to_bill": 0}]}}},
                1003: {"profitability_items": {"costs": {"data": [{"id": "other", "billed": -1_800_000, "to_bill": 0}]}}},
            },
        )
        service = self._make_service(client)
        payload = service.build_projects_dashboard("2026-01-01", refresh=True)
        rows_by_pid = {r["project_id"]: r for r in payload["projects"]}

        self.assertEqual(rows_by_pid[1001]["shipping_cost"], 4_500_000.0)
        self.assertEqual(rows_by_pid[1002]["shipping_cost"], 2_700_000.0)
        self.assertEqual(rows_by_pid[1003]["shipping_cost"], 0.0)
        self.assertEqual(payload["summary"]["shipping_total"], 7_200_000.0)

    def test_s3_d02_po_shipping_included_and_split_po_vs_non_po(self) -> None:
        """S3 / D-02: Shipping bills with purchase_line_id are included in shipping_cost and split into shipping_cost_po and shipping_cost_non_po."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-S3-001",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-05-01 09:00:00",
                "amount_untaxed": 80_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            }
        ]
        records["project.project"] = [
            {
                "id": 100,
                "name": "DA S3 Ship PO",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-S3-001"],
                "account_id": [101, "AA-101"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            }
        ]
        records["account.move.line"] = [
            {
                "id": 601,
                "date": "2026-05-10",
                "name": f"Cước vận chuyển qua PO - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [961, "BILL/2026/061"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 3_000_000,
                "purchase_line_id": [801, "PO001 - Ship Line"],
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            },
            {
                "id": 602,
                "date": "2026-05-12",
                "name": f"Cước vận chuyển lẻ ngoài PO - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [962, "BILL/2026/062"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 1_200_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            },
        ]
        records["account.analytic.line"] = [
            {
                "id": 21,
                "date": "2026-05-10",
                "name": "Cước vận chuyển qua PO",
                "amount": -3_000_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [601, "BILL/2026/061"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
            {
                "id": 22,
                "date": "2026-05-12",
                "name": "Cước vận chuyển lẻ ngoài PO",
                "amount": -1_200_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [602, "BILL/2026/062"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={
                100: {
                    "profitability_items": {
                        "costs": {"data": [{"id": "purchase_order", "billed": -3_000_000, "to_bill": 0}, {"id": "other", "billed": -1_200_000, "to_bill": 0}]}
                    }
                }
            },
        )
        service = self._make_service(client)
        payload = service.build_projects_dashboard("2026-01-01", refresh=True)
        row = payload["projects"][0]

        self.assertEqual(row.get("shipping_cost_po"), 3_000_000.0)
        self.assertEqual(row.get("shipping_cost_non_po"), 1_200_000.0)
        self.assertEqual(row["shipping_cost"], 4_200_000.0)
        self.assertEqual(row["shipping_cost"], row["shipping_cost_po"] + row["shipping_cost_non_po"])

    def test_s4_move_types_out_invoice_excluded_and_in_refund_deducted(self) -> None:
        """S4: in_invoice, in_refund (deducted), entry, in_receipt are included; out_invoice, out_refund, out_receipt are excluded."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-S4-001",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-05-01 09:00:00",
                "amount_untaxed": 100_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            }
        ]
        records["project.project"] = [
            {
                "id": 100,
                "name": "DA S4 Move Types",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-S4-001"],
                "account_id": [101, "AA-101"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            }
        ]
        records["account.move.line"] = [
            {
                "id": 701,
                "date": "2026-05-02",
                "name": "Vendor Bill Ship",
                "move_id": [971, "BILL/001"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 5_000_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            },
            {
                "id": 702,
                "date": "2026-05-03",
                "name": "Vendor Credit Note Ship (Refund)",
                "move_id": [972, "RBILL/001"],
                "parent_state": "posted",
                "move_type": "in_refund",
                "balance": -1_000_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            },
            {
                "id": 703,
                "date": "2026-05-04",
                "name": "Journal Entry Ship",
                "move_id": [973, "MISC/001"],
                "parent_state": "posted",
                "move_type": "entry",
                "balance": 500_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            },
            {
                "id": 704,
                "date": "2026-05-05",
                "name": "Purchase Receipt Ship",
                "move_id": [974, "RCPT/001"],
                "parent_state": "posted",
                "move_type": "in_receipt",
                "balance": 300_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            },
            {
                "id": 705,
                "date": "2026-05-06",
                "name": "Customer Invoice With Ship Analytic",
                "move_id": [975, "INV/001"],
                "parent_state": "posted",
                "move_type": "out_invoice",
                "balance": -8_000_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            },
            {
                "id": 706,
                "date": "2026-05-07",
                "name": "Customer Credit Note With Ship Analytic",
                "move_id": [976, "RINV/001"],
                "parent_state": "posted",
                "move_type": "out_refund",
                "balance": 2_000_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            },
        ]
        records["account.analytic.line"] = [
            {
                "id": 31,
                "date": "2026-05-02",
                "name": "Vendor Bill Ship",
                "amount": -5_000_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [701, "BILL/001"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
            {
                "id": 32,
                "date": "2026-05-03",
                "name": "Vendor Credit Note Ship",
                "amount": 1_000_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [702, "RBILL/001"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
            {
                "id": 33,
                "date": "2026-05-04",
                "name": "Journal Entry Ship",
                "amount": -500_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [703, "MISC/001"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "other",
            },
            {
                "id": 34,
                "date": "2026-05-05",
                "name": "Purchase Receipt Ship",
                "amount": -300_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [704, "RCPT/001"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "other",
            },
            {
                "id": 35,
                "date": "2026-05-06",
                "name": "Customer Invoice",
                "amount": 8_000_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [705, "INV/001"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "other",
            },
            {
                "id": 36,
                "date": "2026-05-07",
                "name": "Customer Refund",
                "amount": -2_000_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [706, "RINV/001"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "other",
            },
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={100: {"profitability_items": {"costs": {"data": [{"id": "other", "billed": -4_800_000, "to_bill": 0}]}}}},
        )
        service = self._make_service(client)
        payload = service.build_projects_dashboard("2026-01-01", refresh=True)
        row = payload["projects"][0]

        self.assertEqual(row["shipping_cost"], 4_800_000.0)

    def test_s5_draft_shipping_bill_separated_into_shipping_draft(self) -> None:
        """S5: Draft shipping bill goes into shipping_draft, NOT into shipping_cost or summary['shipping_total']."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-S5-001",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-05-01 09:00:00",
                "amount_untaxed": 100_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            }
        ]
        records["project.project"] = [
            {
                "id": 100,
                "name": "DA S5 Draft Ship",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-S5-001"],
                "account_id": [101, "AA-101"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            }
        ]
        records["account.move.line"] = [
            {
                "id": 751,
                "date": "2026-05-10",
                "name": f"Posted Ship Bill - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [981, "BILL/2026/081"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 2_000_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            },
            {
                "id": 752,
                "date": "2026-05-15",
                "name": f"Draft Ship Bill - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [982, "DRAFT/2026/082"],
                "parent_state": "draft",
                "move_type": "in_invoice",
                "balance": 1_500_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            },
        ]
        records["account.analytic.line"] = [
            {
                "id": 41,
                "date": "2026-05-10",
                "name": "Posted Ship Bill",
                "amount": -2_000_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [751, "BILL/2026/081"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            }
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={100: {"profitability_items": {"costs": {"data": [{"id": "other", "billed": -2_000_000, "to_bill": -1_500_000}]}}}},
        )
        service = self._make_service(client)
        payload = service.build_projects_dashboard("2026-01-01", refresh=True)
        row = payload["projects"][0]

        self.assertEqual(row["shipping_cost"], 2_000_000.0)
        self.assertEqual(row.get("shipping_draft"), 1_500_000.0)
        self.assertEqual(payload["summary"].get("shipping_total"), 2_000_000.0)

    def test_s6_s7_s8_monthly_aggregation_and_unassigned_shipping(self) -> None:
        """S6, S7, S8: Monthly shipping totals, unassigned shipping (account_id=False), company total invariant, and unassigned endpoint/method."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-S6-001",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-02-01 09:00:00",
                "amount_untaxed": 120_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            }
        ]
        records["project.project"] = [
            {
                "id": 100,
                "name": "DA S6 Monthly & Unassigned",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-S6-001"],
                "account_id": [101, "AA-101"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            }
        ]
        records["account.move.line"] = [
            {
                "id": 801,
                "date": "2026-02-15",
                "name": f"Ship T2 Assigned - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [991, "BILL/2026/091"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 1_500_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            },
            {
                "id": 802,
                "date": "2026-03-20",
                "name": f"Ship T3 Assigned - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [992, "BILL/2026/092"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 2_500_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101,1519": 100},
            },
            {
                "id": 803,
                "date": "2026-03-25",
                "name": f"Ship T3 Unassigned Bonario - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [993, "BILL/2026/093"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 900_000,
                "purchase_line_id": False,
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"1519": 100},
            },
            {
                "id": 804,
                "date": "2026-03-28",
                "name": f"Ship T3 Unassigned Ordinaire - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [994, "BILL/2026/094"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 600_000,
                "purchase_line_id": False,
                "company_id": [2, "Ordinaire Synthetic"],
                "analytic_distribution": {"1522": 100},
            },
        ]
        records["account.analytic.line"] = [
            {
                "id": 51,
                "date": "2026-02-15",
                "name": "Ship T2 Assigned",
                "amount": -1_500_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [801, "BILL/2026/091"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
            {
                "id": 52,
                "date": "2026-03-20",
                "name": "Ship T3 Assigned",
                "amount": -2_500_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [802, "BILL/2026/092"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
            {
                "id": 53,
                "date": "2026-03-25",
                "name": "Ship T3 Unassigned Bonario",
                "amount": -900_000,
                "account_id": False,
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "move_line_id": [803, "BILL/2026/093"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "vendor_bill",
            },
            {
                "id": 54,
                "date": "2026-03-28",
                "name": "Ship T3 Unassigned Ordinaire",
                "amount": -600_000,
                "account_id": False,
                "x_plan5_id": [1522, "[ORD] SC - Logistics OPS"],
                "move_line_id": [804, "BILL/2026/094"],
                "company_id": [2, "Ordinaire Synthetic"],
                "category": "vendor_bill",
            },
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={100: {"profitability_items": {"costs": {"data": [{"id": "other", "billed": -4_000_000, "to_bill": 0}]}}}},
        )
        service = self._make_service(client)

        # 1. Company = "bonario"
        payload_bonario = service.build_projects_dashboard("2026-01-01", company="bonario", refresh=True)
        row = payload_bonario["projects"][0]
        self.assertEqual(row["shipping_cost"], 4_000_000.0)
        self.assertEqual(sum(row["shipping_cost_by_month"].values()), row["shipping_cost"])
        self.assertEqual(row["shipping_cost_by_month"].get("2026-02"), 1_500_000.0)
        self.assertEqual(row["shipping_cost_by_month"].get("2026-03"), 2_500_000.0)

        summary_bon = payload_bonario["summary"]
        assigned_ship_total = summary_bon.get("shipping_total", summary_bon.get("total_shipping_cost"))
        self.assertEqual(assigned_ship_total, 4_000_000.0)
        self.assertEqual(summary_bon.get("shipping_unassigned_total"), 900_000.0)
        self.assertEqual(
            summary_bon.get("shipping_company_total"),
            (assigned_ship_total or 0) + (summary_bon.get("shipping_unassigned_total") or 0),
        )
        month_t3 = summary_bon.get("shipping_by_month", {}).get("2026-03")
        if isinstance(month_t3, dict):
            self.assertEqual(month_t3.get("assigned", month_t3.get("project", 0)), 2_500_000.0)
            self.assertEqual(month_t3.get("unassigned", 0), 900_000.0)
        else:
            self.assertEqual(month_t3, 3_400_000.0)

        # 2. Method get_unassigned_shipping_items
        self.assertTrue(
            hasattr(service, "get_unassigned_shipping_items"),
            "DashboardService must implement get_unassigned_shipping_items",
        )
        unassigned_res = service.get_unassigned_shipping_items(date_from="2026-01-01", company="bonario")
        items = unassigned_res.get("items", unassigned_res) if isinstance(unassigned_res, dict) else unassigned_res
        self.assertEqual(len(items), 1)
        self.assertEqual(float(items[0].get("amount", 0)), 900_000.0)

    def test_s9_custom_cost_breakdown_invariant_in_build_project_dashboard(self) -> None:
        """S9: PO shipping is deducted from purchase_order, non-PO shipping from other_expense, negative numbers are preserved, and sum(expected) == expected_cost_total."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-S9-001",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "currency_id": [1, "VND"],
                "date_order": "2026-05-01 09:00:00",
                "amount_untaxed": 100_000_000,
                "amount_total": 110_000_000,
                "user_id": [2, "Salesperson Synthetic"],
            }
        ]
        records["sale.order.line"] = [
            {
                "id": 1001,
                "sequence": 10,
                "name": "Sofa Alpha",
                "order_id": [10, "SO-S9-001"],
                "display_type": False,
                "is_downpayment": False,
                "product_id": [201, "Sofa"],
                "product_uom_qty": 1,
                "qty_invoiced": 1,
                "qty_to_invoice": 0,
                "price_unit": 100_000_000,
                "discount": 0,
                "price_subtotal": 100_000_000,
                "untaxed_amount_invoiced": 100_000_000,
                "untaxed_amount_to_invoice": 0,
            }
        ]
        records["product.product"] = [{"id": 201, "type": "consu"}]
        records["project.project"] = [
            {
                "id": 100,
                "name": "DA S9 Breakdown Invariant",
                "allow_timesheets": True,
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-S9-001"],
                "account_id": [101, "AA-101"],
                "active": True,
            }
        ]
        records["account.move.line"] = [
            {
                "id": 851,
                "date": "2026-05-05",
                "name": f"PO Ship Bill - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [995, "BILL/095"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 3_000_000,
                "product_id": [202, "Ship Service"],
                "purchase_line_id": [901, "PO Line Ship"],
                "analytic_distribution": {"101,1519": 100},
            },
            {
                "id": 852,
                "date": "2026-05-06",
                "name": f"Non-PO Ship Bill - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [996, "BILL/096"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 6_000_000,
                "product_id": [202, "Ship Service"],
                "purchase_line_id": False,
                "analytic_distribution": {"101,1519": 100},
            },
        ]
        records["account.analytic.line"] = [
            {
                "id": 61,
                "date": "2026-05-05",
                "name": "PO Ship Bill",
                "amount": -3_000_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "product_id": [202, "Ship Service"],
                "move_line_id": [851, "BILL/095"],
                "category": "vendor_bill",
            },
            {
                "id": 62,
                "date": "2026-05-06",
                "name": "Non-PO Ship Bill",
                "amount": -6_000_000,
                "account_id": [101, "AA-101"],
                "x_plan5_id": [1519, "SC - Logistics OPS"],
                "product_id": [202, "Ship Service"],
                "move_line_id": [852, "BILL/096"],
                "category": "vendor_bill",
            },
        ]

        # Native profitability has purchase_order = 12M, vendor_bills (expense) = 5M -> total 17M.
        # PO shipping is 3M -> purchase_order becomes 9M.
        # Non-PO shipping is 6M -> other_expense becomes 5M - 6M = -1M (negative preserved, no max(0, ...)).
        # Total custom_cost_breakdown = 9M (PO) + 9M (Shipping) + (-1M) (Other) = 17M == expected_cost_total!
        client = SyntheticOdooClient(
            records=records,
            panels={
                100: {
                    "profitability_items": {
                        "costs": {
                            "data": [
                                {"id": "purchase_order", "name": "Purchase Orders", "billed": -10_000_000, "to_bill": -2_000_000},
                                {"id": "vendor_bills", "name": "Vendor Bills", "billed": -5_000_000, "to_bill": 0},
                            ]
                        }
                    }
                }
            },
        )
        service = self._make_service(client)
        detail = service.build_project_dashboard(100)

        breakdown = detail["custom_cost_breakdown"]
        expected_total = detail["profitability_costs"]["expected_cost_total"]
        sum_expected = round(sum(item["expected"] for item in breakdown), 2)

        self.assertEqual(
            sum_expected,
            expected_total,
            f"Invariant violated: sum(custom_cost_breakdown.expected)={sum_expected} != expected_cost_total={expected_total}. Breakdown: {breakdown}",
        )
        by_id = {item["id"]: item for item in breakdown}
        self.assertEqual(by_id["shipping_cost"]["expected"], 9_000_000.0)
        self.assertEqual(by_id["purchase_order"]["expected"], 9_000_000.0)
        self.assertEqual(by_id["other_expense"]["expected"], -1_000_000.0)


if __name__ == "__main__":
    unittest.main()
