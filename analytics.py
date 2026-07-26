# analytics.py
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any

from database import fetch_table, execute_query
from market_data import fetch_batch_data, get_ticker_symbol


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
    ✅ حل مشكلة: Cannot compare tz-naive and tz-aware timestamps
    - أي تاريخ (string/naive/aware) -> UTC tz-aware -> ثم إزالة tz => naive موحّد
    """
    if s is None:
        return s
    dt = pd.to_datetime(s, errors="coerce", utc=True)
    try:
        return dt.dt.tz_convert(None)  # remove tz info (becomes naive)
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


def _safe_float(x, default=0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except Exception:
        return float(default)


# ============================================================
# ✅ DB Revision (Cache Key) — يحل مشكلة استمرار الكاش القديم
# ============================================================

def get_portfolio_cache_key() -> str:
    """
    يولّد مفتاح يتغيّر عند أي تغيير بالبيانات.
    يعتمد على أحدث created_at/updated_at/date بالجداول الرئيسية.
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
                    import logging
                    logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at analytics.py:83')
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

        mx = None
        for v in [t, d, w, r]:
            if v is None or pd.isna(v):
                continue
            mx = v if mx is None else max(mx, v)

        if mx is None:
            return "empty"

        return mx.strftime("%Y%m%d%H%M%S")

    except Exception:
        return "unavailable"


# ============================================================
# ✅ Trade status normalization
# ============================================================

