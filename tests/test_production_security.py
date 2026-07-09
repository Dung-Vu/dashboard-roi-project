from __future__ import annotations

import os
import unittest
from unittest.mock import patch
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Settings


def _make_settings(**overrides):
    base = dict(
        odoo_url="http://mock",
        odoo_db="db",
        odoo_user_id=1,
        odoo_api_key="key",
        default_project_id=1035,
        port=5056,
        debug=False,
        dashboard_username="admin",
        dashboard_password="pwd",
        secret_key="secret",
    )
    base.update(overrides)
    return Settings(**base)


class TestProductionSecurity(unittest.TestCase):
    def test_session_cookie_secure_only_when_flask_env_production(self):
        """Secure cookie flag must only be set when FLASK_ENV=production (allows LAN HTTP)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FLASK_ENV", None)
            os.environ.pop("DASHBOARD_COOKIE_SECURE", None)
            with patch("app.get_settings", return_value=_make_settings(debug=False)):
                from app import create_app
                app = create_app()
                self.assertFalse(app.config["SESSION_COOKIE_SECURE"])

    def test_session_cookie_secure_when_flask_env_production(self):
        with patch.dict(os.environ, {"FLASK_ENV": "production"}, clear=False):
            os.environ.pop("DASHBOARD_COOKIE_SECURE", None)
            with patch("app.get_settings", return_value=_make_settings(debug=False)):
                from app import create_app
                app = create_app()
                self.assertTrue(app.config["SESSION_COOKIE_SECURE"])

    def test_cookie_secure_env_override_forces_secure(self):
        with patch.dict(os.environ, {"DASHBOARD_COOKIE_SECURE": "1"}, clear=False):
            os.environ.pop("FLASK_ENV", None)
            with patch("app.get_settings", return_value=_make_settings(debug=True)):
                from app import create_app
                app = create_app()
                self.assertTrue(app.config["SESSION_COOKIE_SECURE"])

    def test_cookie_secure_env_override_disables_secure(self):
        with patch.dict(os.environ, {"DASHBOARD_COOKIE_SECURE": "0"}, clear=False):
            os.environ["FLASK_ENV"] = "production"
            with patch("app.get_settings", return_value=_make_settings(debug=False)):
                from app import create_app
                app = create_app()
                self.assertFalse(app.config["SESSION_COOKIE_SECURE"])

    def test_session_cookie_secure_when_debug_true(self):
        """Verify that SESSION_COOKIE_SECURE is False when debug is enabled (and no production env)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FLASK_ENV", None)
            os.environ.pop("DASHBOARD_COOKIE_SECURE", None)
            with patch("app.get_settings", return_value=_make_settings(debug=True)):
                from app import create_app
                app = create_app()
                self.assertFalse(app.config["SESSION_COOKIE_SECURE"])

    def test_proxy_fix_applied_and_resolves_ip(self):
        """Verify that ProxyFix is applied to wsgi_app and correctly resolves real client IP."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FLASK_ENV", None)
            os.environ.pop("DASHBOARD_COOKIE_SECURE", None)
            with patch("app.get_settings", return_value=_make_settings(debug=True)):
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
