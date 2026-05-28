"""SQLite persistent cache for Odoo API responses."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from threading import Lock


CACHE_DB_PATH = Path(__file__).parent / ".cache.db"
DEFAULT_TTL_SECONDS = 3600  # 1 hour - balance giữa performance và freshness


class PersistentCache:
    def __init__(self, db_path: Path | None = None, ttl: int = DEFAULT_TTL_SECONDS):
        self.db_path = db_path or CACHE_DB_PATH
        self.ttl = ttl
        self._lock = Lock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON cache(created_at)")
            conn.commit()
            conn.close()

    def get(self, key: str) -> dict | None:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            row = conn.execute(
                "SELECT value, created_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
            conn.close()
            if row is None:
                return None
            value_json, created_at = row
            if time.time() - created_at > self.ttl:
                return None
            return json.loads(value_json)

    def set(self, key: str, value: dict):
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, created_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), time.time()),
            )
            conn.commit()
            conn.close()

    def clear(self, prefix: str = ""):
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            if prefix:
                conn.execute("DELETE FROM cache WHERE key LIKE ?", (f"{prefix}%",))
            else:
                conn.execute("DELETE FROM cache")
            conn.commit()
            conn.close()

    def cleanup_expired(self):
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(
                "DELETE FROM cache WHERE ? - created_at > ?",
                (time.time(), self.ttl),
            )
            conn.commit()
            conn.close()
