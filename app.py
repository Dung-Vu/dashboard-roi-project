from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
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

    @app.get("/")
    def index():
        return send_from_directory(BASE_DIR, "index.html")

    @app.get("/styles.css")
    def styles():
        return send_from_directory(BASE_DIR, "styles.css")

    @app.get("/app.js")
    def javascript():
        return send_from_directory(BASE_DIR, "app.js")

    @app.get("/favicon.ico")
    def favicon():
        return ("", 204)

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "default_project_id": settings.default_project_id,
                "odoo": service.test_connection(),
            }
        )

    @app.get("/api/dashboard")
    def dashboard():
        project_id = request.args.get("project_id", default=settings.default_project_id, type=int)
        payload = service.build_project_dashboard(project_id)
        return jsonify(payload)

    @app.get("/api/projects-dashboard")
    def projects_dashboard():
        date_from = request.args.get("date_from", default="2026-01-01", type=str)
        refresh = request.args.get("refresh", default="0") == "1"
        payload = service.build_projects_dashboard(date_from, refresh=refresh)
        return jsonify(payload)

    @app.errorhandler(OdooAPIError)
    def handle_odoo_error(error: OdooAPIError):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": str(error),
                    "model": error.model,
                    "method": error.method,
                }
            ),
            502,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        if isinstance(error, HTTPException):
            return error
        app.logger.exception("Unhandled error")
        return jsonify({"ok": False, "error": str(error)}), 500

    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    app.run(host="0.0.0.0", port=settings.port, debug=settings.debug)