def _normalize_trade_status(trades: pd.DataFrame) -> pd.DataFrame:
    """
    يحسن تصنيف الصفقات Open/Close بشكل أكثر تحملًا للاختلافات:
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
        trades["exit_price"] = 0.0  # ✅ يمنع مشاكل scalar

    status_str = trades["status"].astype(str).str.strip().str.lower()

    has_exit_price = pd.to_numeric(trades.get("exit_price", 0), errors="coerce").fillna(0).astype(float) > 0
    status_says_closed = status_str.isin([
        "close", "closed", "sold", "مغلقة", "مغلق", "تم البيع", "بيع"
    ])

    is_closed = has_exit_price | status_says_closed
    trades["status"] = np.where(is_closed, "Close", "Open")
    return trades


# ============================================================
# ✅ Data quality flags (avoid wrong analytics on zero prices)
# ============================================================

def _price_quality_flags(price: float, prev_close: float) -> dict:
    """
    Flags بسيطة:
    - zero price -> bad
    - prev_close zero while price exists -> warning
    """
    price = _safe_float(price, 0.0)
    prev_close = _safe_float(prev_close, 0.0)

    out = {
        "ok": True,
        "is_zero": False,
        "note": "",
    }
    if price <= 0:
        out["ok"] = False
        out["is_zero"] = True
        out["note"] = "price=0"
        return out

    if prev_close <= 0:
        out["note"] = "prev_close missing"
    return out


# ============================================================
# ✅ MAIN: Portfolio Metrics (Cashflow-based accounting)
# ============================================================

@st.cache_data(ttl=600, show_spinner=False)
def calculate_portfolio_metrics(include_xirr: bool = True, cache_key: str = ""):
    """
    منطقك الأساسي (محاسبة نقدية):
    - cash
    - market value
    - realized/unrealized
    - totals deposits/withdrawals/returns
    ✅ Fix timezone issues
    ✅ Optional XIRR
    ✅ cache_key يكسر الكاش عند أي تغيير بالبيانات

    🔥 إضافات مريحة للواجهة:
    - portfolio_value
    - cash_pct
    - open_positions_df / closed_positions_df
    """
    default_res = {
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
        "open_positions_df": pd.DataFrame(),
        "closed_positions_df": pd.DataFrame(),
        "portfolio_value": 0.0,
        "cash_pct": 0.0,
        "xirr": None,
        "xirr_note": "",
        "data_quality": {"ok": True, "notes": []},
    }

    try:
        # 1) Fetch
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")

        # 2) Normalize dates (CRITICAL FIX)
        trades = _normalize_dates_df(trades, ["date", "exit_date", "created_at", "updated_at"]) if trades is not None else trades
        dep = _normalize_dates_df(dep, ["date", "created_at", "updated_at"]) if dep is not None else dep
        wit = _normalize_dates_df(wit, ["date", "created_at", "updated_at"]) if wit is not None else wit
        ret = _normalize_dates_df(ret, ["date", "created_at", "updated_at"]) if ret is not None else ret

        # 3) Clean numeric
        for df in [dep, wit, ret]:
            if df is not None and not df.empty:
                _clean_num(df, "amount", 0.0)

        total_dep = float(dep["amount"].sum()) if dep is not None and not dep.empty else 0.0
        total_wit = float(wit["amount"].sum()) if wit is not None and not wit.empty else 0.0
        total_ret = float(ret["amount"].sum()) if ret is not None and not ret.empty else 0.0

        # إذا ما فيه صفقات
        if trades is None or trades.empty:
            cash = (total_dep + total_ret) - total_wit
            out = default_res | {
                "total_deposited": total_dep,
                "total_withdrawn": total_wit,
                "total_returns": total_ret,
                "cash": float(cash),
                "portfolio_value": float(cash),
                "cash_pct": 100.0 if float(cash) > 0 else 0.0,
                "deposits": dep if dep is not None else pd.DataFrame(),
                "withdrawals": wit if wit is not None else pd.DataFrame(),
                "returns": ret if ret is not None else pd.DataFrame(),
                "all_trades": pd.DataFrame(),
                "open_positions_df": pd.DataFrame(),
                "closed_positions_df": pd.DataFrame(),
            }
            if include_xirr:
                xirr_val, note = compute_portfolio_xirr(dep, wit, ret, ending_value=float(cash))
                out["xirr"] = xirr_val
                out["xirr_note"] = note
            return out

        # 4) Ensure cols
        for c in ["quantity", "entry_price", "exit_price", "current_price"]:
            _clean_num(trades, c, 0.0)

        if "symbol" not in trades.columns:
            return default_res

        trades = _normalize_trade_status(trades)

        # 5) total cost
        trades["total_cost"] = trades["quantity"] * trades["entry_price"]

        # 6) current price rules
        is_closed = trades["status"] == "Close"

        # ✅ (إصلاح تضخم الكاش) proceeds للصفقات المغلقة = qty * exit_price فقط
        trades["proceeds"] = 0.0
        trades.loc[is_closed, "proceeds"] = (trades.loc[is_closed, "quantity"] * trades.loc[is_closed, "exit_price"]).astype(float)

        # مغلقة: current_price = exit_price (للعرض/market_value)
        trades.loc[is_closed, "current_price"] = trades.loc[is_closed, "exit_price"]

        # صكوك مفتوحة: السعر الحالي = سعر الدخول
        if "asset_type" in trades.columns:
            is_open_sukuk = (trades["status"] == "Open") & (trades["asset_type"].astype(str).str.strip().str.lower() == "sukuk")
            trades.loc[is_open_sukuk, "current_price"] = trades.loc[is_open_sukuk, "entry_price"]

        # أي قيم صفر/NaN خذ entry_price
        trades["current_price"] = trades["current_price"].replace(0, np.nan).fillna(trades["entry_price"])

        # 7) final metrics
        trades["market_value"] = trades["quantity"] * trades["current_price"]
        trades["gain"] = trades["market_value"] - trades["total_cost"]

        trades["gain_pct"] = 0.0
        mask = trades["total_cost"] != 0
        trades.loc[mask, "gain_pct"] = (trades.loc[mask, "gain"] / trades.loc[mask, "total_cost"]) * 100.0

        open_trades = trades[trades["status"] == "Open"].copy()
        closed_trades = trades[trades["status"] == "Close"].copy()

        # 8) Cash equation (منطقك) — ✅ إصلاح: بيع = proceeds وليس market_value
        cash_inflow = total_dep + total_ret + float(closed_trades["proceeds"].sum())
        cash_outflow = total_wit + float(trades["total_cost"].sum())
        cash_calculated = float(cash_inflow - cash_outflow)

        # 9) Data quality checks
        dq_notes = []
        if (pd.to_numeric(open_trades.get("current_price", pd.Series(dtype=float)), errors="coerce").fillna(0.0) <= 0).any():
            dq_notes.append("يوجد صفقات مفتوحة بسعر حالي = 0 (راجع تحديث الأسعار)")
        if (pd.to_numeric(closed_trades.get("exit_price", pd.Series(dtype=float)), errors="coerce").fillna(0.0) <= 0).any():
            dq_notes.append("يوجد صفقات مغلقة بدون سعر بيع (exit_price=0) — هذا يسبب فرق في الكاش")

        data_quality = {"ok": (len(dq_notes) == 0), "notes": dq_notes}

        # ✅ إضافات للواجهة
        portfolio_value = float(open_trades["market_value"].sum() + cash_calculated)
        cash_pct = (float(cash_calculated) / portfolio_value * 100.0) if portfolio_value > 0 else 0.0

        out = {
            "cost_open": float(open_trades["total_cost"].sum()),
            "market_val_open": float(open_trades["market_value"].sum()),
            "unrealized_pl": float(open_trades["gain"].sum()),
            "realized_pl": float(closed_trades["gain"].sum()),
            "cash": float(cash_calculated),
            "portfolio_value": float(portfolio_value),
            "cash_pct": float(cash_pct),
            "total_deposited": float(total_dep),
            "total_withdrawn": float(total_wit),
            "total_returns": float(total_ret),
            "all_trades": trades,
            "open_positions_df": open_trades,
            "closed_positions_df": closed_trades,
            "deposits": dep if dep is not None else pd.DataFrame(),
            "withdrawals": wit if wit is not None else pd.DataFrame(),
            "returns": ret if ret is not None else pd.DataFrame(),
            "xirr": None,
            "xirr_note": "",
            "data_quality": data_quality,
        }

        # 10) XIRR
        if include_xirr:
            ending_value = float(open_trades["market_value"].sum() + cash_calculated)
            xirr_val, note = compute_portfolio_xirr(dep, wit, ret, ending_value=ending_value)
            out["xirr"] = xirr_val
            out["xirr_note"] = note

        return out

    except Exception as e:
        st.error(f"خطأ في التحليل المالي: {e}")
        return default_res


# ============================================================
# ✅ Price Update (Yahoo + Argaam handled in market_data.fetch_batch_data)
# ============================================================

def update_prices():
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

        live_data = fetch_batch_data(open_syms)

        for sym in open_syms:
            norm_sym = get_ticker_symbol(sym) or str(sym).strip().upper()
            d = (
                live_data.get(sym, {})
                or live_data.get(str(sym).strip().upper(), {})
                or live_data.get(norm_sym, {})
                or {}
            )
            price = _safe_float(d.get("price", 0.0), 0.0)
            prev_close = _safe_float(d.get("prev_close", d.get("previous_close", 0.0)), 0.0)

            q = _price_quality_flags(price, prev_close)
            if not q["ok"]:
                continue

            execute_query(
                "UPDATE Trades SET current_price = %s WHERE symbol = %s AND status = 'Open'",
                (float(price), sym),
            )

        st.cache_data.clear()
        return True

    except Exception as e:
        st.error(f"فشل تحديث الأسعار: {e}")
        return False


# ============================================================
# ✅ Equity curve (light helper)
# ============================================================

def generate_equity_curve(trades: pd.DataFrame):
    """
    منحنى نمو بسيط (تقريبي) بناءً على تواريخ الصفقات.
    NOTE: ليس NAV يومي حقيقي.
    """
    if trades is None or trades.empty:
        return pd.DataFrame()

    df = trades.copy()
    if "date" not in df.columns:
        return pd.DataFrame()

    try:
        df["date"] = _to_utc_naive_series(df["date"])
        df = df.sort_values("date")
        if "total_cost" not in df.columns:
            df["total_cost"] = df["quantity"].astype(float) * df["entry_price"].astype(float)
        _clean_num(df, "total_cost", 0.0)
        df["cumulative_invested"] = df["total_cost"].cumsum()
        return df
    except Exception:
        return pd.DataFrame()


# ============================================================
# ✅ XIRR / IRR (Money-weighted return)
# ============================================================

def _build_external_cashflows(dep: pd.DataFrame, wit: pd.DataFrame, ret: pd.DataFrame, ending_value: float):
    """
    Cashflows convention:
    - Deposits: negative (you invest money)
    - Withdrawals: positive (money back to you)
    - Returns/Grants: positive (income)
    - Ending value: positive (liquidation value at end date)
    """
    flows = []

    def add_df(df, sign: float):
        if df is None or df.empty:
            return
        if "amount" not in df.columns:
            return
        date_col = "date" if "date" in df.columns else ("created_at" if "created_at" in df.columns else None)
        if not date_col:
            return
        tmp = df[[date_col, "amount"]].copy()
        tmp[date_col] = _to_utc_naive_series(tmp[date_col])
        tmp["amount"] = pd.to_numeric(tmp["amount"], errors="coerce").fillna(0.0)
        for _, r in tmp.iterrows():
            dt = r[date_col]
            amt = float(r["amount"]) * sign
            if pd.isna(dt) or amt == 0:
                continue
            flows.append((pd.Timestamp(dt), float(amt)))

    add_df(dep, sign=-1.0)
    add_df(wit, sign=+1.0)
    add_df(ret, sign=+1.0)

    end_dt = _today_utc_naive()
    flows.append((end_dt, float(ending_value)))

    if not flows:
        return []

    d = {}
    for dt, amt in flows:
        d.setdefault(dt.normalize(), 0.0)
        d[dt.normalize()] += float(amt)

    out = sorted([(k, v) for k, v in d.items() if abs(v) > 1e-9], key=lambda x: x[0])
    return out


def _xnpv(rate: float, cashflows: List[Tuple[pd.Timestamp, float]]) -> float:
    if rate <= -0.999999:
        return np.inf
    t0 = cashflows[0][0]
    total = 0.0
    for t, c in cashflows:
        days = (t - t0).days
        total += c / ((1 + rate) ** (days / 365.0))
    return total


def _xirr_newton(cashflows: List[Tuple[pd.Timestamp, float]], guess: float = 0.1) -> Optional[float]:
    if not cashflows or len(cashflows) < 2:
        return None

    amts = [c for _, c in cashflows]
    if not (any(a < 0 for a in amts) and any(a > 0 for a in amts)):
        return None

    r = guess
    for _ in range(80):
        f = _xnpv(r, cashflows)
        dr = 1e-5
        f1 = _xnpv(r + dr, cashflows)
        dfdx = (f1 - f) / dr

        if abs(dfdx) < 1e-12:
            break

        nr = r - f / dfdx
        if not np.isfinite(nr):
            break

        if abs(nr - r) < 1e-8:
            return float(nr)

        r = nr

    return None


def _xirr_bisect(cashflows: List[Tuple[pd.Timestamp, float]], lo=-0.95, hi=5.0) -> Optional[float]:
    f_lo = _xnpv(lo, cashflows)
    f_hi = _xnpv(hi, cashflows)

    if not (np.isfinite(f_lo) and np.isfinite(f_hi)):
        return None
    if f_lo == 0:
        return float(lo)
    if f_hi == 0:
        return float(hi)
    if f_lo * f_hi > 0:
        return None

    for _ in range(120):
        mid = (lo + hi) / 2.0
        f_mid = _xnpv(mid, cashflows)
        if not np.isfinite(f_mid):
            return None
        if abs(f_mid) < 1e-8:
            return float(mid)
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid

    return float((lo + hi) / 2.0)


def compute_portfolio_xirr(dep: pd.DataFrame, wit: pd.DataFrame, ret: pd.DataFrame, ending_value: float):
    ending_value = float(ending_value or 0.0)
    if ending_value <= 0:
        return None, "ending_value<=0"

    cashflows = _build_external_cashflows(dep, wit, ret, ending_value)
    if not cashflows or len(cashflows) < 2:
        return None, "no cashflows"

    x = _xirr_newton(cashflows, guess=0.12)
    if x is not None and np.isfinite(x):
        return float(x), "newton"

    x2 = _xirr_bisect(cashflows)
    if x2 is not None and np.isfinite(x2):
        return float(x2), "bisect"

    return None, "no convergence"


# ============================================================
# ✅ Backup wrapper (as you had)
# ============================================================

def create_smart_backup():
    try:
        from backup_system import generate_full_backup
        return generate_full_backup()
    except Exception as e:
        st.error(f"فشل النسخ الاحتياطي: {e}")
        return None, None


# ============================================================
# 📈 Equity Curve (Portfolio NAV) - institutional v2
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def compute_portfolio_equity_curve(
    trades: pd.DataFrame,
    deposits: pd.DataFrame,
    withdrawals: pd.DataFrame,
    returnsgrants: pd.DataFrame,
    days: int = 365,
    interval: str = "1d",
) -> pd.DataFrame:
    """Compute daily NAV (cash + holdings) from trades + cashflows.

    - Uses price history per symbol (market_data.get_chart_history).
    - Works best when you have at least trade dates + entry/exit prices.
    - Fail-safe: returns empty df on any fatal error.
    """
    try:
        import numpy as np
        from datetime import datetime, timedelta
        from market_data import get_chart_history, get_ticker_symbol
        from data_normalizer import normalize_ohlcv

        if trades is None:
            trades = pd.DataFrame()
        if deposits is None:
            deposits = pd.DataFrame()
        if withdrawals is None:
            withdrawals = pd.DataFrame()
        if returnsgrants is None:
            returnsgrants = pd.DataFrame()

        end = pd.Timestamp(datetime.utcnow().date())
        start = end - pd.Timedelta(days=int(max(30, days)))

        # Gather symbols from trades only
        symbols = []
        if not trades.empty and "symbol" in trades.columns:
            symbols = sorted(set(get_ticker_symbol(s) for s in trades["symbol"].astype(str).tolist() if str(s).strip()))

        # Build daily index
        idx = pd.date_range(start=start, end=end, freq="D")
        if len(idx) < 5:
            return pd.DataFrame()

        # Price panels
        prices = {}
        for sym in symbols:
            try:
                years = int(max(1, np.ceil(days / 365) + 1))
                hist = get_chart_history(sym, years=years, interval=interval)
                hist = normalize_ohlcv(hist)
                if hist is None or hist.empty or "Close" not in hist.columns:
                    continue
                close = hist["Close"].copy()
                close.index = pd.to_datetime(close.index, errors="coerce")
                close = close.dropna()
                close = close[close.index >= (start - pd.Timedelta(days=7))]
                if close.empty:
                    continue
                close = close.reindex(idx, method="ffill")
                prices[sym] = close
            except Exception:
                continue

        # Event helpers
        def _as_dt(x):
            try:
                return pd.to_datetime(x, errors="coerce").normalize()
            except Exception:
                return pd.NaT

        events = []
        # deposits (+)
        if not deposits.empty and "date" in deposits.columns and "amount" in deposits.columns:
            for _, r in deposits.iterrows():
                dt = _as_dt(r.get("date"))
                amt = pd.to_numeric(r.get("amount"), errors="coerce")
                if pd.notna(dt) and pd.notna(amt):
                    events.append((dt, "cash", float(amt)))
        # withdrawals (-)
        if not withdrawals.empty and "date" in withdrawals.columns and "amount" in withdrawals.columns:
            for _, r in withdrawals.iterrows():
                dt = _as_dt(r.get("date"))
                amt = pd.to_numeric(r.get("amount"), errors="coerce")
                if pd.notna(dt) and pd.notna(amt):
                    events.append((dt, "cash", -float(amt)))
        # returns (+)
        if not returnsgrants.empty and "date" in returnsgrants.columns and "amount" in returnsgrants.columns:
            for _, r in returnsgrants.iterrows():
                dt = _as_dt(r.get("date"))
                amt = pd.to_numeric(r.get("amount"), errors="coerce")
                if pd.notna(dt) and pd.notna(amt):
                    events.append((dt, "cash", float(amt)))

        # trades: buy/sell
        if not trades.empty and "date" in trades.columns and "quantity" in trades.columns:
            for _, r in trades.iterrows():
                sym = get_ticker_symbol(r.get("symbol"))
                qty = pd.to_numeric(r.get("quantity"), errors="coerce")
                entry = pd.to_numeric(r.get("entry_price"), errors="coerce")
                exit_p = pd.to_numeric(r.get("exit_price"), errors="coerce")
                stt = str(r.get("status") or "").lower()
                dt_buy = _as_dt(r.get("date"))
                if pd.notna(dt_buy) and pd.notna(qty) and pd.notna(entry):
                    events.append((dt_buy, "buy", (sym, float(qty), float(entry))))
                dt_sell = _as_dt(r.get("exit_date"))
                if pd.notna(dt_sell) and pd.notna(qty) and pd.notna(exit_p) and stt in ("closed", "close", "sell", "sold", "تم الإغلاق", "مغلق"):
                    events.append((dt_sell, "sell", (sym, float(qty), float(exit_p))))

        events.sort(key=lambda x: x[0])

        cash = 0.0
        pos = {}  # sym -> qty
        # Build quick map day->events
        ev_by_day = {}
        for dt, typ, val in events:
            ev_by_day.setdefault(dt, []).append((typ, val))

        rows = []
        for day in idx:
            d = day.normalize()
            for typ, val in ev_by_day.get(d, []):
                if typ == "cash":
                    cash += float(val)
                elif typ == "buy":
                    sym, qty, px = val
                    pos[sym] = pos.get(sym, 0.0) + qty
                    cash -= qty * px
                elif typ == "sell":
                    sym, qty, px = val
                    pos[sym] = pos.get(sym, 0.0) - qty
                    if abs(pos.get(sym, 0.0)) < 1e-9:
                        pos.pop(sym, None)
                    cash += qty * px

            holdings = 0.0
            for sym, qty in pos.items():
                series = prices.get(sym)
                if series is None or series.empty:
                    continue
                px = float(series.loc[day]) if day in series.index else float(series.iloc[-1])
                holdings += qty * px

            equity = cash + holdings
            rows.append({"date": day, "cash": cash, "holdings": holdings, "equity": equity})

        out = pd.DataFrame(rows).set_index("date")
        out["returns"] = out["equity"].pct_change().fillna(0.0)
        return out
    except Exception:
        return pd.DataFrame()

