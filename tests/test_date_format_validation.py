from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import json

from app import create_app
from config import Settings
from tests.fixtures.synthetic_data import SyntheticOdooClient, build_base_synthetic_records


class TestDateFormatValidation(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_db_path = tempfile.mkstemp(prefix="roi_test_date_", suffix=".db")
        os.close(self.temp_fd)
        self.db_path = Path(self.temp_db_path)

        self.settings = Settings(
            odoo_url="https://erp.example.com",
            odoo_db="synthetic_db",
            odoo_user_id=1,
            odoo_api_key="synthetic_key",
            default_project_id=100,
            port=5056,
            debug=False,
            dashboard_username="bonario",
            dashboard_password="synthetic_password",
            secret_key="synthetic_secret_key",
        )
        self.fake_odoo = SyntheticOdooClient(records=build_base_synthetic_records(), url="https://erp.example.com")

        with (
            patch("cache.CACHE_DB_PATH", self.db_path),
            patch("app.CACHE_DB_PATH", self.db_path),
            patch("app.get_settings", return_value=self.settings),
            patch("config.get_settings", return_value=self.settings),
            patch("app.OdooAPI", return_value=self.fake_odoo),
        ):
            self.app = create_app()
            self.app.config["TESTING"] = True
            self.client = self.app.test_client()

    def tearDown(self):
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except OSError:
                pass

    def test_invalid_date_format_returns_400(self):
        """Verify that passing an invalid date format (e.g. not YYYY-MM-DD) returns HTTP 400 Bad Request."""
        invalid_dates = [
            "2026/01/01",
            "01-01-2026",
            "not-a-date",
            "2026-13-01",
            "2026-01-32",
            "  ",
        ]
        for date_str in invalid_dates:
            response = self.client.get(f"/api/projects-dashboard?date_from={date_str}")
            self.assertEqual(
                response.status_code,
                400,
                f"Invalid date '{date_str}' must return HTTP 400 Bad Request!",
            )
            data = json.loads(response.data)
            self.assertFalse(data["ok"])
            self.assertIn("date_from must use YYYY-MM-DD format.", data["error"])

    def test_valid_date_format_passes_validation(self):
        """Verify that a valid date format (YYYY-MM-DD) returns HTTP 200 with valid payload using mocked Odoo."""
        response = self.client.get("/api/projects-dashboard?date_from=2026-01-01")
        self.assertEqual(
            response.status_code,
            200,
            "Valid date format with mocked Odoo client must return HTTP 200!",
        )
        data = json.loads(response.data)
        self.assertEqual(data["date_from"], "2026-01-01")
        self.assertIn("projects", data)
        self.assertIn("summary", data)


if __name__ == "__main__":
    unittest.main()
