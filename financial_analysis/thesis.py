from __future__ import annotations

from datetime import datetime, timezone

from database import execute_query, fetch_table
from market_data import get_ticker_symbol


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def get_thesis(symbol):
    normalized = get_ticker_symbol(symbol)
    if not normalized:
        return None
    try:
        frame = fetch_table("investmentthesis")
        if frame is None or frame.empty or "symbol" not in frame.columns:
            return None
        rows = frame[frame["symbol"].astype(str).eq(normalized)]
        if rows.empty:
            return None
        if "last_updated" in rows.columns:
            rows = rows.sort_values("last_updated", ascending=False)
        return rows.iloc[0]
    except Exception:
        return None


def save_thesis(symbol, thesis_text, target_price, recommendation):
    normalized = get_ticker_symbol(symbol)
    if not normalized:
        return False
    text = str(thesis_text or "").strip()
    if len(text) > 20_000:
        return False
    recommendation_text = str(recommendation or "Hold").strip()[:30]
    target = max(0.0, _safe_float(target_price))
    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    return bool(
        execute_query(
            """
            INSERT INTO investmentthesis
                (symbol, thesis_text, target_price, recommendation, last_updated)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (symbol)
            DO UPDATE SET
                thesis_text=EXCLUDED.thesis_text,
                target_price=EXCLUDED.target_price,
                recommendation=EXCLUDED.recommendation,
                last_updated=EXCLUDED.last_updated
            """,
            (
                normalized,
                text,
                target,
                recommendation_text,
                updated_at,
            ),
        )
    )
