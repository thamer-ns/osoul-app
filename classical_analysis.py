# classical_analysis.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from market_data import get_chart_history

# Optional: unify tables with the app's table renderer
try:
    from components import render_custom_table
except Exception:
    render_custom_table = None



# ============================================================
# ✅ Helpers: Safety / Normalization
# ============================================================
def _norm_interval(interval: str) -> str:
    itv = str(interval or "").strip().lower()
    # عربي -> yfinance
    if itv in ["ساعة", "1h", "hour", "1hour", "60m"]:
        return "60m"
    if itv in ["يوم", "daily", "day", "1d"]:
        return "1d"
    if itv in ["أسبوع", "اسبوع", "week", "weekly", "1w", "1wk", "1wk"]:
        return "1wk"
    if itv in ["شهر", "month", "monthly", "1mo"]:
        return "1mo"
    return itv or "1d"


def _fetch_history(symbol: str, interval: str, years: int = 5, period=None) -> pd.DataFrame:
    """
    ✅ يجلب التاريخ بفاصل محدد.
    - إذا market_data.get_chart_history يدعم years=5/period=None: يستخدمه
    - وإلا يعمل fallback على الطريقة القديمة
    """
    itv = _norm_interval(interval)
    try:
        # النسخة الجديدة التي نريدها
        df = get_chart_history(symbol, period=period, interval=itv, years=years)
    except TypeError:
        # fallback للنسخة القديمة (period/interval فقط)
        # للـ intraday غالباً 60d
        if itv in ["60m", "30m", "15m", "5m", "1m", "2m", "90m"]:
            df = get_chart_history(symbol, period or "60d", itv)
        else:
            df = get_chart_history(symbol, period or "5y", itv)
    except Exception:
        df = pd.DataFrame()

    return df


def _ensure_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    تنظيف أعمدة OHLCV:
    Open, High, Low, Close, Volume
    + التعامل مع MultiIndex وlowercase وأعمدة غير نصية.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    d = df.copy()

    # MultiIndex -> خذ level المناسب
    if isinstance(d.columns, pd.MultiIndex):
        # غالباً المستوى 0 هو OHLCV
        d.columns = d.columns.get_level_values(0)

    # اجعل الأعمدة نصية
    d.columns = [str(c[0] if isinstance(c, (tuple, list)) and len(c) else c) for c in d.columns]

    def pick(name: str):
        target = name.lower().replace("_", "").replace("-", "").strip()
        for cand in d.columns:
            key = str(cand).lower().replace("_", "").replace("-", "").strip()
            if key == target:
                return cand
        return None

    o = pick("open")
    h = pick("high")
    l = pick("low")
    c = pick("close")
    v = pick("volume")

    # Adj Close fallback
    if c is None:
        adj = pick("adj close") or pick("adjclose")
        if adj is not None:
            c = adj

    if c is None:
        return pd.DataFrame()

    if o is None:
        d["Open"] = d[c]
        o = "Open"
    if h is None:
        d["High"] = d[c]
        h = "High"
    if l is None:
        d["Low"] = d[c]
        l = "Low"
    if v is None:
        d["Volume"] = 0.0
        v = "Volume"

    out = d.rename(columns={o: "Open", h: "High", l: "Low", c: "Close", v: "Volume"})

    # Sort index
    try:
        if not isinstance(out.index, pd.DatetimeIndex):
            out.index = pd.to_datetime(out.index, errors="coerce")
        out = out.sort_index()
    except Exception:
        pass

    # Cast numeric
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["Open", "High", "Low", "Close"])
    return out



# ============================================================
# ✅ UI Helpers (Cards/Tables) - Additive only
# ============================================================
def _os_card(title: str, rows: list, icon: str = "insights"):
    """Small card using the CSS already defined in styles.py (.os-card / .os-kv)."""
    try:
        body = ""
        for k, v in (rows or []):
            body += f"""<div class='os-kv'><div class='os-k'>{k}</div><div class='os-v'>{v}</div></div>"""
        st.markdown(
            f"""
            <div class="os-card">
              <div class="os-card-title"><span class="mi">{icon}</span>{title}</div>
              {body}
            </div>
            """,
            unsafe_allow_html=True,
        )
    except Exception:
        st.markdown(f"**{title}**")
        for k, v in (rows or []):
            st.write(f"- {k}: {v}")

