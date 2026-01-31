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
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n).mean()


def _pivot_points(series: pd.Series, left=3, right=3, mode="high"):
    """Return list of (i, value) where i is positional index"""
    if series is None or len(series) < left + right + 3:
        return []
    arr = series.values
    pivots = []
    for i in range(left, len(arr) - right):
        w = arr[i - left : i + right + 1]
        if mode == "high":
            if arr[i] == np.nanmax(w):
                pivots.append((i, float(arr[i])))
        else:
            if arr[i] == np.nanmin(w):
                pivots.append((i, float(arr[i])))
    return pivots


# ============================================================
# ✅ Zones + Confirmation
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
    vma = (
        float(df["Volume"].rolling(20).mean().iloc[-1])
        if "Volume" in df.columns and len(df) >= 20
        else 0.0
    )
    ok = (vma > 0) and (v >= factor * vma)
    return v, vma, ok


def _cross_up(close, prev_close, level):
    return (close > level) and (prev_close <= level)


def _cross_down(close, prev_close, level):
    return (close < level) and (prev_close >= level)


# ============================================================
# ✅ Fibonacci (Swing-based)
# ============================================================
def _fib_from_range(swing_low: float, swing_high: float, direction="up"):
    lo = float(swing_low)
    hi = float(swing_high)
    diff = hi - lo
    if diff == 0:
        return {}

    if direction == "up":
        return {
            "Fib 100% (Top)": hi,
            "Fib 78.6%": hi - (0.214 * diff),
            "Fib 61.8% (Golden)": hi - (0.382 * diff),
            "Fib 50%": hi - (0.5 * diff),
            "Fib 38.2%": hi - (0.618 * diff),
            "Fib 23.6%": hi - (0.764 * diff),
            "Fib 0% (Bottom)": lo,
        }
    else:
        return {
            "Fib 100% (Bottom)": lo,
            "Fib 78.6%": lo + (0.214 * (hi - lo)),
            "Fib 61.8% (Golden)": lo + (0.382 * (hi - lo)),
            "Fib 50%": lo + (0.5 * (hi - lo)),
            "Fib 38.2%": lo + (0.618 * (hi - lo)),
            "Fib 23.6%": lo + (0.764 * (hi - lo)),
            "Fib 0% (Top)": hi,
        }


def calculate_swing_fibonacci_levels(df: pd.DataFrame, left=3, right=3):
    if df is None or len(df) < 60:
        return {}, {"ok": False, "reason": "not enough data"}

    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    ph = _pivot_points(high, left=left, right=right, mode="high")
    pl = _pivot_points(low, left=left, right=right, mode="low")

    if not ph or not pl:
        hh = float(high.tail(120).max())
        ll = float(low.tail(120).min())
        if hh <= ll:
            return {}, {"ok": False, "reason": "bad range"}
        return (
            _fib_from_range(ll, hh, direction="up"),
            {"ok": True, "fallback": True, "swing_low": ll, "swing_high": hh, "direction": "up"},
        )

    last_hi_i, last_hi = ph[-1]
    last_lo_i, last_lo = pl[-1]

    if last_lo_i < last_hi_i:
        swing_low, swing_high, direction = last_lo, last_hi, "up"
    else:
        # آخر حركة ممكن تكون هبوط (نخلي الاتجاه down للتصحيح فوق القاع)
        swing_low, swing_high, direction = last_lo, last_hi, "down"

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

    if timeframe == "Daily":
        if len(dfx) < 2:
            return None
        use = dfx.iloc[-2]  # أمس المكتمل
        ts = str(dfx.index[-2].date()) if isinstance(dfx.index, pd.DatetimeIndex) else "prev"
        return {"H": float(use["High"]), "L": float(use["Low"]), "C": float(use["Close"]), "O": float(use["Open"]), "ts": ts}

    if timeframe == "Weekly":
        wk = dfx.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
        wk.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
        if len(wk) < 2:
            return None
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


