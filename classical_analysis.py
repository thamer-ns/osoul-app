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
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return float(default)
        return float(x)
    except Exception:
        return float(default)


def calculate_fibonacci_levels(df: pd.DataFrame, lookback: int = 90) -> dict:
    """
    ✅ فيبوناتشي قياسي على آخر lookback شمعة.
    نفترض Trend صاعد داخل النافذة: من Low إلى High
    مستويات التصحيح = من High نزولاً:
      23.6% / 38.2% / 50% / 61.8% / 78.6%
    """
    if df is None or df.empty or len(df) < 30:
        return {}

    w = df.tail(int(max(30, lookback))).copy()
    hi = _to_float(w["High"].max(), 0.0)
    lo = _to_float(w["Low"].min(), 0.0)
    diff = hi - lo
    if diff <= 0:
        return {}

    levels = {
        "High (0%)": hi,
        "23.6%": hi - 0.236 * diff,
        "38.2%": hi - 0.382 * diff,
        "50.0%": hi - 0.500 * diff,
        "61.8%": hi - 0.618 * diff,
        "78.6%": hi - 0.786 * diff,
        "Low (100%)": lo,
    }
    return levels


def calculate_daily_pivots(df: pd.DataFrame) -> dict:
    """
    ✅ Pivot Points Standard على شمعة أمس المكتملة (اليومي فقط).
    """
    if df is None or df.empty or len(df) < 3:
        return {}

    last = df.iloc[-2]  # أمس
    H = _to_float(last["High"])
    L = _to_float(last["Low"])
    C = _to_float(last["Close"])

    if H <= 0 or L <= 0 or C <= 0:
        return {}

    PP = (H + L + C) / 3.0
    R1 = (2 * PP) - L
    S1 = (2 * PP) - H
    R2 = PP + (H - L)
    S2 = PP - (H - L)

    return {"PP": PP, "R1": R1, "R2": R2, "S1": S1, "S2": S2}


def _level_break_or_bounce(df: pd.DataFrame, level: float, tol_pct: float = 0.35) -> str:
    """
    ✅ تشخيص بسيط وآمن حول أقرب مستوى:
    - كسر لأعلى: إغلاقين متتاليين فوق المستوى
    - كسر لأسفل: إغلاقين متتاليين تحت المستوى
    - ارتداد: لمس قريب + إغلاق رجع فوق/تحت
    - قرب فقط: داخل نطاق التحمّل بدون تأكيد
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

    # Bounce logic (touch within tol and reject)
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

    # ثابت يومي لتفادي لخبطة Pivot
    df = get_chart_history(symbol, period="6mo", interval="1d")
    if df is None or df.empty or len(df) < 40:
        st.warning("بيانات غير كافية للتحليل الكلاسيكي")
        return

    # حماية أعمدة
    for col in ["Open", "High", "Low", "Close"]:
        if col not in df.columns:
            st.warning("البيانات لا تحتوي أعمدة OHLC المطلوبة.")
            return

    curr_price = _to_float(df["Close"].iloc[-1])
    if curr_price <= 0:
        st.warning("سعر الإغلاق غير صالح.")
        return

    # إعدادات
    st.markdown("#### ⚙️ إعدادات العرض")
    a1, a2, a3 = st.columns(3)
    with a1:
        fib_lookback = st.selectbox("نطاق فيبوناتشي", [60, 90, 120, 180], index=1)
    with a2:
        show_fibs = st.checkbox("إظهار فيبوناتشي", value=True)
    with a3:
        show_pivots = st.checkbox("إظهار Pivot اليومية", value=True)

    tol_pct = st.slider("حساسية القرب من المستوى (%)", 0.1, 2.0, 0.6, 0.1)

    piv = calculate_daily_pivots(df) if show_pivots else {}
    fibs = calculate_fibonacci_levels(df, lookback=fib_lookback) if show_fibs else {}

    # --- Chart ---
    fig = go.Figure()
    plot_df = df.tail(90)

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

    # Pivot lines
    if piv:
        pivot_levels = [
            (piv["R2"], "R2", "red"),
            (piv["R1"], "R1", "red"),
            (piv["PP"], "Pivot", "black"),
            (piv["S1"], "S1", "green"),
            (piv["S2"], "S2", "green"),
        ]
        for level, name, color in pivot_levels:
            fig.add_hline(
                y=_to_float(level),
                line_dash="dashdot",
                line_color=color,
                line_width=1,
                annotation_text=f"Daily {name}: {_to_float(level):.2f}",
                annotation_position="bottom right",
            )

    # Fibonacci lines (أقل تزاحم: نميّز 50/61.8)
    if fibs:
        for name, level in fibs.items():
            level = _to_float(level)
            is_key = name in ("61.8%", "50.0%")
            fig.add_hline(
                y=level,
                line_dash="solid" if is_key else "dot",
                line_color="gold" if name == "61.8%" else "gray",
                line_width=2 if is_key else 1,
                annotation_text=f"Fib {name}: {level:.2f}",
                annotation_position="top left",
            )

    fig.update_layout(
        title=f"خريطة المستويات الرئيسية لـ {symbol}",
        height=520,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- Metrics ---
    if piv:
        st.markdown("#### 🔢 Pivot اليومية (مبنية على شمعة أمس)")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("المقاومة 2", f"{piv['R2']:.2f}", delta_color="inverse")
        c2.metric("المقاومة 1", f"{piv['R1']:.2f}", delta_color="inverse")
        c3.metric("الارتكاز (PP)", f"{piv['PP']:.2f}", delta=round(curr_price - piv["PP"], 2))
        c4.metric("الدعم 1", f"{piv['S1']:.2f}")
        c5.metric("الدعم 2", f"{piv['S2']:.2f}")

    # --- Smart Verdict ---
    st.markdown("---")
    st.markdown("### 💡 الخلاصة الكلاسيكية الذكية")

    # 1) Pivot verdict
    if piv:
        if curr_price > piv["PP"]:
            st.success("✅ السعر فوق Pivot اليومي — الميل قصير المدى إيجابي (راقب R1 ثم R2).")
        else:
            st.error("🔻 السعر تحت Pivot اليومي — الميل قصير المدى سلبي (راقب S1 ثم S2).")
    else:
        st.info("Pivot غير متاحة (تعذر حسابها من بيانات الأمس).")

    # 2) Closest level verdict (Fib أو Pivot حسب المتاح)
    levels_pool = {}
    if fibs:
        levels_pool.update({f"Fib {k}": _to_float(v) for k, v in fibs.items()})
    if piv:
        levels_pool.update({f"Pivot {k}": _to_float(v) for k, v in piv.items()})

    if levels_pool:
        closest_name, closest_level = min(levels_pool.items(), key=lambda x: abs(x[1] - curr_price))
        dist_pct = abs(curr_price - closest_level) / max(curr_price, 1e-9) * 100.0

        msg = _level_break_or_bounce(df, closest_level, tol_pct=tol_pct)
        st.write(f"**أقرب مستوى:** {closest_name} = **{closest_level:.2f}** | البعد: **{dist_pct:.2f}%**")

        if msg:
            # تصنيف بصري بسيط
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