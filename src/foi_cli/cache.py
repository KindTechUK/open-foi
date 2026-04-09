"""SQLite-based disk cache with TTL for feed API responses."""

import sqlite3
import time
from pathlib import Path


DEFAULT_CACHE_DIR = Path.home() / ".config" / "foi-cli"
DEFAULT_TTL = 3600  # 1 hour


class Cache:
    def __init__(self, path: Path | None = None):
        self._path = path or DEFAULT_CACHE_DIR / "cache.db"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(key TEXT PRIMARY KEY, value TEXT, created_at REAL, ttl INTEGER)"
        )
        self._conn.commit()

    def get(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value, created_at, ttl FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        value, created_at, ttl = row
        if time.time() - created_at > ttl:
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._conn.commit()
            return None
        return value

    def set(self, key: str, value: str, ttl: int = DEFAULT_TTL) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, created_at, ttl) VALUES (?, ?, ?, ?)",
            (key, value, time.time(), ttl),
        )
        self._conn.commit()

    def clear(self) -> int:
        cursor = self._conn.execute("SELECT COUNT(*) FROM cache")
        count = cursor.fetchone()[0]
        self._conn.execute("DELETE FROM cache")
        self._conn.commit()
        return count

    def stats(self) -> dict:
        row = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(LENGTH(value)), 0), MIN(created_at) FROM cache"
        ).fetchone()
        now = time.time()
        expired = self._conn.execute(
            "SELECT COUNT(*) FROM cache WHERE (? - created_at) > ttl", (now,)
        ).fetchone()[0]
        return {
            "entries": row[0],
            "size_bytes": row[1],
            "oldest_age_seconds": round(now - row[2]) if row[2] else 0,
            "expired": expired,
        }

    def close(self) -> None:
        self._conn.close()
