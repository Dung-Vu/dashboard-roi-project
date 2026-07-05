from __future__ import annotations

import os
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import create_app, LoginRateLimiter
from cache import PersistentCache
from config import Settings
from odoo_client import OdooAPIError


class TestAuditorVerification(unittest.TestCase):
    def setUp(self):
        # Setup a temporary DB for tests
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)
        self.db_path = Path(self.temp_db_path)

    def tearDown(self):
        if self.db_path.exists():
            try:
                os.remove(self.temp_db_path)
            except Exception:
                pass

    def test_login_rate_limiter_expiry_cleanup(self):
        """Test that LoginRateLimiter deletes records older than period when checking rate limiting."""
        limiter = LoginRateLimiter(max_attempts=3, period=1, db_path=self.db_path)
        ip = "192.168.1.100"

        # Record 3 attempts
        limiter.record_failed_attempt(ip)
        limiter.record_failed_attempt(ip)
        limiter.record_failed_attempt(ip)

        # Should be rate limited now
        self.assertTrue(limiter.is_rate_limited(ip))

        # Wait for period (1s) to expire
        time.sleep(1.1)

        # Should no longer be rate limited
        self.assertFalse(limiter.is_rate_limited(ip))

    def test_persistent_cache_cleanup_expired(self):
        """Test that cleanup_expired deletes entries older than TTL."""
        cache = PersistentCache(db_path=self.db_path, ttl=1)
        cache.set("key1", {"data": "val1"})
        
        # Immediate get works
        self.assertEqual(cache.get("key1"), {"data": "val1"})

        # Wait for TTL to expire
        time.sleep(1.1)

        # get returns None because it's expired
        self.assertIsNone(cache.get("key1"))

        # Add another key and run cleanup_expired
        cache.set("key2", {"data": "val2"})
        # We simulate that key1 is expired and key2 is fresh.
        # Check that cleanup_expired removes key1 from the database.
        cache.cleanup_expired()
        
        # Verify in database directly
        import sqlite3
        import contextlib
        with contextlib.closing(sqlite3.connect(str(self.db_path))) as conn:
            rows = conn.execute("SELECT key FROM cache").fetchall()
            keys = [r[0] for r in rows]
            self.assertIn("key2", keys)
            self.assertNotIn("key1", keys)

    def test_sanitize_error_message_removes_secrets(self):
        """Test that _sanitize_error_message filters out Odoo API key and DB name from OdooAPIError responses when debug is True."""
        mock_settings = Settings(
            odoo_url="https://secret-domain.odoo.com",
            odoo_db="super_secret_db",
            odoo_user_id=123,
            odoo_api_key="super_secret_api_key_xyz",
            default_project_id=1035,
            port=5056,
            debug=True,  # must be True for error details to show
            dashboard_username="admin",
            dashboard_password="pwd",
            secret_key="secret"
        )
        
        with patch("app.get_settings", return_value=mock_settings):
            app = create_app()
            app.config["TESTING"] = True
            client = app.test_client()

            @app.route("/test-error-endpoint")
            def trigger_error():
                raise OdooAPIError(
                    "Error occurred on https://secret-domain.odoo.com database super_secret_db using key super_secret_api_key_xyz",
                    model="sale.order",
                    method="search_read"
                )

            response = client.get("/test-error-endpoint")
            self.assertEqual(response.status_code, 502)
            data = response.get_json()
            
            error_msg = data.get("error", "")
            self.assertNotIn("secret-domain", error_msg)
            self.assertNotIn("super_secret_db", error_msg)
            self.assertNotIn("super_secret_api_key_xyz", error_msg)
            self.assertIn("********", error_msg)


if __name__ == "__main__":
    unittest.main()
