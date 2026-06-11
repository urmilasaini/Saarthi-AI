"""MongoDB key-value cache with TTL. Replaces SQLite. Fail-open on every operation."""

import functools
import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta

from app import config

logger = logging.getLogger("saarthi.cache")

_collection = None
_conn = None


def _use_sqlite():
    return bool(getattr(config, "CACHE_DB", None))


def _get_conn():
    """SQLite cache connection used by tests/local fallback."""
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.CACHE_DB, check_same_thread=False)
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL NOT NULL)"
        )
        _conn.commit()
    return _conn


def _get_collection():
    global _collection
    if _collection is None:
        from app.db import get_db
        col = get_db()["api_cache"]
        col.create_index("expires_at", expireAfterSeconds=0)
        _collection = col
    return _collection


def get(key: str):
    """Return cached value or None. Any failure is a miss."""
    try:
        if _use_sqlite():
            now_ts = datetime.now(timezone.utc).timestamp()
            row = _get_conn().execute(
                "SELECT value, expires_at FROM cache WHERE key = ?",
                (key,),
            ).fetchone()
            if not row:
                return None
            value_json, expires_at = row
            if expires_at <= now_ts:
                _get_conn().execute("DELETE FROM cache WHERE key = ?", (key,))
                _get_conn().commit()
                return None
            return json.loads(value_json)

        doc = _get_collection().find_one({"key": key}, {"_id": 0, "value": 1})
        return doc["value"] if doc else None
    except Exception as error:
        logger.warning("Cache read failed (treating as miss): %s", error)
        return None


def set(key: str, value, ttl_seconds: int):
    """Write to cache. Any failure is silently skipped."""
    try:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        if _use_sqlite():
            _get_conn().execute(
                "REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), expires_at.timestamp()),
            )
            _get_conn().commit()
            return

        _get_collection().replace_one(
            {"key": key},
            {"key": key, "value": value, "expires_at": expires_at},
            upsert=True,
        )
    except Exception as error:
        logger.warning("Cache write failed (skipping): %s", error)


def cached(ttl_seconds: int):
    """Decorator: cache a function's JSON-serializable result by its arguments."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            raw = json.dumps(
                [func.__module__, func.__name__, args, kwargs],
                sort_keys=True, default=str,
            )
            key = hashlib.sha256(raw.encode()).hexdigest()
            hit = get(key)
            if hit is not None:
                return hit
            result = func(*args, **kwargs)
            if result is not None:
                set(key, result, ttl_seconds)
            return result
        return wrapper
    return decorator