def _render_levels_table(rows: list):
    """Render levels table with unified styling."""
    if not rows:
        st.info("لا توجد مستويات لعرضها.")
        return
    df = pd.DataFrame(rows)
    if render_custom_table:
        # Build cols spec similar to trades table styling
        cols_spec = []
        for c in df.columns:
            lbl = str(c)
            typ = "money" if "سعر" in lbl or "Price" in lbl else "text"
            cols_spec.append((c, lbl, typ))
        render_custom_table(df, cols_spec)
    else:
        st.dataframe(df, width="stretch", hide_index=True)


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
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
            if np.isfinite(arr[i]) and arr[i] == np.nanmax(w):
                pivots.append((i, float(arr[i])))
        else:
            if np.isfinite(arr[i]) and arr[i] == np.nanmin(w):
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
    vma = float(df["Volume"].rolling(20).mean().iloc[-1]) if "Volume" in df.columns and len(df) >= 20 else 0.0
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


def calculate_swing_fibonacci_levels(df: pd.DataFrame, left=3, right=3, min_bars=60):
    if df is None or len(df) < int(min_bars):
        return {}, {"ok": False, "reason": f"not enough data (need {min_bars})"}

    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    ph = _pivot_points(high, left=left, right=right, mode="high")
    pl = _pivot_points(low, left=left, right=right, mode="low")

    if not ph or not pl:
        hh = float(high.tail(min(120, len(high))).max())
        ll = float(low.tail(min(120, len(low))).min())
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


def _last_completed_bar(df: pd.DataFrame):
    """
    يرجع OHLC للشمعة المكتملة السابقة لأي فاصل (ساعة/يوم/أسبوع/شهر)
    """
    if df is None or df.empty or len(df) < 2:
        return None
    use = df.iloc[-2]
    ts = ""
    try:
        ts = str(df.index[-2])
        if isinstance(df.index, pd.DatetimeIndex):
            ts = str(df.index[-2].to_pydatetime())
    except Exception:
        ts = "prev"
    return {"H": float(use["High"]), "L": float(use["Low"]), "C": float(use["Close"]), "O": float(use["Open"]), "ts": ts}


def _calc_pivots_from_df(df: pd.DataFrame, pivot_type: str):
    src = _last_completed_bar(df)
    if not src:
        return {}, None
    H, L, C, O = src["H"], src["L"], src["C"], src["O"]
    if pivot_type == "Standard":
        return pivot_standard(H, L, C), src
    if pivot_type == "Camarilla":
        return pivot_camarilla(H, L, C), src
    return pivot_woodie(H, L, C, O), src


# ============================================================
# ✅ Auto الدعم/المقاومة (Clustered from pivots)
# ============================================================
def _cluster_levels(levels: list[float], tol: float):
    if not levels:
        return []
    lv = sorted([float(x) for x in levels if np.isfinite(x)])
    if not lv:
        return []
    clusters = []
    cur = [lv[0]]
    for x in lv[1:]:
        if abs(x - float(np.mean(cur))) <= tol:
            cur.append(x)
        else:
            clusters.append(float(np.mean(cur)))
            cur = [x]
    clusters.append(float(np.mean(cur)))
    return clusters


def auto_support_resistance_levels(df: pd.DataFrame, lookback=220, left=3, right=3, max_levels=10):
    if df is None or df.empty or len(df) < max(50, left + right + 10):
        return [], []

    d = df.tail(int(min(lookback, len(df)))).copy()
    high = d["High"].astype(float)
    low = d["Low"].astype(float)

    ph = _pivot_points(high, left=left, right=right, mode="high")
    pl = _pivot_points(low, left=left, right=right, mode="low")

    res = [p[1] for p in ph]
    sup = [p[1] for p in pl]

    atr_last = float(_atr(d, 14).iloc[-1]) if len(d) >= 20 else 0.0
    close_last = float(d["Close"].iloc[-1])
    tol = max(0.35 * atr_last, 0.004 * close_last)

    res_c = _cluster_levels(res, tol=tol)[-max_levels:]
    sup_c = _cluster_levels(sup, tol=tol)[-max_levels:]

    return sup_c, res_c


