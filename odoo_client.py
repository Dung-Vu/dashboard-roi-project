from __future__ import annotations

import atexit
import itertools
import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)


class OdooAPIError(Exception):
    def __init__(self, message: str, model: str = "", method: str = ""):
        super().__init__(message)
        self.model = model
        self.method = method


class OdooAPI:
    def __init__(self, url: str, db: str, user_id: int, api_key: str):
        base_url = url.rstrip("/")
        if base_url.endswith("/jsonrpc"):
            base_url = base_url[: -len("/jsonrpc")]

        self.url = base_url
        self.db = db
        self.uid = user_id
        self.api_key = api_key
        self.jsonrpc_url = f"{self.url}/jsonrpc"
        self.timeout = (5, 60)
        self.request_counter = itertools.count(1)

        retry = Retry(
            total=3,
            backoff_factor=1,
            backoff_jitter=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=retry)

        self.session = requests.Session()
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        atexit.register(self.close)

    def call_method(
        self,
        model: str,
        method: str,
        args: list | None = None,
        kwargs: dict | None = None,
    ) -> list | dict | int | bool | None:
        if args is None:
            args = [[]]
        if kwargs is None:
            kwargs = {}

        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [
                    self.db,
                    self.uid,
                    self.api_key,
                    model,
                    method,
                    args,
                    kwargs,
                ],
            },
            "id": next(self.request_counter),
        }

        try:
            response = self.session.post(
                self.jsonrpc_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
        except requests.exceptions.Timeout as exc:
            raise OdooAPIError(f"Request timeout: {exc}", model=model, method=method) from exc
        except requests.exceptions.ConnectionError as exc:
            raise OdooAPIError(f"Connection error: {exc}", model=model, method=method) from exc
        except Exception as exc:
            raise OdooAPIError(str(exc), model=model, method=method) from exc

        if "error" in result:
            error = result["error"]
            message = error.get("data", {}).get("message") or error.get("message") or str(error)
            raise OdooAPIError(message, model=model, method=method)

        return result.get("result")

    def search_read(
        self,
        model: str,
        domain: list,
        fields: list[str] | None = None,
        limit: int = 0,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if fields is None:
            fields = ["id", "name"]

        kwargs: dict[str, Any] = {"fields": fields}
        if limit:
            kwargs["limit"] = limit
        if offset:
            kwargs["offset"] = offset

        result = self.call_method(model, "search_read", [domain], kwargs)
        return result or []

    def test_connection(self) -> dict[str, Any]:
        users = self.search_read("res.users", [["id", "=", self.uid]], ["name", "login"], limit=1)
        if not users:
            return {"ok": False, "error": "Cannot reach Odoo"}
        return {"ok": True, "user": users[0]}

    def close(self) -> None:
        if hasattr(self, "session") and self.session:
            self.session.close()
            logger.debug("Closed Odoo JSON-RPC session")