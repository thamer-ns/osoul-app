# analytics.py (FIXED: tz-naive vs tz-aware + safer numeric/date handling)

import pandas as pd
import numpy as np
from database import fetch_table, execute_query
from market_data import fetch_batch_data
import streamlit as st


# ============================================================
# ✅ Helpers: Safe numeric + datetime normalization
# ============================================================

def _clean_num(df: pd.DataFrame, col: str):
    """تنظيف البيانات الرقمية لضمان عدم توقف الحسابات."""
    if df is None:
        return
    if col not in df.columns:
        df[col] = 0.0
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)


def _to_utc_naive_series(s: pd.Series) -> pd.Series:
    """
    ✅ يحل مشكلة: Cannot compare tz-naive and tz-aware timestamps
    - يحوّل أي تاريخ (naive/aware/string) -> datetime UTC -> ثم يزيل timezone (naive) بشكل موحّد
    """
    if s is None:
        return s
    dt = pd.to_datetime(s, errors="coerce", utc=True)
    try:
        # dt is tz-aware UTC -> remove tz -> naive
        return dt.dt.tz_convert(None)
    except Exception:
        # لو ما كانت dt Series datetime64tz لأي سبب
        return pd.to_datetime(dt, errors="coerce")


def _normalize_trades_dates(trades: pd.DataFrame) -> pd.DataFrame:
    if trades is None or trades.empty:
        return trades

    trades = trades.copy()

    # أعمدة تاريخ شائعة
    for c in ["date", "exit_date", "created_at", "updated_at"]:
        if c in trades.columns:
            trades[c] = _to_utc_naive_series(trades[c])

    return trades