# ============================================================
# 🏛️ MAIN UI
# ============================================================
def render_classical_analysis(symbol: str, interval: str = "1d"):
    """
    ✅ interval: '60m'/'1d'/'1wk'/'1mo'
    التحليل (Fib + دعوم/مقاومات تلقائية + Trend + Volume) مبني على هذا الفاصل.
    Pivot Day/Week/Month يتم حسابها من بياناتها الخاصة (حتى لو التحليل على الساعة).
    """
    itv = _norm_interval(interval)

    st.markdown("### 🏛️ التحليل الكلاسيكي المطوّر (Multi-Timeframe Pivots + Swing Fib + دعوم/مقاومات تلقائية + Zones + ATR/Volume)")

    # -----------------------------
    # Controls (Main)
    # -----------------------------
    topA, topB, topC = st.columns([1.2, 1.2, 2.0])

    # اختيار الفاصل (لو ما تبغاه هنا وخليته في views، ما يضر — فقط مرره للدالة)
    itv_ui = topA.selectbox(
        "الفاصل الزمني (Classical)",
        ["ساعة", "يوم", "أسبوع", "شهر"],
        index=0 if itv == "60m" else 1 if itv == "1d" else 2 if itv == "1wk" else 3,
        key=f"cl_tf_{symbol}"
    )
    itv = _norm_interval(itv_ui)

    pivot_type = topB.selectbox("Pivot Type", ["Standard", "Camarilla", "Woodie"], index=0, key=f"cl_pivot_{symbol}")

    with topC:
        st.caption("ملاحظة: Pivot Day/Week/Month يتم حسابها من بياناتها، حتى لو التحليل الأساسي على الساعة.")

    colA, colB, colC, colD = st.columns([1.25, 1.25, 1.25, 1.25])
    show_zones = colA.checkbox("Zones بدل Lines", value=True, key=f"cl_z_{symbol}")
    show_fib = colB.checkbox("إظهار Fibonacci Swing", value=True, key=f"cl_fib_{symbol}")
    show_sr = colC.checkbox("إظهار Auto الدعم/المقاومة", value=True, key=f"cl_sr_{symbol}")
    show_pivots = colD.checkbox("إظهار Pivot Day/Week/Month", value=True, key=f"cl_piv_{symbol}")

    colE, colF, colG, colH = st.columns([1.25, 1.25, 1.25, 1.25])
    show_daily = colE.checkbox("Daily Pivot", value=True, key=f"cl_pd_{symbol}") if show_pivots else False
    show_weekly = colF.checkbox("Weekly Pivot", value=True, key=f"cl_pw_{symbol}") if show_pivots else False
    show_monthly = colG.checkbox("Monthly Pivot", value=False, key=f"cl_pm_{symbol}") if show_pivots else False
    fib_sens = colH.selectbox("Swing Sensitivity", ["3", "5", "7"], index=0, key=f"cl_fs_{symbol}")

    # -----------------------------
    # Fetch Base Data (for classical analysis)
    # -----------------------------
    base_raw = _fetch_history(symbol, interval=itv, years=5, period=None)
    df = _ensure_ohlcv(base_raw)

    # حد أدنى حسب الفاصل
    min_need = 120 if itv == "1d" else 80 if itv == "60m" else 60 if itv == "1wk" else 40
    if df.empty or len(df) < min_need:
        st.warning(f"بيانات غير كافية لهذا الفاصل (نحتاج تقريباً {min_need} شمعة أو أكثر).")
        return

    # Indicators on BASE timeframe
    df["ATR14"] = _atr(df, 14)
    df["SMA200"] = df["Close"].rolling(200).mean() if len(df) >= 200 else np.nan
    df["VOL_MA20"] = df["Volume"].rolling(20).mean() if len(df) >= 20 else np.nan

    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else last_close
    last_atr = float(df["ATR14"].iloc[-1]) if "ATR14" in df.columns and not pd.isna(df["ATR14"].iloc[-1]) else 0.0
    last_sma200 = float(df["SMA200"].iloc[-1]) if "SMA200" in df.columns and not pd.isna(df["SMA200"].iloc[-1]) else np.nan

    # -----------------------------
    # Fibonacci Swing (BASE)
    # -----------------------------
    fibs, fib_meta = ({}, {})
    if show_fib:
        left = right = int(fib_sens)
        fib_min = 80 if itv == "60m" else 100 if itv == "1d" else 60 if itv == "1wk" else 40
        fibs, fib_meta = calculate_swing_fibonacci_levels(df, left=left, right=right, min_bars=fib_min)

    # -----------------------------
    # دعوم/مقاومات تلقائية (BASE)
    # -----------------------------
    supports, resistances = ([], [])
    if show_sr:
        lookback = 300 if itv in ["60m", "1d"] else 220
        supports, resistances = auto_support_resistance_levels(df, lookback=lookback, left=3, right=3, max_levels=10)

    # -----------------------------
    # Pivots Multi-TF (computed from their own histories)
    # -----------------------------
    pivots_pack = []  # list of dict: {tf, pivots, src}
    if show_pivots:
        if show_daily:
            d1 = _ensure_ohlcv(_fetch_history(symbol, interval="1d", years=5, period=None))
            p, src = _calc_pivots_from_df(d1, pivot_type) if not d1.empty else ({}, None)
            if p and src:
                pivots_pack.append({"tf": "Daily", "pivots": p, "src": src})

        if show_weekly:
            w1 = _ensure_ohlcv(_fetch_history(symbol, interval="1wk", years=10, period=None))
            p, src = _calc_pivots_from_df(w1, pivot_type) if not w1.empty else ({}, None)
            if p and src:
                pivots_pack.append({"tf": "Weekly", "pivots": p, "src": src})

        if show_monthly:
            m1 = _ensure_ohlcv(_fetch_history(symbol, interval="1mo", years=15, period=None))
            p, src = _calc_pivots_from_df(m1, pivot_type) if not m1.empty else ({}, None)
            if p and src:
                pivots_pack.append({"tf": "Monthly", "pivots": p, "src": src})

    # -----------------------------
    # Chart window (BASE)
    # -----------------------------
    tail_n = 160 if itv == "1d" else 220 if itv == "60m" else 140 if itv == "1wk" else 100
    plot_df = df.tail(tail_n).copy()

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

    # SMA200 (BASE)
    if not np.isnan(last_sma200) and "SMA200" in plot_df.columns:
        fig.add_trace(
            go.Scatter(
                x=plot_df.index,
                y=plot_df["SMA200"],
                mode="lines",
                name="SMA200",
                line=dict(width=2, color="#1f77b4"),
            )
        )

    # -------- Fib levels (BASE)
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

    # -------- Pivots (multi TF)
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

            label = f"{tf} {pivot_type} {k}"

            if show_zones:
                fig.add_hrect(
                    y0=lo, y1=hi,
                    fillcolor=color, opacity=op,
                    line_width=0,
                    annotation_text=f"{label}",
                    annotation_position="bottom right"
                )
            else:
                fig.add_hline(
                    y=y,
                    line_dash=dash, line_color=color, line_width=1,
                    annotation_text=f"{label}: {y:.2f}",
                    annotation_position="bottom right"
                )

    # -------- دعوم/مقاومات تلقائية (BASE)
    if show_sr:
        for lvl in supports:
            y = float(lvl)
            lo, hi, w = _zone_bounds(y, last_atr, last_close)
            if show_zones:
                fig.add_hrect(y0=lo, y1=hi, fillcolor="#2ca02c", opacity=0.06, line_width=0,
                              annotation_text=f"Auto الدعم {y:.2f}", annotation_position="bottom left")
            else:
                fig.add_hline(y=y, line_dash="dot", line_color="#2ca02c", line_width=1)

        for lvl in resistances:
            y = float(lvl)
            lo, hi, w = _zone_bounds(y, last_atr, last_close)
            if show_zones:
                fig.add_hrect(y0=lo, y1=hi, fillcolor="#d62728", opacity=0.06, line_width=0,
                              annotation_text=f"Auto المقاومة {y:.2f}", annotation_position="top left")
            else:
                fig.add_hline(y=y, line_dash="dot", line_color="#d62728", line_width=1)

    fig.update_layout(
        title=f"خريطة المستويات لـ {symbol} ({itv})",
        height=560,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch")

    # --------------------------------------------------------
    # ✅ Levels Snapshot (Unified cards + table) - Additive only
    # --------------------------------------------------------
    try:
        st.markdown("#### 🧱 لقطة المستويات (من نفس التحليل)")
        rows_cards = []

        # Trend
        trend_note = "غير متاح"
        if not np.isnan(last_sma200):
            trend_note = "صاعد (فوق SMA200)" if last_close > last_sma200 else "هابط (تحت SMA200)"
        else:
            trend_note = "لا يوجد SMA200 كافٍ"

        v, vma, vol_ok = _vol_confirm(df, factor=1.2)
        rows_cards.append(("Trend", trend_note))
        rows_cards.append(("ATR(14)", f"{last_atr:.3f}" if last_atr > 0 else "N/A"))
        rows_cards.append(("تأكيد الحجم", "✅ قوي" if vol_ok else ("⚠️ ضعيف" if vma > 0 else "N/A")))

        st.markdown("<div class='os-grid'>", unsafe_allow_html=True)
        st.markdown("<div class='os-col-6'>", unsafe_allow_html=True)
        _os_card("ملخص سريع", [("السعر الحالي", f"{last_close:.2f}"), *rows_cards], icon="stacked_line_chart")
        st.markdown("</div>", unsafe_allow_html=True)

        # Nearest key levels (best-effort)
        lvl_rows = []
        if show_sr:
            for s in supports[:4]:
                lvl_rows.append({"النوع": "الدعم", "المستوى": f"{float(s):.2f}"})
            for r in resistances[:4]:
                lvl_rows.append({"النوع": "المقاومة", "المستوى": f"{float(r):.2f}"})

        if show_fib and fibs:
            for k, v_ in list(fibs.items())[:6]:
                lvl_rows.append({"النوع": f"Fib {k}", "المستوى": f"{float(v_):.2f}"})

        if show_pivots and pivots_pack:
            for pack in pivots_pack[:3]:
                p = pack.get("pivots") or {}
                for key_ in ["P", "R1", "R2", "S1", "S2"]:
                    if key_ in p:
                        lvl_rows.append({"النوع": f"{pack['tf']} {key_}", "المستوى": f"{float(p[key_]):.2f}"})

        st.markdown("<div class='os-col-6'>", unsafe_allow_html=True)
        if lvl_rows:
            _os_card("أقرب مستويات مهمة", [("عدد المستويات", str(len(lvl_rows))), ("ملاحظة", "تم تجميعها من (Fib/SR/Pivots)")], icon="layers")
        else:
            _os_card("أقرب مستويات مهمة", [("ملاحظة", "لا توجد مستويات كافية لعرض لقطة")], icon="layers")
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if lvl_rows:
            with st.expander("📋 جدول المستويات (موحّد)"):
                _render_levels_table(lvl_rows)
    except Exception:
        pass

    # --------------------------------------------------------
    # Summary Cards

    # --------------------------------------------------------
    st.markdown("#### 🔢 ملخص سريع")
    trend_is_bull = False
    trend_note = "غير متاح"
    if not np.isnan(last_sma200):
        trend_is_bull = last_close > last_sma200
        trend_note = "صاعد (فوق SMA200)" if trend_is_bull else "هابط (تحت SMA200)"
    else:
        trend_note = "لا يوجد SMA200 كافٍ لهذا الفاصل"

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
    # priority: Weekly -> Daily -> Monthly
    primary = None
    for want in ["Weekly", "Daily", "Monthly"]:
        for pack in pivots_pack:
            if pack["tf"] == want:
                primary = pack
                break
        if primary:
            break

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
        above_res = sorted([x for x in resistances if x > last_close])
        if above_res:
            scen_up_name, scen_up = ("Auto المقاومة", float(above_res[0]))

    if np.isnan(scen_dn) and supports:
        below_sup = sorted([x for x in supports if x < last_close])
        if below_sup:
            scen_dn_name, scen_dn = ("Auto الدعم", float(below_sup[-1]))

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
    if primary and primary.get("pivots") and "PP" in primary["pivots"] and not np.isnan(last_sma200):
        pp = float(primary["pivots"]["PP"])
        if (last_close > pp) and (not trend_is_bull):
            st.warning("⚠️ فوق Pivot لكن تحت SMA200: الأفضل مضاربة/ارتداد بحذر (احتمال كسر كاذب).")
        elif (last_close < pp) and trend_is_bull:
            st.warning("⚠️ تحت Pivot لكن فوق SMA200: قد يكون تصحيح داخل ترند صاعد.")
        else:
            st.success("✅ Pivot و Trend متوافقين (قراءة أنظف).")

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

    with st.expander("🧾 تفاصيل الحساب (للتوثيق وتجنب سوء الفهم)"):
        st.write("**الفاصل الأساسي:**", itv)
        st.write("**بيانات فيبوناتشي:**", fib_meta if show_fib else "تم إيقاف فيبوناتشي")
        st.write("**محاور الارتكاز المستخدمة:**", [{"tf": p["tf"], "src": p["src"], "keys": list(p["pivots"].keys())} for p in pivots_pack])
        st.write("**دعوم/مقاومات تلقائية:**", {"supports": supports, "resistances": resistances})
        st.write("**Volume:**", {"today_volume": v, "vol_ma20": vma, "confirmed": vol_ok})
