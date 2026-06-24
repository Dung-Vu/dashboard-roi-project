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
        import threading
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

        self._thread_local = threading.local()
        self._sessions_lock = threading.Lock()
        self._sessions: list[requests.Session] = []
        self._retry = Retry(
            total=3,
            backoff_factor=1,
            backoff_jitter=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            raise_on_status=False,
        )
        self._adapter = HTTPAdapter(pool_connections=30, pool_maxsize=30, max_retries=self._retry)
        atexit.register(self.close)

    @property
    def session(self) -> requests.Session:
        if not hasattr(self._thread_local, "session"):
            session = requests.Session()
            session.mount("http://", self._adapter)
            session.mount("https://", self._adapter)
            self._thread_local.session = session
            with self._sessions_lock:
                self._sessions.append(session)
        return self._thread_local.session

    def _sanitize(self, text: str) -> str:
        if not text:
            return text
        from urllib.parse import urlparse
        
        sensitive_terms = []
        if self.url:
            sensitive_terms.append(self.url)
            try:
                parsed = urlparse(self.url)
                if parsed.netloc:
                    sensitive_terms.append(parsed.netloc)
                    if parsed.hostname:
                        sensitive_terms.append(parsed.hostname)
                        parts = parsed.hostname.split(".")
                        if len(parts) > 1:
                            sensitive_terms.append(parts[0])
            except Exception:
                pass
        if self.db:
            sensitive_terms.append(self.db)
        if self.api_key:
            sensitive_terms.append(self.api_key)
        if hasattr(self, "uid") and self.uid:
            sensitive_terms.append(str(self.uid))
            
        unique_terms = sorted(list(set(term for term in sensitive_terms if term and len(term) > 3)), key=len, reverse=True)
        for term in unique_terms:
            text = text.replace(term, "********")
        return text

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
            raise OdooAPIError("Request timeout", model=model, method=method) from None
        except requests.exceptions.ConnectionError as exc:
            raise OdooAPIError("Connection error", model=model, method=method) from None
        except Exception as exc:
            sanitized_exc = self._sanitize(str(exc))
            raise OdooAPIError(f"Odoo request failed: {sanitized_exc}", model=model, method=method) from None

        if "error" in result:
            error = result["error"]
            message = error.get("data", {}).get("message") or error.get("message") or str(error)
            raise OdooAPIError(self._sanitize(message), model=model, method=method)

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
        with self._sessions_lock:
            for session in self._sessions:
                try:
                    session.close()
                except Exception:
                    pass
            self._sessions.clear()
        logger.debug("Closed all Odoo JSON-RPC sessions")