from __future__ import annotations

import unittest
from unittest.mock import patch
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Settings


class TestProductionSecurity(unittest.TestCase):
    def test_session_cookie_secure_when_debug_false(self):
        """Verify that SESSION_COOKIE_SECURE is True when debug is disabled."""
        mock_settings = Settings(
            odoo_url="http://mock",
            odoo_db="db",
            odoo_user_id=1,
            odoo_api_key="key",
            default_project_id=1035,
            port=5056,
            debug=False,
            dashboard_username="admin",
            dashboard_password="pwd",
            secret_key="secret"
        )
        with patch("app.get_settings", return_value=mock_settings):
            from app import create_app
            app = create_app()
            self.assertTrue(app.config["SESSION_COOKIE_SECURE"])

    def test_session_cookie_secure_when_debug_true(self):
        """Verify that SESSION_COOKIE_SECURE is False when debug is enabled."""
        mock_settings = Settings(
            odoo_url="http://mock",
            odoo_db="db",
            odoo_user_id=1,
            odoo_api_key="key",
            default_project_id=1035,
            port=5056,
            debug=True,
            dashboard_username="admin",
            dashboard_password="pwd",
            secret_key="secret"
        )
        with patch("app.get_settings", return_value=mock_settings):
            from app import create_app
            app = create_app()
            self.assertFalse(app.config["SESSION_COOKIE_SECURE"])

    def test_proxy_fix_applied_and_resolves_ip(self):
        """Verify that ProxyFix is applied to wsgi_app and correctly resolves real client IP."""
        mock_settings = Settings(
            odoo_url="http://mock",
            odoo_db="db",
            odoo_user_id=1,
            odoo_api_key="key",
            default_project_id=1035,
            port=5056,
            debug=True,
            dashboard_username="admin",
            dashboard_password="pwd",
            secret_key="secret"
        )
        with patch("app.get_settings", return_value=mock_settings):
            from app import create_app
            app = create_app()
            self.assertIsInstance(app.wsgi_app, ProxyFix)

            app.config["TESTING"] = True
            client = app.test_client()

            @app.route("/test-ip-resolving")
            def test_ip_resolving():
                from flask import request
                return {"remote_addr": request.remote_addr}

            # With ProxyFix configured with x_for=1, X-Forwarded-For: client, proxy1, proxy2
            # resolves request.remote_addr to client or proxy2 depending on setting.
            # Here, x_for=1 means it takes 1 proxy into account. So X-Forwarded-For: 203.0.113.195
            # gets resolved as the remote client IP.
            response = client.get("/test-ip-resolving", headers={"X-Forwarded-For": "203.0.113.195"})
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertEqual(data["remote_addr"], "203.0.113.195")


if __name__ == "__main__":
    unittest.main()
