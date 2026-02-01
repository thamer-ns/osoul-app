import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any

from database import fetch_table, execute_query


# ============================================================
# ✅ Helpers: numeric + timezone-safe datetime
# ============================================================

def _clean_num(df: pd.DataFrame, col: str, default: float = 0.0):
    """تنظيف البيانات الرقمية لضمان عدم توقف الحسابات."""
    if df is None:
        return
    if col not in df.columns:
        df[col] = default
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(default)


def _to_utc_naive_series(s: pd.Series) -> pd.Series:
    """
    ✅ حل مشكلة tz-aware vs tz-naive
    - أي تاريخ -> UTC -> ثم إزالة tz
    """
    if s is None:
        return s
    dt = pd.to_datetime(s, errors="coerce", utc=True)
    try:
        return dt.dt.tz_convert(None)
    except Exception:
        try:
            return pd.to_datetime(dt, errors="coerce").dt.tz_localize(None)
        except Exception:
            return pd.to_datetime(dt, errors="coerce")


def _normalize_dates_df(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = _to_utc_naive_series(df[c])
    return df


def _today_utc_naive() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc)).tz_convert(None)


def _safe_float(x, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except Exception:
        return float(default)


# ============================================================
# ✅ DB Revision (Cache Key)  — كسر الكاش عند أي تغيير بالجداول
# ============================================================

def get_portfolio_cache_key() -> str:
    """
    يولّد مفتاح كاش يتغيّر عند أي تغيير بالبيانات.
    يعتمد على أحدث created_at/updated_at/date بالجداول الرئيسية.
    - إذا ما توفرت أعمدة الزمن، يرجع timestamp بالثواني كحل احتياطي.
    """
    def _max_dt(df: pd.DataFrame, cols: List[str]) -> Optional[pd.Timestamp]:
        if df is None or df.empty:
            return None
        mx = None
        for c in cols:
            if c in df.columns:
                s = pd.to_datetime(df[c], errors="coerce", utc=True)
                try:
                    s = s.dt.tz_convert(None)
                except Exception:
                    pass
                v = s.max()
                if pd.isna(v):
                    continue
                mx = v if mx is None else max(mx, v)
        return mx

    try:
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")

        t = _max_dt(trades, ["updated_at", "created_at", "date", "exit_date"])
        d = _max_dt(dep, ["updated_at", "created_at", "date"])
        w = _max_dt(wit, ["updated_at", "created_at", "date"])
        r = _max_dt(ret, ["updated_at", "created_at", "date"])

        # اجمعهم في قيمة واحدة
        mx = None
        for v in [t, d, w, r]:
            if v is None or pd.isna(v):
                continue
            mx = v if mx is None else max(mx, v)

        if mx is None:
            return str(int(datetime.now(timezone.utc).timestamp()))

        return mx.strftime("%Y%m%d%H%M%S")

    except Exception:
        # fallback: لا نكسر التشغيل
        return str(int(datetime.now(timezone.utc).timestamp()))


# ============================================================
# ✅ Trade status normalization
# ============================================================

def _normalize_trade_status(trades: pd.DataFrame) -> pd.DataFrame:
    """
    تصنيف Open/Close بشكل متحمّل:
    - status نص عربي/إنجليزي
    - exit_price
    - exit_date
    """
    if trades is None or trades.empty:
        return trades

    trades = trades.copy()

    if "status" not in trades.columns:
        trades["status"] = "Open"
    if "exit_date" not in trades.columns:
        trades["exit_date"] = pd.NaT
    if "asset_type" not in trades.columns:
        trades["asset_type"] = "Stock"
    if "exit_price" not in trades.columns:
        trades["exit_price"] = 0.0  # ✅ يمنع scalar crash

    status_str = trades["status"].astype(str).str.strip().str.lower()

    exit_price_num = pd.to_numeric(trades["exit_price"], errors="coerce").fillna(0.0)
    has_exit_price = exit_price_num.astype(float) > 0

    has_exit_date = trades["exit_date"].notna()

    status_says_closed = status_str.isin([
        "close", "closed", "sold", "مغلقة", "مغلق", "تم البيع", "بيع"
    ])

    # ✅ مهم: لا تعتبر الصفقة مغلقة فقط لأن exit_date موجود إذا exit_price = 0
    # هذا يقلل تضخيم/تشويش الكاش بسبب صفقات “مغلقة شكليًا”
    is_closed = has_exit_price | status_says_closed
    # إذا عندك exit_date معتبر عندك، فعّل السطر التالي:
    # is_closed = is_closed | (has_exit_date & has_exit_price)

    trades["status"] = np.where(is_closed, "Close", "Open")
    return trades


# ============================================================
# ✅ MAIN: Portfolio Metrics (Cashflow-based accounting)
# ============================================================

@st.cache_data(ttl=600, show_spinner=False)
def calculate_portfolio_metrics(include_xirr: bool = True, cache_key: str = "") -> Dict[str, Any]:
    """
    ✅ cache_key: يمر من views.py (get_portfolio_cache_key)
    - أي تغيير بالبيانات -> يتغير المفتاح -> الكاش يتكسر فورًا
    """
    default_res: Dict[str, Any] = {
        "cost_open": 0.0,
        "market_val_open": 0.0,
        "cash": 0.0,
        "unrealized_pl": 0.0,
        "realized_pl": 0.0,
        "total_deposited": 0.0,
        "total_withdrawn": 0.0,
        "total_returns": 0.0,
        "deposits": pd.DataFrame(),
        "withdrawals": pd.DataFrame(),
        "returns": pd.DataFrame(),
        "all_trades": pd.DataFrame(),
        "xirr": None,
        "xirr_note": "",
        "data_quality": {"ok": True, "notes": []},
    }

    try:
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")

        trades = _normalize_dates_df(trades, ["date", "exit_date", "created_at", "updated_at"]) if trades is not None else trades
        dep = _normalize_dates_df(dep, ["date", "created_at", "updated_at"]) if dep is not None else dep
        wit = _normalize_dates_df(wit, ["date", "created_at", "updated_at"]) if wit is not None else wit
        ret = _normalize_dates_df(ret, ["date", "created_at", "updated_at"]) if ret is not None else ret

        for df in [dep, wit, ret]:
            if df is not None and not df.empty:
                _clean_num(df, "amount", 0.0)

        total_dep = float(dep["amount"].sum()) if dep is not None and not dep.empty else 0.0
        total_wit = float(wit["amount"].sum()) if wit is not None and not wit.empty else 0.0
        total_ret = float(ret["amount"].sum()) if ret is not None and not ret.empty else 0.0

        if trades is None or trades.empty:
            cash = (total_dep + total_ret) - total_wit
            out = {**default_res, **{
                "total_deposited": total_dep,
                "total_withdrawn": total_wit,
                "total_returns": total_ret,
                "cash": float(cash),
                "deposits": dep if dep is not None else pd.DataFrame(),
                "withdrawals": wit if wit is not None else pd.DataFrame(),
                "returns": ret if ret is not None else pd.DataFrame(),
                "all_trades": pd.DataFrame(),
            }}
            return out

        for c in ["quantity", "entry_price", "exit_price", "current_price"]:
            _clean_num(trades, c, 0.0)

        if "symbol" not in trades.columns:
            return default_res

        trades = _normalize_trade_status(trades)

        trades["total_cost"] = trades["quantity"] * trades["entry_price"]

        is_closed = trades["status"] == "Close"

        # ✅ proceeds للصفقات المغلقة يعتمد فقط على exit_price
        # هذا يمنع تضخيم الكاش إذا current_price تغير أو صار fallback غلط
        closed_exit_price = pd.to_numeric(trades.loc[is_closed, "exit_price"], errors="coerce").fillna(0.0)
        closed_qty = pd.to_numeric(trades.loc[is_closed, "quantity"], errors="coerce").fillna(0.0)
        trades["proceeds"] = 0.0
        trades.loc[is_closed, "proceeds"] = (closed_qty * closed_exit_price).astype(float)

        # صكوك مفتوحة: current_price = entry_price
        asset_type = trades["asset_type"].astype(str).str.strip().str.lower() if "asset_type" in trades.columns else "stock"
        is_open_sukuk = (trades["status"] == "Open") & (asset_type == "sukuk")

        # current_price للعرض فقط (market_value)
        # للمغلقة نعرض exit_price، للمفتوحة نستخدم current_price/entry_price
        trades.loc[is_closed, "current_price"] = trades.loc[is_closed, "exit_price"]
        trades.loc[is_open_sukuk, "current_price"] = trades.loc[is_open_sukuk, "entry_price"]
        trades["current_price"] = trades["current_price"].replace(0, np.nan).fillna(trades["entry_price"])

        trades["market_value"] = trades["quantity"] * trades["current_price"]
        trades["gain"] = trades["market_value"] - trades["total_cost"]

        trades["gain_pct"] = 0.0
        mask = trades["total_cost"] != 0
        trades.loc[mask, "gain_pct"] = (trades.loc[mask, "gain"] / trades.loc[mask, "total_cost"]) * 100.0

        open_trades = trades[trades["status"] == "Open"].copy()
        closed_trades = trades[trades["status"] == "Close"].copy()

        # ✅ Cash equation (أوضح وأكثر دقة)
        # cash = deposits + returns + proceeds(sells) - withdrawals - total_cost(buys)
        cash_in = total_dep + total_ret + float(closed_trades["proceeds"].sum())
        cash_out = total_wit + float(trades["total_cost"].sum())
        cash_calculated = float(cash_in - cash_out)

        dq_notes = []
        # صفقات مغلقة بدون exit_price
        if (closed_trades.get("exit_price", pd.Series(dtype=float)) <= 0).any():
            dq_notes.append("يوجد صفقات مغلقة بدون سعر بيع (exit_price=0) — هذا يؤثر على الكاش الحقيقي")
        # صفقات مفتوحة بسعر 0
        if (pd.to_numeric(open_trades.get("current_price", pd.Series(dtype=float)), errors="coerce").fillna(0.0) <= 0).any():
            dq_notes.append("يوجد صفقات مفتوحة بسعر حالي = 0 (راجع تحديث الأسعار)")

        data_quality = {"ok": (len(dq_notes) == 0), "notes": dq_notes}

        out: Dict[str, Any] = {
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
            "xirr": None,
            "xirr_note": "",
            "data_quality": data_quality,
        }

        return out

    except Exception as e:
        st.error(f"خطأ في التحليل المالي: {e}")
        return default_res


# ============================================================
# ✅ Price Update
# ============================================================

def update_prices() -> bool:
    """تحديث الأسعار للأسهم المفتوحة (غير الصكوك)."""
    try:
        df = fetch_table("Trades")
        if df is None or df.empty:
            return True

        if "symbol" not in df.columns:
            return True

        if "status" not in df.columns:
            df["status"] = "Open"

        status_open = df["status"].astype(str).str.strip().str.lower().isin(["open", "مفتوح"])
        if "asset_type" in df.columns:
            not_sukuk = df["asset_type"].astype(str).str.strip().str.lower().ne("sukuk")
        else:
            not_sukuk = True

        open_syms = df[status_open & not_sukuk]["symbol"].dropna().astype(str).unique().tolist()
        open_syms = [s.strip() for s in open_syms if s and s.strip()]
        if not open_syms:
            return True

        from market_data import fetch_batch_data
        live_data = fetch_batch_data(open_syms)

        for sym in open_syms:
            d = live_data.get(sym, {}) or {}
            price = _safe_float(d.get("price", 0.0), 0.0)
            if price <= 0:
                continue

            execute_query(
                "UPDATE Trades SET current_price = %s WHERE symbol = %s AND status = 'Open'",
                (float(price), sym),
            )

        # ✅ كسر الكاش بعد التحديث
        st.cache_data.clear()
        return True

    except Exception as e:
        st.error(f"فشل تحديث الأسعار: {e}")
        return False


# ============================================================
# ✅ Backup wrapper
# ============================================================

def create_smart_backup():
    try:
        from backup_system import generate_full_backup
        return generate_full_backup()
    except Exception as e:
        st.error(f"فشل النسخ الاحتياطي: {e}")
        return None, None