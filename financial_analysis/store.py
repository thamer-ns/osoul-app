# financial_analysis/store_full.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import pandas as pd

from database import execute_query, fetch_table
from market_data import get_ticker_symbol
from .utils import _safe_date_str


# ==============================================================
# 💾 Full Statements (JSONB) Save / Fetch
# ==============================================================
_TABLE_NAME = "financialstatements_raw"


def ensure_financialstatements_raw_table() -> None:
    """Create table if it doesn't exist (Postgres/Supabase friendly)."""
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
        id BIGSERIAL PRIMARY KEY,
        symbol TEXT NOT NULL,
        statement TEXT NOT NULL, -- income|balance|cashflow
        period_type TEXT NOT NULL, -- Annual|Quarterly|TTM
        as_of DATE NOT NULL,
        scale TEXT NOT NULL DEFAULT 'raw', -- raw|thousands
        currency TEXT,
        source TEXT,
        data_json JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(symbol, statement, period_type, as_of, scale)
    );
    """
    execute_query(ddl)

    # Update trigger is optional; we just set updated_at in UPSERT.
    return


def save_full_statement_record(
    symbol: str,
    statement: str,
    period_type: str,
    as_of: str,
    data: Dict[str, Any],
    *,
    scale: str = "raw",
    currency: Optional[str] = None,
    source: str = "YahooJSON",
) -> bool:
    """Save one statement for one period (as_of)."""
    ensure_financialstatements_raw_table()

    sym = get_ticker_symbol(symbol)
    st = str(statement or "").strip().lower()
    if st not in ("income", "balance", "cashflow"):
        return False

    ptype = str(period_type or "Annual").strip().title()
    if ptype not in ("Annual", "Quarterly", "Ttm"):
        # allow "TTM" too
        ptype = "TTM" if str(period_type or "").strip().upper() == "TTM" else "Annual"
    if ptype == "Ttm":
        ptype = "TTM"

    as_of_d = _safe_date_str(as_of)
    sc = str(scale or "raw").strip().lower()
    if sc not in ("raw", "thousands"):
        sc = "raw"

    payload = json.dumps(data or {}, ensure_ascii=False)

    query = f"""
    INSERT INTO {_TABLE_NAME}
        (symbol, statement, period_type, as_of, scale, currency, source, data_json, updated_at)
    VALUES
        (%s, %s, %s, %s::date, %s, %s, %s, %s::jsonb, NOW())
    ON CONFLICT (symbol, statement, period_type, as_of, scale)
    DO UPDATE SET
        currency = EXCLUDED.currency,
        source = EXCLUDED.source,
        data_json = EXCLUDED.data_json,
        updated_at = NOW()
    ;
    """
    params = (sym, st, ptype, as_of_d, sc, currency, source[:50], payload)
    return bool(execute_query(query, params))


def fetch_full_statement_records(
    symbol: str,
    statement: str,
    period_type: str = "Annual",
    *,
    scale: str = "thousands",
) -> pd.DataFrame:
    """Return DataFrame: rows are line items, columns are period end dates."""
    ensure_financialstatements_raw_table()

    sym = get_ticker_symbol(symbol)
    st = str(statement or "").strip().lower()
    ptype = str(period_type or "Annual").strip()
    ptype = "TTM" if ptype.upper() == "TTM" else ptype.title()
    sc = str(scale or "thousands").strip().lower()
    if sc not in ("raw", "thousands"):
        sc = "thousands"

    query = f"""
    SELECT as_of::text AS as_of, data_json
    FROM {_TABLE_NAME}
    WHERE symbol = %s AND statement = %s AND period_type = %s AND scale = %s
    ORDER BY as_of DESC;
    """
    df = fetch_table(query, (sym, st, ptype, sc))
    if df is None or df.empty:
        return pd.DataFrame()

    cols = {}
    for _, row in df.iterrows():
        d = str(row.get("as_of") or "")
        data = row.get("data_json") or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        cols[d] = pd.Series(data)

    out = pd.DataFrame(cols)
    # Stable order: latest first
    out = out.loc[~out.index.duplicated(keep="first")]
    return out


def has_full_statement(symbol: str, statement: str, period_type: str = "Annual", *, scale: str = "thousands") -> bool:
    try:
        df = fetch_full_statement_records(symbol, statement, period_type, scale=scale)
        return df is not None and not df.empty
    except Exception:
        return False
