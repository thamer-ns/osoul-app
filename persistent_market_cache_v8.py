"""Shared PostgreSQL/SQLite cache for public market history and quotes.

The in-process cache remains the hot path. This cache only handles cold starts
and worker restarts, allowing the first authenticated page to use the last valid
snapshot immediately while a bounded refresh runs in the background.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import threading
import time
from typing import Any, Hashable

import pandas as pd

LOGGER = logging.getLogger(__name__)
TABLE = "market_runtime_cache_v8"
_INSTALL_LOCK = threading.RLock()
_INSTALLED = False
_MAX_HISTORY_BYTES = 4_500_000


def _adapt(query: str, kind: str) -> str:
    import database

    return database._adapt_query_for_kind(query, kind)  # noqa: SLF001


def install_persistent_market_cache() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        import database

        ddl = f"""
            CREATE TABLE IF NOT EXISTS {TABLE}(
                cache_key TEXT PRIMARY KEY,
                cache_kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                attrs_json TEXT NOT NULL,
                stored_at_epoch BIGINT NOT NULL,
                expires_at_epoch BIGINT NOT NULL
            )
        """
        if not database.execute_query(ddl):
            raise RuntimeError("تعذر إنشاء مخزن بيانات السوق السريع V8")
        if not database.execute_query(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_expiry "
            f"ON {TABLE}(expires_at_epoch)"
        ):
            raise RuntimeError("تعذر إنشاء فهرس مخزن بيانات السوق V8")
        _INSTALLED = True


def _key(kind: str, value: Hashable) -> str:
    raw = json.dumps(
        [kind, value],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _write(
    *,
    cache_key: str,
    kind: str,
    payload_json: str,
    attrs_json: str,
    ttl_seconds: float,
) -> bool:
    install_persistent_market_cache()
    import database

    conn = None
    db_kind = ""
    now = int(time.time())
    try:
        conn, db_kind = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            _adapt(
                f"""
                INSERT INTO {TABLE}(
                    cache_key,cache_kind,payload_json,attrs_json,
                    stored_at_epoch,expires_at_epoch
                ) VALUES(%s,%s,%s,%s,%s,%s)
                ON CONFLICT(cache_key) DO UPDATE SET
                    cache_kind=excluded.cache_kind,
                    payload_json=excluded.payload_json,
                    attrs_json=excluded.attrs_json,
                    stored_at_epoch=excluded.stored_at_epoch,
                    expires_at_epoch=excluded.expires_at_epoch
                """,
                db_kind,
            ),
            (
                cache_key,
                kind,
                payload_json,
                attrs_json,
                now,
                now + max(60, int(ttl_seconds)),
            ),
        )
        conn.commit()
        return True
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                LOGGER.debug("Persistent cache rollback failed", exc_info=True)
        LOGGER.info("Persistent market cache write failed", exc_info=True)
        return False
    finally:
        if conn is not None:
            database.put_connection(conn, db_kind)


def _read(
    cache_key: str,
    kind: str,
    *,
    max_stale_seconds: float,
) -> tuple[str, str, float] | None:
    install_persistent_market_cache()
    import database

    conn = None
    db_kind = ""
    try:
        conn, db_kind = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            _adapt(
                f"SELECT payload_json,attrs_json,stored_at_epoch "
                f"FROM {TABLE} WHERE cache_key=%s AND cache_kind=%s "
                "AND stored_at_epoch>=%s LIMIT 1",
                db_kind,
            ),
            (
                cache_key,
                kind,
                int(time.time() - max(60.0, max_stale_seconds)),
            ),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        if hasattr(row, "keys"):
            payload = str(row["payload_json"])
            attrs = str(row["attrs_json"])
            stored = float(row["stored_at_epoch"])
        else:
            payload, attrs, stored = str(row[0]), str(row[1]), float(row[2])
        return payload, attrs, max(0.0, time.time() - stored)
    except Exception:
        LOGGER.info("Persistent market cache read failed", exc_info=True)
        return None
    finally:
        if conn is not None:
            database.put_connection(conn, db_kind)


def save_history(
    key: Hashable,
    frame: pd.DataFrame,
    *,
    ttl_seconds: float,
) -> bool:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return False
    output = frame.tail(2000).copy(deep=True)
    try:
        payload = output.to_json(
            orient="split",
            date_format="iso",
            double_precision=10,
        )
    except Exception:
        LOGGER.info("Unable to serialize history cache", exc_info=True)
        return False
    if len(payload.encode("utf-8")) > _MAX_HISTORY_BYTES:
        output = output.tail(1000)
        payload = output.to_json(
            orient="split",
            date_format="iso",
            double_precision=10,
        )
    attrs = json.dumps(
        dict(getattr(frame, "attrs", {}) or {}),
        ensure_ascii=False,
        default=str,
    )
    return _write(
        cache_key=_key("history", key),
        kind="history",
        payload_json=payload,
        attrs_json=attrs,
        ttl_seconds=ttl_seconds,
    )


def load_history(
    key: Hashable,
    *,
    max_stale_seconds: float,
) -> tuple[pd.DataFrame, float] | None:
    item = _read(
        _key("history", key),
        "history",
        max_stale_seconds=max_stale_seconds,
    )
    if item is None:
        return None
    payload, attrs_json, age = item
    try:
        frame = pd.read_json(io.StringIO(payload), orient="split")
        if not isinstance(frame.index, pd.DatetimeIndex):
            parsed = pd.to_datetime(frame.index, utc=True, errors="coerce")
            if not parsed.isna().all():
                frame.index = parsed
        attrs = json.loads(attrs_json) if attrs_json else {}
        if isinstance(attrs, dict):
            frame.attrs.update(attrs)
        lineage = dict(frame.attrs.get("data_lineage") or {})
        lineage.update(
            {
                "persistent_cache": True,
                "persistent_age_seconds": round(age, 3),
                "is_stale": True,
                "cache_mode": "persistent_stale_while_revalidate",
            }
        )
        frame.attrs["data_lineage"] = lineage
        return frame, age
    except Exception:
        LOGGER.info("Unable to decode persistent history cache", exc_info=True)
        return None


def save_quote(
    symbol: str,
    payload: dict[str, Any],
    *,
    ttl_seconds: float,
) -> bool:
    if not isinstance(payload, dict):
        return False
    try:
        price = float(payload.get("price") or 0.0)
    except (TypeError, ValueError, OverflowError):
        return False
    if price <= 0:
        return False
    return _write(
        cache_key=_key("quote", str(symbol).strip().upper()),
        kind="quote",
        payload_json=json.dumps(payload, ensure_ascii=False, default=str),
        attrs_json="{}",
        ttl_seconds=ttl_seconds,
    )


def load_quote(
    symbol: str,
    *,
    max_stale_seconds: float,
) -> tuple[dict[str, Any], float] | None:
    item = _read(
        _key("quote", str(symbol).strip().upper()),
        "quote",
        max_stale_seconds=max_stale_seconds,
    )
    if item is None:
        return None
    payload_json, _attrs, age = item
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    payload.update(
        {
            "persistent_cache": True,
            "persistent_age_seconds": round(age, 3),
            "is_stale": True,
            "cache_mode": "persistent_stale_while_revalidate",
        }
    )
    return payload, age


def prune_expired(*, grace_seconds: int = 7 * 86400) -> None:
    install_persistent_market_cache()
    import database

    conn = None
    db_kind = ""
    try:
        conn, db_kind = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            _adapt(
                f"DELETE FROM {TABLE} WHERE expires_at_epoch<%s",
                db_kind,
            ),
            (int(time.time()) - max(0, int(grace_seconds)),),
        )
        conn.commit()
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                LOGGER.debug("Persistent cache prune rollback failed", exc_info=True)
        LOGGER.debug("Persistent cache prune failed", exc_info=True)
    finally:
        if conn is not None:
            database.put_connection(conn, db_kind)


__all__ = [
    "TABLE",
    "install_persistent_market_cache",
    "load_history",
    "load_quote",
    "prune_expired",
    "save_history",
    "save_quote",
]
