# analytics.py
import math
from datetime import datetime, date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from database import fetch_table, execute_query
from market_data import fetch_batch_data, get_chart_history, get_ticker_symbol


# ============================================================
# 🧰 Helpers: تنظيف/توحيد
# ============================================================
def _now_utc():
    # Streamlit Cloud غالباً UTC
    return datetime.utcnow()

def _to_dt(x):
    try:
        return pd.to_datetime(x)
    except Exception:
        return pd.NaT

def _clean_num(df: pd.DataFrame, col: str):
    """تنظيف البيانات الرقمية لضمان عدم توقف الحسابات."""
    if df is None or df.empty:
        return
    if col not in df.columns:
        df[col] = 0.0
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

def _safe_float(x, default=0.0):
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return float(default)
        return float(x)
    except Exception:
        return float(default)

def _norm_status(s):
    s = str(s or "").strip().lower()
    if s in ("close", "closed", "sold", "مغلقة", "مغلق", "تم البيع"):
        return "Close"
    return "Open"

def _is_sukuk(x):
    return str(x or "").strip().lower() in ("sukuk", "صكوك", "صك")

def _ensure_price_quality_columns():
    """
    ✅ إضافة أعمدة جودة السعر بدون كسر (Postgres only).
    - current_price_source: مصدر السعر (yahoo/argaam/none)
    - current_price_updated_at: وقت آخر تحديث
    - current_price_is_stale: 1 إذا قديم
    """
    try:
        execute_query('ALTER TABLE trades ADD COLUMN IF NOT EXISTS current_price_source TEXT', ())
        execute_query('ALTER TABLE trades ADD COLUMN IF NOT EXISTS current_price_updated_at TIMESTAMP', ())
        execute_query('ALTER TABLE trades ADD COLUMN IF NOT EXISTS current_price_is_stale INT DEFAULT 0', ())
        return True
    except Exception:
        return False


# ============================================================
# 🧾 Cashflows: بناء تدفقات نقدية خارجية (Deposits/Withdrawals/Returns)
# ============================================================
def _load_cashflows_tables():
    trades = fetch_table("Trades")
    dep = fetch_table("Deposits")
    wit = fetch_table("Withdrawals")
    ret = fetch_table("ReturnsGrants")

    if trades is None: trades = pd.DataFrame()
    if dep is None: dep = pd.DataFrame()
    if wit is None: wit = pd.DataFrame()
    if ret is None: ret = pd.DataFrame()

    # تنظيف
    for df, col in [(dep, "amount"), (wit, "amount"), (ret, "amount")]:
        if df is not None and not df.empty:
            _clean_num(df, col)
            if "date" in df.columns:
                df["date"] = df["date"].apply(_to_dt)

    if trades is not None and not trades.empty:
        # تنظيف أعمدة trades
        for c in ["quantity", "entry_price", "exit_price", "current_price"]:
            _clean_num(trades, c)
        for c in ["date", "exit_date"]:
            if c in trades.columns:
                trades[c] = trades[c].apply(_to_dt)
        if "status" not in trades.columns:
            trades["status"] = "Open"
        if "asset_type" not in trades.columns:
            trades["asset_type"] = "Stock"
        trades["status"] = trades["status"].apply(_norm_status)

    return trades, dep, wit, ret


def _external_cashflows(dep: pd.DataFrame, wit: pd.DataFrame, ret: pd.DataFrame) -> pd.DataFrame:
    """
    🔸 منظور المستثمر (Investor POV):
    - الإيداع = تدفق سلبي (أنت تدفع فلوس للمحفظة)
    - السحب = تدفق إيجابي (فلوس ترجع لك)
    - العوائد/المنح = تدفق إيجابي
    """
    rows = []

    if dep is not None and not dep.empty and "date" in dep.columns:
        for _, r in dep.iterrows():
            d = r.get("date", pd.NaT)
            amt = _safe_float(r.get("amount", 0))
            if pd.isna(d) or amt == 0:
                continue
            rows.append({"date": pd.to_datetime(d).date(), "amount": -abs(amt), "type": "deposit"})

    if wit is not None and not wit.empty and "date" in wit.columns:
        for _, r in wit.iterrows():
            d = r.get("date", pd.NaT)
            amt = _safe_float(r.get("amount", 0))
            if pd.isna(d) or amt == 0:
                continue
            rows.append({"date": pd.to_datetime(d).date(), "amount": abs(amt), "type": "withdrawal"})

    if ret is not None and not ret.empty and "date" in ret.columns:
        for _, r in ret.iterrows():
            d = r.get("date", pd.NaT)
            amt = _safe_float(r.get("amount", 0))
            if pd.isna(d) or amt == 0:
                continue
            rows.append({"date": pd.to_datetime(d).date(), "amount": abs(amt), "type": "return/grant"})

    if not rows:
        return pd.DataFrame(columns=["date", "amount", "type"])

    cf = pd.DataFrame(rows)
    cf = cf.sort_values("date")
    return cf


