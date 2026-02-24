from __future__ import annotations

# financial_analysis/store.py
import logging
import pandas as pd
import json
from typing import Any, Dict, Optional

from database import execute_query, fetch_table, fetch_df, get_connection, put_connection, table_exists
from market_data import get_ticker_symbol, _symbol_variants
from .utils import _safe_float, _safe_float_none, _safe_date_str

logger = logging.getLogger(__name__)
_TABLE_NAME = "financialstatements_raw"



# ==============================================================
# 🔧 Schema compatibility / migration-safe helpers
# ==============================================================
def _db_kind() -> str:
    conn = None
    kind = "sqlite"
    try:
        conn, kind = get_connection()
        return str(kind or "sqlite")
    except Exception:
        logger.exception("Failed to detect DB kind in financial_analysis.store")
        return "sqlite"
    finally:
        try:
            if conn is not None:
                put_connection(conn, kind)
        except Exception:
            logger.exception("Failed to return DB connection while detecting kind")


def _table_columns(table_name: str) -> set[str]:
    cols: set[str] = set()
    conn = None
    kind = "sqlite"
    try:
        conn, kind = get_connection()
        cur = conn.cursor()
        if kind == "postgres":
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s
                  AND table_schema IN (current_schema(), 'public')
                """,
                (table_name,),
            )
            cols = {str(r[0]).lower() for r in (cur.fetchall() or [])}
        else:
            cur.execute(f"PRAGMA table_info({table_name})")
            cols = {str(r[1]).lower() for r in (cur.fetchall() or [])}
    except Exception:
        logger.exception("Failed reading columns for table %s", table_name)
        cols = set()
    finally:
        try:
            if conn is not None:
                put_connection(conn, kind)
        except Exception:
            logger.exception("Failed returning DB connection after reading columns for %s", table_name)
    return cols


def _exec_best_effort(sql: str, *, log_level: str = "warning") -> bool:
    ok = False
    try:
        ok = bool(execute_query(sql))
    except Exception:
        logger.exception("DB execute threw in _exec_best_effort")
        ok = False
    if not ok:
        if log_level == "debug":
            logger.debug("Best-effort SQL failed: %s", sql)
        elif log_level == "error":
            logger.error("Best-effort SQL failed: %s", sql)
        else:
            logger.warning("Best-effort SQL failed: %s", sql)
    return ok


def _ensure_financialstatements_table_compat() -> None:
    """Migration-safe shim for light table schema (date/date_str compatibility)."""
    if not table_exists("financialstatements"):
        return

    kind = _db_kind()
    cols = _table_columns("financialstatements")
    if not cols:
        return

    if "date_str" not in cols:
        if kind == "postgres":
            _exec_best_effort("ALTER TABLE financialstatements ADD COLUMN IF NOT EXISTS date_str TEXT")
        else:
            _exec_best_effort("ALTER TABLE financialstatements ADD COLUMN date_str TEXT")
        cols = _table_columns("financialstatements")

    if "date_str" in cols and "date" in cols:
        _exec_best_effort(
            """
            UPDATE financialstatements
            SET date_str = COALESCE(NULLIF(CAST(date_str AS TEXT), ''), CAST(date AS TEXT))
            WHERE date IS NOT NULL
            """,
            log_level="debug",
        )

    _exec_best_effort(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_financialstatements_uq
        ON financialstatements(symbol, date_str, period_type)
        """,
        log_level="debug",
    )


