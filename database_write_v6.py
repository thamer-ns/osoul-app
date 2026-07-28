"""Small rowcount-aware write helper used by security-sensitive journals.

The legacy ``database.execute_query`` intentionally returns only success/failure,
which cannot distinguish an inserted row from ``ON CONFLICT DO NOTHING``.  This
helper keeps the existing connection lifecycle and placeholder adaptation while
returning the affected-row count without exposing connection objects to callers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable

import database
from osoli_logging import redact_text

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WriteResult:
    ok: bool
    rowcount: int
    returned: tuple[Any, ...] | None = None
    reason: str | None = None


def execute_write(
    query: str,
    params: Iterable[Any] | None = None,
    *,
    fetch_one: bool = False,
) -> WriteResult:
    """Execute one parameterized write and return its actual row count."""
    conn = None
    kind = ""
    try:
        conn, kind = database.get_connection()
        cursor = conn.cursor()
        adapted = database._adapt_query_for_kind(str(query), kind)  # noqa: SLF001
        cursor.execute(adapted, tuple(params or ()))
        returned = tuple(cursor.fetchone()) if fetch_one and cursor.description else None
        rowcount = max(0, int(cursor.rowcount or 0))
        conn.commit()
        return WriteResult(True, rowcount, returned)
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                LOGGER.debug("Rollback failed", exc_info=True)
        LOGGER.warning("Secure write failed: %s", redact_text(exc))
        return WriteResult(False, 0, None, "database_write_failed")
    finally:
        if conn is not None:
            database.put_connection(conn, kind)


__all__ = ["WriteResult", "execute_write"]