# ============================================================
# 🧠 XIRR (IRR على تواريخ غير منتظمة)
# ============================================================
def _xnpv(rate: float, cashflows: list[tuple[date, float]]) -> float:
    """NPV لتواريخ غير منتظمة."""
    if not cashflows:
        return 0.0
    d0 = cashflows[0][0]
    total = 0.0
    for d, amt in cashflows:
        days = (d - d0).days
        total += amt / ((1.0 + rate) ** (days / 365.0))
    return total

def _xirr(cashflows: list[tuple[date, float]], guess=0.10) -> float | None:
    """
    Newton-Raphson + fallback bisection.
    يرجع نسبة مئوية (مثلاً 0.25 = 25%) أو None إذا ما ينفع.
    """
    if not cashflows or len(cashflows) < 2:
        return None

    # لازم يكون فيه تغير إشارة
    amts = [a for _, a in cashflows]
    if not (any(a > 0 for a in amts) and any(a < 0 for a in amts)):
        return None

    # Newton
    rate = float(guess)
    for _ in range(50):
        f = _xnpv(rate, cashflows)
        # مشتقة تقريبية
        eps = 1e-6
        f2 = _xnpv(rate + eps, cashflows)
        der = (f2 - f) / eps
        if abs(der) < 1e-12:
            break
        new_rate = rate - f / der
        # منع انفجار
        if not np.isfinite(new_rate):
            break
        # حدود معقولة
        if new_rate <= -0.9999:
            new_rate = -0.9999
        if abs(new_rate - rate) < 1e-8:
            return float(new_rate)
        rate = new_rate

    # Bisection fallback
    lo, hi = -0.9999, 10.0  # حتى 1000% سنوي
    f_lo = _xnpv(lo, cashflows)
    f_hi = _xnpv(hi, cashflows)
    if f_lo * f_hi > 0:
        return None

    for _ in range(80):
        mid = (lo + hi) / 2.0
        f_mid = _xnpv(mid, cashflows)
        if abs(f_mid) < 1e-8:
            return float(mid)
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid

    return float((lo + hi) / 2.0)