def _ensure_financialstatements_raw_schema() -> None:
    """Create/upgrade financialstatements_raw to support legacy + new columns safely."""
    kind = _db_kind()
    if not table_exists(_TABLE_NAME):
        if kind == "postgres":
            ddl = f"""
            CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
                id BIGSERIAL PRIMARY KEY,
                symbol TEXT,
                date_str TEXT,
                period_type TEXT,
                source TEXT,
                payload TEXT,
                statement TEXT,
                as_of DATE,
                scale TEXT DEFAULT 'raw',
                currency TEXT,
                data_json JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        else:
            ddl = f"""
            CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                date_str TEXT,
                period_type TEXT,
                source TEXT,
                payload TEXT,
                statement TEXT,
                as_of TEXT,
                scale TEXT DEFAULT 'raw',
                currency TEXT,
                data_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        _exec_best_effort(ddl, log_level="error")

    cols = _table_columns(_TABLE_NAME)
    if not cols:
        return

    add_cols: list[tuple[str, str]] = []
    if "date_str" not in cols:
        add_cols.append(("date_str", "TEXT"))
    if "period_type" not in cols:
        add_cols.append(("period_type", "TEXT"))
    if "source" not in cols:
        add_cols.append(("source", "TEXT"))
    if "payload" not in cols:
        add_cols.append(("payload", "TEXT"))
    if "statement" not in cols:
        add_cols.append(("statement", "TEXT"))
    if "as_of" not in cols:
        add_cols.append(("as_of", "DATE" if kind == "postgres" else "TEXT"))
    if "scale" not in cols:
        add_cols.append(("scale", "TEXT"))
    if "currency" not in cols:
        add_cols.append(("currency", "TEXT"))
    if "data_json" not in cols:
        add_cols.append(("data_json", "JSONB" if kind == "postgres" else "TEXT"))
    if "updated_at" not in cols:
        add_cols.append(("updated_at", "TIMESTAMPTZ" if kind == "postgres" else "TEXT"))
    if "created_at" not in cols:
        add_cols.append(("created_at", "TIMESTAMPTZ" if kind == "postgres" else "TEXT"))

    for col_name, col_type in add_cols:
        if kind == "postgres":
            _exec_best_effort(f"ALTER TABLE {_TABLE_NAME} ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
        else:
            _exec_best_effort(f"ALTER TABLE {_TABLE_NAME} ADD COLUMN {col_name} {col_type}")

    cols = _table_columns(_TABLE_NAME)
    if not cols:
        return

    if "as_of" in cols and "date_str" in cols:
        _exec_best_effort(
            f"""
            UPDATE {_TABLE_NAME}
            SET as_of = COALESCE(as_of, NULLIF(CAST(date_str AS TEXT), ''))
            WHERE date_str IS NOT NULL
            """,
            log_level="debug",
        )
    if "data_json" in cols and "payload" in cols:
        _exec_best_effort(
            f"""
            UPDATE {_TABLE_NAME}
            SET data_json = COALESCE(data_json, NULLIF(payload, ''))
            WHERE payload IS NOT NULL
            """,
            log_level="debug",
        )
    if "date_str" in cols and "as_of" in cols:
        _exec_best_effort(
            f"""
            UPDATE {_TABLE_NAME}
            SET date_str = COALESCE(NULLIF(CAST(date_str AS TEXT), ''), CAST(as_of AS TEXT))
            WHERE as_of IS NOT NULL
            """,
            log_level="debug",
        )
    if "payload" in cols and "data_json" in cols:
        _exec_best_effort(
            f"""
            UPDATE {_TABLE_NAME}
            SET payload = COALESCE(payload, CAST(data_json AS TEXT))
            WHERE data_json IS NOT NULL
            """,
            log_level="debug",
        )
    if "scale" in cols:
        _exec_best_effort(f"UPDATE {_TABLE_NAME} SET scale = COALESCE(NULLIF(scale, ''), 'raw')", log_level="debug")
    if "updated_at" in cols:
        _exec_best_effort(f"UPDATE {_TABLE_NAME} SET updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)", log_level="debug")

    _exec_best_effort(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {_TABLE_NAME}_uq
        ON {_TABLE_NAME} (symbol, statement, period_type, as_of, scale)
        """,
        log_level="debug",
    )


# ==============================================================
# 💾 DB Save / Fetch
# ==============================================================

def save_financial_record(symbol, date_str, data, period_type="Annual", source="Manual"):
    """
    حفظ السجل المالي الخفيف مع توافق خلفي لعمود التاريخ (date/date_str) وتسجيل واضح للأخطاء.
    """
    try:
        _ensure_financialstatements_table_compat()

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
        vals = {k: _safe_float_none((data or {}).get(k, None)) for k in keys}

        numeric_abs = []
        for v in vals.values():
            try:
                if v is None:
                    continue
                fv = float(v)
                if pd.notna(fv):
                    numeric_abs.append(abs(fv))
            except Exception:
                logger.warning("Non-numeric financial value skipped while saving financial record", exc_info=True)
                continue

        if not numeric_abs or sum(numeric_abs) == 0:
            logger.warning("Skipping empty financial record for %s (%s)", symbol, date_str)
            return False

        query = """
            INSERT INTO financialstatements
            (symbol, date_str, period_type, source,
             revenue, net_income,
             total_assets, total_liabilities, total_equity,
             operating_cash_flow, current_assets, current_liabilities, long_term_debt)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (symbol, date_str, period_type)
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
        if not ok:
            logger.error("Failed to save financial record for %s %s (%s)", symbol, date_str, period_type)
        return bool(ok)
    except Exception:
        logger.exception("DB Error in save_financial_record(symbol=%r, date_str=%r)", symbol, date_str)
        return False


def get_stored_financials_df(symbol, period_type="Annual"):
    """
    ✅ يرجع DataFrame من financialstatements
    """
    try:
        _ensure_financialstatements_table_compat()
        raw_symbol = symbol
        symbol = get_ticker_symbol(symbol)
        variants = _symbol_variants(raw_symbol)
        period_type = str(period_type or "Annual").strip().title()

        # ✅ لا تجلب الجدول كامل. استخدم استعلام مفلتر لضمان ظهور البيانات حتى مع كبر الجدول.
        vs = [str(v) for v in variants if v]
        if not vs:
            vs = [symbol]

        # build WHERE symbol = %s OR ...
        sym_clause = " OR ".join(["symbol=%s"] * len(vs))
        q = f"""
        SELECT *
        FROM financialstatements
        WHERE ({sym_clause}) AND LOWER(TRIM(period_type)) = LOWER(TRIM(%s))
        ORDER BY date_str DESC;
        """
        df = fetch_df(q, tuple(vs + [period_type]))
        if df is None or df.empty:
            # fallback (older behavior)
            df = fetch_table("financialstatements")
            if df is None or df.empty:
                return pd.DataFrame()
            if "symbol" in df.columns:
                df = df[df["symbol"].astype(str).isin(vs)]
            if "period_type" in df.columns:
                df = df[df["period_type"].astype(str).str.title() == period_type]

        # normalize date columns
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.sort_values("date", ascending=False)
        elif "date_str" in df.columns:
            df["date_str"] = pd.to_datetime(df["date_str"], errors="coerce")
            df = df.sort_values("date_str", ascending=False)

        return df
    except Exception:
        logger.exception("Failed to fetch stored financials for %s (%s)", symbol, period_type)
        return pd.DataFrame()




# ==============================================================
# 🧱 Full Statements RAW storage (compatible with older versions)
# ==============================================================

def ensure_financialstatements_raw_table() -> None:
    """Create/upgrade raw statements table in a migration-safe way.

    يدعم النسخ القديمة (date_str/payload) والنسخة الأحدث (statement/as_of/data_json)
    بدون حذف البيانات الحالية.
    """
    try:
        _ensure_financialstatements_raw_schema()
    except Exception:
        logger.exception("Failed ensuring financialstatements_raw schema compatibility")
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

    # نكتب الحقول القديمة والجديدة معًا قدر الإمكان للحفاظ على التوافق الخلفي.
    query = f"""
    INSERT INTO {_TABLE_NAME}
        (symbol, statement, period_type, as_of, scale, currency, source, data_json, date_str, payload, updated_at)
    VALUES
        (%s, %s, %s, %s::date, %s, %s, %s, %s::jsonb, %s, %s, NOW())
    ON CONFLICT (symbol, statement, period_type, as_of, scale)
    DO UPDATE SET
        currency = EXCLUDED.currency,
        source = EXCLUDED.source,
        data_json = EXCLUDED.data_json,
        updated_at = NOW()
    ;
    """
    params = (sym, st, ptype, as_of_d, sc, currency, source[:50], payload, as_of_d, payload)
    ok = bool(execute_query(query, params))
    if not ok:
        logger.error("Failed to save full statement record for %s/%s %s %s", sym, st, ptype, as_of_d)
    return ok


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

    if _db_kind() == "postgres":
        query = f"""
    SELECT as_of::text AS as_of, data_json
    FROM {_TABLE_NAME}
    WHERE symbol = %s AND statement = %s AND period_type = %s AND scale = %s
    ORDER BY as_of DESC;
    """
    else:
        query = f"""
    SELECT CAST(as_of AS TEXT) AS as_of, data_json
    FROM {_TABLE_NAME}
    WHERE symbol = %s AND statement = %s AND period_type = %s AND scale = %s
    ORDER BY as_of DESC;
    """
    df = fetch_df(query, (sym, st, ptype, sc))
    if df is None or df.empty:
        # legacy fallback: table may only have date_str/payload and no statement split
        try:
            q_legacy = f"""
            SELECT date_str AS as_of, payload AS data_json
            FROM {_TABLE_NAME}
            WHERE symbol = %s AND LOWER(TRIM(period_type)) = LOWER(TRIM(%s))
            ORDER BY date_str DESC
            """
            df = fetch_df(q_legacy, (sym, ptype))
        except Exception:
            logger.exception("Legacy fallback fetch failed for financialstatements_raw")
            df = pd.DataFrame()
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


def get_full_statements_freshness(
    symbol: str,
    *,
    period_type: str = "Annual",
    scale: str = "thousands",
) -> dict:
    """Return freshness + source summary for stored *full* statements.

    Uses financialstatements_raw.updated_at + source.

    Returns:
      {"updated_at": str|None, "sources": [..], "completeness": "complete"|"partial"|"none"}
    """
    ensure_financialstatements_raw_table()

    sym = get_ticker_symbol(symbol)
    ptype = str(period_type or "Annual").strip()
    ptype = "TTM" if ptype.upper() == "TTM" else ptype.title()
    sc = str(scale or "thousands").strip().lower()
    if sc not in ("raw", "thousands"):
        sc = "thousands"

    # latest update + sources (Postgres/SQLite compatible)
    if _db_kind() == "postgres":
        q = f"""
    SELECT
      MAX(updated_at) AS updated_at,
      ARRAY_AGG(DISTINCT source) AS sources
    FROM {_TABLE_NAME}
    WHERE symbol=%s AND period_type=%s AND scale=%s;
    """
    else:
        q = f"""
    SELECT
      MAX(updated_at) AS updated_at,
      GROUP_CONCAT(DISTINCT source) AS sources
    FROM {_TABLE_NAME}
    WHERE symbol=%s AND period_type=%s AND scale=%s;
    """
    meta = fetch_df(q, (sym, ptype, sc))
    updated_at = None
    sources = []
    try:
        if meta is not None and (not meta.empty):
            updated_at = meta.iloc[0].get("updated_at")
            sources = meta.iloc[0].get("sources") or []
    except Exception:
        updated_at, sources = None, []

    # completeness: do we have all 3 statements?
    try:
        have_income = has_full_statement(sym, "income", ptype, scale=sc)
        have_cash = has_full_statement(sym, "cashflow", ptype, scale=sc)
        have_balance = has_full_statement(sym, "balance", ptype, scale=sc)
        if have_income and have_cash and have_balance:
            completeness = "complete"
        elif have_income or have_cash or have_balance:
            completeness = "partial"
        else:
            completeness = "none"
    except Exception:
        logger.exception("Failed completeness check for full statements freshness")
        completeness = "none"

    # normalize serialization
    try:
        if hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()
        elif updated_at is not None:
            updated_at = str(updated_at)
    except Exception:
        logger.exception("Failed to normalize updated_at in full statements freshness")
        updated_at = None

    try:
        if isinstance(sources, str):
            sources = [s.strip() for s in sources.split(",") if str(s).strip()]
        elif sources is None:
            sources = []
        else:
            sources = [str(s) for s in list(sources) if s]
    except Exception:
        logger.exception("Failed to normalize sources in full statements freshness")
        sources = []

    return {"updated_at": updated_at, "sources": sources, "completeness": completeness}


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
        logger.exception("has_full_statement failed for %s / %s / %s", symbol, statement, period_type)
        return False
