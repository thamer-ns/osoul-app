"""Strict write-result handling for the legacy database API."""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple


def install_database_write_hardening() -> None:
    """Patch ``database.execute_query`` while preserving its bool API.

    Legacy code treated any syntactically successful UPDATE/DELETE as success,
    even when no record matched. The patched function returns ``False`` for a
    zero-row data mutation so the UI cannot display a false confirmation.
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
            command_match = re.match(
                r"^\s*([A-Za-z]+)",
                str(query or ""),
            )
            command = (
                command_match.group(1).upper()
                if command_match
                else ""
            )
            affected = int(cursor.rowcount or 0)
            connection.commit()
            if command in {"INSERT", "UPDATE", "DELETE"}:
                return affected != 0
            return True
        except Exception as exc:
            try:
                database._set_last_db_error(redact_text(exc))
            except Exception:
                pass
            try:
                connection.rollback()
            except Exception:
                pass
            return False
        finally:
            database.put_connection(connection, kind)

    database.execute_query = execute_query_strict
    database._strict_execute_query_installed = True
