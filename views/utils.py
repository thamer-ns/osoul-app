"""Lightweight view helpers with no analytics, Plotly, AI or network imports."""
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def normalize_symbol(symbol: object) -> str:
    raw = str(symbol or "").strip().upper().replace(" ", "")
    if not raw or raw.lower() == "nan":
        return ""
    if raw.isdigit():
        return f"{raw}.SR"
    if raw.endswith("SR") and not raw.endswith(".SR") and raw[:-2].isdigit():
        return f"{raw[:-2]}.SR"
    return raw


def clean_symbols(values: Iterable[object] | None) -> list[str]:
    normalized = {normalize_symbol(value) for value in (values or [])}
    return sorted(item for item in normalized if item and item != ".SR")


def safe_status_series(frame: pd.DataFrame | None) -> pd.Series:
    if frame is None or frame.empty or "status" not in frame.columns:
        index = frame.index if isinstance(frame, pd.DataFrame) else None
        return pd.Series("", index=index, dtype=str)
    return frame["status"].astype(str).str.strip().str.lower()
