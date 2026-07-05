from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

import dashboard_service
from dashboard_service import (
    DashboardService,
    SHIPPING_ANALYTIC_ACCOUNT_IDS_FALLBACK,
)


class FakeClient:
    """Minimal stub OdooAPI so we can exercise shipping detection without network."""
    SC_ACCOUNTS = [
        (1519, "SC - Logistics OPS"),
        (1518, "SC - Logistics SO"),
        (1271, "SC - Rush logistics - Ship gấp"),
        (566, "SC_Shipping (CLT, demo...)"),
        (1522, "[ORD] SC - Logistics OPS"),
        (1523, "[ORD] SC - Logistics SO"),
        (1270, "[ORD] SC - Rush logistics - Ship gấp"),
        (1239, "[ORD] SC_Shipping (CLT, demo...)"),
    ]
    BD_ACCOUNTS = [
        (506, "BD_Shipping (CLT, demo...)"),
        (1427, "ORD - BD_Shipping (CLT, demo...)"),
    ]

    def __init__(self):
        self.search_read_calls = []

    def search_read(self, model, domain, fields, limit=0, offset=0):
        self.search_read_calls.append((model, tuple(tuple(d) for d in domain), tuple(fields), limit))
        if model != "account.analytic.account":
            return []
        # Honour the domain's plan_id.name ILIKE SC by only returning SC accounts.
        plan_filter_sc = any(
            len(leaf) == 3 and leaf[0] == "plan_id.name" and leaf[2].lower() == "sc"
            for leaf in domain
        )
        if plan_filter_sc:
            return [
                {"id": aid, "name": name, "plan_id": [10, "Departments / SC Dept"]}
                for aid, name in self.SC_ACCOUNTS
            ]
        # Return everything when no plan filter — used by tests for explicit assertions.
        return [
            {"id": aid, "name": name, "plan_id": [10, "Departments / SC Dept"]}
            for aid, name in self.SC_ACCOUNTS
        ] + [
            {"id": aid, "name": name, "plan_id": [11, "Departments / BD Dept"]}
            for aid, name in self.BD_ACCOUNTS
        ]


class ShippingDetectionTest(unittest.TestCase):
    def setUp(self):
        self.service = DashboardService.__new__(DashboardService)
        # Bypass __init__ to keep the test offline.
        self.service.client = FakeClient()
        self.service._shipping_account_ids = None
        self.service._shipping_account_ids_lock = __import__("threading").Lock()
        self.service._shipping_account_ids_refresh_at = 0.0

    def test_fallback_set_is_complete(self):
        """Static fallback whitelist must include all 8 SC shipping accounts."""
        expected = {566, 1239, 1270, 1271, 1518, 1519, 1522, 1523}
        self.assertTrue(
            expected.issubset(SHIPPING_ANALYTIC_ACCOUNT_IDS_FALLBACK),
            f"Missing SC shipping IDs from fallback whitelist: {expected - SHIPPING_ANALYTIC_ACCOUNT_IDS_FALLBACK}",
        )

    def test_dynamic_discovery_includes_sc_accounts_excludes_bd(self):
        ids = self.service._get_shipping_account_ids()
        sc_ids = {1519, 1518, 1271, 566, 1522, 1523, 1270, 1239}
        for sid in sc_ids:
            self.assertIn(sid, ids, f"SC shipping account {sid} not in dynamic whitelist")
        for bd_id in {506, 1427}:
            self.assertNotIn(bd_id, ids, f"BD shipping account {bd_id} leaked into whitelist")

    def test_dynamic_discovery_uses_fallback_when_search_fails(self):
        class BrokenClient:
            def search_read(self, *args, **kwargs):
                raise RuntimeError("boom")
        svc = DashboardService.__new__(DashboardService)
        svc.client = BrokenClient()
        svc._shipping_account_ids = None
        svc._shipping_account_ids_lock = __import__("threading").Lock()
        svc._shipping_account_ids_refresh_at = 0.0
        ids = svc._get_shipping_account_ids()
        # When Odoo discovery fails, fallback should still cover all 8 SC accounts.
        for sid in {566, 1239, 1270, 1271, 1518, 1519, 1522, 1523}:
            self.assertIn(sid, ids)

    def test_is_shipping_distribution_matches_each_sc_account(self):
        # After _get_shipping_account_ids runs, every SC shipping account should match.
        for sid in (1519, 1518, 1271, 566, 1522, 1523, 1270, 1239):
            dist = {f"{sid},1781": 100.0}
            self.assertTrue(
                self.service._is_shipping_distribution(dist),
                f"Shipping account {sid} not detected in distribution {dist}",
            )

    def test_is_shipping_distribution_rejects_non_shipping_accounts(self):
        # Even if project account 1781 is present, a non-shipping account alone
        # must not classify the line as shipping.
        non_ship_ids = (1236, 1781, 13, 99)
        for nid in non_ship_ids:
            dist = {f"{nid}": 100.0}
            self.assertFalse(
                self.service._is_shipping_distribution(dist),
                f"Non-shipping account {nid} incorrectly flagged as shipping",
            )

    def test_is_shipping_distribution_handles_string_payload(self):
        # Odoo can return analytic_distribution as a JSON-encoded string in some fields.
        import json as _json
        for sid in (1519, 1522, 1518):
            dist = {f"{sid},1781": 100.0}
            self.assertTrue(
                self.service._is_shipping_distribution(_json.dumps(dist)),
                f"String-encoded dist with {sid} not detected",
            )

    def test_is_shipping_distribution_handles_empty_and_invalid(self):
        for value in (None, "", {}, "not a dict", []):
            self.assertFalse(self.service._is_shipping_distribution(value))

    def test_module_file_no_longer_has_hardcoded_shipping_ids(self):
        """Regression guard — the old '1519/1271' hardcode must not reappear in shipping calc."""
        src = Path(dashboard_service.__file__).read_text(encoding="utf-8")
        forbidden = [
            'if "1519" in parts or "1271" in parts',
            'if "1271" in parts or "1519" in parts',
        ]
        for snippet in forbidden:
            self.assertNotIn(snippet, src, f"Hardcoded shipping detection found: {snippet!r}")
        # Whitelist constant must still reference 1519 (curated IDs), but detection path uses helper.
        self.assertIn("1519", src)


if __name__ == "__main__":
    unittest.main()