def _calc_pivots_for_tf(df: pd.DataFrame, tf: str, pivot_type: str):
    src = _get_last_completed_ohlc(df, tf)
    if not src:
        return {}, None
    H, L, C, O = src["H"], src["L"], src["C"], src["O"]
    if pivot_type == "Standard":
        return pivot_standard(H, L, C), src
    if pivot_type == "Camarilla":
        return pivot_camarilla(H, L, C), src
    return pivot_woodie(H, L, C, O), src


# ============================================================
# ✅ Auto Support/Resistance (Clustered from pivots)
# ============================================================
def _cluster_levels(levels: list[float], tol: float):
    """
    يجمع المستويات المتقاربة ضمن tol (سعر).
    يرجع قائمة مستويات "ممثلة" (متوسط المجموعة).
    """
    if not levels:
        return []
    lv = sorted([float(x) for x in levels if np.isfinite(x)])
    clusters = []
    cur = [lv[0]]
    for x in lv[1:]:
        if abs(x - np.mean(cur)) <= tol:
            cur.append(x)
        else:
            clusters.append(float(np.mean(cur)))
            cur = [x]
    clusters.append(float(np.mean(cur)))
    return clusters


def auto_support_resistance_levels(df: pd.DataFrame, lookback=220, left=3, right=3, max_levels=10):
    """
    يطلع مستويات دعم/مقاومة من pivot highs/lows ويعمل clustering لتقليل الضوضاء.
    """
    if df is None or df.empty or len(df) < max(80, left + right + 10):
        return [], []

    d = df.tail(int(lookback)).copy()
    high = d["High"].astype(float)
    low = d["Low"].astype(float)

    ph = _pivot_points(high, left=left, right=right, mode="high")
    pl = _pivot_points(low, left=left, right=right, mode="low")

    res = [p[1] for p in ph]
    sup = [p[1] for p in pl]

    atr_last = float(_atr(d, 14).iloc[-1]) if len(d) >= 20 else 0.0
    close_last = float(d["Close"].iloc[-1])
    tol = max(0.35 * atr_last, 0.004 * close_last)  # tolerance

    res_c = _cluster_levels(res, tol=tol)[-max_levels:]
    sup_c = _cluster_levels(sup, tol=tol)[-max_levels:]

    return sup_c, res_c


