from __future__ import annotations

import unittest
from flask import json
from app import create_app
from config import get_settings


class TestDateFormatValidation(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

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
        """Verify that a valid date format (YYYY-MM-DD) does not trigger 400 validation error."""
        # Using a mock service or calling the route where Odoo is mocked out.
        # Since we just want to ensure validation passes, we can see if it bypasses 400
        # (even if Odoo call fails with 502/something else, it shouldn't be 400).
        response = self.client.get("/api/projects-dashboard?date_from=2026-01-01")
        self.assertNotEqual(
            response.status_code,
            400,
            "Valid date format should pass validation and not return HTTP 400!",
        )


if __name__ == "__main__":
    unittest.main()