# ============================================================
# 📈 بناء Equity Curve يومي (لـ TWR + Risk)
# ============================================================
@st.cache_data(ttl=900, show_spinner=False)
def _build_daily_equity_curve(trades: pd.DataFrame, dep: pd.DataFrame, wit: pd.DataFrame, ret: pd.DataFrame, lookback_days=365):
    """
    يبني منحنى يومي تقريبي:
    - يعتمد على Yahoo (get_chart_history) لأسعار الإغلاق
    - يفترض: الكمية ثابتة من تاريخ الشراء حتى تاريخ الخروج (أو اليوم)
    - يحسب كاش من:
        * التدفقات الخارجية (dep/wit/ret)
        * مشتريات/مبيعات trades على entry/exit
    """
    if trades is None or trades.empty:
        return pd.DataFrame()

    # تحديد نطاق زمني
    today = pd.Timestamp.utcnow().normalize()
    start = today - pd.Timedelta(days=int(lookback_days))

    # تواريخ صفقات (entry/exit)
    t_min = trades["date"].min() if "date" in trades.columns else pd.NaT
    if pd.notna(t_min):
        start = min(start, pd.to_datetime(t_min).normalize())

    end = today

    # يوميات
    idx = pd.date_range(start=start, end=end, freq="D")
    curve = pd.DataFrame(index=idx)
    curve["external_cf"] = 0.0
    curve["trade_cf"] = 0.0
    curve["cash"] = 0.0
    curve["positions_value"] = 0.0
    curve["total_value"] = 0.0

    # External cashflows (نفس المنظور: deposits=- , withdrawals=+, returns=+)
    cf_ext = _external_cashflows(dep, wit, ret)
    if not cf_ext.empty:
        g = cf_ext.groupby("date")["amount"].sum()
        for d, amt in g.items():
            ts = pd.Timestamp(d)
            if ts in curve.index:
                curve.loc[ts, "external_cf"] += float(amt)

    # Trade cashflows:
    # Investor POV داخل الحسابات اليومية (محفظة):
    # - شراء سهم: كاش يطلع من المحفظة => trade_cf سالب
    # - بيع سهم: كاش يدخل => trade_cf موجب
    tr = trades.copy()
    tr["symbol"] = tr["symbol"].astype(str)
    tr["status"] = tr["status"].apply(_norm_status)
    if "exit_date" not in tr.columns:
        tr["exit_date"] = pd.NaT

    # تجاهل الصكوك من بناء الأسعار (قيمتها ثابتة غالباً)
    # لكن نحسب CF للشراء/البيع إن وجدت
    for _, r in tr.iterrows():
        d_in = r.get("date", pd.NaT)
        if pd.notna(d_in):
            ts = pd.to_datetime(d_in).normalize()
            cost = _safe_float(r.get("quantity", 0)) * _safe_float(r.get("entry_price", 0))
            if ts in curve.index and cost != 0:
                curve.loc[ts, "trade_cf"] += -abs(cost)

        if r.get("status") == "Close":
            d_out = r.get("exit_date", pd.NaT)
            if pd.notna(d_out):
                ts2 = pd.to_datetime(d_out).normalize()
                proceeds = _safe_float(r.get("quantity", 0)) * _safe_float(r.get("exit_price", 0))
                if ts2 in curve.index and proceeds != 0:
                    curve.loc[ts2, "trade_cf"] += abs(proceeds)

    # بناء أسعار يومية لكل رمز (Close)
    symbols = sorted(set([get_ticker_symbol(s) for s in tr["symbol"].dropna().unique().tolist()]))
    price_map = {}

    for sym in symbols:
        if not sym:
            continue
        try:
            # نجيب سنة+ احتياط
            dfp = get_chart_history(sym, period="2y", interval="1d")
            if dfp is None or dfp.empty or "Close" not in dfp.columns:
                continue
            s = dfp["Close"].copy()
            s.index = pd.to_datetime(s.index).normalize()
            s = s[~s.index.duplicated(keep="last")]
            # نعيد فهرسة يومي
            s = s.reindex(idx).ffill()
            price_map[sym] = s
        except Exception:
            continue

    # قيمة المراكز اليومية
    # نفترض: المركز موجود بين entry_date..exit_date/اليوم
    pos_val = pd.Series(0.0, index=idx)

    for _, r in tr.iterrows():
        sym_raw = r.get("symbol")
        sym = get_ticker_symbol(sym_raw)
        qty = _safe_float(r.get("quantity", 0))

        d_in = r.get("date", pd.NaT)
        if pd.isna(d_in) or qty == 0:
            continue
        start_i = pd.to_datetime(d_in).normalize()

        if r.get("status") == "Close" and pd.notna(r.get("exit_date", pd.NaT)):
            end_i = pd.to_datetime(r.get("exit_date")).normalize()
        else:
            end_i = end

        if start_i > end_i:
            continue

        if _is_sukuk(r.get("asset_type")):
            # صكوك: قيمة ثابتة تقريبياً على entry_price
            px = _safe_float(r.get("entry_price", 0))
            rng = (idx >= start_i) & (idx <= end_i)
            pos_val.loc[rng] += qty * px
            continue

        s_close = price_map.get(sym)
        if s_close is None or s_close.empty:
            # fallback: استخدم entry_price ثابت (بدل 0)
            px = _safe_float(r.get("entry_price", 0))
            rng = (idx >= start_i) & (idx <= end_i)
            pos_val.loc[rng] += qty * px
            continue

        rng = (idx >= start_i) & (idx <= end_i)
        pos_val.loc[rng] += qty * s_close.loc[rng].values

    curve["positions_value"] = pos_val.values

    # كاش يومي: نجمع كل CF
    # ملاحظة: external_cf (deposits=-/withdrawals=+/returns=+)
    # trade_cf (buys=-/sells=+)
    curve["cash"] = (curve["external_cf"] + curve["trade_cf"]).cumsum()

    curve["total_value"] = curve["cash"] + curve["positions_value"]

    # تنظيف: القيم السالبة جداً أحياناً بسبب بيانات ناقصة
    curve.replace([np.inf, -np.inf], np.nan, inplace=True)
    curve["total_value"] = curve["total_value"].fillna(method="ffill").fillna(0.0)

    return curve


