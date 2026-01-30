# classical_analysis.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from market_data import get_chart_history


# ============================================================
# ✅ Helpers: Safety / Normalization
# ============================================================
def _ensure_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # Normalize MultiIndex columns (yfinance sometimes)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Normalize column names
    rename = {}
    for c in df.columns:
        base = c[0] if isinstance(c, (tuple, list)) and len(c) else c
        s = str(base).strip()
        rename[c] = s.title() if s else s
    df.rename(columns=rename, inplace=True)

    # Ensure OHLCV
    if "Close" not in df.columns:
        return pd.DataFrame()

    if "Open" not in df.columns:
        df["Open"] = df["Close"]
    for col in ["High", "Low"]:
        if col not in df.columns:
            df[col] = df["Close"]
    if "Volume" not in df.columns:
        df["Volume"] = 0.0

    # Sort index
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.sort_index()

    # Cast numeric
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
    return df


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(n).mean()
    return atr


def _pivot_points(series: pd.Series, left=3, right=3, mode="high"):
    """Return list of (i, value) where i is positional index"""
    if series is None or len(series) < left + right + 3:
        return []

    arr = series.values
    pivots = []
    for i in range(left, len(arr) - right):
        w = arr[i - left: i + right + 1]
        if mode == "high":
            if arr[i] == np.nanmax(w):
                pivots.append((i, float(arr[i])))
        else:
            if arr[i] == np.nanmin(w):
                pivots.append((i, float(arr[i])))
    return pivots


# ============================================================
# ✅ Fibonacci (Swing-based, not max/min)
# ============================================================
def calculate_swing_fibonacci_levels(df: pd.DataFrame, left=3, right=3):
    """
    يبني فيبوناتشي على آخر موجة Swing (آخر قاع/قمة واضحين).
    يرجع: dict(level_name -> price), meta
    """
    if df is None or len(df) < 60:
        return {}, {"ok": False, "reason": "not enough data"}

    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    ph = _pivot_points(high, left=left, right=right, mode="high")
    pl = _pivot_points(low, left=left, right=right, mode="low")

    if not ph or not pl:
        # fallback بسيط
        hh = float(high.tail(120).max())
        ll = float(low.tail(120).min())
        if hh <= ll:
            return {}, {"ok": False, "reason": "bad range"}
        return _fib_from_range(ll, hh, direction="up"), {"ok": True, "fallback": True, "swing_low": ll, "swing_high": hh}

    # pick last pivot high/low
    last_hi_i, last_hi = ph[-1]
    last_lo_i, last_lo = pl[-1]

    # Determine last impulse direction using which came later
    if last_lo_i < last_hi_i:
        # impulse up: low -> high
        swing_low, swing_high = last_lo, last_hi
        direction = "up"
    else:
        # impulse down: high -> low
        swing_low, swing_high = last_lo, last_hi
        direction = "down"

    if swing_high == swing_low:
        return {}, {"ok": False, "reason": "flat"}

    levels = _fib_from_range(swing_low, swing_high, direction=direction)
    meta = {
        "ok": True,
        "fallback": False,
        "direction": direction,
        "swing_low": float(swing_low),
        "swing_high": float(swing_high),
    }
    return levels, meta


def _fib_from_range(swing_low: float, swing_high: float, direction="up"):
    """
    Standard retracement levels:
    0, 23.6, 38.2, 50, 61.8, 78.6, 100
    """
    lo = float(swing_low)
    hi = float(swing_high)
    diff = hi - lo
    if diff == 0:
        return {}

    ratios = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    out = {}

    if direction == "up":
        # from low to high, retracements are below top
        out["Fib 100% (Top)"] = hi
        out["Fib 78.6%"] = hi - (0.214 * diff)   # (1 - 0.786)=0.214
        out["Fib 61.8% (Golden)"] = hi - (0.382 * diff)
        out["Fib 50%"] = hi - (0.5 * diff)
        out["Fib 38.2%"] = hi - (0.618 * diff)
        out["Fib 23.6%"] = hi - (0.764 * diff)
        out["Fib 0% (Bottom)"] = lo
    else:
        # impulse down: high to low, retracements are above bottom
        out["Fib 100% (Bottom)"] = lo
        out["Fib 78.6%"] = lo + (0.214 * (hi - lo))
        out["Fib 61.8% (Golden)"] = lo + (0.382 * (hi - lo))
        out["Fib 50%"] = lo + (0.5 * (hi - lo))
        out["Fib 38.2%"] = lo + (0.618 * (hi - lo))
        out["Fib 23.6%"] = lo + (0.764 * (hi - lo))
        out["Fib 0% (Top)"] = hi

    return out


