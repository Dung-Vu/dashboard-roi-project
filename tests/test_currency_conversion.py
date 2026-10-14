from __future__ import annotations

import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from dashboard_service import DashboardService
from odoo_client import OdooAPI

VND, USD, COMPANY = 23, 1, 1


class TestCurrencyConversion(unittest.TestCase):
    """res.currency._convert is private on Odoo.com (RPC raises), so conversion must
    be done from res.currency.rate without calling it."""

    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db_path = Path(path)
        self.client = MagicMock(spec=OdooAPI)

        def search_read(model, domain, fields=None, limit=0, offset=0):
            if model == "res.company":
                return [{"id": COMPANY, "currency_id": [VND, "VND"]}]
            if model == "res.currency.rate":
                currency_id = domain[0][2]
                if currency_id == USD:
                    return [
                        {"name": "2026-01-01", "rate": 1 / 25000, "company_id": False},
                        {"name": "2026-06-01", "rate": 1 / 26000, "company_id": False},
                        {"name": "2026-06-01", "rate": 1 / 26500, "company_id": [COMPANY, "Bonario"]},
                    ]
                return []  # VND is the base currency: no rate rows
            raise AssertionError(f"unexpected model {model}")

        self.client.search_read.side_effect = search_read
        self.client.call_method.side_effect = AssertionError("call_method must not be used for conversion")
        with patch("cache.CACHE_DB_PATH", self.db_path):
            self.service = DashboardService(self.client)

    def tearDown(self):
        if self.db_path.exists():
            os.remove(self.db_path)

    def test_converts_with_company_rate_on_date(self):
        result = self.service._convert_to_company_currency(Decimal("100"), USD, COMPANY, "2026-07-15")
        self.assertEqual(round(result, 2), Decimal("2650000.00"))

    def test_uses_oldest_rate_before_first_rate_date(self):
        result = self.service._convert_to_company_currency(Decimal("1"), USD, COMPANY, "2025-12-01")
        # company-specific rates exist, so only those are used
        self.assertEqual(round(result, 2), Decimal("26500.00"))

    def test_same_currency_is_unchanged_and_rates_are_cached(self):
        self.assertEqual(
            self.service._convert_to_company_currency(Decimal("5"), VND, COMPANY, "2026-07-15"),
            Decimal("5"),
        )
        for _ in range(3):
            self.service._convert_to_company_currency(Decimal("1"), USD, COMPANY, "2026-07-15")
        models = [c.args[0] for c in self.client.search_read.call_args_list]
        self.assertEqual(models.count("res.company"), 1)
        self.assertEqual(models.count("res.currency.rate"), 2)  # USD + VND, once each
        self.client.call_method.assert_not_called()


if __name__ == "__main__":
    unittest.main()
