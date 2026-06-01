from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

import os
# Isolate test cache database to prevent contamination of the production database
TEST_CACHE_DB = Path(__file__).parent / "test_cache.db"
os.environ["CACHE_DB_PATH"] = str(TEST_CACHE_DB)

from dashboard_service import DashboardService


class FakeOdooClient:
    def __init__(self, records=None, conversions=None, panels=None, field_relations=None):
        self.records = records or {}
        self.conversions = conversions or {}
        self.panels = panels or {}
        self.field_relations = field_relations or {}
        self.calls = []
        self.url = "http://localhost:8069"

    def search_read(self, model, domain, fields=None, limit=0, offset=0):
        self.calls.append(("search_read", model, domain, fields))
        records = [dict(record) for record in self.records.get(model, [])]
        matches = [record for record in records if self._matches(record, domain)]
        if offset:
            matches = matches[offset:]
        if limit:
            matches = matches[:limit]
        return matches

    def call_method(self, model, method, args=None, kwargs=None):
        self.calls.append(("call_method", model, method, args))
        if method == "search_read":
            domain = args[0] if args else []
            fields = (kwargs or {}).get("fields")
            limit = (kwargs or {}).get("limit", 0)
            return self.search_read(model, domain, fields, limit=limit)
        if model == "res.currency" and method == "_convert":
            currency_id = args[0][0]
            amount = Decimal(str(args[1]))
            return self.conversions.get(currency_id, amount)
        if model == "project.project" and method == "get_panel_data":
            project_id = args[0][0]
            return self.panels.get(project_id, {})
        if method == "fields_get":
            field_names = args[0] if args else []
            return {
                field: {"relation": self.field_relations.get((model, field))}
                for field in field_names
                if self.field_relations.get((model, field))
            }
        return {}

    def _matches(self, record, domain):
        for field, operator, value in domain:
            actual = self._get_field(record, field)
            comparable = self._comparable_value(actual)
            if operator == "=" and comparable != value:
                return False
            if operator == "!=" and comparable == value:
                return False
            if operator == "in" and not self._matches_in(actual, value):
                return False
            if operator == ">=" and str(comparable) < str(value):
                return False
            if operator == "ilike" and str(value) not in str(actual):
                return False
        return True

    def _matches_in(self, actual, values):
        comparable = self._comparable_value(actual)
        if isinstance(comparable, list):
            return any(item in values for item in comparable)
        return comparable in values

    def _comparable_value(self, value):
        if isinstance(value, list) and value and isinstance(value[0], int):
            return value[0]
        return value

    def _get_field(self, record, field):
        if "." not in field:
            return record.get(field)
        value = record
        for part in field.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        return value


