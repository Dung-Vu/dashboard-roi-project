"""Behavioral unit tests for Revenue, Scope, Currency & KPI Rules (A-02..A-04, B-01, B-03, E-01..E-03)."""
from __future__ import annotations

import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from cache import PersistentCache
from dashboard_service import DashboardService
from odoo_client import OdooAPIError
from tests.fixtures.synthetic_data import (
    SYNTHETIC_CUSTOMER_ALPHA,
    SYNTHETIC_CUSTOMER_BETA,
    SyntheticOdooClient,
    build_base_synthetic_records,
)


class RevenueRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_fd, self.temp_db_path = tempfile.mkstemp(prefix="roi_test_rev_", suffix=".db")
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

    def test_a02_date_from_boundary_uses_utc_plus_7_timezone(self) -> None:
        """A-02: date_from='2026-01-01' (ICT UTC+7) corresponds to '2025-12-31 17:00:00' UTC."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-ICT-2026-01-01-01H",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2025-12-31 18:00:00",  # 2026-01-01 01:00:00 UTC+7 -> INCLUDE
                "amount_untaxed": 100_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            },
            {
                "id": 11,
                "name": "SO-ICT-2025-12-31-23H30",
                "state": "sale",
                "partner_id": [2, SYNTHETIC_CUSTOMER_BETA],
                "date_order": "2025-12-31 16:30:00",  # 2025-12-31 23:30:00 UTC+7 -> EXCLUDE
                "amount_untaxed": 90_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            },
        ]
        records["project.project"] = [
            {
                "id": 100,
                "name": "DA New Year ICT",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-ICT-2026-01-01-01H"],
                "account_id": [101, "AA-101"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            },
            {
                "id": 101,
                "name": "DA Old Year ICT",
                "partner_id": [2, SYNTHETIC_CUSTOMER_BETA],
                "sale_order_id": [11, "SO-ICT-2025-12-31-23H30"],
                "account_id": [102, "AA-102"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            },
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={
                100: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -40_000_000, "to_bill": 0}]}}},
                101: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -30_000_000, "to_bill": 0}]}}},
            },
        )
        service = self._make_service(client)
        payload = service.build_projects_dashboard("2026-01-01", refresh=True)
        project_ids = [r["project_id"] for r in payload["projects"]]

        self.assertIn(100, project_ids, "Order at 2025-12-31 18:00:00 UTC (2026-01-01 01:00 ICT) must be included!")
        self.assertNotIn(101, project_ids, "Order at 2025-12-31 16:30:00 UTC (2025-12-31 23:30 ICT) must be excluded!")

    def test_a03_shared_sale_order_marks_shared_so_and_deduplicates_summary_bg_untaxed(self) -> None:
        """A-03: 1 SO (200M) linked to 2 Done projects marks both shared_so=True and counts 200M once in summary['total_bg_untaxed']."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-SHARED-001",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-03-01 09:00:00",
                "amount_untaxed": 200_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            },
            {
                "id": 11,
                "name": "SO-SINGLE-002",
                "state": "sale",
                "partner_id": [2, SYNTHETIC_CUSTOMER_BETA],
                "date_order": "2026-03-02 09:00:00",
                "amount_untaxed": 100_000_000,
                "x_sale_order_tag_ids": [102],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            },
        ]
        records["project.project"] = [
            {
                "id": 101,
                "name": "DA Shared Phase 1",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-SHARED-001"],
                "account_id": [201, "AA-201"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            },
            {
                "id": 102,
                "name": "DA Shared Phase 2",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-SHARED-001"],
                "account_id": [202, "AA-202"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            },
            {
                "id": 103,
                "name": "DA Single",
                "partner_id": [2, SYNTHETIC_CUSTOMER_BETA],
                "sale_order_id": [11, "SO-SINGLE-002"],
                "account_id": [203, "AA-203"],
                "company_id": [1, "Bonario Synthetic"],
                "active": True,
            },
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={
                101: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -50_000_000, "to_bill": 0}]}}},
                102: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -30_000_000, "to_bill": 0}]}}},
                103: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -40_000_000, "to_bill": 0}]}}},
            },
        )
        service = self._make_service(client)
        payload = service.build_projects_dashboard("2026-01-01", refresh=True)
        rows_by_id = {r["project_id"]: r for r in payload["projects"]}

        self.assertTrue(rows_by_id[101].get("shared_so"), "Project 101 sharing SO 10 must have shared_so=True")
        self.assertTrue(rows_by_id[102].get("shared_so"), "Project 102 sharing SO 10 must have shared_so=True")
        self.assertFalse(rows_by_id[103].get("shared_so"), "Project 103 with unique SO 11 must have shared_so=False")
        self.assertEqual(
            payload["summary"]["total_bg_untaxed"],
            300_000_000.0,
            "summary['total_bg_untaxed'] must deduplicate shared SO (200M + 100M = 300M, not 500M)",
        )

    def test_a04_project_with_empty_company_key_does_not_leak_into_specific_company_scope(self) -> None:
        """A-04: Project with company_key == '' must not appear in company='bonario' or company='ordinaire'."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-BON",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-03-01 09:00:00",
                "amount_untaxed": 100_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            },
            {
                "id": 11,
                "name": "SO-ORD",
                "state": "sale",
                "partner_id": [2, SYNTHETIC_CUSTOMER_BETA],
                "date_order": "2026-03-02 09:00:00",
                "amount_untaxed": 80_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [2, "Ordinaire Synthetic"],
            },
            {
                "id": 12,
                "name": "SO-NOCOMP",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-03-03 09:00:00",
                "amount_untaxed": 50_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": False,
            },
        ]
        records["project.project"] = [
            {"id": 100, "name": "P Bonario", "sale_order_id": [10, "SO-BON"], "company_id": [1, "Bonario Synthetic"], "active": True},
            {"id": 101, "name": "P Ordinaire", "sale_order_id": [11, "SO-ORD"], "company_id": [2, "Ordinaire Synthetic"], "active": True},
            {"id": 102, "name": "P NoCompany", "sale_order_id": [12, "SO-NOCOMP"], "company_id": False, "active": True},
        ]

        client = SyntheticOdooClient(records=records)
        service = self._make_service(client)

        bonario_payload = service.build_projects_dashboard("2026-01-01", company="bonario", refresh=True)
        ordinaire_payload = service.build_projects_dashboard("2026-01-01", company="ordinaire", refresh=True)
        all_payload = service.build_projects_dashboard("2026-01-01", company="all", refresh=True)

        self.assertEqual([r["project_id"] for r in bonario_payload["projects"]], [100])
        self.assertEqual([r["project_id"] for r in ordinaire_payload["projects"]], [101])
        self.assertEqual({r["project_id"] for r in all_payload["projects"]}, {100, 101, 102})

    def test_b01_cancelled_and_draft_sale_orders_excluded_and_refund_total_reported(self) -> None:
        """B-01: SO with state 'cancel' or 'draft' are excluded; out_refund credit notes populate summary['refund_total'] without reducing total_bg_untaxed."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-CONFIRMED",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-04-01 09:00:00",
                "amount_untaxed": 150_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            },
            {
                "id": 11,
                "name": "SO-CANCELLED",
                "state": "cancel",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-04-02 09:00:00",
                "amount_untaxed": 90_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            },
            {
                "id": 12,
                "name": "SO-DRAFT",
                "state": "draft",
                "partner_id": [2, SYNTHETIC_CUSTOMER_BETA],
                "date_order": "2026-04-03 09:00:00",
                "amount_untaxed": 60_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            },
        ]
        records["project.project"] = [
            {"id": 100, "name": "P Confirmed", "sale_order_id": [10, "SO-CONFIRMED"], "account_id": [101, "AA-101"], "company_id": [1, "Bonario Synthetic"], "active": True},
            {"id": 101, "name": "P Cancelled", "sale_order_id": [11, "SO-CANCELLED"], "account_id": [102, "AA-102"], "company_id": [1, "Bonario Synthetic"], "active": True},
            {"id": 102, "name": "P Draft", "sale_order_id": [12, "SO-DRAFT"], "account_id": [103, "AA-103"], "company_id": [1, "Bonario Synthetic"], "active": True},
        ]
        records["sale.order.line"] = [
            {"id": 1001, "name": "Item", "order_id": [10, "SO-CONFIRMED"], "price_subtotal": 150_000_000, "analytic_distribution": {"101": 100}}
        ]
        records["account.move"] = [
            {
                "id": 900,
                "name": "RINV/2026/001",
                "move_type": "out_refund",
                "state": "posted",
                "date": "2026-04-15",
                "invoice_origin": "SO-CONFIRMED",
                "amount_untaxed": 15_000_000,
                "amount_untaxed_signed": -15_000_000,
                "company_id": [1, "Bonario Synthetic"],
            }
        ]
        records["account.move.line"] = [
            {
                "id": 701,
                "name": "Credit note line",
                "move_id": [900, "RINV/2026/001"],
                "parent_state": "posted",
                "move_type": "out_refund",
                "date": "2026-04-15",
                "balance": 15_000_000,
                "price_subtotal": 15_000_000,
                "sale_line_ids": [1001],
                "company_id": [1, "Bonario Synthetic"],
                "analytic_distribution": {"101": 100},
            }
        ]
        records["account.analytic.line"] = [
            {
                "id": 801,
                "name": "Credit note analytic",
                "date": "2026-04-15",
                "amount": -15_000_000,
                "account_id": [101, "AA-101"],
                "move_line_id": [701, "RINV/2026/001"],
                "company_id": [1, "Bonario Synthetic"],
                "category": "invoice",
            }
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={
                100: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -50_000_000, "to_bill": 0}]}}},
            },
        )
        service = self._make_service(client)
        payload = service.build_projects_dashboard("2026-01-01", refresh=True)

        pids = [r["project_id"] for r in payload["projects"]]
        self.assertEqual(pids, [100], "Cancelled and draft sale orders must be excluded")
        self.assertEqual(payload["summary"]["total_bg_untaxed"], 150_000_000.0)
        self.assertEqual(payload["summary"].get("refund_total"), 15_000_000.0)

    def test_b03_foreign_currency_conversion_and_no_silent_zero_on_failure(self) -> None:
        """B-03: Foreign currency converts to VND via res.currency.rate, and conversion failure raises or flags instead of silently dropping to 0."""
        records = build_base_synthetic_records()
        records["purchase.order.line"] = [
            {
                "id": 901,
                "name": "Imported Lamp USD",
                "order_id": [801, "PO-USD-001"],
                "order_id.state": "purchase",
                "product_id": [50, "Lamp"],
                "product_qty": 1,
                "qty_invoiced": 0,
                "price_subtotal": 1_000,  # 1,000 USD
                "currency_id": [2, "USD"],
                "company_id": [1, "Bonario Synthetic"],
                "date_planned": "2026-05-10",
                "analytic_distribution": {"77": 100},
            }
        ]

        # 1. Successful conversion from res.currency.rate (res.currency._convert is
        #    private on Odoo.com and must not be called): 1,000 USD -> 25,400,000 VND
        records_ok = dict(records)
        records_ok["res.currency.rate"] = [
            {"id": 1, "currency_id": [2, "USD"], "name": "2026-01-01", "rate": 1 / 25_400, "company_id": False},
        ]
        client_ok = SyntheticOdooClient(records=records_ok)
        service_ok = self._make_service(client_ok)
        po_sources, _ = service_ok._get_po_open_commitments(77, set())
        self.assertEqual(len(po_sources), 1)
        self.assertEqual(round(po_sources[0]["amount"], 2), Decimal("25400000.00"))
        self.assertFalse(any(c[0] == "call_method" and c[1] == "res.currency" for c in client_ok.calls))

        # 2. Failed conversion (no USD rate) must NOT silently return empty 0 commitment
        client_err = SyntheticOdooClient(records=records)
        service_err = self._make_service(client_err)
        raised = False
        sources_err = []
        try:
            sources_err, _ = service_err._get_po_open_commitments(77, set())
        except OdooAPIError:
            raised = True

        if not raised:
            self.assertTrue(
                len(sources_err) > 0 and (sources_err[0].get("conversion_error") or sources_err[0].get("amount", 0) > 0),
                "Foreign currency conversion failure must raise OdooAPIError or flag conversion_error, never silently drop to 0!",
            )

    def test_e01_e02_e03_zero_revenue_done_project_cost_included_and_negative_gp_range_label(self) -> None:
        """E-01, E-02, E-03: Done project with bg_untaxed=0 and cost=20M is included in total_adjusted_expected_cost, reduces total_gp_amount, increments zero_revenue_projects=1; _gp_range_label(Decimal('-0.5')) == '<0%'."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-NORMAL-100M",
                "state": "sale",
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "date_order": "2026-04-01 09:00:00",
                "amount_untaxed": 100_000_000,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            },
            {
                "id": 11,
                "name": "SO-ZERO-REV-WARRANTY",
                "state": "sale",
                "partner_id": [2, SYNTHETIC_CUSTOMER_BETA],
                "date_order": "2026-04-02 09:00:00",
                "amount_untaxed": 0,
                "x_sale_order_tag_ids": [101],
                "x_studio_selection_field_q4_1imrcsjj8": "Done",
                "company_id": [1, "Bonario Synthetic"],
            },
        ]
        records["project.project"] = [
            {"id": 100, "name": "DA Normal", "sale_order_id": [10, "SO-NORMAL-100M"], "account_id": [101, "AA-101"], "company_id": [1, "Bonario Synthetic"], "active": True},
            {"id": 101, "name": "DA Zero Revenue Warranty", "sale_order_id": [11, "SO-ZERO-REV-WARRANTY"], "account_id": [102, "AA-102"], "company_id": [1, "Bonario Synthetic"], "active": True},
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={
                100: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -60_000_000, "to_bill": 0}]}}},
                101: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -20_000_000, "to_bill": 0}]}}},
            },
        )
        service = self._make_service(client)
        payload = service.build_projects_dashboard("2026-01-01", refresh=True)
        summary = payload["summary"]

        # E-01 & E-02: Zero-revenue Done project's 20M cost must be included in summary costs and reduce total_gp_amount
        self.assertEqual(summary["total_bg_untaxed"], 100_000_000.0)
        self.assertEqual(summary["total_adjusted_expected_cost"], 80_000_000.0)
        self.assertEqual(summary["total_gp_amount"], 20_000_000.0)
        self.assertEqual(summary.get("zero_revenue_projects"), 1)

        # E-03: Negative fractional GP% between -1 and 0 must be labeled '<0%', not '0-20%'
        self.assertEqual(service._gp_range_label(Decimal("-0.5")), "<0%")
        self.assertEqual(service._gp_range_label(Decimal("-0.01")), "<0%")
        self.assertEqual(service._gp_range_label(Decimal("0")), "0-20%")


if __name__ == "__main__":
    unittest.main()
