from __future__ import annotations

import contextlib
import csv
import hmac
import io
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, redirect, request, send_from_directory, session
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from cache import CACHE_DB_PATH
from config import Settings, get_settings
from dashboard_service import DashboardService
from odoo_client import OdooAPI, OdooAPIError


BASE_DIR = Path(__file__).resolve().parent


def _validate_date_param(date_from: str) -> str:
    if not isinstance(date_from, str):
        raise ValueError("date_from must use YYYY-MM-DD format.")
    cleaned = date_from.strip()
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError("date_from must use YYYY-MM-DD format.") from exc


def _sanitize_error_message(message: Any, settings: Settings | None = None) -> str:
    if message is None:
        return ""
    text = str(message)
    if not text:
        return text

    if settings is None:
        try:
            settings = get_settings()
        except Exception:
            return text

    sensitive_terms: list[str] = []
    if getattr(settings, "odoo_url", None):
        sensitive_terms.append(settings.odoo_url)
        try:
            parsed = urlparse(settings.odoo_url)
            if parsed.netloc:
                sensitive_terms.append(parsed.netloc)
            if parsed.hostname:
                sensitive_terms.append(parsed.hostname)
                parts = parsed.hostname.split(".")
                if len(parts) > 1 and len(parts[0]) >= 3:
                    sensitive_terms.append(parts[0])
        except Exception:
            pass
    if getattr(settings, "odoo_db", None):
        sensitive_terms.append(str(settings.odoo_db))
    if getattr(settings, "odoo_api_key", None):
        sensitive_terms.append(str(settings.odoo_api_key))

    uid_val = getattr(settings, "odoo_user_id", None)
    short_uid: str | None = None
    if uid_val is not None and str(uid_val):
        uid_str = str(uid_val)
        if len(uid_str) >= 3:
            sensitive_terms.append(uid_str)
        else:
            short_uid = uid_str

    unique_terms = sorted(
        {term for term in sensitive_terms if term and len(term) > 2},
        key=len,
        reverse=True,
    )
    for term in unique_terms:
        if term.isalnum() or re.match(r"^\w+$", term):
            text = re.sub(rf"\b{re.escape(term)}\b", "********", text)
        else:
            text = text.replace(term, "********")
    if short_uid:
        text = re.sub(rf"\b{re.escape(short_uid)}\b", "********", text)
    return text