class CostPipelineTest(unittest.TestCase):
    def test_current_project_final_cost_uses_posted_actual_plus_draft_commitment(self):
        client = FakeOdooClient(
            {
                "account.analytic.line": [
                    {
                        "id": 1,
                        "account_id": 77,
                        "date": "2026-05-01",
                        "name": "Posted vendor bill",
                        "amount": -115_863_651,
                        "product_id": [10, "Material"],
                        "move_line_id": [100, "BILL/001"],
                        "category": "vendor_bill",
                    }
                ],
                "account.move.line": [
                    {
                        "id": 100,
                        "date": "2026-05-01",
                        "name": "Posted vendor bill",
                        "move_id": [500, "BILL/001"],
                        "parent_state": "posted",
                        "move_type": "in_invoice",
                        "balance": 115_863_651,
                        "product_id": [10, "Material"],
                        "purchase_line_id": [900, "PO line"],
                    },
                    {
                        "id": 101,
                        "date": "2026-05-15",
                        "name": "Draft vendor bill",
                        "move_id": [501, "DRAFT/001"],
                        "parent_state": "draft",
                        "move_type": "in_invoice",
                        "balance": 2_960_000,
                        "product_id": [11, "Install service"],
                        "purchase_line_id": [901, "PO line draft"],
                        "analytic_distribution": {"77": 100},
                    },
                ],
                "purchase.order.line": [
                    {
                        "id": 901,
                        "name": "Already covered by draft bill",
                        "order_id": [800, "PO001"],
                        "product_id": [11, "Install service"],
                        "product_qty": 1,
                        "qty_invoiced": 0,
                        "price_subtotal": 2_960_000,
                        "currency_id": [1, "VND"],
                        "company_id": [1, "Company"],
                        "date_planned": "2026-05-15",
                        "analytic_distribution": {"77": 100},
                    }
                ],
                "res.company": [{"id": 1, "currency_id": [1, "VND"]}],
            }
        )
        service = DashboardService(client)

        pipeline = service._build_accounting_cost_pipeline(
            {"account_id": [77, "Project analytic"]},
            [],
            {
                "billed_cost_total": Decimal("115216732"),
                "open_commitment_total": Decimal("2960000"),
                "expected_cost_total": Decimal("118176732"),
            },
        )

        self.assertEqual(pipeline["summary"]["posted_actual_total"], Decimal("115863651"))
        self.assertEqual(pipeline["summary"]["open_commitment_total"], Decimal("2960000"))
        self.assertEqual(pipeline["summary"]["final_cost_total"], Decimal("118823651"))
        self.assertEqual(
            pipeline["reconciliation"]["final_vs_native_expected_gap"],
            Decimal("646919"),
        )

    def test_draft_multicurrency_bill_uses_accounting_balance(self):
        client = FakeOdooClient(
            {
                "account.analytic.line": [],
                "account.move.line": [
                    {
                        "id": 201,
                        "date": "2026-05-20",
                        "name": "CNY draft bill",
                        "move_id": [601, "DRAFT/CNY"],
                        "parent_state": "draft",
                        "move_type": "in_invoice",
                        "balance": 2_960_000,
                        "product_id": [12, "Imported part"],
                        "purchase_line_id": False,
                        "analytic_distribution": {"77": 100},
                    }
                ],
                "purchase.order.line": [],
            }
        )
        service = DashboardService(client)

        sources = service._get_draft_bill_commitments(77)

        self.assertEqual(sources[0]["amount"], Decimal("2960000"))

    def test_analytic_distribution_match_accepts_combined_account_key(self):
        service = DashboardService(FakeOdooClient())

        self.assertTrue(service._analytic_distribution_matches({"1265,1581": 100}, 1581))
        self.assertTrue(service._analytic_distribution_matches({"1265,1581": 100}, 1265))
        self.assertFalse(service._analytic_distribution_matches({"1265,1581": 100}, 1141))

    def test_posted_vendor_bill_is_actual_not_commitment(self):
        client = FakeOdooClient(
            {
                "account.analytic.line": [
                    {
                        "id": 1,
                        "account_id": 77,
                        "date": "2026-05-01",
                        "name": "Posted bill",
                        "amount": -2_960_000,
                        "product_id": [10, "Service"],
                        "move_line_id": [100, "BILL/001"],
                        "category": "vendor_bill",
                    }
                ],
                "account.move.line": [
                    {
                        "id": 100,
                        "date": "2026-05-01",
                        "name": "Posted bill",
                        "move_id": [500, "BILL/001"],
                        "parent_state": "posted",
                        "move_type": "in_invoice",
                        "balance": 2_960_000,
                        "product_id": [10, "Service"],
                        "purchase_line_id": False,
                    }
                ],
                "purchase.order.line": [],
            }
        )
        service = DashboardService(client)

        pipeline = service._build_accounting_cost_pipeline(
            {"account_id": [77, "Project analytic"]},
            [],
            {
                "billed_cost_total": Decimal("0"),
                "open_commitment_total": Decimal("0"),
                "expected_cost_total": Decimal("0"),
            },
        )

        self.assertEqual(pipeline["summary"]["posted_actual_total"], Decimal("2960000"))
        self.assertEqual(pipeline["summary"]["open_commitment_total"], Decimal("0"))

    def test_final_cost_logic_does_not_read_product_standard_price(self):
        source = Path("dashboard_service.py").read_text(encoding="utf-8")

        self.assertNotIn("standard_price", source)