# ============================================================
# 🏛️ MAIN UI
# ============================================================
def render_classical_analysis(symbol: str):
    st.markdown("### 🏛️ التحليل الكلاسيكي المطوّر (Multi-Pivots + Swing Fib + Auto S/R + Zones + ATR/Volume)")

    df = get_chart_history(symbol, period="2y", interval="1d")
    df = _ensure_ohlcv(df)

    if df.empty or len(df) < 150:
        st.warning("بيانات غير كافية (نحتاج تقريباً 150 يوم أو أكثر).")
        return

    # Indicators
    df["SMA200"] = df["Close"].rolling(200).mean()
    df["ATR14"] = _atr(df, 14)
    df["VOL_MA20"] = df["Volume"].rolling(20).mean()

    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else last_close
    last_atr = float(df["ATR14"].iloc[-1]) if not pd.isna(df["ATR14"].iloc[-1]) else 0.0
    last_sma200 = float(df["SMA200"].iloc[-1]) if not pd.isna(df["SMA200"].iloc[-1]) else np.nan

    # --------------------------------------------------------
    # Controls
    # --------------------------------------------------------
    colA, colB, colC, colD = st.columns([1.25, 1.25, 1.25, 1.25])
    pivot_type = colA.selectbox("Pivot Type", ["Standard", "Camarilla", "Woodie"], index=0)
    show_zones = colB.checkbox("Zones بدل Lines", value=True)
    show_fib = colC.checkbox("إظهار Fibonacci Swing", value=True)
    show_sr = colD.checkbox("إظهار Auto Support/Resistance", value=True)

    colE, colF, colG, colH = st.columns([1.25, 1.25, 1.25, 1.25])
    show_daily = colE.checkbox("Daily Pivots", value=True)
    show_weekly = colF.checkbox("Weekly Pivots", value=True)
    show_monthly = colG.checkbox("Monthly Pivots", value=False)
    fib_sens = colH.selectbox("Swing Sensitivity", ["3", "5", "7"], index=0)

    # --------------------------------------------------------
    # Compute Pivots (multi)
    # --------------------------------------------------------
    pivots_pack = []  # list of dict: {tf, pivots, src}
    if show_daily:
        p, src = _calc_pivots_for_tf(df, "Daily", pivot_type)
        if p and src:
            pivots_pack.append({"tf": "Daily", "pivots": p, "src": src})
    if show_weekly:
        p, src = _calc_pivots_for_tf(df, "Weekly", pivot_type)
        if p and src:
            pivots_pack.append({"tf": "Weekly", "pivots": p, "src": src})
    if show_monthly:
        p, src = _calc_pivots_for_tf(df, "Monthly", pivot_type)
        if p and src:
            pivots_pack.append({"tf": "Monthly", "pivots": p, "src": src})

    # --------------------------------------------------------
    # Fibonacci Swing
    # --------------------------------------------------------
    fibs, fib_meta = ({}, {})
    if show_fib:
        left = right = int(fib_sens)
        fibs, fib_meta = calculate_swing_fibonacci_levels(df, left=left, right=right)

    # --------------------------------------------------------
    # Auto S/R
    # --------------------------------------------------------
    supports, resistances = ([], [])
    if show_sr:
        supports, resistances = auto_support_resistance_levels(df, lookback=240, left=3, right=3, max_levels=10)

    # --------------------------------------------------------
    # Chart
    # --------------------------------------------------------
    plot_df = df.tail(160).copy()

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

    # SMA200
    if not np.isnan(last_sma200):
        fig.add_trace(
            go.Scatter(
                x=plot_df.index,
                y=plot_df["SMA200"],
                mode="lines",
                name="SMA200",
                line=dict(width=2, color="#1f77b4"),
            )
        )

    # -------- Fib levels
    if show_fib and fibs:
        for name, level in fibs.items():
            y = float(level)
            lo, hi, w = _zone_bounds(y, last_atr, last_close)

            if "Golden" in name:
                color, width, dash = "gold", 2, "solid"
            elif "Top" in name or "Bottom" in name:
                color, width, dash = "gray", 1, "dot"
            else:
                color, width, dash = "#4c78a8", 1, "dot"

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

    # -------- Pivots (multi TF) with different opacity
    tf_style = {
        "Daily": {"opacity": 0.08, "dash": "dashdot"},
        "Weekly": {"opacity": 0.10, "dash": "dash"},
        "Monthly": {"opacity": 0.12, "dash": "solid"},
    }

    for pack in pivots_pack:
        tf = pack["tf"]
        piv = pack["pivots"]
        src = pack["src"]
        dash = tf_style.get(tf, {}).get("dash", "dash")
        op = tf_style.get(tf, {}).get("opacity", 0.09)
        ts = src.get("ts", "")

        order = [k for k in ["R4", "R3", "R2", "R1", "PP", "S1", "S2", "S3", "S4"] if k in piv]
        for k in order:
            y = float(piv[k])
            lo, hi, w = _zone_bounds(y, last_atr, last_close)

            if k.startswith("R"):
                color = "#d62728"
            elif k.startswith("S"):
                color = "#2ca02c"
            else:
                color = "#000000"

            label = f"{tf} {pivot_type} {k} ({ts})"

            if show_zones:
                fig.add_hrect(
                    y0=lo, y1=hi,
                    fillcolor=color, opacity=op,
                    line_width=0,
                    annotation_text=label,
                    annotation_position="bottom right"
                )
            else:
                fig.add_hline(
                    y=y,
                    line_dash=dash, line_color=color, line_width=1,
                    annotation_text=f"{label}: {y:.2f}",
                    annotation_position="bottom right"
                )

    # -------- Auto S/R
    if show_sr:
        # draw as thinner zones/lines to avoid clutter
        for lvl in supports:
            y = float(lvl)
            lo, hi, w = _zone_bounds(y, last_atr, last_close)
            if show_zones:
                fig.add_hrect(y0=lo, y1=hi, fillcolor="#2ca02c", opacity=0.06, line_width=0,
                              annotation_text=f"Auto Support {y:.2f}", annotation_position="bottom left")
            else:
                fig.add_hline(y=y, line_dash="dot", line_color="#2ca02c", line_width=1)

        for lvl in resistances:
            y = float(lvl)
            lo, hi, w = _zone_bounds(y, last_atr, last_close)
            if show_zones:
                fig.add_hrect(y0=lo, y1=hi, fillcolor="#d62728", opacity=0.06, line_width=0,
                              annotation_text=f"Auto Resistance {y:.2f}", annotation_position="top left")
            else:
                fig.add_hline(y=y, line_dash="dot", line_color="#d62728", line_width=1)

    fig.update_layout(
        title=f"خريطة المستويات لـ {symbol}",
        height=560,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # --------------------------------------------------------
    # Summary Cards
    # --------------------------------------------------------
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
    d4.metric("تأكيد الحجم", "✅ قوي" if vol_ok else ("⚠️ ضعيف" if vma > 0 else "N/A"))

    # --------------------------------------------------------
    # Verdict: Two scenarios using nearest key levels
    # --------------------------------------------------------
    st.markdown("---")
    st.markdown("### 🧠 الخلاصة (سيناريوهين + فلترة الاتجاه + تأكيد الحجم)")

    # Nearest fib info
    if show_fib and fibs:
        closest_name, closest_lvl = min(fibs.items(), key=lambda x: abs(float(x[1]) - last_close))
        lo, hi, w = _zone_bounds(float(closest_lvl), last_atr, last_close)
        if lo <= last_close <= hi:
            st.info(f"💡 السعر داخل Zone قرب **{closest_name}** ({float(closest_lvl):.2f}) | سماحية≈{w:.2f}")
        else:
            st.info(f"📌 أقرب فيبو: **{closest_name}** ({float(closest_lvl):.2f})")

    # Pick a primary pivot set for scenarios:
    # priority: Weekly -> Daily -> Monthly (because weekly levels are usually more meaningful)
    primary = None
    for want in ["Weekly", "Daily", "Monthly"]:
        for pack in pivots_pack:
            if pack["tf"] == want:
                primary = pack
                break
        if primary:
            break

    # Determine scenario levels (prefer pivot R1/S1, else auto SR, else fib)
    scen_up_name, scen_up = ("-", np.nan)
    scen_dn_name, scen_dn = ("-", np.nan)

    if primary and primary.get("pivots"):
        p = primary["pivots"]
        if "R1" in p:
            scen_up_name, scen_up = (f"{primary['tf']} R1", float(p["R1"]))
        if "S1" in p:
            scen_dn_name, scen_dn = (f"{primary['tf']} S1", float(p["S1"]))

    # fallback to auto SR
    if np.isnan(scen_up) and resistances:
        # nearest resistance above price
        above_res = sorted([x for x in resistances if x > last_close])
        if above_res:
            scen_up_name, scen_up = ("Auto Resistance", float(above_res[0]))

    if np.isnan(scen_dn) and supports:
        below_sup = sorted([x for x in supports if x < last_close])
        if below_sup:
            scen_dn_name, scen_dn = ("Auto Support", float(below_sup[-1]))

    # fallback to fib
    if (np.isnan(scen_up) or np.isnan(scen_dn)) and fibs:
        fb = sorted([(k, float(v)) for k, v in fibs.items()], key=lambda x: x[1])
        above = [x for x in fb if x[1] > last_close]
        below = [x for x in fb if x[1] < last_close]
        if np.isnan(scen_up) and above:
            scen_up_name, scen_up = (above[0][0], above[0][1])
        if np.isnan(scen_dn) and below:
            scen_dn_name, scen_dn = (below[-1][0], below[-1][1])

    # Trend/pivot conflict notes
    if primary and primary.get("pivots") and "PP" in primary["pivots"]:
        pp = float(primary["pivots"]["PP"])
        if not np.isnan(last_sma200):
            if (last_close > pp) and (not trend_is_bull):
                st.warning("⚠️ فوق Pivot لكن تحت SMA200: الأفضل مضاربة/ارتداد بحذر (احتمال كسر كاذب).")
            elif (last_close < pp) and trend_is_bull:
                st.warning("⚠️ تحت Pivot لكن فوق SMA200: قد يكون تصحيح داخل ترند صاعد.")
            else:
                st.success("✅ Pivot و Trend متوافقين (قراءة أنظف).")

    # Break confirmations
    up_break = (not np.isnan(scen_up)) and _cross_up(last_close, prev_close, float(scen_up))
    dn_break = (not np.isnan(scen_dn)) and _cross_down(last_close, prev_close, float(scen_dn))

    cA, cB = st.columns(2)

    with cA:
        st.markdown("#### 🚀 سيناريو اختراق (Bullish)")
        if np.isnan(scen_up):
            st.info("لا يوجد مستوى اختراق واضح حالياً.")
        else:
            lo, hi, w = _zone_bounds(float(scen_up), last_atr, last_close)
            st.write(f"- مستوى الاختراق: **{scen_up_name} = {float(scen_up):.2f}** (Zone ±{w:.2f})")
            if up_break and vol_ok:
                st.success("✅ اختراق + حجم مؤكد (إشارة أقوى لاستمرار).")
            elif up_break and not vol_ok:
                st.warning("⚠️ اختراق بدون حجم قوي (راقب الكسر الكاذب).")
            else:
                st.info("📌 لم يحدث اختراق مؤكد بعد (انتظر إغلاق واضح فوق المستوى).")

            # Target: next resistance from pivots/autoSR/fib
            target = None
            if primary and "R2" in primary.get("pivots", {}):
                target = float(primary["pivots"]["R2"])
            elif resistances:
                above_res = sorted([x for x in resistances if x > float(scen_up)])
                if above_res:
                    target = float(above_res[0])
            elif fibs:
                above_lvls = sorted([float(v) for v in fibs.values() if float(v) > float(scen_up)])
                if above_lvls:
                    target = float(above_lvls[0])

            if target is not None:
                st.write(f"- هدف محتمل: **{target:.2f}**")
            st.caption("Invalidation: رجوع وإغلاق تحت Zone الاختراق.")

    with cB:
        st.markdown("#### 🧨 سيناريو كسر (Bearish)")
        if np.isnan(scen_dn):
            st.info("لا يوجد مستوى كسر واضح حالياً.")
        else:
            lo, hi, w = _zone_bounds(float(scen_dn), last_atr, last_close)
            st.write(f"- مستوى الكسر: **{scen_dn_name} = {float(scen_dn):.2f}** (Zone ±{w:.2f})")
            if dn_break and vol_ok:
                st.error("⛔ كسر + حجم مؤكد (إشارة أقوى لاستمرار هبوط).")
            elif dn_break and not vol_ok:
                st.warning("⚠️ كسر بدون حجم قوي (راقب الكسر الكاذب).")
            else:
                st.info("📌 لم يحدث كسر مؤكد بعد (انتظر إغلاق واضح تحت المستوى).")

            # Target: next support from pivots/autoSR/fib
            target = None
            if primary and "S2" in primary.get("pivots", {}):
                target = float(primary["pivots"]["S2"])
            elif supports:
                below_sup = sorted([x for x in supports if x < float(scen_dn)])
                if below_sup:
                    target = float(below_sup[-1])
            elif fibs:
                below_lvls = sorted([float(v) for v in fibs.values() if float(v) < float(scen_dn)])
                if below_lvls:
                    target = float(below_lvls[-1])

            if target is not None:
                st.write(f"- هدف محتمل: **{target:.2f}**")
            st.caption("Invalidation: رجوع وإغلاق فوق Zone الكسر.")

    # --------------------------------------------------------
    # Debug/Explain (optional)
    # --------------------------------------------------------
    with st.expander("🧾 تفاصيل الحساب (للتوثيق وتجنب سوء الفهم)"):
        st.write("**Fib Meta:**", fib_meta if show_fib else "Fib disabled")
        st.write("**Pivots Used:**", [{"tf": p["tf"], "src": p["src"], "keys": list(p["pivots"].keys())} for p in pivots_pack])
        st.write("**Auto S/R:**", {"supports": supports, "resistances": resistances})
        st.write("**Volume:**", {"today_volume": v, "vol_ma20": vma, "confirmed": vol_ok})