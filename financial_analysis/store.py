# financial_analysis/store.py
import pandas as pd
import json
from typing import Any, Dict, Optional

from database import execute_query, fetch_table
from market_data import get_ticker_symbol
from .utils import _safe_float, _safe_date_str


# ==============================================================
# 💾 DB Save / Fetch
# ==============================================================
def save_financial_record(symbol, date_str, data, period_type="Annual", source="Manual"):
    """
    ✅ إصلاح أسماء الجداول:
    - financialstatements (lowercase) بدون quotes
    """
    try:
        symbol = get_ticker_symbol(symbol)
        date_str = _safe_date_str(date_str)
        period_type = str(period_type or "Annual").strip().title()
        source = str(source or "Manual").strip()[:30]

        keys = [
            "revenue",
            "net_income",
            "total_assets",
            "total_liabilities",
            "total_equity",
            "operating_cash_flow",
            "current_assets",
            "current_liabilities",
            "long_term_debt",
        ]

        vals = {k: _safe_float((data or {}).get(k, 0)) for k in keys}

        if sum(abs(v) for v in vals.values()) == 0:
            return False

        query = """
            INSERT INTO financialstatements
            (symbol, date, period_type, source,
             revenue, net_income,
             total_assets, total_liabilities, total_equity,
             operating_cash_flow, current_assets, current_liabilities, long_term_debt)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (symbol, date, period_type)
            DO UPDATE SET
                revenue=EXCLUDED.revenue,
                net_income=EXCLUDED.net_income,
                total_assets=EXCLUDED.total_assets,
                total_liabilities=EXCLUDED.total_liabilities,
                total_equity=EXCLUDED.total_equity,
                operating_cash_flow=EXCLUDED.operating_cash_flow,
                current_assets=EXCLUDED.current_assets,
                current_liabilities=EXCLUDED.current_liabilities,
                long_term_debt=EXCLUDED.long_term_debt,
                source=EXCLUDED.source;
        """

        ok = execute_query(
            query,
            (
                symbol,
                date_str,
                period_type,
                source,
                vals["revenue"],
                vals["net_income"],
                vals["total_assets"],
                vals["total_liabilities"],
                vals["total_equity"],
                vals["operating_cash_flow"],
                vals["current_assets"],
                vals["current_liabilities"],
                vals["long_term_debt"],
            ),
        )
        return bool(ok)
    except Exception as e:
        print(f"DB Error: {e}")
        return False


def get_stored_financials_df(symbol, period_type="Annual"):
    """
    ✅ يرجع DataFrame من financialstatements
    """
    try:
        symbol = get_ticker_symbol(symbol)
        period_type = str(period_type or "Annual").strip().title()

        df = fetch_table("financialstatements")
        if df is None or df.empty:
            return pd.DataFrame()

        if "symbol" in df.columns:
            df = df[df["symbol"].astype(str) == symbol]
        if "period_type" in df.columns:
            df = df[df["period_type"].astype(str).str.title() == period_type]

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")

        return df.sort_values("date", ascending=False) if "date" in df.columns else df
    except Exception:
        return pd.DataFrame()




# ==============================================================
# 🧱 Full Statements RAW storage (compatible with older versions)
# ==============================================================
def ensure_financialstatements_raw_table() -> None:
    """Create table if it doesn't exist (Postgres/Supabase friendly).

    ✅ مهم: بعض المستخدمين لديهم نسخة قديمة من الجدول بدون UNIQUE/Index مناسب،
    وبالتالي جملة ON CONFLICT تفشل (no unique constraint).
    لذلك ننشئ Unique Index بشكل آمن (IF NOT EXISTS) حتى لو كان الجدول موجود مسبقًا.
    """
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
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    execute_query(ddl)

    # ✅ Ensure unique index exists for UPSERT (even if table existed before)
    try:
        execute_query(
            f"""CREATE UNIQUE INDEX IF NOT EXISTS {_TABLE_NAME}_uq
            ON {_TABLE_NAME} (symbol, statement, period_type, as_of, scale);"""
        )
    except Exception:
        pass

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


def has_full_statement(symbol: str, statement: str = None, period_type: str = "Annual", *, scale: str = "thousands") -> bool:
    """Return True if there is a stored full statement record.

    Backward-compatible behavior:
    - Some callers omitted `statement` (e.g., has_full_statement(symbol, period_type="Annual")).
      In that case we check whether *any* of (income/balance/cashflow) exists.
    """
    try:
        if statement:
            df = fetch_full_statement_records(symbol, statement, period_type, scale=scale)
            return df is not None and not df.empty

        for st_name in ("income", "balance", "cashflow"):
            df = fetch_full_statement_records(symbol, st_name, period_type, scale=scale)
            if df is not None and not df.empty:
                return True
        return False
    except Exception:
        return False
