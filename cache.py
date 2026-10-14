"""SQLite persistent cache for Odoo API responses."""
from __future__ import annotations

import contextlib
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Any


logger = logging.getLogger(__name__)

CACHE_DB_PATH = Path(os.getenv("CACHE_DB_PATH", Path(__file__).parent / ".cache.db"))
DEFAULT_TTL_SECONDS = 3600  # 1 hour - balance giữa performance và freshness

_ORIG_TIME = time.time
_BASE_WALL = float(_ORIG_TIME())
_BASE_MONO = float(time.monotonic())


def _now() -> float:
    if time.time is _ORIG_TIME:
        return float(_BASE_WALL + (time.monotonic() - _BASE_MONO))
    return float(time.time())


class PersistentCache:
    _db_locks: dict[str, Lock] = {}
    _db_locks_guard = Lock()

    def __init__(self, db_path: Path | str | None = None, ttl: int = DEFAULT_TTL_SECONDS):
        self.db_path = Path(db_path) if db_path is not None else Path(CACHE_DB_PATH)
        self.ttl = float(ttl)
        resolved_path = str(self.db_path.resolve())
        with self._db_locks_guard:
            if resolved_path not in self._db_locks:
                self._db_locks[resolved_path] = Lock()
            self._lock = self._db_locks[resolved_path]
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL
            )
        """)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(cache)").fetchall()}
        if "expires_at" not in cols:
            conn.execute("ALTER TABLE cache ADD COLUMN expires_at REAL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON cache(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_expires_at ON cache(expires_at)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS locks (
                key TEXT PRIMARY KEY,
                expires_at REAL NOT NULL,
                owner_id TEXT
            )
        """)
        lock_cols = {row[1] for row in conn.execute("PRAGMA table_info(locks)").fetchall()}
        if "owner_id" not in lock_cols:
            conn.execute("ALTER TABLE locks ADD COLUMN owner_id TEXT")
        conn.commit()

    def _recover_corrupt_db(self) -> None:
        """Recover from a corrupted SQLite database or missing schema without raising."""
        try:
            for suffix in ("", "-wal", "-shm"):
                candidate = Path(f"{self.db_path}{suffix}")
                if candidate.exists():
                    try:
                        candidate.unlink()
                    except OSError:
                        pass
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                self._create_tables(conn)
        except Exception as exc:
            logger.error(f"Failed to recover corrupt cache DB at {self.db_path}: {exc}")

    def _init_db(self) -> None:
        with self._lock:
            try:
                with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                    self._create_tables(conn)
            except sqlite3.DatabaseError:
                self._recover_corrupt_db()
            except sqlite3.Error as exc:
                logger.error(f"Failed to initialize cache DB at {self.db_path}: {exc}")

    def get(self, key: str, allow_stale: bool = False) -> Any | None:
        with self._lock:
            now = _now()
            try:
                with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                    row = conn.execute(
                        "SELECT value, created_at, expires_at FROM cache WHERE key = ?",
                        (key,),
                    ).fetchone()
                    if row is None:
                        return None
                    value_json, created_at, expires_at = row
                    is_expired = (
                        (expires_at is not None and now >= float(expires_at))
                        or (expires_at is None and (now - float(created_at)) >= self.ttl)
                    )
                    if is_expired and not allow_stale:
                        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                        conn.commit()
                        return None
                    try:
                        return json.loads(value_json)
                    except (json.JSONDecodeError, TypeError):
                        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                        conn.commit()
                        return None
            except sqlite3.DatabaseError:
                self._recover_corrupt_db()
                return None
            except sqlite3.Error:
                return None

    def get_with_meta(self, key: str, allow_stale: bool = False) -> dict[str, Any] | None:
        with self._lock:
            now = _now()
            try:
                with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                    row = conn.execute(
                        "SELECT value, created_at, expires_at FROM cache WHERE key = ?",
                        (key,),
                    ).fetchone()
                    if row is None:
                        return None
                    value_json, created_at, expires_at = row
                    is_expired = (
                        (expires_at is not None and now >= float(expires_at))
                        or (expires_at is None and (now - float(created_at)) >= self.ttl)
                    )
                    if is_expired and not allow_stale:
                        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                        conn.commit()
                        return None
                    try:
                        parsed = json.loads(value_json)
                    except (json.JSONDecodeError, TypeError):
                        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                        conn.commit()
                        return None
                    return {
                        "value": parsed,
                        "created_at": float(created_at),
                        "expires_at": float(expires_at) if expires_at is not None else None,
                        "is_expired": is_expired,
                    }
            except sqlite3.DatabaseError:
                self._recover_corrupt_db()
                return None
            except sqlite3.Error:
                return None

    def set(self, key: str, value: Any, ttl: int | float | None = None) -> None:
        with self._lock:
            now = _now()
            effective_ttl = float(self.ttl if ttl is None else ttl)
            expires_at = float(now + effective_ttl)
            serialized = json.dumps(value)
            try:
                with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO cache (key, value, created_at, expires_at) VALUES (?, ?, ?, ?)",
                        (key, serialized, now, expires_at),
                    )
                    conn.commit()
            except sqlite3.DatabaseError:
                self._recover_corrupt_db()
                try:
                    with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                        conn.execute(
                            "INSERT OR REPLACE INTO cache (key, value, created_at, expires_at) VALUES (?, ?, ?, ?)",
                            (key, serialized, now, expires_at),
                        )
                        conn.commit()
                except sqlite3.Error:
                    pass
            except sqlite3.Error:
                pass

    def clear(self, prefix: str = "") -> None:
        with self._lock:
            try:
                with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                    if prefix:
                        conn.execute("DELETE FROM cache WHERE key LIKE ?", (f"{prefix}%",))
                    else:
                        conn.execute("DELETE FROM cache")
                    conn.commit()
            except sqlite3.DatabaseError:
                self._recover_corrupt_db()
            except sqlite3.Error:
                pass

    def cleanup_expired(self) -> int:
        with self._lock:
            now = _now()
            try:
                with contextlib.closing(sqlite3.connect(str(self.db_path), timeout=30.0)) as conn:
                    cursor = conn.execute(
                        "DELETE FROM cache WHERE (expires_at IS NOT NULL AND ? >= expires_at) "
                        "OR (expires_at IS NULL AND ? - created_at >= ?)",
                        (now, now, self.ttl),
                    )
                    conn.commit()
                    return cursor.rowcount
            except sqlite3.DatabaseError:
                self._recover_corrupt_db()
                return 0
            except sqlite3.Error:
                return 0

    def acquire_warmer_lock(
        self,
        lock_key: str,
        lock_ttl: int | float | None = None,
        owner_id: str | None = None,
        ttl_seconds: int | float | None = None,
    ) -> bool:
        effective_ttl = float(
            ttl_seconds
            if ttl_seconds is not None
            else (lock_ttl if lock_ttl is not None else 300.0)
        )
        with self._lock:
            try:
                with contextlib.closing(
                    sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level=None)
                ) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        now = _now()
                        expires_at = float(now + effective_ttl)
                        conn.execute("DELETE FROM locks WHERE expires_at <= ?", (now,))
                        conn.execute(
                            "INSERT OR FAIL INTO locks (key, expires_at, owner_id) VALUES (?, ?, ?)",
                            (lock_key, expires_at, owner_id),
                        )
                        conn.execute("COMMIT")
                        return True
                    except sqlite3.IntegrityError:
                        with contextlib.suppress(sqlite3.Error):
                            conn.execute("ROLLBACK")
                        return False
                    except Exception:
                        with contextlib.suppress(sqlite3.Error):
                            conn.execute("ROLLBACK")
                        return False
            except Exception:
                return False

    def release_warmer_lock(self, lock_key: str, owner_id: str | None = None) -> bool:
        with self._lock:
            try:
                with contextlib.closing(
                    sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level=None)
                ) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        if owner_id is not None:
                            cursor = conn.execute(
                                "DELETE FROM locks WHERE key = ? AND owner_id = ?",
                                (lock_key, owner_id),
                            )
                        else:
                            cursor = conn.execute(
                                "DELETE FROM locks WHERE key = ?",
                                (lock_key,),
                            )
                        conn.execute("COMMIT")
                        return cursor.rowcount > 0
                    except Exception:
                        with contextlib.suppress(sqlite3.Error):
                            conn.execute("ROLLBACK")
                        return False
            except Exception:
                return False

