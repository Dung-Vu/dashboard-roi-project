"""SQLite persistent cache for Odoo API responses."""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import time
from pathlib import Path
from threading import Lock


CACHE_DB_PATH = Path(os.getenv("CACHE_DB_PATH", Path(__file__).parent / ".cache.db"))
DEFAULT_TTL_SECONDS = 3600  # 1 hour - balance giữa performance và freshness


class PersistentCache:
    def __init__(self, db_path: Path | None = None, ttl: int = DEFAULT_TTL_SECONDS):
        self.db_path = db_path or CACHE_DB_PATH
        self.ttl = ttl
        self._lock = Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._lock:
            with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS cache (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        created_at REAL NOT NULL
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON cache(created_at)")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS locks (
                        key TEXT PRIMARY KEY,
                        expires_at REAL NOT NULL
                    )
                """)
                conn.commit()

    def get(self, key: str) -> dict | None:
        with self._lock:
            with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                row = conn.execute(
                    "SELECT value, created_at FROM cache WHERE key = ?", (key,)
                ).fetchone()
            if row is None:
                return None
            value_json, created_at = row
            if time.time() - created_at > self.ttl:
                return None
            return json.loads(value_json)

    def set(self, key: str, value: dict):
        with self._lock:
            with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, created_at) VALUES (?, ?, ?)",
                    (key, json.dumps(value), time.time()),
                )
                conn.commit()

    def clear(self, prefix: str = ""):
        with self._lock:
            with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                if prefix:
                    conn.execute("DELETE FROM cache WHERE key LIKE ?", (f"{prefix}%",))
                else:
                    conn.execute("DELETE FROM cache")
                conn.commit()

    def cleanup_expired(self):
        with self._lock:
            with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                conn.execute(
                    "DELETE FROM cache WHERE ? - created_at > ?",
                    (time.time(), self.ttl),
                )
                conn.commit()

    def acquire_warmer_lock(self, lock_key: str, lock_ttl: int) -> bool:
        with self._lock:
            now = time.time()
            expires_at = now + lock_ttl
            try:
                with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=5.0)) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("DELETE FROM locks WHERE expires_at < ?", (now,))
                    conn.execute(
                        "INSERT OR FAIL INTO locks (key, expires_at) VALUES (?, ?)",
                        (lock_key, expires_at)
                    )
                    conn.commit()
                    return True
            except sqlite3.IntegrityError:
                return False
            except Exception:
                return False

    def release_warmer_lock(self, lock_key: str) -> None:
        with self._lock:
            try:
                with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=5.0)) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("DELETE FROM locks WHERE key = ?", (lock_key,))
                    conn.commit()
            except Exception:
                pass
