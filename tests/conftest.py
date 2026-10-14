"""Global pytest/unittest guard to block any network or RPC call to Odoo production."""
from __future__ import annotations

import os
from pathlib import Path
import pytest
import requests

from config import is_odoo_prod_blocked
from odoo_client import PROD_DB, PROD_HOST, ProdBlockedError

# Ignore standalone live investigation scripts during test discovery
collect_ignore = [
    "investigate_shipping.py",
    "investigate_shipping_detail.py",
    "survey_shipping_master.py",
    "verify_shipping_fix.py",
]

# Pre-populate safe test environment variables BEFORE config.py runs load_dotenv()
Path("/tmp/roi_recon").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("ODOO_BLOCK_PROD", "1")
if PROD_HOST in os.environ.get("ODOO_URL", "").lower() or not os.environ.get("ODOO_URL"):
    os.environ["ODOO_URL"] = "https://testing1210-2.odoo.com"
if os.environ.get("ODOO_DB", "").strip().lower() == PROD_DB or not os.environ.get("ODOO_DB"):
    os.environ["ODOO_DB"] = "testing1210-2"
os.environ.setdefault("ODOO_USER_ID", "208")
os.environ.setdefault("ODOO_API_KEY", "synthetic-test-api-key")
os.environ.setdefault("DASHBOARD_USERNAME", "bonario")
os.environ.setdefault("DASHBOARD_PASSWORD", "synthetic-test-password")
os.environ.setdefault("SECRET_KEY", "synthetic-test-secret-key-0123456789")
os.environ.setdefault("CACHE_DB_PATH", "/tmp/roi_recon/pytest_cache.db")


def _assert_not_prod(url: str | None = None, db: str | None = None) -> None:
    check_url = (url or "").strip().lower()
    check_db = (db or "").strip().lower()
    if PROD_HOST in check_url or check_db == PROD_DB:
        raise ProdBlockedError("PROD BLOCKED")


_orig_session_request = requests.Session.request


def _guarded_session_request(self, method, url, *args, **kwargs):
    if is_odoo_prod_blocked():
        _assert_not_prod(str(url))
    return _orig_session_request(self, method, url, *args, **kwargs)


requests.Session.request = _guarded_session_request

_orig_session_send = requests.Session.send


def _guarded_session_send(self, request, *args, **kwargs):
    if is_odoo_prod_blocked():
        _assert_not_prod(str(getattr(request, "url", "")))
    return _orig_session_send(self, request, *args, **kwargs)


requests.Session.send = _guarded_session_send


def pytest_collection_modifyitems(session, config, items):
    # Ensure test_stress_performance uses /tmp so it doesn't pollute repo or fail in read-only sandbox
    import sys
    if "tests.test_stress_performance" in sys.modules:
        mod = sys.modules["tests.test_stress_performance"]
        mod.STRESS_CACHE_DB = Path("/tmp/roi_recon/stress_cache.db")
    os.environ["CACHE_DB_PATH"] = "/tmp/roi_recon/pytest_cache.db"


@pytest.fixture(autouse=True)
def _enforce_prod_block_env(monkeypatch):
    monkeypatch.setenv("ODOO_BLOCK_PROD", "1")
    env_url = os.environ.get("ODOO_URL", "")
    env_db = os.environ.get("ODOO_DB", "")
    if PROD_HOST in env_url.lower() or env_db.strip().lower() == PROD_DB:
        monkeypatch.setenv("ODOO_URL", "https://testing1210-2.odoo.com")
        monkeypatch.setenv("ODOO_DB", "testing1210-2")
