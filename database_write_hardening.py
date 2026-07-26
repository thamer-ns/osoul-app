"""Strict write-result handling for the legacy database API."""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple


def install_database_write_hardening() -> None:
    """Patch ``database.execute_query`` while preserving its bool API.

    User-facing INSERT/UPDATE/DELETE calls return ``False`` when no row changed.
    Idempotent schema backfills are allowed to affect zero rows because that
    simply means the migration was already complete.
    """
    import database
    from osoli_logging import redact_text

    if getattr(database, "_strict_execute_query_installed", False):
        return

    def execute_query_strict(
        query: str,
        params: Optional[Tuple[Any, ...]] = None,
    ) -> bool:
        connection, kind = database.get_connection()
        try:
            cursor = connection.cursor()
            adapted = database._adapt_query_for_kind(query, kind)
            cursor.execute(adapted, params or ())
            raw_query = str(query or "")
            command_match = re.match(r"^\s*([A-Za-z]+)", raw_query)
            command = command_match.group(1).upper() if command_match else ""
            affected = int(cursor.rowcount or 0)
            connection.commit()

            normalized = " ".join(raw_query.lower().split())
            idempotent_backfill = (
                command == "UPDATE"
                and "user_id is null" in normalized
                and "portfolio_id is null" in normalized
            )
            if idempotent_backfill:
                return True
            if command in {"INSERT", "UPDATE", "DELETE"}:
                return affected != 0
            return True
        except Exception as exc:
            try:
                database._set_last_db_error(redact_text(exc))
            except Exception:
                import logging
                logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)
            try:
                connection.rollback()
            except Exception:
                import logging
                logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)
            return False
        finally:
            database.put_connection(connection, kind)

    database.execute_query = execute_query_strict
    database._strict_execute_query_installed = True