class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, period: int = 300, db_path: Path | None = None):
        self.max_attempts = max_attempts
        self.period = period
        self.db_path = db_path or CACHE_DB_PATH
        self.lock = Lock()
        self._init_db()

    def _init_db(self):
        with self.lock:
            with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS login_attempts (
                        ip TEXT,
                        timestamp REAL
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_ip_ts ON login_attempts(ip, timestamp)")
                conn.commit()

    def is_rate_limited(self, ip: str) -> bool:
        with self.lock:
            now = time.time()
            cutoff = now - self.period
            with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                # Clean up old attempts
                conn.execute("DELETE FROM login_attempts WHERE timestamp < ?", (cutoff,))
                conn.commit()
                # Count current attempts
                row = conn.execute(
                    "SELECT COUNT(*) FROM login_attempts WHERE ip = ? AND timestamp >= ?",
                    (ip, cutoff)
                ).fetchone()
                count = row[0] if row else 0
                return count >= self.max_attempts

    def record_failed_attempt(self, ip: str):
        with self.lock:
            now = time.time()
            with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                conn.execute(
                    "INSERT INTO login_attempts (ip, timestamp) VALUES (?, ?)",
                    (ip, now)
                )
                conn.commit()


def create_app() -> Flask:
    settings = get_settings()
    limiter = LoginRateLimiter()

    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = OdooAPI(
        settings.odoo_url,
        settings.odoo_db,
        settings.odoo_user_id,
        settings.odoo_api_key,
    )
    service = DashboardService(client)

    app = Flask(__name__)
    if getattr(settings, "behind_proxy", False) or os.getenv("BEHIND_PROXY", "0") == "1":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    app.secret_key = settings.secret_key

    session_secure = not settings.debug or os.getenv("FLASK_ENV") == "production"

    app.config.update(
        SESSION_COOKIE_SECURE=session_secure,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    )

    if (
        not app.testing
        and not app.config.get("TESTING")
        and "unittest" not in sys.modules
        and "pytest" not in sys.modules
        and os.environ.get("DISABLE_WARMER") != "1"
    ):
        service.start_background_warmer(interval_seconds=900)

    def require_auth(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if app.testing or app.config.get("TESTING") is True:
                return f(*args, **kwargs)
            if not session.get("authenticated"):
                return jsonify({"ok": False, "error": "Unauthorized"}), 401
            return f(*args, **kwargs)
        return decorated

    @app.post("/api/login")
    def login():
        ip = request.remote_addr or "unknown"
        if limiter.is_rate_limited(ip):
            return jsonify({"ok": False, "error": "Quá nhiều lần thử đăng nhập thất bại. Vui lòng thử lại sau 5 phút."}), 429

        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            limiter.record_failed_attempt(ip)
            return jsonify({"ok": False, "error": "Sai tên đăng nhập hoặc mật khẩu"}), 401

        username = body.get("username", "")
        password = body.get("password", "")
        if not isinstance(username, str) or not isinstance(password, str):
            limiter.record_failed_attempt(ip)
            return jsonify({"ok": False, "error": "Sai tên đăng nhập hoặc mật khẩu"}), 401

        expected_user = (settings.dashboard_username or "").lower().encode("utf-8")
        actual_user = username.lower().encode("utf-8")
        expected_pass = (settings.dashboard_password or "").encode("utf-8")
        actual_pass = password.encode("utf-8")

        user_ok = hmac.compare_digest(actual_user, expected_user)
        pass_ok = hmac.compare_digest(actual_pass, expected_pass)
        if user_ok and pass_ok:
            session.permanent = True
            session["authenticated"] = True
            return jsonify({"ok": True})

        limiter.record_failed_attempt(ip)
        return jsonify({"ok": False, "error": "Sai tên đăng nhập hoặc mật khẩu"}), 401

    @app.post("/api/logout")
    def logout():
        session.pop("authenticated", None)
        return jsonify({"ok": True})

    @app.get("/api/auth-status")
    def auth_status():
        return jsonify({"authenticated": bool(session.get("authenticated"))})

    @app.get("/")
    def index():
        response = send_from_directory(BASE_DIR, "index.html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.get("/styles.css")
    def styles():
        response = send_from_directory(BASE_DIR, "styles.css")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.get("/app.js")
    def javascript():
        response = send_from_directory(BASE_DIR, "app.js")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.get("/assets/<path:filename>")
    def serve_assets(filename):
        response = send_from_directory(BASE_DIR / "assets", filename)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.get("/favicon.ico")
    def favicon():
        return send_from_directory(BASE_DIR / "assets", "favicon.png")

    @app.get("/api/health")
    @require_auth
    def health():
        odoo_health = service.test_connection()
        return jsonify(
            {
                "ok": True,
                "default_project_id": settings.default_project_id,
                "odoo": {"ok": bool(odoo_health.get("ok"))},
            }
        )

    @app.get("/api/dashboard")
    @require_auth
    def dashboard():
        project_id = request.args.get("project_id", default=settings.default_project_id, type=int)
        payload = service.build_project_dashboard(project_id)
        return jsonify(payload)

    @app.get("/api/projects-dashboard")
    @require_auth
    def projects_dashboard():
        date_from = request.args.get("date_from", default="2026-01-01", type=str)
        date_from = _validate_date_param(date_from)
        company = request.args.get("company", default="all", type=str)
        refresh = request.args.get("refresh", default="0") == "1"
        payload = service.build_projects_dashboard(date_from, company=company, refresh=refresh)
        return jsonify(payload)

    @app.post("/api/projects-dashboard/update-giai-trinh")
    @require_auth
    def update_giai_trinh():
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return jsonify({"ok": False, "error": "Invalid JSON body"}), 400

        raw_project_id = body.get("project_id")
        if raw_project_id is None or isinstance(raw_project_id, bool):
            return jsonify({"ok": False, "error": "project_id must be a positive integer"}), 400
        if isinstance(raw_project_id, int):
            project_id = raw_project_id
        elif isinstance(raw_project_id, str) and raw_project_id.strip().isdigit():
            project_id = int(raw_project_id.strip())
        else:
            return jsonify({"ok": False, "error": "project_id must be a positive integer"}), 400
        if project_id <= 0:
            return jsonify({"ok": False, "error": "project_id must be a positive integer"}), 400

        giai_trinh = body.get("x_studio_giai_trinh", "")
        if giai_trinh is None:
            giai_trinh = ""
        if not isinstance(giai_trinh, str):
            return jsonify({"ok": False, "error": "x_studio_giai_trinh must be a string"}), 400
        if len(giai_trinh) > 5000:
            return jsonify({"ok": False, "error": "x_studio_giai_trinh exceeds maximum length of 5000 characters"}), 400

        success = service.update_project_giai_trinh(project_id, giai_trinh)
        if not success:
            return jsonify({"ok": False, "error": "Failed to update project in Odoo"}), 502
        return jsonify({"ok": True})

    @app.get("/api/projects-dashboard/delta")
    @require_auth
    def projects_dashboard_delta():
        last_sync = request.args.get("last_sync", default="", type=str)
        company = request.args.get("company", default="all", type=str)
        date_from = request.args.get("date_from", default="2026-01-01", type=str)
        date_from = _validate_date_param(date_from)
        payload = service.get_delta_updates(last_sync, company_key=company, date_from=date_from)
        return jsonify(payload)

    @app.get("/api/shipping/unassigned")
    @require_auth
    def shipping_unassigned():
        date_from = request.args.get("date_from", "2026-01-01")
        date_from = _validate_date_param(date_from)
        company = request.args.get("company", "all")
        output_format = request.args.get("format", "json").strip().lower()
        if hasattr(service, "get_unassigned_shipping_items"):
            result = service.get_unassigned_shipping_items(date_from=date_from, company=company)
        else:
            result = {
                "ok": True,
                "date_from": date_from,
                "company": company,
                "count": 0,
                "total_amount": 0.0,
                "items": [],
            }
        if output_format == "csv":
            fieldnames = [
                "date",
                "move_name",
                "ref",
                "partner_name",
                "name",
                "amount",
                "shipping_account_id",
                "shipping_account_name",
                "company_name",
                "is_po",
            ]
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for item in result.get("items", []):
                if isinstance(item, dict):
                    writer.writerow({col: item.get(col, "") for col in fieldnames})
            csv_bytes = buf.getvalue().encode("utf-8-sig")
            return Response(
                csv_bytes,
                status=200,
                mimetype="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="unassigned_shipping_{date_from}.csv"'
                },
            )
        return jsonify(result)

    @app.get("/api/redirect/sale-order/<int:so_id>")
    @require_auth
    def redirect_to_sale_order(so_id):
        current_settings = get_settings()
        url = f"{current_settings.odoo_url.rstrip('/')}/web#id={so_id}&model=sale.order&view_type=form"
        return redirect(url, code=302)

    @app.errorhandler(ValueError)
    def handle_value_error(error: ValueError):
        return jsonify({"ok": False, "error": _sanitize_error_message(error, settings)}), 400

    @app.errorhandler(OdooAPIError)
    def handle_odoo_error(error: OdooAPIError):
        app.logger.error(f"OdooAPIError occurred: {error} (model: {error.model}, method: {error.method})", exc_info=True)
        payload = {
            "ok": False,
            "error": "Cannot load dashboard data from Odoo",
        }
        if settings.debug:
            payload.update(
                {
                    "error": _sanitize_error_message(str(error), settings),
                    "model": _sanitize_error_message(error.model, settings),
                    "method": _sanitize_error_message(error.method, settings),
                }
            )
        return (
            jsonify(payload),
            502,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        if isinstance(error, HTTPException):
            return error
        app.logger.exception("Unhandled error")
        message = _sanitize_error_message(str(error), settings) if settings.debug else "Internal server error"
        return jsonify({"ok": False, "error": message}), 500

    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    app.run(host="0.0.0.0", port=settings.port, debug=settings.debug)

