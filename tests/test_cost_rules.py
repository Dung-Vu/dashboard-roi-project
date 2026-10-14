"""Behavioral unit tests for Cost Pipeline & Accounting Rules (C-01..C-07, B-02)."""
from __future__ import annotations

import os
import tempfile
import unittest
from decimal import Decimal
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


class CostRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_fd, self.temp_db_path = tempfile.mkstemp(prefix="roi_test_cost_", suffix=".db")
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

    def test_c01_posted_draft_and_po_commitments_respect_analytic_distribution_percentage(self) -> None:
        """C-01: _get_posted_actual_costs, _get_draft_bill_commitments, and _get_po_open_commitments multiply by % in analytic_distribution."""
        records = build_base_synthetic_records()
        records["account.analytic.line"] = [
            {
                "id": 1,
                "account_id": [77, "AA-Project-77"],
                "date": "2026-05-01",
                "name": f"Posted bill 40% - {SYNTHETIC_VENDOR_GAMMA}",
                "amount": -4_000_000,
                "product_id": [10, "Material Alpha"],
                "move_line_id": [100, "BILL/2026/001"],
                "category": "vendor_bill",
            }
        ]
        records["account.move.line"] = [
            {
                "id": 100,
                "date": "2026-05-01",
                "name": f"Posted bill 100% balance - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [500, "BILL/2026/001"],
                "parent_state": "posted",
                "move_type": "in_invoice",
                "balance": 10_000_000,
                "product_id": [10, "Material Alpha"],
                "purchase_line_id": False,
                "analytic_distribution": {"77,1519": 40, "88": 60},
            },
            {
                "id": 101,
                "date": "2026-05-10",
                "name": f"Draft bill 40% - {SYNTHETIC_VENDOR_GAMMA}",
                "move_id": [501, "DRAFT/2026/001"],
                "parent_state": "draft",
                "move_type": "in_invoice",
                "balance": 5_000_000,
                "product_id": [11, "Service Beta"],
                "purchase_line_id": False,
                "analytic_distribution": {"77": 40, "88": 60},
            },
        ]
        records["purchase.order.line"] = [
            {
                "id": 901,
                "name": "PO line 25% share",
                "order_id": [800, "PO001"],
                "order_id.state": "purchase",
                "product_id": [12, "Furniture Item"],
                "product_qty": 2,
                "qty_invoiced": 0,
                "price_subtotal": 20_000_000,
                "currency_id": [1, "VND"],
                "company_id": [1, "Bonario Synthetic"],
                "date_planned": "2026-05-20",
                "analytic_distribution": {"77": 25, "88": 75},
            }
        ]

        client = SyntheticOdooClient(records=records)
        service = self._make_service(client)

        posted_entries, posted_sources = service._get_posted_actual_costs(77)
        self.assertEqual(len(posted_sources), 1)
        self.assertEqual(posted_sources[0]["amount"], Decimal("4000000"))
        self.assertEqual(posted_entries[0]["amount"], Decimal("-4000000"))

        draft_sources = service._get_draft_bill_commitments(77)
        self.assertEqual(len(draft_sources), 1)
        self.assertEqual(draft_sources[0]["amount"], Decimal("2000000"))

        po_sources, _ = service._get_po_open_commitments(77, set())
        self.assertEqual(len(po_sources), 1)
        self.assertEqual(po_sources[0]["amount"], Decimal("5000000"))

    def test_c02_partial_draft_bill_on_po_retains_remaining_po_open_commitment(self) -> None:
        """C-02: PO of 10 units (100M) with Draft Bill of 3 units (30M) -> draft=30M, po_open=70M, open_commitment=100M."""
        records = build_base_synthetic_records()
        records["account.analytic.line"] = []
        records["account.move.line"] = [
            {
                "id": 201,
                "date": "2026-05-12",
                "name": "Draft bill for 3 units",
                "move_id": [601, "DRAFT/2026/002"],
                "parent_state": "draft",
                "move_type": "in_invoice",
                "quantity": 3,
                "price_unit": 10_000_000,
                "price_subtotal": 30_000_000,
                "balance": 30_000_000,
                "product_id": [20, "Chair Alpha"],
                "purchase_line_id": [910, "PO002 - Chair Alpha"],
                "analytic_distribution": {"77": 100},
            }
        ]
        records["purchase.order.line"] = [
            {
                "id": 910,
                "name": "PO002 - Chair Alpha (10 units)",
                "order_id": [810, "PO002"],
                "order_id.state": "purchase",
                "product_id": [20, "Chair Alpha"],
                "product_qty": 10,
                "qty_invoiced": 0,
                "price_unit": 10_000_000,
                "price_subtotal": 100_000_000,
                "currency_id": [1, "VND"],
                "company_id": [1, "Bonario Synthetic"],
                "date_planned": "2026-05-25",
                "analytic_distribution": {"77": 100},
            }
        ]

        client = SyntheticOdooClient(records=records)
        service = self._make_service(client)

        pipeline = service._build_accounting_cost_pipeline(
            {"account_id": [77, "AA-Project-77"]},
            [],
            {
                "billed_cost_total": Decimal("0"),
                "open_commitment_total": Decimal("100000000"),
                "expected_cost_total": Decimal("100000000"),
            },
        )

        self.assertEqual(pipeline["summary"]["draft_bill_commitment_total"], Decimal("30000000"))
        self.assertEqual(pipeline["summary"]["po_open_commitment_total"], Decimal("70000000"))
        self.assertEqual(pipeline["summary"]["open_commitment_total"], Decimal("100000000"))

    def test_c03_stock_valuation_fallback_preserves_actual_cost_total_and_handles_returns(self) -> None:
        """C-03: Stock valuation fallback is not overwritten to 0 by accounting_pipeline, and return layers (value > 0) reduce cost instead of abs() increasing it."""
        records = build_base_synthetic_records()
        raw_lines = [
            {
                "id": 501,
                "sequence": 1,
                "name": "Curtain Fabric",
                "display_type": False,
                "is_downpayment": False,
                "product_id": [30, "Fabric"],
                "product_uom_qty": 8,
                "qty_invoiced": 8,
                "qty_to_invoice": 0,
                "price_unit": 2_000_000,
                "discount": 0,
                "price_subtotal": 16_000_000,
                "untaxed_amount_invoiced": 16_000_000,
                "untaxed_amount_to_invoice": 0,
            }
        ]
        records["stock.move"] = [
            {
                "id": 601,
                "sale_line_id": [501, "Curtain Fabric"],
                "state": "done",
                "picking_id": [701, "WH/OUT/0001"],
                "stock_valuation_layer_ids": [801, 802],
            }
        ]
        records["stock.valuation.layer"] = [
            {
                "id": 801,
                "stock_move_id": [601, "WH/OUT/0001"],
                "value": -10_000_000,  # Outgoing delivery cost = 10M
                "description": "Delivery WH/OUT/0001",
            },
            {
                "id": 802,
                "stock_move_id": [601, "WH/IN/RETURN/0001"],
                "value": 2_000_000,  # Customer return into stock reduces cost by 2M -> net 8M
                "description": "Return WH/IN/0001",
            },
        ]

        client = SyntheticOdooClient(records=records)
        service = self._make_service(client)

        stock_map = service._get_stock_cost_map(raw_lines)
        self.assertEqual(stock_map[501]["actual_cost"], Decimal("8000000"))

        cost_model = service._build_cost_model(
            {"id": 100, "account_id": [77, "AA-77"]},
            raw_lines,
            {30: {"id": 30, "type": "product"}},
            {
                "billed_cost_total": Decimal("0"),
                "open_commitment_total": Decimal("0"),
                "expected_cost_total": Decimal("0"),
            },
        )
        self.assertEqual(cost_model["summary"]["actual_cost_total"], Decimal("8000000"))

    def test_c04_cogs_on_out_invoice_is_recorded_in_posted_actual_costs(self) -> None:
        """C-04: COGS lines on posted out_invoice (category != 'invoice') are included in _get_posted_actual_costs."""
        records = build_base_synthetic_records()
        records["account.analytic.line"] = [
            {
                "id": 1,
                "account_id": [77, "AA-77"],
                "date": "2026-05-05",
                "name": "COGS - Sofa Alpha",
                "amount": -3_500_000,
                "product_id": [40, "Sofa Alpha"],
                "move_line_id": [301, "INV/2026/001"],
                "category": "other",
            }
        ]
        records["account.move.line"] = [
            {
                "id": 301,
                "date": "2026-05-05",
                "name": "COGS - Sofa Alpha",
                "move_id": [701, "INV/2026/001"],
                "parent_state": "posted",
                "move_type": "out_invoice",
                "display_type": "cogs",
                "balance": 3_500_000,
                "product_id": [40, "Sofa Alpha"],
                "purchase_line_id": False,
                "analytic_distribution": {"77": 100},
            }
        ]

        client = SyntheticOdooClient(records=records)
        service = self._make_service(client)

        posted_entries, posted_sources = service._get_posted_actual_costs(77)
        self.assertEqual(len(posted_sources), 1)
        self.assertEqual(posted_sources[0]["amount"], Decimal("3500000"))
        self.assertEqual(len(posted_entries), 1)

    def test_c06_reversal_entry_and_multi_foreign_order_conservation(self) -> None:
        """C-06: Positive amount reversal entry reverses foreign cost adjustments, and multiple foreign_order_ids do not duplicate total cost."""
        records = build_base_synthetic_records()
        records["sale.order"] = [
            {"id": 10, "name": "SO-10", "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA], "amount_untaxed": 50_000_000},
            {"id": 20, "name": "SO-20", "partner_id": [2, SYNTHETIC_CUSTOMER_BETA], "amount_untaxed": 50_000_000},
            {"id": 30, "name": "SO-30", "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA], "amount_untaxed": 50_000_000},
        ]
        projects = [
            {"id": 1, "name": "P1", "sale_order_id": [10, "SO-10"], "account_id": [101, "AA-101"]},
            {"id": 2, "name": "P2", "sale_order_id": [20, "SO-20"], "account_id": [102, "AA-102"]},
            {"id": 3, "name": "P3", "sale_order_id": [30, "SO-30"], "account_id": [103, "AA-103"]},
        ]
        records["sale.order.line"] = [
            {"id": 1001, "name": "L1", "order_id": [10, "SO-10"], "price_subtotal": 10_000_000, "analytic_distribution": {"101": 100}},
            {"id": 2001, "name": "L2", "order_id": [20, "SO-20"], "price_subtotal": 10_000_000, "analytic_distribution": {"101": 100}},
            {"id": 3001, "name": "L3", "order_id": [30, "SO-30"], "price_subtotal": 10_000_000, "analytic_distribution": {"101": 100}},
        ]
        records["account.move.line"] = [
            # Move line 401: foreign cost from SO-20 booked on account 101, then reversed by entry 2
            {"id": 401, "name": "ML-401", "move_id": [801, "INV/1"], "sale_line_ids": [2001], "product_id": [50, "Item"]},
            # Move line 402: shared across SO-20 and SO-30 booked on account 101 (cost = 6,000,000)
            {"id": 402, "name": "ML-402", "move_id": [802, "INV/2"], "sale_line_ids": [2001, 3001], "product_id": [50, "Item"]},
        ]
        records["account.analytic.line"] = [
            # Entry 1 & 2: -5M and +5M reversal on ML-401 -> net should be 0
            {"id": 1, "name": "Orig", "amount": -5_000_000, "account_id": [101, "AA-101"], "move_line_id": [401, "ML-401"], "product_id": [50, "Item"], "category": "invoice"},
            {"id": 2, "name": "Rev", "amount": 5_000_000, "account_id": [101, "AA-101"], "move_line_id": [401, "ML-401"], "product_id": [50, "Item"], "category": "invoice"},
            # Entry 3: -6M on ML-402 (linked to both SO-20 and SO-30) -> removed from P1 = 6M, total added to P2 + P3 = 6M (not 12M)
            {"id": 3, "name": "Shared", "amount": -6_000_000, "account_id": [101, "AA-101"], "move_line_id": [402, "ML-402"], "product_id": [50, "Item"], "category": "invoice"},
        ]

        client = SyntheticOdooClient(records=records)
        service = self._make_service(client)

        sale_orders_by_id = {o["id"]: o for o in records["sale.order"]}
        adjustments = service._build_dashboard_analytic_adjustments(projects, sale_orders_by_id)

        total_removed = sum(adj["foreign_cost_removed"] for adj in adjustments.values())
        total_added = sum(adj["foreign_cost_added"] for adj in adjustments.values())

        self.assertEqual(total_removed, Decimal("6000000"))
        self.assertEqual(
            total_added,
            Decimal("6000000"),
            f"Total foreign_cost_added ({total_added}) must equal total_removed (6,000,000) without duplication or ignoring reversals",
        )

    def test_c07_parse_analytic_account_ids_parses_json_string_and_dict(self) -> None:
        """C-07: _parse_analytic_account_ids('{"1265,1581": 100}') returns {1265, 1581}."""
        service = self._make_service(SyntheticOdooClient())
        parsed_str = service._parse_analytic_account_ids('{"1265,1581": 100}')
        self.assertEqual(parsed_str, {1265, 1581})

        parsed_dict = service._parse_analytic_account_ids({"1265,1581": 100})
        self.assertEqual(parsed_dict, {1265, 1581})

    def test_b02_downpayment_total_uses_invoiced_amount_and_not_marked_stale(self) -> None:
        """B-02: Downpayment line uses invoiced deposit amount for downpayment_total and does not trigger false is_stale."""
        records = build_base_synthetic_records()
        records["project.project"] = [
            {
                "id": 100,
                "name": "DA Downpayment Test",
                "allow_timesheets": True,
                "partner_id": [1, SYNTHETIC_CUSTOMER_ALPHA],
                "sale_order_id": [10, "SO-DP-001"],
                "account_id": [101, "AA-101"],
                "active": True,
            }
        ]
        records["sale.order"] = [
            {
                "id": 10,
                "name": "SO-DP-001",
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
                "name": "Main Product Line",
                "order_id": [10, "SO-DP-001"],
                "display_type": False,
                "is_downpayment": False,
                "product_id": [201, "Product A"],
                "product_uom_qty": 1,
                "qty_invoiced": 0,
                "qty_to_invoice": 1,
                "price_unit": 100_000_000,
                "discount": 0,
                "price_subtotal": 100_000_000,
                "untaxed_amount_invoiced": 0,
                "untaxed_amount_to_invoice": 100_000_000,
            },
            {
                "id": 1002,
                "sequence": 20,
                "name": "Down Payment 30%",
                "order_id": [10, "SO-DP-001"],
                "display_type": False,
                "is_downpayment": True,
                "product_id": [202, "Down payment"],
                "product_uom_qty": 0,
                "qty_invoiced": 1,
                "qty_to_invoice": 0,
                "price_unit": 30_000_000,
                "discount": 0,
                "price_subtotal": 0,
                "untaxed_amount_invoiced": 30_000_000,
                "untaxed_amount_to_invoice": 0,
            },
        ]
        records["product.product"] = [
            {"id": 201, "type": "consu"},
            {"id": 202, "type": "service"},
        ]

        client = SyntheticOdooClient(
            records=records,
            panels={100: {"profitability_items": {"costs": {"data": []}}}},
        )
        service = self._make_service(client)
        detail = service.build_project_dashboard(100)

        dp_lines = [l for l in detail["lines"] if l["kind"] == "downpayment"]
        self.assertEqual(len(dp_lines), 1)
        self.assertFalse(dp_lines[0]["is_stale"], "Downpayment line must not be flagged as stale when price_subtotal=0 and untaxed_amount_invoiced>0")
        self.assertEqual(detail["summary"]["stale_line_count"], 0)
        self.assertEqual(detail["summary"]["downpayment_total"], 30_000_000.0)


if __name__ == "__main__":
    unittest.main()
