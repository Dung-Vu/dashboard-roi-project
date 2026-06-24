from __future__ import annotations

import logging
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, redirect, session
from werkzeug.exceptions import HTTPException

from config import get_settings
from dashboard_service import DashboardService
from odoo_client import OdooAPI, OdooAPIError


BASE_DIR = Path(__file__).resolve().parent


def create_app() -> Flask:
    settings = get_settings()

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
    app.secret_key = settings.secret_key

    def require_auth(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            import sys
            if app.testing or app.config.get("TESTING") or "unittest" in sys.modules or "pytest" in sys.modules:
                return f(*args, **kwargs)
            if not session.get("authenticated"):
                return jsonify({"ok": False, "error": "Unauthorized"}), 401
            return f(*args, **kwargs)
        return decorated

    @app.post("/api/login")
    def login():
        body = request.get_json() or {}
        username = body.get("username", "")
        password = body.get("password", "")
        if username.lower() == settings.dashboard_username.lower() and password == settings.dashboard_password:
            session["authenticated"] = True
            return jsonify({"ok": True})
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
        company = request.args.get("company", default="all", type=str)
        refresh = request.args.get("refresh", default="0") == "1"
        payload = service.build_projects_dashboard(date_from, company=company, refresh=refresh)
        return jsonify(payload)

    @app.post("/api/projects-dashboard/update-giai-trinh")
    @require_auth
    def update_giai_trinh():
        body = request.get_json() or {}
        project_id = body.get("project_id")
        giai_trinh = body.get("x_studio_giai_trinh", "")
        if not project_id:
            return jsonify({"ok": False, "error": "project_id is required"}), 400
        
        success = service.update_project_giai_trinh(project_id, giai_trinh)
        return jsonify({"ok": success})

    @app.get("/api/projects-dashboard/delta")
    @require_auth
    def projects_dashboard_delta():
        last_sync = request.args.get("last_sync", default="", type=str)
        company = request.args.get("company", default="all", type=str)
        date_from = request.args.get("date_from", default="2026-01-01", type=str)
        payload = service.get_delta_updates(last_sync, company_key=company, date_from=date_from)
        return jsonify(payload)

    @app.get("/api/redirect/sale-order/<int:so_id>")
    @require_auth
    def redirect_to_sale_order(so_id):
        settings = get_settings()
        url = f"{settings.odoo_url.rstrip('/')}/web#id={so_id}&model=sale.order&view_type=form"
        return redirect(url, code=302)

    def _sanitize_error_message(message: str) -> str:
        if not message:
            return message
        from urllib.parse import urlparse
        sensitive_terms = []
        if settings.odoo_url:
            sensitive_terms.append(settings.odoo_url)
            try:
                parsed = urlparse(settings.odoo_url)
                if parsed.netloc:
                    sensitive_terms.append(parsed.netloc)
                    if parsed.hostname:
                        sensitive_terms.append(parsed.hostname)
                        parts = parsed.hostname.split(".")
                        if len(parts) > 1:
                            sensitive_terms.append(parts[0])
            except Exception:
                pass
        if settings.odoo_db:
            sensitive_terms.append(settings.odoo_db)
        if settings.odoo_api_key:
            sensitive_terms.append(settings.odoo_api_key)
        if settings.odoo_user_id:
            sensitive_terms.append(str(settings.odoo_user_id))
            
        unique_terms = sorted(list(set(term for term in sensitive_terms if term and len(term) > 2)), key=len, reverse=True)
        for term in unique_terms:
            message = message.replace(term, "********")
        return message

    @app.errorhandler(OdooAPIError)
    def handle_odoo_error(error: OdooAPIError):
        payload = {
            "ok": False,
            "error": "Cannot load dashboard data from Odoo",
        }
        if settings.debug:
            payload.update(
                {
                    "error": _sanitize_error_message(str(error)),
                    "model": _sanitize_error_message(error.model),
                    "method": _sanitize_error_message(error.method),
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
        message = _sanitize_error_message(str(error)) if settings.debug else "Internal server error"
        return jsonify({"ok": False, "error": message}), 500

    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    app.run(host="0.0.0.0", port=settings.port, debug=settings.debug)