def _normalize_cashflow_dates(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()
    if "date" in df.columns:
        df["date"] = _to_utc_naive_series(df["date"])
    return df


# ============================================================
# ✅ Portfolio Metrics (Cashflow-based accounting, as you designed)
# ============================================================

@st.cache_data(ttl=60, show_spinner=False)
def calculate_portfolio_metrics():
    """
    حساب مقاييس المحفظة (بدون أي عمولات أو ضرائب).
    الحساب يعتمد على التدفق النقدي الصافي المباشر.
    ✅ تم إصلاح تواريخ tz-aware/tz-naive
    """
    default_res = {
        "cost_open": 0.0, "market_val_open": 0.0, "cash": 0.0,
        "unrealized_pl": 0.0, "realized_pl": 0.0,
        "total_deposited": 0.0, "total_withdrawn": 0.0, "total_returns": 0.0,
        "deposits": pd.DataFrame(), "withdrawals": pd.DataFrame(),
        "returns": pd.DataFrame(), "all_trades": pd.DataFrame()
    }

    try:
        # 1) Fetch tables (اسماء Capital ما تضر لأن database.py يعمل normalize)
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")

        # 2) Normalize dates (FIX)
        trades = _normalize_trades_dates(trades)
        dep = _normalize_cashflow_dates(dep)
        wit = _normalize_cashflow_dates(wit)
        ret = _normalize_cashflow_dates(ret)

        # 3) Clean numeric cols
        for df in [dep, wit, ret]:
            if df is not None and not df.empty:
                _clean_num(df, "amount")

        total_dep = float(dep["amount"].sum()) if dep is not None and not dep.empty else 0.0
        total_wit = float(wit["amount"].sum()) if wit is not None and not wit.empty else 0.0
        total_ret = float(ret["amount"].sum()) if ret is not None and not ret.empty else 0.0

        # إذا لا توجد صفقات
        if trades is None or trades.empty:
            default_res.update({
                "total_deposited": total_dep,
                "total_withdrawn": total_wit,
                "total_returns": total_ret,
                "cash": (total_dep + total_ret) - total_wit,
                "deposits": dep if dep is not None else pd.DataFrame(),
                "withdrawals": wit if wit is not None else pd.DataFrame(),
                "returns": ret if ret is not None else pd.DataFrame(),
                "all_trades": pd.DataFrame(),
            })
            return default_res

        # 4) Ensure core columns exist
        for c in ["quantity", "entry_price", "exit_price", "current_price"]:
            _clean_num(trades, c)

        if "status" not in trades.columns:
            trades["status"] = "Open"
        if "exit_date" not in trades.columns:
            trades["exit_date"] = pd.NaT
        if "asset_type" not in trades.columns:
            trades["asset_type"] = "Stock"

        # 5) Compute total_cost
        trades["total_cost"] = trades["quantity"] * trades["entry_price"]

        # 6) Normalize status + closed detection (more robust)
        status_str = trades["status"].astype(str).str.strip().str.lower()
        has_exit_price = trades["exit_price"] > 0
        has_exit_date = trades["exit_date"].notna()
        status_says_closed = status_str.isin(["close", "closed", "sold", "مغلقة", "مغلق", "تم البيع"])

        is_closed = has_exit_price | has_exit_date | status_says_closed
        trades["status"] = np.where(is_closed, "Close", "Open")

        # 7) Current price rules
        # Closed: current_price = exit_price
        trades.loc[is_closed, "current_price"] = trades.loc[is_closed, "exit_price"]

        # Open Sukuk: current_price = entry_price
        is_open_sukuk = (trades["status"] == "Open") & (trades["asset_type"].astype(str).str.lower() == "sukuk")
        trades.loc[is_open_sukuk, "current_price"] = trades.loc[is_open_sukuk, "entry_price"]

        # Fill zeros/NaNs with entry_price as fallback
        trades["current_price"] = trades["current_price"].replace(0, np.nan)
        trades["current_price"] = trades["current_price"].fillna(trades["entry_price"])

        # 8) Final trade metrics
        trades["market_value"] = trades["quantity"] * trades["current_price"]
        trades["gain"] = trades["market_value"] - trades["total_cost"]

        trades["gain_pct"] = 0.0
        mask = trades["total_cost"] != 0
        trades.loc[mask, "gain_pct"] = (trades.loc[mask, "gain"] / trades.loc[mask, "total_cost"]) * 100.0

        open_trades = trades[trades["status"] == "Open"]
        closed_trades = trades[trades["status"] == "Close"]

        # 9) Cash equation (your accounting logic)
        cash_inflow = total_dep + total_ret + float(closed_trades["market_value"].sum())
        cash_outflow = total_wit + float(trades["total_cost"].sum())
        cash_calculated = float(cash_inflow - cash_outflow)

        return {
            "cost_open": float(open_trades["total_cost"].sum()),
            "market_val_open": float(open_trades["market_value"].sum()),
            "unrealized_pl": float(open_trades["gain"].sum()),
            "realized_pl": float(closed_trades["gain"].sum()),
            "cash": float(cash_calculated),
            "total_deposited": float(total_dep),
            "total_withdrawn": float(total_wit),
            "total_returns": float(total_ret),
            "all_trades": trades,
            "deposits": dep if dep is not None else pd.DataFrame(),
            "withdrawals": wit if wit is not None else pd.DataFrame(),
            "returns": ret if ret is not None else pd.DataFrame(),
        }

    except Exception as e:
        # لا نخلي خطأ واحد يطيح الصفحة ويظهر "اختفت البيانات"
        st.error(f"خطأ في التحليل المالي: {e}")
        return default_res


# ============================================================
# ✅ Price Update (uses market_data.fetch_batch_data)
# ============================================================

def update_prices():
    """تحديث الأسعار للأسهم المفتوحة (غير الصكوك)."""
    try:
        df = fetch_table("Trades")
        if df is None or df.empty:
            return True

        # Normalize status column in case it comes mixed
        if "status" not in df.columns:
            return True

        # فقط الأسهم المفتوحة (ليست صكوك)
        asset_col = "asset_type" if "asset_type" in df.columns else None
        sym_col = "symbol" if "symbol" in df.columns else None
        if not sym_col:
            return True

        status_open = df["status"].astype(str).str.strip().str.lower().isin(["open", "مفتوح"])
        not_sukuk = True
        if asset_col:
            not_sukuk = df[asset_col].astype(str).str.strip().str.lower().ne("sukuk")

        open_stocks = df[status_open & not_sukuk][sym_col].dropna().astype(str).unique().tolist()
        open_stocks = [s.strip() for s in open_stocks if s and str(s).strip()]
        if not open_stocks:
            return True

        live_data = fetch_batch_data(open_stocks)

        # تحديث السعر الحالي
        for sym in open_stocks:
            data = live_data.get(sym, {}) or {}
            try:
                price = float(data.get("price", 0) or 0)
            except Exception:
                price = 0.0

            if price > 0:
                execute_query(
                    "UPDATE Trades SET current_price = %s WHERE symbol = %s AND status = 'Open'",
                    (price, sym),
                )

        # تحديث الكاش فقط، لا يمس DB
        st.cache_data.clear()
        return True

    except Exception as e:
        st.error(f"فشل تحديث الأسعار: {e}")
        return False


# ============================================================
# Optional helpers (as-is)
# ============================================================

def generate_equity_curve(df: pd.DataFrame):
    """توليد منحنى النمو (تقريبي)."""
    if df is None or df.empty or "date" not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    try:
        df["date"] = _to_utc_naive_series(df["date"])
        df = df.sort_values("date")
        if "total_cost" not in df.columns:
            df["total_cost"] = 0.0
        _clean_num(df, "total_cost")
        df["cumulative_invested"] = df["total_cost"].cumsum()
        return df
    except Exception:
        return pd.DataFrame()


def create_smart_backup():
    try:
        from backup_system import generate_full_backup
        return generate_full_backup()
    except Exception as e:
        st.error(f"فشل النسخ الاحتياطي: {e}")
        return None, None