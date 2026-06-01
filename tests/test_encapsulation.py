from __future__ import annotations

import unittest
from decimal import Decimal
from urllib.parse import urlparse
import requests
from flask import json

from app import create_app
from config import get_settings
from odoo_client import OdooAPI, OdooAPIError
from dashboard_service import DashboardService
from tests.test_cost_pipeline import FakeOdooClient


class ServerSideEncapsulationTest(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.app = create_app()
        self.client = self.app.test_client()

    def test_dashboard_meta_excludes_odoo_url(self):
        """Verify that _build_projects_dashboard_meta does not leak the odoo_url in success payload."""
        fake_client = FakeOdooClient()
        fake_client.url = "https://bonario-vietnam.odoo.com"
        service = DashboardService(fake_client)
        
        meta = service._build_projects_dashboard_meta([], [], "2026-01-01", "all")
        self.assertNotIn("odoo_url", meta, "odoo_url must NOT be exposed in success payload metadata!")

    def test_sale_order_redirect_route(self):
        """Verify that /api/redirect/sale-order/<int:so_id> performs a 302 redirect to Odoo URL."""
        response = self.client.get("/api/redirect/sale-order/45")
        self.assertEqual(response.status_code, 302, "Local sale order redirect must return HTTP 302!")
        
        location = response.headers.get("Location")
        self.assertIsNotNone(location, "Redirect response must include Location header!")
        self.assertIn(f"id=45", location)
        self.assertIn("model=sale.order", location)
        self.assertIn("view_type=form", location)
        self.assertTrue(location.startswith(self.settings.odoo_url.rstrip("/")), "Redirect URL must start with setting-configured Odoo URL!")

    def test_odoo_api_exception_chaining_suppressed_and_sanitized(self):
        """Verify traceback chaining is suppressed and credentials are redacted in raised exception message."""
        api = OdooAPI(
            url="https://bonario-vietnam.odoo.com",
            db="bonario_db_name",
            user_id=42,
            api_key="shh_super_secret_api_key_123"
        )
        
        # Test Timeout Exception sanitization
        try:
            # We mock post request to raise standard timeout exception
            def fake_post(*args, **kwargs):
                raise requests.exceptions.Timeout("Connection to bonario-vietnam.odoo.com timed out with key shh_super_secret_api_key_123 on database bonario_db_name")
            
            api.session.post = fake_post
            api.call_method("sale.order", "search_read")
        except OdooAPIError as exc:
            self.assertIsNone(exc.__cause__, "Traceback chaining must be suppressed via 'from None'!")
            self.assertEqual(str(exc), "Request timeout", "Timeout exception message should be sanitized to simple Request timeout!")

        # Test general Exception sanitization
        try:
            def fake_post_general(*args, **kwargs):
                raise ValueError("Could not connect to database bonario_db_name at https://bonario-vietnam.odoo.com using key shh_super_secret_api_key_123")
                
            api.session.post = fake_post_general
            api.call_method("sale.order", "search_read")
        except OdooAPIError as exc:
            self.assertIsNone(exc.__cause__, "Traceback chaining must be suppressed via 'from None'!")
            exc_str = str(exc)
            self.assertNotIn("bonario-vietnam.odoo.com", exc_str, "Odoo hostname must be sanitized out!")
            self.assertNotIn("bonario_db_name", exc_str, "Odoo database name must be sanitized out!")
            self.assertNotIn("shh_super_secret_api_key_123", exc_str, "Odoo API key must be sanitized out!")
            self.assertIn("********", exc_str, "Redacted terms must be replaced by asterisks!")

    def test_flask_debug_error_handler_redacts_credentials(self):
        """Verify that Flask global error handler redacts sensitive connection details in debug mode responses."""
        from unittest.mock import patch
        from config import Settings
        
        mock_settings = Settings(
            odoo_url="https://bonario-vietnam.odoo.com",
            odoo_db="bonario_db_name",
            odoo_user_id=424242,
            odoo_api_key="shh_super_secret_api_key_123",
            default_project_id=1035,
            port=5056,
            debug=True
        )
        
        with patch('app.get_settings', return_value=mock_settings), patch('config.get_settings', return_value=mock_settings):
            debug_app = create_app()

        @debug_app.get("/trigger-odoo-error")
        def trigger_odoo_error():
            raise OdooAPIError("Odoo connection failed: url is https://bonario-vietnam.odoo.com db is bonario_db_name key is shh_super_secret_api_key_123 user is 424242", model="sale.order", method="search_read")

        @debug_app.get("/trigger-general-error")
        def trigger_general_error():
            raise Exception("Unexpected failure on server bonario-vietnam.odoo.com database bonario_db_name key shh_super_secret_api_key_123 user 424242")
        
        client = debug_app.test_client()

        # Test OdooAPIError handling
        response = client.get("/trigger-odoo-error")
        self.assertEqual(response.status_code, 502)
        data = json.loads(response.data)
        self.assertFalse(data["ok"])
        
        err_msg = data["error"]
        self.assertNotIn("bonario-vietnam.odoo.com", err_msg)
        self.assertNotIn("bonario_db_name", err_msg)
        self.assertNotIn("shh_super_secret_api_key_123", err_msg)
        self.assertNotIn("424242", err_msg)
        self.assertIn("********", err_msg)

        # Test unexpected Exception handling
        response = client.get("/trigger-general-error")
        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertFalse(data["ok"])
        
        err_msg = data["error"]
        self.assertNotIn("bonario-vietnam.odoo.com", err_msg)
        self.assertNotIn("bonario_db_name", err_msg)
        self.assertNotIn("shh_super_secret_api_key_123", err_msg)
        self.assertNotIn("424242", err_msg)
        self.assertIn("********", err_msg)


if __name__ == "__main__":
    unittest.main()
