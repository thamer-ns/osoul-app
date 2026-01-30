import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from market_data import get_chart_history


# ============================================================
# 🧮 Helpers
# ============================================================
def _to_float(x, default=0.0) -> float:
    try:
        if x is None:
            return float(default)
        if isinstance(x, (np.floating, np.integer)):
            return float(x)
        if isinstance(x, float) and np.isnan(x):
            return float(default)
        return float(x)
    except Exception:
        return float(default)


def _safe_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    # تأكد من الأعمدة
    for col in ["Open", "High", "Low", "Close"]:
        if col not in df.columns:
            return pd.DataFrame()
    # ترتيب
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.sort_index()
    # تنظيف قيم غير صالحة
    for c in ["Open", "High", "Low", "Close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    return df


# ============================================================
# 🧷 Fibonacci
# ============================================================
def calculate_fibonacci_levels(df: pd.DataFrame, lookback: int = 90, trend: str = "Uptrend") -> dict:
    """
    ✅ فيبوناتشي قياسي على آخر lookback شمعة.
    trend:
      - Uptrend: Low -> High, retracements from High downwards
      - Downtrend: High -> Low, retracements from Low upwards
    """
    if df is None or df.empty or len(df) < 30:
        return {}

    w = df.tail(int(max(30, lookback))).copy()
    hi = _to_float(w["High"].max(), 0.0)
    lo = _to_float(w["Low"].min(), 0.0)
    diff = hi - lo
    if diff <= 0:
        return {}

    if trend == "Downtrend":
        # قياس من High إلى Low: مستويات التصحيح صعوداً من القاع
        base_low = lo
        levels = {
            "Low (0%)": base_low,
            "23.6%": base_low + 0.236 * diff,
            "38.2%": base_low + 0.382 * diff,
            "50.0%": base_low + 0.500 * diff,
            "61.8%": base_low + 0.618 * diff,
            "78.6%": base_low + 0.786 * diff,
            "High (100%)": hi,
        }
        meta = {"trend": "Downtrend", "hi": hi, "lo": lo}
        return {"levels": levels, "meta": meta}

    # Uptrend (default): مستويات التصحيح نزولاً من القمة
    base_high = hi
    levels = {
        "High (0%)": base_high,
        "23.6%": base_high - 0.236 * diff,
        "38.2%": base_high - 0.382 * diff,
        "50.0%": base_high - 0.500 * diff,
        "61.8%": base_high - 0.618 * diff,
        "78.6%": base_high - 0.786 * diff,
        "Low (100%)": lo,
    }
    meta = {"trend": "Uptrend", "hi": hi, "lo": lo}
    return {"levels": levels, "meta": meta}


# ============================================================
# 📍 Pivot Points (Standard) — Daily/Weekly/Monthly
# ============================================================
def _standard_pivots_from_ohlc(H: float, L: float, C: float) -> dict:
    H = _to_float(H)
    L = _to_float(L)
    C = _to_float(C)
    if H <= 0 or L <= 0 or C <= 0:
        return {}
    PP = (H + L + C) / 3.0
    R1 = (2 * PP) - L
    S1 = (2 * PP) - H
    R2 = PP + (H - L)
    S2 = PP - (H - L)
    return {"PP": PP, "R1": R1, "R2": R2, "S1": S1, "S2": S2}


def calculate_daily_pivots(df: pd.DataFrame) -> dict:
    """
    Pivot يومي على شمعة أمس المكتملة (Daily).
    """
    if df is None or df.empty or len(df) < 3:
        return {}
    last = df.iloc[-2]
    return _standard_pivots_from_ohlc(last["High"], last["Low"], last["Close"])


def calculate_weekly_pivots(df: pd.DataFrame) -> dict:
    """
    Pivot أسبوعي على آخر أسبوع مكتمل:
    - نجمع أسبوعياً (W-FRI) لأنه يناسب تداول (الجمعة إغلاق أسبوعي غالباً).
    - نأخذ الأسبوع قبل الأخير لأن الأخير قد يكون غير مكتمل حسب اليوم.
    """
    if df is None or df.empty or len(df) < 40:
        return {}
    if not isinstance(df.index, pd.DatetimeIndex):
        return {}

    wk = df.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    if len(wk) < 2:
        return {}
    last_complete = wk.iloc[-2]  # الأسبوع المكتمل
    return _standard_pivots_from_ohlc(last_complete["High"], last_complete["Low"], last_complete["Close"])


def calculate_monthly_pivots(df: pd.DataFrame) -> dict:
    """
    Pivot شهري على آخر شهر مكتمل.
    """
    if df is None or df.empty or len(df) < 60:
        return {}
    if not isinstance(df.index, pd.DatetimeIndex):
        return {}

    mo = df.resample("M").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    if len(mo) < 2:
        return {}
    last_complete = mo.iloc[-2]  # الشهر المكتمل
    return _standard_pivots_from_ohlc(last_complete["High"], last_complete["Low"], last_complete["Close"])


# ============================================================
# 🧠 Level verdict: Break/Bounce
# ============================================================
def _level_break_or_bounce(df: pd.DataFrame, level: float, tol_pct: float = 0.6) -> str:
    """
    تشخيص بسيط وآمن حول مستوى معيّن:
    - كسر لأعلى: إغلاقين متتاليين فوق المستوى + هامش tol
    - كسر لأسفل: إغلاقين متتاليين تحت المستوى + هامش tol
    - ارتداد: لمس قريب + إغلاق رجع فوق/تحت
    """
    if df is None or df.empty or len(df) < 3 or level <= 0:
        return ""

    c0 = _to_float(df["Close"].iloc[-1])
    c1 = _to_float(df["Close"].iloc[-2])
    l0 = _to_float(df["Low"].iloc[-1])
    h0 = _to_float(df["High"].iloc[-1])

    tol = (tol_pct / 100.0) * max(level, 1e-9)

    # Breakouts: 2 closes confirm
    if (c0 > level + tol) and (c1 > level + tol):
        return "📈 كسر مؤكد لأعلى (إغلاقين فوق المستوى)"
    if (c0 < level - tol) and (c1 < level - tol):
        return "📉 كسر مؤكد لأسفل (إغلاقين تحت المستوى)"

    # Bounce / rejection
    touched = (abs(l0 - level) <= tol) or (abs(h0 - level) <= tol) or (abs(c0 - level) <= tol)
    if touched:
        if (l0 <= level + tol) and (c0 > level + tol):
            return "🔄 ارتداد محتمل لأعلى (لمس/قرب + إغلاق أعلى)"
        if (h0 >= level - tol) and (c0 < level - tol):
            return "🔄 ارتداد محتمل لأسفل (لمس/قرب + إغلاق أسفل)"
        return "👀 قرب شديد من المستوى (بدون تأكيد كسر/ارتداد)"

    return ""


# ============================================================
# 🏛️ Main UI
# ============================================================
def render_classical_analysis(symbol: str):
    st.markdown("### 🏛️ التحليل الكلاسيكي (Price Action & Pivot Points)")

    # نجيب بيانات يومية فقط لتفادي اختلاف pivots
    df = get_chart_history(symbol, period="18mo", interval="1d")
    df = _safe_df(df)

    if df.empty or len(df) < 80:
        st.warning("بيانات غير كافية للتحليل الكلاسيكي")
        return

    curr_price = _to_float(df["Close"].iloc[-1])
    if curr_price <= 0:
        st.warning("سعر الإغلاق غير صالح.")
        return

    # =========================
    # ⚙️ إعدادات
    # =========================
    st.markdown("#### ⚙️ إعدادات العرض")
    a1, a2, a3, a4 = st.columns(4)
    with a1:
        fib_lookback = st.selectbox("نطاق فيبوناتشي", [60, 90, 120, 180, 240], index=1)
    with a2:
        fib_trend = st.selectbox("اتجاه فيبوناتشي", ["Uptrend", "Downtrend"], index=0)
    with a3:
        show_fibs = st.checkbox("إظهار فيبوناتشي", value=True)
    with a4:
        show_pivots = st.checkbox("إظهار Pivot", value=True)

    tol_pct = st.slider("حساسية القرب من المستوى (%)", 0.1, 2.0, 0.6, 0.1)

    # أي pivots تظهر؟
    if show_pivots:
        p1, p2, p3 = st.columns(3)
        with p1:
            show_daily = st.checkbox("Daily Pivot", value=True)
        with p2:
            show_weekly = st.checkbox("Weekly Pivot", value=True)
        with p3:
            show_monthly = st.checkbox("Monthly Pivot", value=False)
    else:
        show_daily = show_weekly = show_monthly = False

    # حساب المستويات
    piv_daily = calculate_daily_pivots(df) if show_daily else {}
    piv_weekly = calculate_weekly_pivots(df) if show_weekly else {}
    piv_monthly = calculate_monthly_pivots(df) if show_monthly else {}

    fib_pack = calculate_fibonacci_levels(df, lookback=fib_lookback, trend=fib_trend) if show_fibs else {}
    fibs = (fib_pack.get("levels") if fib_pack else {}) or {}
    fib_meta = (fib_pack.get("meta") if fib_pack else {}) or {}

    # =========================
    # 📈 Chart
    # =========================
    plot_df = df.tail(120)

    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=plot_df.index,
            open=plot_df["Open"],
            high=plot_df["High"],
            low=plot_df["Low"],
            close=plot_df["Close"],
            name="السعر",
        )
    )

    # Pivots drawing helper
    def _draw_pivots(piv: dict, prefix: str, colors: dict):
        if not piv:
            return
        lines = [
            (piv.get("R2"), f"{prefix} R2", colors.get("R", "red")),
            (piv.get("R1"), f"{prefix} R1", colors.get("R", "red")),
            (piv.get("PP"), f"{prefix} PP", colors.get("PP", "black")),
            (piv.get("S1"), f"{prefix} S1", colors.get("S", "green")),
            (piv.get("S2"), f"{prefix} S2", colors.get("S", "green")),
        ]
        for level, name, color in lines:
            level = _to_float(level)
            if level <= 0:
                continue
            fig.add_hline(
                y=level,
                line_dash="dashdot",
                line_color=color,
                line_width=1,
                annotation_text=f"{name}: {level:.2f}",
                annotation_position="bottom right",
            )

    # draw pivots with slightly different color themes
    _draw_pivots(piv_daily, "Daily", {"R": "#D50000", "S": "#00C853", "PP": "#000000"})
    _draw_pivots(piv_weekly, "Weekly", {"R": "#B71C1C", "S": "#1B5E20", "PP": "#263238"})
    _draw_pivots(piv_monthly, "Monthly", {"R": "#880E4F", "S": "#004D40", "PP": "#37474F"})

    # Fibonacci lines (تمييز 50/61.8)
    if fibs:
        for name, level in fibs.items():
            level = _to_float(level)
            if level <= 0:
                continue
            is_key = name in ("61.8%", "50.0%")
            fig.add_hline(
                y=level,
                line_dash="solid" if is_key else "dot",
                line_color="gold" if name == "61.8%" else "gray",
                line_width=2 if is_key else 1,
                annotation_text=f"Fib {name}: {level:.2f}",
                annotation_position="top left",
            )

    # title details
    title_extra = ""
    if fib_meta:
        title_extra = f" | Fib({fib_meta.get('trend')}, hi={_to_float(fib_meta.get('hi')):.2f}, lo={_to_float(fib_meta.get('lo')):.2f})"

    fig.update_layout(
        title=f"خريطة المستويات الرئيسية لـ {symbol}{title_extra}",
        height=560,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=35, b=10),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # =========================
    # 🔢 Metrics (Daily/Weekly/Monthly)
    # =========================
    def _metrics_block(piv: dict, label: str):
        if not piv:
            st.info(f"{label}: غير متاح")
            return
        st.markdown(f"#### 🔢 {label}")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("R2", f"{_to_float(piv['R2']):.2f}", delta_color="inverse")
        c2.metric("R1", f"{_to_float(piv['R1']):.2f}", delta_color="inverse")
        c3.metric("PP", f"{_to_float(piv['PP']):.2f}", delta=round(curr_price - _to_float(piv["PP"]), 2))
        c4.metric("S1", f"{_to_float(piv['S1']):.2f}")
        c5.metric("S2", f"{_to_float(piv['S2']):.2f}")

    if show_pivots:
        if show_daily:
            _metrics_block(piv_daily, "Daily Pivot (على شمعة أمس)")
        if show_weekly:
            _metrics_block(piv_weekly, "Weekly Pivot (آخر أسبوع مكتمل)")
        if show_monthly:
            _metrics_block(piv_monthly, "Monthly Pivot (آخر شهر مكتمل)")

    # =========================
    # 💡 Smart Verdict
    # =========================
    st.markdown("---")
    st.markdown("### 💡 الخلاصة الكلاسيكية الذكية")

    # 1) Pivot bias priority: Daily then Weekly then Monthly
    pivot_bias_msg = None
    pivot_bias_type = "info"

    def _bias_from_piv(piv: dict, label: str):
        if not piv:
            return None, "info"
        pp = _to_float(piv.get("PP"))
        if pp <= 0:
            return None, "info"
        if curr_price > pp:
            return f"✅ {label}: السعر فوق PP — ميل إيجابي (راقب R1/R2)", "success"
        return f"🔻 {label}: السعر تحت PP — ميل سلبي (راقب S1/S2)", "error"

    for piv, lbl in [(piv_daily, "Daily"), (piv_weekly, "Weekly"), (piv_monthly, "Monthly")]:
        msg, typ = _bias_from_piv(piv, lbl)
        if msg:
            pivot_bias_msg, pivot_bias_type = msg, typ
            break

    if pivot_bias_msg:
        if pivot_bias_type == "success":
            st.success(pivot_bias_msg)
        elif pivot_bias_type == "error":
            st.error(pivot_bias_msg)
        else:
            st.info(pivot_bias_msg)
    else:
        st.info("Pivot غير متاحة حالياً (تعذر حسابها من البيانات).")

    # 2) Closest level verdict (Fib + all shown pivots)
    levels_pool = {}

    if fibs:
        levels_pool.update({f"Fib {k}": _to_float(v) for k, v in fibs.items()})

    if piv_daily:
        levels_pool.update({f"Daily {k}": _to_float(v) for k, v in piv_daily.items()})
    if piv_weekly:
        levels_pool.update({f"Weekly {k}": _to_float(v) for k, v in piv_weekly.items()})
    if piv_monthly:
        levels_pool.update({f"Monthly {k}": _to_float(v) for k, v in piv_monthly.items()})

    # تنظيف pool من القيم الصفرية
    levels_pool = {k: v for k, v in levels_pool.items() if v and v > 0}

    if levels_pool:
        closest_name, closest_level = min(levels_pool.items(), key=lambda x: abs(x[1] - curr_price))
        dist_pct = abs(curr_price - closest_level) / max(curr_price, 1e-9) * 100.0
        st.write(
            f"**أقرب مستوى حالياً:** {closest_name} = **{closest_level:.2f}** | "
            f"البعد: **{dist_pct:.2f}%**"
        )

        msg = _level_break_or_bounce(df, closest_level, tol_pct=tol_pct)
        if msg:
            if "كسر مؤكد" in msg and "لأعلى" in msg:
                st.success(msg)
            elif "كسر مؤكد" in msg and "لأسفل" in msg:
                st.error(msg)
            elif "ارتداد" in msg:
                st.warning(msg)
            else:
                st.info(msg)
    else:
        st.info("لا توجد مستويات لعرضها.")