def _calc_twr_from_curve(curve: pd.DataFrame) -> float | None:
    """
    TWR يومي:
    r_t = (V_t - V_{t-1} - CF_ext_t) / V_{t-1}
    حيث CF_ext_t: التدفقات الخارجية فقط (إيداع/سحب/عوائد)
    """
    if curve is None or curve.empty:
        return None
    if "total_value" not in curve.columns or "external_cf" not in curve.columns:
        return None

    v = curve["total_value"].astype(float)
    cf = curve["external_cf"].astype(float)

    v_prev = v.shift(1)
    # تجنب القسمة على صفر
    denom = v_prev.replace(0, np.nan)

    r = (v - v_prev - cf) / denom
    r = r.replace([np.inf, -np.inf], np.nan).dropna()

    if r.empty:
        return None

    twr = float(np.prod(1.0 + r.values) - 1.0)
    return twr


def _risk_from_curve(curve: pd.DataFrame) -> dict:
    """
    يحسب:
    - max drawdown
    - volatility (daily)
    - VaR 95%
    """
    out = {
        "max_drawdown_pct": None,
        "volatility_daily_pct": None,
        "var_95_daily_pct": None,
        "cagr_approx_pct": None,
    }
    if curve is None or curve.empty or "total_value" not in curve.columns:
        return out

    v = curve["total_value"].astype(float)
    ret = v.pct_change().replace([np.inf, -np.inf], np.nan).dropna()

    if not ret.empty:
        out["volatility_daily_pct"] = float(ret.std() * 100.0)
        out["var_95_daily_pct"] = float(np.nanpercentile(ret.values, 5) * 100.0)

    # Max drawdown
    roll_max = v.cummax()
    dd = (v / roll_max) - 1.0
    if not dd.empty:
        out["max_drawdown_pct"] = float(dd.min() * 100.0)

    # CAGR approximation (لو عندنا أكثر من 30 يوم)
    if len(v) > 30:
        days = (curve.index[-1] - curve.index[0]).days
        if days > 0 and v.iloc[0] > 0:
            out["cagr_approx_pct"] = float(((v.iloc[-1] / v.iloc[0]) ** (365.0 / days) - 1.0) * 100.0)

    return out


def _beta_vs_tasi(curve: pd.DataFrame) -> float | None:
    """
    Beta تقديري مقابل TASI باستخدام عوائد يومية.
    """
    try:
        if curve is None or curve.empty or "total_value" not in curve.columns:
            return None

        v = curve["total_value"].astype(float)
        r_p = v.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        if r_p.empty:
            return None

        df_t = get_chart_history("^TASI.SR", period="2y", interval="1d")
        if df_t is None or df_t.empty or "Close" not in df_t.columns:
            return None

        s = df_t["Close"].copy()
        s.index = pd.to_datetime(s.index).normalize()
        s = s[~s.index.duplicated(keep="last")]
        s = s.reindex(curve.index).ffill()

        r_m = s.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        common = r_p.index.intersection(r_m.index)
        if len(common) < 30:
            return None

        rp = r_p.loc[common].values
        rm = r_m.loc[common].values

        cov = float(np.cov(rp, rm)[0, 1])
        var = float(np.var(rm))
        if var <= 1e-12:
            return None
        return cov / var
    except Exception:
        return None