# ============================================================
# ✅ Pivot Points (Standard / Woodie / Camarilla)
# ============================================================
def pivot_standard(H, L, C):
    PP = (H + L + C) / 3
    R1 = (2 * PP) - L
    S1 = (2 * PP) - H
    R2 = PP + (H - L)
    S2 = PP - (H - L)
    R3 = H + 2 * (PP - L)
    S3 = L - 2 * (H - PP)
    return {"PP": PP, "R1": R1, "S1": S1, "R2": R2, "S2": S2, "R3": R3, "S3": S3}


def pivot_woodie(H, L, C, O):
    PP = (H + L + 2 * O) / 4
    R1 = (2 * PP) - L
    S1 = (2 * PP) - H
    R2 = PP + (H - L)
    S2 = PP - (H - L)
    return {"PP": PP, "R1": R1, "S1": S1, "R2": R2, "S2": S2}


def pivot_camarilla(H, L, C):
    rng = (H - L)
    if rng <= 0:
        return {"PP": C}
    R1 = C + (rng * 1.1 / 12)
    S1 = C - (rng * 1.1 / 12)
    R2 = C + (rng * 1.1 / 6)
    S2 = C - (rng * 1.1 / 6)
    R3 = C + (rng * 1.1 / 4)
    S3 = C - (rng * 1.1 / 4)
    R4 = C + (rng * 1.1 / 2)
    S4 = C - (rng * 1.1 / 2)
    return {"PP": C, "R1": R1, "S1": S1, "R2": R2, "S2": S2, "R3": R3, "S3": S3, "R4": R4, "S4": S4}


def _get_last_completed_ohlc(df: pd.DataFrame, timeframe: str):
    """
    timeframe: "Daily", "Weekly", "Monthly"
    يرجع dict: H,L,C,O, ts_label
    """
    if df is None or df.empty:
        return None

    dfx = df.copy()

    # We'll exclude "today" candle for daily pivots if market candle not closed.
    # safest: always use the last *completed* candle -> take -2 if last index is today
    if timeframe == "Daily":
        if len(dfx) < 2:
            return None
        last = dfx.iloc[-1]
        prev = dfx.iloc[-2]

        # if last candle is same date as "now" (server timezone unknown), still safest to use prev
        # we simply use prev candle for daily pivots always.
        use = prev
        ts = str(dfx.index[-2].date()) if isinstance(dfx.index, pd.DatetimeIndex) else "prev"
        return {"H": float(use["High"]), "L": float(use["Low"]), "C": float(use["Close"]), "O": float(use["Open"]), "ts": ts}

    if timeframe == "Weekly":
        # resample to weeks ending Friday for Tadawul (approx)
        wk = dfx.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
        wk.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
        if len(wk) < 2:
            return None
        # last full week is wk.iloc[-2]
        use = wk.iloc[-2]
        ts = str(wk.index[-2].date())
        return {"H": float(use["High"]), "L": float(use["Low"]), "C": float(use["Close"]), "O": float(use["Open"]), "ts": ts}

    if timeframe == "Monthly":
        mo = dfx.resample("M").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
        mo.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
        if len(mo) < 2:
            return None
        use = mo.iloc[-2]
        ts = str(mo.index[-2].date())
        return {"H": float(use["High"]), "L": float(use["Low"]), "C": float(use["Close"]), "O": float(use["Open"]), "ts": ts}

    return None


# ============================================================
# ✅ Zones + Breakout confirmation (ATR + Volume)
# ============================================================
def _zone_bounds(level: float, atr_val: float, close: float):
    """
    Zone width:
    - uses ATR as primary (0.5 ATR)
    - and price percent as fallback (0.5%)
    """
    lv = float(level)
    c = float(close) if close and close > 0 else lv
    w_atr = 0.5 * float(atr_val) if atr_val and atr_val > 0 else 0.0
    w_pct = 0.005 * c
    w = max(w_atr, w_pct, 0.0)
    return lv - w, lv + w, w


