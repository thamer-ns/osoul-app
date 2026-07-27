"""Strict JSON helpers for database payloads.

PostgreSQL JSONB rejects JavaScript-style NaN and Infinity values that Python's
``json.dumps`` emits by default. Financial/technical payloads must therefore
be normalised before persistence rather than silently losing cache records.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any


logger = logging.getLogger(__name__)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        number = float(value)
        return number if math.isfinite(number) else None
    # numpy scalars expose item() without importing numpy here.
    if hasattr(value, "item") and callable(value.item):
        try:
            value = value.item()
        except Exception:
            logger.debug(
                "Unable to convert scalar through item(); preserving original value",
                exc_info=True,
            )
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def strict_json_dumps(value: Any) -> str:
    return json.dumps(
        json_safe(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