# ============================================================
# ✅ Portfolio Metrics (المنطق الحالي + إضافات XIRR/TWR/Risk)
# ============================================================
@st.cache_data(ttl=60, show_spinner=False)
def calculate_portfolio_metrics(include_performance=True, lookback_days=365):
    """
    ✅ منطقك الحالي (Cashflow-based) + إضافات اختيارية:
    - XIRR (MWR)
    - TWR
    - Risk: max drawdown, vol, VaR, beta
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
        # إضافات
        "portfolio_value": 0.0,
        "xirr_pct": None,
        "twr_pct": None,
        "risk": {},
        "beta_vs_tasi": None,
        "equity_curve": pd.DataFrame(),
    }

    try:
        trades, dep, wit, ret = _load_cashflows_tables()

        # totals
        total_dep = dep["amount"].sum() if dep is not None and not dep.empty and "amount" in dep.columns else 0.0
        total_wit = wit["amount"].sum() if wit is not None and not wit.empty and "amount" in wit.columns else 0.0
        total_ret = ret["amount"].sum() if ret is not None and not ret.empty and "amount" in ret.columns else 0.0

        total_dep = _safe_float(total_dep)
        total_wit = _safe_float(total_wit)
        total_ret = _safe_float(total_ret)

        # إذا لا توجد صفقات
        if trades is None or trades.empty:
            cash = (total_dep + total_ret) - total_wit
            res = default_res.copy()
            res.update({
                "total_deposited": total_dep,
                "total_withdrawn": total_wit,
                "total_returns": total_ret,
                "cash": _safe_float(cash),
                "portfolio_value": _safe_float(cash),
                "deposits": dep, "withdrawals": wit, "returns": ret,
                "all_trades": trades if trades is not None else pd.DataFrame()
            })
            # أداء اختياري (لو عندك تدفقات فقط)
            if include_performance:
                cf = _external_cashflows(dep, wit, ret)
                if not cf.empty:
                    cashflows = [(d, a) for d, a in zip(cf["date"], cf["amount"])]
                    # القيمة النهائية = الكاش الحالي (تدفق موجب)
                    cashflows.append((date.today(), _safe_float(cash)))
                    irr = _xirr(cashflows)
                    res["xirr_pct"] = None if irr is None else float(irr * 100.0)
            return res

        # --- تجهيز trades ---
        trades = trades.copy()

        # إجمالي التكلفة
        trades["total_cost"] = trades["quantity"] * trades["entry_price"]

        # تحديد مغلق/مفتوح بدقة
        is_closed = (
            (trades["exit_price"] > 0) |
            (trades["status"].astype(str).str.lower().isin(["close", "closed", "sold", "مغلقة"])) |
            (trades["exit_date"].notna() & (trades["exit_date"].astype(str) != "None") & (trades["exit_date"].astype(str) != "NaT"))
        )
        trades["status"] = np.where(is_closed, "Close", "Open")

        # تحديث current_price:
        # - المغلقة: current_price = exit_price
        trades.loc[trades["status"] == "Close", "current_price"] = trades.loc[trades["status"] == "Close", "exit_price"]

        # - الصكوك المفتوحة: current_price = entry_price
        is_open_sukuk = (trades["status"] == "Open") & (trades["asset_type"].apply(_is_sukuk))
        trades.loc[is_open_sukuk, "current_price"] = trades.loc[is_open_sukuk, "entry_price"]

        # - البقية: fill
        trades["current_price"] = trades["current_price"].replace(0, np.nan).fillna(trades["entry_price"])

        # الحسابات
        trades["market_value"] = trades["quantity"] * trades["current_price"]
        trades["gain"] = trades["market_value"] - trades["total_cost"]

        trades["gain_pct"] = 0.0
        mask = trades["total_cost"] != 0
        trades.loc[mask, "gain_pct"] = (trades.loc[mask, "gain"] / trades.loc[mask, "total_cost"]) * 100.0

        open_trades = trades[trades["status"] == "Open"]
        closed_trades = trades[trades["status"] == "Close"]

        # --- كاش دقيق (منطقك الحالي) ---
        cash_inflow = total_dep + total_ret + closed_trades["market_value"].sum()
        cash_outflow = total_wit + trades["total_cost"].sum()
        cash_calculated = _safe_float(cash_inflow - cash_outflow)

        portfolio_value = _safe_float(cash_calculated + open_trades["market_value"].sum())

        res = default_res.copy()
        res.update({
            "cost_open": _safe_float(open_trades["total_cost"].sum()),
            "market_val_open": _safe_float(open_trades["market_value"].sum()),
            "unrealized_pl": _safe_float(open_trades["gain"].sum()),
            "realized_pl": _safe_float(closed_trades["gain"].sum()),
            "cash": cash_calculated,
            "portfolio_value": portfolio_value,
            "total_deposited": total_dep,
            "total_withdrawn": total_wit,
            "total_returns": total_ret,
            "all_trades": trades,
            "deposits": dep, "withdrawals": wit, "returns": ret,
        })

        # ====================================================
        # ✅ Performance إضافي (XIRR + TWR + Risk)
        # ====================================================
        if include_performance:
            # 1) XIRR (MWR)
            cf = _external_cashflows(dep, wit, ret)
            cashflows = []
            if not cf.empty:
                cashflows = [(d, a) for d, a in zip(cf["date"], cf["amount"])]

            # القيمة النهائية تدفق موجب
            cashflows.append((date.today(), portfolio_value))

            irr = _xirr(cashflows, guess=0.12)
            res["xirr_pct"] = None if irr is None else float(irr * 100.0)

            # 2) TWR (من منحنى يومي)
            curve = _build_daily_equity_curve(trades, dep, wit, ret, lookback_days=int(lookback_days))
            res["equity_curve"] = curve

            twr = _calc_twr_from_curve(curve) if curve is not None and not curve.empty else None
            res["twr_pct"] = None if twr is None else float(twr * 100.0)

            # 3) Risk
            res["risk"] = _risk_from_curve(curve)
            res["beta_vs_tasi"] = _beta_vs_tasi(curve)

        return res

    except Exception as e:
        st.error(f"خطأ في التحليل المالي: {e}")
        return default_res


# ============================================================
# 💹 Update Prices (Yahoo + Argaam) + Quality Flags
# ============================================================
def update_prices(stale_minutes=30):
    """
    تحديث أسعار الأسهم المفتوحة (غير صكوك):
    - يعتمد على market_data.fetch_batch_data (Yahoo + Argaam فقط حسب طلبك)
    - يضيف Quality flags: source + updated_at + is_stale
    """
    try:
        _ensure_price_quality_columns()

        df = fetch_table("Trades")
        if df is None or df.empty:
            return True

        # تطبيع أعمدة
        if "status" not in df.columns:
            df["status"] = "Open"
        if "asset_type" not in df.columns:
            df["asset_type"] = "Stock"

        df["status"] = df["status"].apply(_norm_status)

        open_mask = (df["status"] == "Open") & (~df["asset_type"].apply(_is_sukuk))
        open_stocks = df.loc[open_mask, "symbol"].dropna().astype(str).unique().tolist()
        if not open_stocks:
            return True

        live_data = fetch_batch_data(open_stocks)

        now_ts = _now_utc()

        for sym in open_stocks:
            data = live_data.get(sym) or {}
            price = _safe_float(data.get("price", 0.0))
            source = str(data.get("source", "none") or "none").lower()

            # إذا السعر 0: نعلمه stale/none ولا نحدّث current_price
            if price > 0:
                execute_query(
                    """
                    UPDATE trades
                    SET current_price=%s,
                        current_price_source=%s,
                        current_price_updated_at=%s,
                        current_price_is_stale=0
                    WHERE symbol=%s AND status='Open'
                    """,
                    (price, source, now_ts, sym)
                )
            else:
                # علّمها stale فقط
                execute_query(
                    """
                    UPDATE trades
                    SET current_price_source=%s,
                        current_price_updated_at=%s,
                        current_price_is_stale=1
                    WHERE symbol=%s AND status='Open'
                    """,
                    (source, now_ts, sym)
                )

        # إذا تبي “stale” حسب الزمن: نقدر نحدّثه هنا (اختياري)
        try:
            execute_query(
                """
                UPDATE trades
                SET current_price_is_stale = 1
                WHERE status='Open'
                  AND current_price_updated_at IS NOT NULL
                  AND current_price_updated_at < (NOW() - INTERVAL '%s minutes')
                """,
                (int(stale_minutes),)
            )
        except Exception:
            pass

        st.cache_data.clear()
        return True

    except Exception as e:
        st.error(f"فشل تحديث الأسعار: {e}")
        return False


# ============================================================
# 📉 Equity Curve بسيط (منطقك السابق) + احتياطي
# ============================================================
def generate_equity_curve(trades_df: pd.DataFrame):
    """
    منحنى تراكمي بسيط (ليس TWR)، مفيد للعرض السريع.
    """
    if trades_df is None or trades_df.empty or "date" not in trades_df.columns:
        return pd.DataFrame()
    df = trades_df.copy()
    try:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        if "total_cost" not in df.columns:
            df["total_cost"] = pd.to_numeric(df.get("quantity", 0), errors="coerce").fillna(0) * pd.to_numeric(df.get("entry_price", 0), errors="coerce").fillna(0)
        df["cumulative_invested"] = df["total_cost"].cumsum()
        return df
    except Exception:
        return pd.DataFrame()


# ============================================================
# 🧠 Backup
# ============================================================
def create_smart_backup():
    try:
        from backup_system import generate_full_backup
        return generate_full_backup()
    except Exception as e:
        st.error(f"فشل النسخ الاحتياطي: {e}")
        return None, None