def _vol_confirm(df: pd.DataFrame, factor=1.2):
    if df is None or df.empty:
        return 0.0, 0.0, False
    v = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0.0
    vma = float(df["Volume"].rolling(20).mean().iloc[-1]) if "Volume" in df.columns and len(df) >= 20 else 0.0
    ok = (vma > 0) and (v >= factor * vma)
    return v, vma, ok


def _cross_up(close, prev_close, level):
    return (close > level) and (prev_close <= level)


def _cross_down(close, prev_close, level):
    return (close < level) and (prev_close >= level)


# ============================================================
# 🏛️ MAIN UI
# ============================================================
def render_classical_analysis(symbol: str):
    st.markdown("### 🏛️ التحليل الكلاسيكي المطوّر (Fib Swing + Pivot + Zones + ATR + Volume)")

    df = get_chart_history(symbol, period="2y", interval="1d")
    df = _ensure_ohlcv(df)

    if df.empty or len(df) < 120:
        st.warning("بيانات غير كافية (نحتاج على الأقل ~120 يوم).")
        return

    # Indicators
    df["SMA200"] = df["Close"].rolling(200).mean()
    df["ATR14"] = _atr(df, 14)
    df["VOL_MA20"] = df["Volume"].rolling(20).mean()

    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else last_close
    last_atr = float(df["ATR14"].iloc[-1]) if not pd.isna(df["ATR14"].iloc[-1]) else 0.0
    last_sma200 = float(df["SMA200"].iloc[-1]) if not pd.isna(df["SMA200"].iloc[-1]) else np.nan

    # UI controls
    c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.2, 1.4])
    pivot_type = c1.selectbox("Pivot Type", ["Standard", "Camarilla", "Woodie"], index=0)
    pivot_tf = c2.selectbox("Pivot Timeframe", ["Daily", "Weekly", "Monthly"], index=0)
    fib_sens = c3.selectbox("Swing Sensitivity", ["3", "5", "7"], index=0)
    show_zones = c4.checkbox("إظهار Zones بدل Lines", value=True)

    # ----------------------------
    # 1) Pivots (Daily/Weekly/Monthly)
    # ----------------------------
    piv_src = _get_last_completed_ohlc(df, pivot_tf)
    pivots = {}
    piv_label = ""
    if piv_src:
        H, L, C, O = piv_src["H"], piv_src["L"], piv_src["C"], piv_src["O"]
        piv_label = piv_src["ts"]
        if pivot_type == "Standard":
            pivots = pivot_standard(H, L, C)
        elif pivot_type == "Camarilla":
            pivots = pivot_camarilla(H, L, C)
        else:
            pivots = pivot_woodie(H, L, C, O)

    # ----------------------------
    # 2) Swing Fibonacci
    # ----------------------------
    left = right = int(fib_sens)
    fibs, fib_meta = calculate_swing_fibonacci_levels(df, left=left, right=right)

    # ----------------------------
    # 3) Chart
    # ----------------------------
    plot_df = df.tail(140).copy()  # enough context

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=plot_df.index,
        open=plot_df["Open"], high=plot_df["High"],
        low=plot_df["Low"], close=plot_df["Close"],
        name="السعر"
    ))

    # Add SMA200 for trend filter visibility
    if not np.isnan(last_sma200):
        fig.add_trace(go.Scatter(
            x=plot_df.index, y=plot_df["SMA200"],
            mode="lines", name="SMA200",
            line=dict(width=2, color="#1f77b4")
        ))

    # Fib levels as lines/zones
    if fibs:
        for name, level in fibs.items():
            y = float(level)
            lo, hi, w = _zone_bounds(y, last_atr, last_close)

            # colors
            if "Golden" in name:
                color = "gold"
                width = 2
                dash = "solid"
            elif "Top" in name or "Bottom" in name:
                color = "gray"
                width = 1
                dash = "dot"
            else:
                color = "#4c78a8"
                width = 1
                dash = "dot"

            if show_zones:
                fig.add_hrect(
                    y0=lo, y1=hi,
                    fillcolor=color, opacity=0.12,
                    line_width=0,
                    annotation_text=name,
                    annotation_position="top left"
                )
            else:
                fig.add_hline(
                    y=y,
                    line_dash=dash, line_color=color, line_width=width,
                    annotation_text=f"{name}: {y:.2f}",
                    annotation_position="top left"
                )

    # Pivot levels lines/zones
    if pivots:
        # ordered display
        pivot_keys = [k for k in ["R4", "R3", "R2", "R1", "PP", "S1", "S2", "S3", "S4"] if k in pivots]
        for k in pivot_keys:
            y = float(pivots[k])
            lo, hi, w = _zone_bounds(y, last_atr, last_close)

            if k.startswith("R"):
                color = "#d62728"
            elif k.startswith("S"):
                color = "#2ca02c"
            else:
                color = "#000000"

            label = f"{pivot_tf} {pivot_type} {k} ({piv_label})"
            if show_zones:
                fig.add_hrect(
                    y0=lo, y1=hi,
                    fillcolor=color, opacity=0.08,
                    line_width=0,
                    annotation_text=label,
                    annotation_position="bottom right"
                )
            else:
                fig.add_hline(
                    y=y,
                    line_dash="dashdot", line_color=color, line_width=1,
                    annotation_text=f"{label}: {y:.2f}",
                    annotation_position="bottom right"
                )

    fig.update_layout(
        title=f"خريطة المستويات لـ {symbol}",
        height=520,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)

    # ----------------------------
    # 4) Dashboard numbers
    # ----------------------------
    st.markdown("#### 🔢 ملخص سريع")

    trend_is_bull = False
    trend_note = "غير متاح"
    if not np.isnan(last_sma200):
        trend_is_bull = last_close > last_sma200
        trend_note = "صاعد (فوق SMA200)" if trend_is_bull else "هابط (تحت SMA200)"

    v, vma, vol_ok = _vol_confirm(df, factor=1.2)

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("السعر الحالي", f"{last_close:.2f}")
    d2.metric("Trend Filter", trend_note)
    d3.metric("ATR(14)", f"{last_atr:.3f}" if last_atr > 0 else "N/A")
    d4.metric("Volume Confirm", "✅ قوي" if vol_ok else ("⚠️ ضعيف" if vma > 0 else "N/A"))

    # ----------------------------
    # 5) Intelligent verdict (Scenario-based)
    # ----------------------------
    st.markdown("---")
    st.markdown("### 🧠 الخلاصة (سيناريوهين + فلترة الاتجاه + تأكيد الحجم)")

    # Choose key pivot levels for scenarios
    pp = float(pivots.get("PP", np.nan)) if pivots else np.nan
    r1 = float(pivots.get("R1", np.nan)) if pivots else np.nan
    s1 = float(pivots.get("S1", np.nan)) if pivots else np.nan

    # Nearest fib level
    fib_msg = ""
    if fibs:
        closest_name, closest_lvl = min(fibs.items(), key=lambda x: abs(float(x[1]) - last_close))
        lo, hi, w = _zone_bounds(float(closest_lvl), last_atr, last_close)
        if lo <= last_close <= hi:
            fib_msg = f"💡 السعر داخل Zone قرب **{closest_name}** ({float(closest_lvl):.2f}) | سماحية≈{w:.2f}"
        else:
            fib_msg = f"📌 أقرب فيبو: **{closest_name}** ({float(closest_lvl):.2f})"

    if fib_msg:
        st.info(fib_msg)

    # Pivot bias (but filtered)
    if not np.isnan(pp):
        if last_close > pp:
            raw_bias = "إيجابي فوق Pivot"
        else:
            raw_bias = "سلبي تحت Pivot"

        # Trend filter adjustment
        if trend_note != "غير متاح":
            if (last_close > pp) and (not trend_is_bull):
                st.warning("⚠️ Pivot إيجابي لكن Trend العام هابط (تفضيل مضاربة/ارتداد بحذر).")
            elif (last_close < pp) and (trend_is_bull):
                st.warning("⚠️ Pivot سلبي لكن Trend العام صاعد (قد يكون تصحيح داخل ترند صاعد).")
            else:
                st.success(f"✅ اتجاه Pivot: {raw_bias}")
        else:
            st.info(f"Pivot Bias: {raw_bias}")

    # Scenario levels: prefer R1/S1; if missing, fall back to closest fib zones
    if np.isnan(r1) or np.isnan(s1):
        # fallback: pick two fib levels around price
        fb = sorted([(k, float(v)) for k, v in (fibs or {}).items()], key=lambda x: x[1])
        above = [x for x in fb if x[1] > last_close]
        below = [x for x in fb if x[1] < last_close]
        r_level = above[0] if above else None
        s_level = below[-1] if below else None
        scen_up_name, scen_up = (r_level[0], r_level[1]) if r_level else ("-", np.nan)
        scen_dn_name, scen_dn = (s_level[0], s_level[1]) if s_level else ("-", np.nan)
    else:
        scen_up_name, scen_up = ("R1", r1)
        scen_dn_name, scen_dn = ("S1", s1)

    # Breakout confirmation logic
    up_break = (not np.isnan(scen_up)) and _cross_up(last_close, prev_close, float(scen_up))
    dn_break = (not np.isnan(scen_dn)) and _cross_down(last_close, prev_close, float(scen_dn))

    # Scenario blocks
    cA, cB = st.columns(2)

    with cA:
        st.markdown("#### 🚀 سيناريو اختراق (Bullish)")
        if np.isnan(scen_up):
            st.info("لا يوجد مستوى اختراق واضح حالياً.")
        else:
            lo, hi, w = _zone_bounds(float(scen_up), last_atr, last_close)
            st.write(f"- مستوى الاختراق: **{scen_up_name} = {float(scen_up):.2f}** (Zone ±{w:.2f})")
            if up_break:
                if vol_ok:
                    st.success("✅ تم الاختراق + حجم مؤكد (أقوى احتمال استمرار).")
                else:
                    st.warning("⚠️ تم الاختراق لكن بدون تأكيد حجم قوي (احتمال كسر كاذب).")
            else:
                st.info("📌 لم يحدث اختراق مؤكد بعد (انتظر إغلاق واضح فوق المستوى).")

            # Targets: next pivot R2 (if exists) or next fib above
            target = pivots.get("R2") if pivots and "R2" in pivots else None
            if target is None and fibs:
                above_lvls = sorted([float(v) for v in fibs.values() if float(v) > last_close])
                target = above_lvls[1] if len(above_lvls) > 1 else (above_lvls[0] if above_lvls else None)

            if target is not None:
                st.write(f"- هدف محتمل: **{float(target):.2f}**")
            st.caption("Invalidation: رجوع وإغلاق تحت Zone الاختراق.")

    with cB:
        st.markdown("#### 🧨 سيناريو كسر (Bearish)")
        if np.isnan(scen_dn):
            st.info("لا يوجد مستوى كسر واضح حالياً.")
        else:
            lo, hi, w = _zone_bounds(float(scen_dn), last_atr, last_close)
            st.write(f"- مستوى الكسر: **{scen_dn_name} = {float(scen_dn):.2f}** (Zone ±{w:.2f})")
            if dn_break:
                if vol_ok:
                    st.error("⛔ تم الكسر + حجم مؤكد (أقوى احتمال استمرار هبوط).")
                else:
                    st.warning("⚠️ تم الكسر لكن بدون تأكيد حجم قوي (قد يكون كسر كاذب).")
            else:
                st.info("📌 لم يحدث كسر مؤكد بعد (انتظر إغلاق واضح تحت المستوى).")

            # Targets: next pivot S2 (if exists) or next fib below
            target = pivots.get("S2") if pivots and "S2" in pivots else None
            if target is None and fibs:
                below_lvls = sorted([float(v) for v in fibs.values() if float(v) < last_close])
                target = below_lvls[-2] if len(below_lvls) > 1 else (below_lvls[-1] if below_lvls else None)

            if target is not None:
                st.write(f"- هدف محتمل: **{float(target):.2f}**")
            st.caption("Invalidation: رجوع وإغلاق فوق Zone الكسر.")

    # Extra notes: swing meta
    with st.expander("🧾 تفاصيل حساب Swing Fib / Pivots (للتوثيق)"):
        st.write("**Swing Fib Meta:**", fib_meta)
        st.write("**Pivot Candle Used:**", piv_src if piv_src else "N/A")
        st.write("**Volume:**", {"today_volume": v, "vol_ma20": vma, "confirmed": vol_ok})