class ProjectsDashboardTest(unittest.TestCase):
    def test_projects_dashboard_shape_and_weighted_gp_use_native_expected_cost(self):
        client = FakeOdooClient(
            records={
                "sale.order": [
                    {
                        "id": 10,
                        "name": "BG001",
                        "partner_id": [1, "Client A"],
                        "date_order": "2026-01-02 09:00:00",
                        "amount_untaxed": 100_000_000,
                        "x_sale_order_tag_ids": [101, 102],
                        "x_studio_selection_field_q4_1imrcsjj8": "Done",
                    },
                    {
                        "id": 11,
                        "name": "BG002",
                        "partner_id": [2, "Client B"],
                        "date_order": "2026-02-03 09:00:00",
                        "amount_untaxed": 200_000_000,
                        "x_sale_order_tag_ids": [101],
                        "x_studio_selection_field_q4_1imrcsjj8": "Done",
                    },
                    {
                        "id": 12,
                        "name": "BG003",
                        "partner_id": [3, "Client C"],
                        "date_order": "2026-03-04 09:00:00",
                        "amount_untaxed": 0,
                        "x_sale_order_tag_ids": [103],
                        "x_studio_selection_field_q4_1imrcsjj8": "Done",
                    },
                ],
                "project.project": [
                    {"id": 100, "name": "Project A", "partner_id": [1, "Client A"], "sale_order_id": [10, "BG001"]},
                    {"id": 101, "name": "Project B", "partner_id": [2, "Client B"], "sale_order_id": [11, "BG002"]},
                    {"id": 102, "name": "Project C", "partner_id": [3, "Client C"], "sale_order_id": [12, "BG003"]},
                ],
                "crm.tag": [
                    {"id": 101, "name": "Nội thất rời"},
                    {"id": 102, "name": "Rèm"},
                    {"id": 103, "name": "Giấy dán tường"},
                ],
            },
            panels={
                100: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -60_000_000, "to_bill": 0}]}}},
                101: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -100_000_000, "to_bill": 0}]}}},
                102: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -5_000_000, "to_bill": 0}]}}},
            },
            field_relations={("sale.order", "x_sale_order_tag_ids"): "crm.tag"},
        )
        service = DashboardService(client)

        payload = service.build_projects_dashboard("2026-01-01", refresh=True)

        self.assertEqual(set(payload.keys()), {"projects", "summary", "tag_buckets", "tag_gp_ranks", "meta", "date_from", "company", "fetched_at", "cached_at"})
        self.assertEqual(len(payload["projects"]), 3)
        self.assertEqual(payload["summary"]["total_projects"], 3)
        self.assertEqual(payload["summary"]["valid_project_count"], 2)
        self.assertEqual(payload["summary"]["total_bg_untaxed"], 300_000_000)
        self.assertEqual(payload["summary"]["total_native_expected_cost"], 160_000_000)
        self.assertEqual(payload["summary"]["weighted_gp_percent"], 46.67)
        self.assertIsNone(next(row for row in payload["projects"] if row["project_id"] == 102)["gp_percent"])
        self.assertEqual(payload["tag_buckets"]["Nội thất rời"][">200tr"]["count"], 1)
        self.assertEqual(payload["tag_buckets"]["Rèm"]["100-200tr"]["weighted_gp_percent"], 40.0)
        self.assertEqual(payload["tag_buckets"]["Giấy dán tường"]["<10tr"]["count"], 0)
        self.assertEqual(payload["meta"]["date_field"], "sale.order.date_order")
        self.assertEqual(payload["meta"]["project_scope"], "all_order_states")
        self.assertEqual(payload["meta"]["summary_scope"], "done_only")
        self.assertEqual(payload["meta"]["counts"]["list_projects"], 3)
        self.assertEqual(payload["meta"]["counts"]["done_projects"], 3)
        self.assertEqual(payload["meta"]["counts"]["valid_done_projects"], 2)
        self.assertEqual(payload["meta"]["state_counts"], {"Done": 3})

    def test_tier_boundaries(self):
        service = DashboardService(FakeOdooClient())

        self.assertEqual(service._tier_for_amount(Decimal("9999999")), "<10tr")
        self.assertEqual(service._tier_for_amount(Decimal("10000000")), "10-100tr")
        self.assertEqual(service._tier_for_amount(Decimal("100000000")), "100-200tr")
        self.assertEqual(service._tier_for_amount(Decimal("200000000")), ">200tr")

    def test_excluded_salesperson_matches_odoo_combined_display_name(self):
        order = {"user_id": [208, "CEO office, Đỗ Thị Hải Yến"]}

        self.assertTrue(DashboardService._is_excluded_salesperson(order))

    def test_gp_range_label_uses_five_percent_bucket_after_forty(self):
        service = DashboardService(FakeOdooClient())

        self.assertEqual(service._gp_range_label(Decimal("20.0")), "0-20%")
        self.assertEqual(service._gp_range_label(Decimal("40.0")), "21-40%")
        self.assertEqual(service._gp_range_label(Decimal("41.0")), "41-45%")
        self.assertEqual(service._gp_range_label(Decimal("45.999")), "41-45%")
        self.assertEqual(service._gp_range_label(Decimal("46.0")), "46-50%")

    def test_tag_gp_rank_prefers_count_then_total_bg(self):
        service = DashboardService(FakeOdooClient())
        rows = [
            {"tags": ["Rèm"], "bg_untaxed": 100_000_000, "gp_percent": 46.2},
            {"tags": ["Rèm"], "bg_untaxed": 50_000_000, "gp_percent": 47.9},
            {"tags": ["Rèm"], "bg_untaxed": 300_000_000, "gp_percent": 52.0},
            {"tags": ["Rèm"], "bg_untaxed": 10_000_000, "gp_percent": 55.0},
            {"tags": ["Rèm"], "bg_untaxed": 0, "gp_percent": None},
        ]

        ranks = service._build_tag_gp_ranks(rows)

        self.assertEqual(ranks["Rèm"][0]["range"], "51-55%")
        self.assertEqual(ranks["Rèm"][0]["count"], 2)
        self.assertEqual(ranks["Rèm"][1]["range"], "46-50%")

    def test_projects_dashboard_multi_company_sync(self):
        client = FakeOdooClient(
            records={
                "res.company": [
                    {"id": 1, "name": "Bonario", "active": True},
                    {"id": 2, "name": "Ordinaire", "active": True},
                ],
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
                    },
                    {
                        "id": 11,
                        "name": "SO002",
                        "partner_id": [2, "Client B"],
                        "date_order": "2026-02-03 09:00:00",
                        "amount_untaxed": 200_000_000,
                        "x_sale_order_tag_ids": [101],
                        "x_studio_selection_field_q4_1imrcsjj8": "Done",
                        "company_id": [2, "Ordinaire"],
                    },
                ],
                "project.project": [
                    {"id": 100, "name": "Project Bonario", "partner_id": [1, "Client A"], "sale_order_id": [10, "SO001"], "company_id": [1, "Bonario"]},
                    {"id": 101, "name": "Project Ordinaire", "partner_id": [2, "Client B"], "sale_order_id": [11, "SO002"], "company_id": [2, "Ordinaire"]},
                ],
                "crm.tag": [
                    {"id": 101, "name": "Nội thất rời"},
                ],
            },
            panels={
                100: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -60_000_000, "to_bill": 0}]}}},
                101: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -100_000_000, "to_bill": 0}]}}},
            },
            field_relations={("sale.order", "x_sale_order_tag_ids"): "crm.tag"},
        )
        service = DashboardService(client)

        # Build dashboard for "bonario" company
        payload = service.build_projects_dashboard("2026-01-01", company="bonario", refresh=True)

        # 1. Assert projects filters correctly by company_key
        self.assertEqual(len(payload["projects"]), 1)
        self.assertEqual(payload["projects"][0]["project_id"], 100)
        self.assertEqual(payload["projects"][0]["company_key"], "bonario")

        # 2. Assert summary is calculated only on the selected company's projects
        self.assertEqual(payload["summary"]["total_projects"], 1)
        self.assertEqual(payload["summary"]["valid_project_count"], 1)
        self.assertEqual(payload["summary"]["total_bg_untaxed"], 100_000_000.0)
        self.assertEqual(payload["summary"]["total_native_expected_cost"], 60_000_000.0)
        self.assertEqual(payload["summary"]["total_adjusted_expected_cost"], 60_000_000.0)
        self.assertEqual(payload["summary"]["total_gp_amount"], 40_000_000.0)
        self.assertEqual(payload["summary"]["weighted_gp_percent"], 40.0)

        # 3. Assert tag_buckets and tag_gp_ranks aggregate projects from all companies combined
        # Bonario project: 100M untaxed -> 100-200tr tier
        # Ordinaire project: 200M untaxed -> >200tr tier
        self.assertEqual(payload["tag_buckets"]["Nội thất rời"]["100-200tr"]["count"], 1)
        self.assertEqual(payload["tag_buckets"]["Nội thất rời"]["100-200tr"]["bg_untaxed"], 100_000_000.0)
        self.assertEqual(payload["tag_buckets"]["Nội thất rời"][">200tr"]["count"], 1)
        self.assertEqual(payload["tag_buckets"]["Nội thất rời"][">200tr"]["bg_untaxed"], 200_000_000.0)

        # Tag GP ranks: should have ranks from all companies combined
        # Bonario project GP% is 40.0% -> range "21-40%"
        # Ordinaire project GP% is 50.0% -> range "46-50%"
        ranks = payload["tag_gp_ranks"]["Nội thất rời"]
        self.assertEqual(len(ranks), 2)
        ranges = {r["range"] for r in ranks}
        self.assertIn("21-40%", ranges)
        self.assertIn("46-50%", ranges)

    def test_combined_analytic_distribution_key_does_not_adjust_cost_when_project_account_is_present(self):
        client = FakeOdooClient(
            records={
                "sale.order": [
                    {
                        "id": 2594,
                        "name": "BG-202506-2392",
                        "partner_id": [1, "Client A"],
                        "date_order": "2026-04-15 09:21:23",
                        "amount_untaxed": 65_634_541,
                        "x_sale_order_tag_ids": [101],
                        "x_studio_selection_field_q4_1imrcsjj8": "Done",
                        "company_id": [1, "Bonario"],
                    },
                ],
                "project.project": [
                    {
                        "id": 1481,
                        "name": "BG-202506-2392 - Template - BG VLDT",
                        "partner_id": [1, "Client A"],
                        "sale_order_id": [2594, "BG-202506-2392"],
                        "account_id": [1581, "BG-202506-2392"],
                        "company_id": [1, "Bonario"],
                        "active": True,
                    },
                ],
                "sale.order.line": [
                    {
                        "id": 15203,
                        "name": "Wallpaper",
                        "order_id": [2594, "BG-202506-2392"],
                        "price_subtotal": 4_704_000,
                        "analytic_distribution": {"1265,1581": 100},
                    },
                ],
                "account.analytic.line": [],
                "crm.tag": [
                    {"id": 101, "name": "Nội thất rời"},
                ],
            },
            panels={
                1481: {"profitability_items": {"costs": {"data": [{"id": "cost", "billed": -25_366_300, "to_bill": 0}]}}},
            },
            field_relations={("sale.order", "x_sale_order_tag_ids"): "crm.tag"},
        )
        service = DashboardService(client)

        payload = service.build_projects_dashboard("2026-01-01", company="bonario", refresh=True)
        row = payload["projects"][0]

        self.assertNotIn("has_analytic_mismatch", row)
        self.assertNotIn("data_quality_notes", row)
        self.assertEqual(row["native_expected_cost"], 25_366_300)
        self.assertEqual(row["adjusted_expected_cost"], 25_366_300)
        self.assertEqual(row["cost_added_amount"], 0)
        self.assertEqual(row["cost_removed_amount"], 0)


if __name__ == "__main__":
    unittest.main()


def tearDownModule():
    # Clean up test database cache file
    test_db = Path(__file__).parent / "test_cache.db"
    if test_db.exists():
        try:
            test_db.unlink()
        except Exception:
            pass
