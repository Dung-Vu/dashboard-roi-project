from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import requests
from flask import json

from app import create_app
from config import Settings
from odoo_client import OdooAPI, OdooAPIError
from dashboard_service import DashboardService
from tests.fixtures.synthetic_data import SyntheticOdooClient


class ServerSideEncapsulationTest(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_db_path = tempfile.mkstemp(prefix="roi_test_encap_", suffix=".db")
        os.close(self.temp_fd)
        self.db_path = Path(self.temp_db_path)

        self.settings = Settings(
            odoo_url="https://erp.example.com",
            odoo_db="synthetic_erp_db",
            odoo_user_id=42,
            odoo_api_key="shh_super_secret_api_key_123",
            default_project_id=1035,
            port=5056,
            debug=False,
            dashboard_username="bonario",
            dashboard_password="synthetic_password",
            secret_key="synthetic_secret_key",
        )
        with (
            patch("cache.CACHE_DB_PATH", self.db_path),
            patch("app.CACHE_DB_PATH", self.db_path),
            patch("app.get_settings", return_value=self.settings),
            patch("config.get_settings", return_value=self.settings),
            patch("app.OdooAPI", return_value=SyntheticOdooClient(url="https://erp.example.com")),
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

    def test_dashboard_meta_excludes_odoo_url(self):
        """Verify that _build_projects_dashboard_meta does not leak the odoo_url in success payload."""
        fake_client = SyntheticOdooClient(url="https://erp.example.com")
        with patch("cache.CACHE_DB_PATH", self.db_path):
            service = DashboardService(fake_client)

        meta = service._build_projects_dashboard_meta([], [], "2026-01-01", "all")
        self.assertNotIn("odoo_url", meta, "odoo_url must NOT be exposed in success payload metadata!")

    def test_sale_order_redirect_route(self):
        """Verify that /api/redirect/sale-order/<int:so_id> performs a 302 redirect to Odoo URL."""
        with patch("app.get_settings", return_value=self.settings), patch("config.get_settings", return_value=self.settings):
            response = self.client.get("/api/redirect/sale-order/45")
        self.assertEqual(response.status_code, 302, "Local sale order redirect must return HTTP 302!")

        location = response.headers.get("Location")
        self.assertIsNotNone(location, "Redirect response must include Location header!")
        self.assertIn("id=45", location)
        self.assertIn("model=sale.order", location)
        self.assertIn("view_type=form", location)
        self.assertTrue(
            location.startswith(self.settings.odoo_url.rstrip("/")),
            "Redirect URL must start with setting-configured Odoo URL!",
        )

    def test_odoo_api_exception_chaining_suppressed_and_sanitized(self):
        """Verify traceback chaining is suppressed and credentials are redacted in raised exception message."""
        api = OdooAPI(
            url="https://erp.example.com",
            db="synthetic_erp_db",
            user_id=4242,
            api_key="shh_super_secret_api_key_123",
        )

        # Test Timeout Exception sanitization
        try:
            def fake_post(*args, **kwargs):
                raise requests.exceptions.Timeout(
                    "Connection to erp.example.com timed out with key shh_super_secret_api_key_123 on database synthetic_erp_db"
                )

            api.session.post = fake_post
            api.call_method("sale.order", "search_read")
        except OdooAPIError as exc:
            self.assertIsNone(exc.__cause__, "Traceback chaining must be suppressed via 'from None'!")
            self.assertEqual(str(exc), "Request timeout", "Timeout exception message should be sanitized to simple Request timeout!")

        # Test general Exception sanitization
        try:
            def fake_post_general(*args, **kwargs):
                raise ValueError(
                    "Could not connect to database synthetic_erp_db at https://erp.example.com using key shh_super_secret_api_key_123"
                )

            api.session.post = fake_post_general
            api.call_method("sale.order", "search_read")
        except OdooAPIError as exc:
            self.assertIsNone(exc.__cause__, "Traceback chaining must be suppressed via 'from None'!")
            exc_str = str(exc)
            self.assertNotIn("erp.example.com", exc_str, "Odoo hostname must be sanitized out!")
            self.assertNotIn("synthetic_erp_db", exc_str, "Odoo database name must be sanitized out!")
            self.assertNotIn("shh_super_secret_api_key_123", exc_str, "Odoo API key must be sanitized out!")
            self.assertIn("********", exc_str, "Redacted terms must be replaced by asterisks!")

    def test_flask_debug_error_handler_redacts_credentials(self):
        """Verify that Flask global error handler redacts sensitive connection details in debug mode responses."""
        mock_settings = Settings(
            odoo_url="https://erp.example.com",
            odoo_db="synthetic_erp_db",
            odoo_user_id=424242,
            odoo_api_key="shh_super_secret_api_key_123",
            default_project_id=1035,
            port=5056,
            debug=True,
            dashboard_username="bonario",
            dashboard_password="synthetic_password",
            secret_key="synthetic_secret_key",
        )

        with (
            patch("cache.CACHE_DB_PATH", self.db_path),
            patch("app.CACHE_DB_PATH", self.db_path),
            patch("app.get_settings", return_value=mock_settings),
            patch("config.get_settings", return_value=mock_settings),
            patch("app.OdooAPI", return_value=SyntheticOdooClient(url="https://erp.example.com")),
        ):
            debug_app = create_app()
            debug_app.config["TESTING"] = True

        @debug_app.get("/trigger-odoo-error")
        def trigger_odoo_error():
            raise OdooAPIError(
                "Odoo connection failed: url is https://erp.example.com db is synthetic_erp_db key is shh_super_secret_api_key_123 user is 424242",
                model="sale.order",
                method="search_read",
            )

        @debug_app.get("/trigger-general-error")
        def trigger_general_error():
            raise Exception(
                "Unexpected failure on server erp.example.com database synthetic_erp_db key shh_super_secret_api_key_123 user 424242"
            )

        client = debug_app.test_client()

        # Test OdooAPIError handling
        response = client.get("/trigger-odoo-error")
        self.assertEqual(response.status_code, 502)
        data = json.loads(response.data)
        self.assertFalse(data["ok"])

        err_msg = data["error"]
        self.assertNotIn("erp.example.com", err_msg)
        self.assertNotIn("synthetic_erp_db", err_msg)
        self.assertNotIn("shh_super_secret_api_key_123", err_msg)
        self.assertNotIn("424242", err_msg)
        self.assertIn("********", err_msg)

        # Test unexpected Exception handling
        response = client.get("/trigger-general-error")
        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertFalse(data["ok"])

        err_msg = data["error"]
        self.assertNotIn("erp.example.com", err_msg)
        self.assertNotIn("synthetic_erp_db", err_msg)
        self.assertNotIn("shh_super_secret_api_key_123", err_msg)
        self.assertNotIn("424242", err_msg)
        self.assertIn("********", err_msg)


if __name__ == "__main__":
    unittest.main()
