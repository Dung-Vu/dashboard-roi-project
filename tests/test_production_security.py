from __future__ import annotations

from datetime import timedelta
import os
import unittest
from unittest.mock import MagicMock, patch
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Settings, is_odoo_prod_blocked
from odoo_client import OdooAPI, ProdBlockedError, PROD_HOST, PROD_DB


class TestProductionSecurity(unittest.TestCase):
    def _make_settings(
        self,
        *,
        debug: bool = False,
        behind_proxy: bool = False,
        odoo_block_prod: bool = False,
    ) -> Settings:
        return Settings(
            odoo_url="https://test.odoo.example.com",
            odoo_db="test_odoo_db",
            odoo_user_id=208,
            odoo_api_key="synthetic_secret_key_abc123",
            default_project_id=1035,
            port=5056,
            debug=debug,
            dashboard_username="admin",
            dashboard_password="pwd",
            secret_key="synthetic_flask_secret_key",
            behind_proxy=behind_proxy,
            odoo_block_prod=odoo_block_prod,
        )

    def test_session_cookie_secure_when_debug_false(self):
        """Verify that SESSION_COOKIE_SECURE is True when debug is disabled and lifetime is 12h."""
        mock_settings = self._make_settings(debug=False)
        with patch("app.get_settings", return_value=mock_settings):
            from app import create_app
            app = create_app()
            self.assertTrue(app.config["SESSION_COOKIE_SECURE"])
            self.assertEqual(app.config["PERMANENT_SESSION_LIFETIME"], timedelta(hours=12))

    def test_session_cookie_secure_when_debug_true(self):
        """Verify that SESSION_COOKIE_SECURE is False when debug is enabled."""
        mock_settings = self._make_settings(debug=True)
        with patch.dict(os.environ, {"FLASK_ENV": "development"}, clear=False):
            with patch("app.get_settings", return_value=mock_settings):
                from app import create_app
                app = create_app()
                self.assertFalse(app.config["SESSION_COOKIE_SECURE"])

    def test_require_auth_enforced_when_testing_not_set(self):
        """SEC-02: Without TESTING=True, protected endpoints must return 401 even under pytest/unittest."""
        mock_settings = self._make_settings(debug=False)
        with patch("app.get_settings", return_value=mock_settings):
            from app import create_app
            app = create_app()
            # Explicitly do NOT set app.config["TESTING"] = True
            client = app.test_client()

            resp1 = client.get("/api/projects-dashboard")
            self.assertEqual(resp1.status_code, 401)

            resp2 = client.get("/api/shipping/unassigned")
            self.assertEqual(resp2.status_code, 401)

            resp3 = client.post(
                "/api/projects-dashboard/update-giai-trinh",
                json={"project_id": 10, "x_studio_giai_trinh": "test"},
            )
            self.assertEqual(resp3.status_code, 401)

    def test_proxy_fix_disabled_by_default_prevents_xff_spoofing(self):
        """G-02: By default (BEHIND_PROXY=0), ProxyFix is NOT applied and X-Forwarded-For is ignored."""
        mock_settings = self._make_settings(debug=True, behind_proxy=False)
        with patch.dict(os.environ, {"BEHIND_PROXY": "0"}, clear=False):
            with patch("app.get_settings", return_value=mock_settings):
                from app import create_app
                app = create_app()
                self.assertNotIsInstance(app.wsgi_app, ProxyFix)

                app.config["TESTING"] = True
                client = app.test_client()

                @app.route("/test-ip-no-proxy")
                def test_ip_no_proxy():
                    from flask import request
                    return {"remote_addr": request.remote_addr}

                response = client.get(
                    "/test-ip-no-proxy",
                    headers={"X-Forwarded-For": "203.0.113.195"},
                )
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertNotEqual(data["remote_addr"], "203.0.113.195")

    def test_proxy_fix_applied_when_behind_proxy_enabled(self):
        """G-02: Verify that ProxyFix is applied only when BEHIND_PROXY=1 / behind_proxy=True."""
        mock_settings = self._make_settings(debug=True, behind_proxy=True)
        with patch.dict(os.environ, {"BEHIND_PROXY": "1"}, clear=False):
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

                response = client.get(
                    "/test-ip-resolving",
                    headers={"X-Forwarded-For": "203.0.113.195"},
                )
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertEqual(data["remote_addr"], "203.0.113.195")

    def test_odoo_prod_allowed_by_default_when_env_unset(self):
        """Item 1: Without ODOO_BLOCK_PROD in env, OdooAPI with prod URL/db does NOT raise (HTTP mocked)."""
        env_without_block = {k: v for k, v in os.environ.items() if k != "ODOO_BLOCK_PROD"}
        with patch.dict(os.environ, env_without_block, clear=True):
            self.assertFalse(is_odoo_prod_blocked())
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": [{"id": 208, "name": "User"}]}
            with patch("requests.Session.post", return_value=mock_resp) as mock_post:
                api = OdooAPI(
                    url=f"https://{PROD_HOST}",
                    db=PROD_DB,
                    user_id=208,
                    api_key="synthetic_key",
                )
                res = api.call_method("res.users", "search_read", [[["id", "=", 208]]], {"fields": ["name"]})
                self.assertEqual(res, [{"id": 208, "name": "User"}])
                mock_post.assert_called_once()

    def test_odoo_block_prod_guard(self):
        """Item 1: ODOO_BLOCK_PROD=1 blocks PROD_HOST and PROD_DB with ProdBlockedError('PROD BLOCKED')."""
        with patch.dict(os.environ, {"ODOO_BLOCK_PROD": "1"}, clear=False):
            self.assertTrue(is_odoo_prod_blocked())
            with self.assertRaises(ProdBlockedError) as ctx_url:
                OdooAPI(
                    url=f"https://{PROD_HOST}",
                    db="safe_db",
                    user_id=208,
                    api_key="synthetic_key",
                )
            self.assertEqual(str(ctx_url.exception), "PROD BLOCKED")

            with self.assertRaises(ProdBlockedError) as ctx_db:
                OdooAPI(
                    url="https://test.odoo.example.com",
                    db=PROD_DB,
                    user_id=208,
                    api_key="synthetic_key",
                )
            self.assertEqual(str(ctx_db.exception), "PROD BLOCKED")

    def test_pytest_default_env_blocks_prod(self):
        """Item 1: Running inside tests/ (conftest.py) has ODOO_BLOCK_PROD=1 active by default and blocks prod."""
        self.assertEqual(os.environ.get("ODOO_BLOCK_PROD"), "1")
        self.assertTrue(is_odoo_prod_blocked())
        with self.assertRaises(ProdBlockedError):
            OdooAPI(
                url=f"https://{PROD_HOST}",
                db=PROD_DB,
                user_id=208,
                api_key="synthetic_key",
            )

    def test_odoo_client_sanitize_redacts_3_digit_uid_and_credentials(self):
        """Verify OdooAPI._sanitize redacts 3-digit user_id (e.g. 208), api_key, db, and hostname."""
        api = OdooAPI(
            url="https://test.odoo.example.com",
            db="test_odoo_db",
            user_id=208,
            api_key="synthetic_secret_key_abc123",
        )
        raw = "Error for user 208 on db test_odoo_db at test.odoo.example.com with key synthetic_secret_key_abc123"
        sanitized = api._sanitize(raw)
        self.assertNotIn("208", sanitized)
        self.assertNotIn("test_odoo_db", sanitized)
        self.assertNotIn("test.odoo.example.com", sanitized)
        self.assertNotIn("synthetic_secret_key_abc123", sanitized)
        self.assertIn("********", sanitized)

    def test_value_error_handler_sanitizes_sensitive_info(self):
        """G-02: @app.errorhandler(ValueError) must pass through _sanitize_error_message."""
        mock_settings = self._make_settings(debug=True)
        with patch("app.get_settings", return_value=mock_settings):
            from app import create_app
            app = create_app()
            app.config["TESTING"] = True

            @app.get("/trigger-value-error")
            def trigger_value_error():
                raise ValueError(
                    "Invalid value for db test_odoo_db user 208 key synthetic_secret_key_abc123 at https://test.odoo.example.com"
                )

            client = app.test_client()
            resp = client.get("/trigger-value-error")
            self.assertEqual(resp.status_code, 400)
            payload = resp.get_json()
            self.assertFalse(payload["ok"])
            self.assertNotIn("test_odoo_db", payload["error"])
            self.assertNotIn("208", payload["error"])
            self.assertNotIn("synthetic_secret_key_abc123", payload["error"])
            self.assertNotIn("test.odoo.example.com", payload["error"])

    def test_update_giai_trinh_validation_and_502_on_failure(self):
        """G-02: Strict validation on update-giai-trinh and 502 when service returns False."""
        mock_settings = self._make_settings(debug=False)
        with patch("app.get_settings", return_value=mock_settings):
            from app import create_app
            with patch("app.DashboardService") as mock_service_cls:
                mock_service = MagicMock()
                mock_service_cls.return_value = mock_service
                app = create_app()
                app.config["TESTING"] = True
                client = app.test_client()

                # Reject boolean project_id
                resp_bool = client.post(
                    "/api/projects-dashboard/update-giai-trinh",
                    json={"project_id": True, "x_studio_giai_trinh": "note"},
                )
                self.assertEqual(resp_bool.status_code, 400)

                # Reject non-numeric project_id
                resp_str = client.post(
                    "/api/projects-dashboard/update-giai-trinh",
                    json={"project_id": "abc", "x_studio_giai_trinh": "note"},
                )
                self.assertEqual(resp_str.status_code, 400)

                # Reject non-string x_studio_giai_trinh
                resp_non_str = client.post(
                    "/api/projects-dashboard/update-giai-trinh",
                    json={"project_id": 123, "x_studio_giai_trinh": ["invalid"]},
                )
                self.assertEqual(resp_non_str.status_code, 400)

                # Reject overly long x_studio_giai_trinh (> 5000 chars)
                resp_long = client.post(
                    "/api/projects-dashboard/update-giai-trinh",
                    json={"project_id": 123, "x_studio_giai_trinh": "x" * 5001},
                )
                self.assertEqual(resp_long.status_code, 400)

                # Service returns False -> 502
                mock_service.update_project_giai_trinh.return_value = False
                resp_fail = client.post(
                    "/api/projects-dashboard/update-giai-trinh",
                    json={"project_id": 123, "x_studio_giai_trinh": "valid note"},
                )
                self.assertEqual(resp_fail.status_code, 502)

                # Service returns True -> 200
                mock_service.update_project_giai_trinh.return_value = True
                resp_ok = client.post(
                    "/api/projects-dashboard/update-giai-trinh",
                    json={"project_id": "123", "x_studio_giai_trinh": "valid note"},
                )
                self.assertEqual(resp_ok.status_code, 200)
                self.assertTrue(resp_ok.get_json()["ok"])

    def test_shipping_unassigned_json_and_csv(self):
        """G-02: Verify GET /api/shipping/unassigned supports JSON and UTF-8-SIG CSV export."""
        mock_settings = self._make_settings(debug=False)
        with patch("app.get_settings", return_value=mock_settings):
            from app import create_app
            with patch("app.DashboardService") as mock_service_cls:
                mock_service = MagicMock()
                mock_service.get_unassigned_shipping_items.return_value = {
                    "ok": True,
                    "date_from": "2026-01-01",
                    "company": "all",
                    "count": 1,
                    "total_amount": 250000.0,
                    "items": [
                        {
                            "date": "2026-02-15",
                            "move_name": "BILL/2026/02/0001",
                            "ref": "SHIP-01",
                            "partner_name": "Viettel Post",
                            "name": "Chi phí vận chuyển",
                            "amount": 250000.0,
                            "shipping_account_id": 1519,
                            "shipping_account_name": "SC - Logistics OPS",
                            "company_name": "Bonario",
                            "is_po": False,
                        }
                    ],
                }
                mock_service_cls.return_value = mock_service
                app = create_app()
                app.config["TESTING"] = True
                client = app.test_client()

                resp_json = client.get("/api/shipping/unassigned?date_from=2026-01-01&company=all")
                self.assertEqual(resp_json.status_code, 200)
                data = resp_json.get_json()
                self.assertTrue(data["ok"])
                self.assertEqual(data["count"], 1)

                resp_csv = client.get("/api/shipping/unassigned?date_from=2026-01-01&company=all&format=csv")
                self.assertEqual(resp_csv.status_code, 200)
                self.assertTrue(resp_csv.data.startswith(b"\xef\xbb\xbf"))
                csv_text = resp_csv.data.decode("utf-8-sig")
                self.assertIn(
                    "date,move_name,ref,partner_name,name,amount,shipping_account_id,shipping_account_name,company_name,is_po",
                    csv_text,
                )
                self.assertIn("BILL/2026/02/0001", csv_text)


if __name__ == "__main__":
    unittest.main()

