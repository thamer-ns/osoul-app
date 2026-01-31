# classical_analysis.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from market_data import get_chart_history

# ============================================================
# ✅ 1. أدوات مساعدة: تنظيف ومعالجة البيانات
# ============================================================
def _ensure_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """تأكيد وجود أعمدة OHLCV وتنسيقها"""
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # معالجة MultiIndex (مشكلة yfinance الشهيرة)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # توحيد أسماء الأعمدة
    rename = {}
    for c in df.columns:
        base = c[0] if isinstance(c, (tuple, list)) and len(c) else c
        s = str(base).strip()
        rename[c] = s.title() if s else s
    df.rename(columns=rename, inplace=True)

    # التأكد من الأساسيات
    if "Close" not in df.columns:
        return pd.DataFrame()

    if "Open" not in df.columns: df["Open"] = df["Close"]
    for col in ["High", "Low"]:
        if col not in df.columns: df[col] = df["Close"]
    if "Volume" not in df.columns: df["Volume"] = 0.0

    # ترتيب التاريخ
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.sort_index()

    # تحويل لأرقام
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
    return df

def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """حساب متوسط المدى الحقيقي (ATR) لقياس التذبذب وسماكة المناطق"""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def _pivot_points(series: pd.Series, left=3, right=3, mode="high"):
    """تحديد القمم والقيعان المحلية (Fractals)"""
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
# ✅ 2. منطق المناطق والتأكيد (Zones & Confirmation)
# ============================================================
def _zone_bounds(level: float, atr_val: float, close: float):
    """
    حساب سمك المنطقة السعرية (Zone) بدلاً من خط رفيع.
    يعتمد على ATR أو نسبة مئوية من السعر.
    """
    lv = float(level)
    c = float(close) if close and close > 0 else lv
    w_atr = 0.5 * float(atr_val) if atr_val and atr_val > 0 else 0.0
    w_pct = 0.005 * c # 0.5% كحد أدنى
    w = max(w_atr, w_pct, 0.0)
    return lv - w, lv + w, w

def _vol_confirm(df: pd.DataFrame, factor=1.2):
    """هل الفوليوم الحالي أعلى من المتوسط بـ 20%؟"""
    if df is None or df.empty:
        return 0.0, 0.0, False
    v = float(df["Volume"].iloc[-1])
    vma = float(df["Volume"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else 0.0
    ok = (vma > 0) and (v >= factor * vma)
    return v, vma, ok

def _cross_up(close, prev_close, level):
    return (close > level) and (prev_close <= level)

def _cross_down(close, prev_close, level):
    return (close < level) and (prev_close >= level)

# ============================================================
# ✅ 3. فيبوناتشي (Swing Fibonacci)
# ============================================================
def _fib_from_range(swing_low: float, swing_high: float, direction="up"):
    lo, hi = float(swing_low), float(swing_high)
    diff = hi - lo
    if diff == 0: return {}

    if direction == "up":
        return {
            "Fib 100% (High)": hi,
            "Fib 78.6%": hi - (0.214 * diff),
            "Fib 61.8% (Golden)": hi - (0.382 * diff),
            "Fib 50%": hi - (0.5 * diff),
            "Fib 38.2%": hi - (0.618 * diff),
            "Fib 23.6%": hi - (0.764 * diff),
            "Fib 0% (Low)": lo,
        }
    else:
        return {
            "Fib 100% (Low)": lo,
            "Fib 78.6%": lo + (0.214 * (hi - lo)),
            "Fib 61.8% (Golden)": lo + (0.382 * (hi - lo)),
            "Fib 50%": lo + (0.5 * (hi - lo)),
            "Fib 38.2%": lo + (0.618 * (hi - lo)),
            "Fib 23.6%": lo + (0.764 * (hi - lo)),
            "Fib 0% (High)": hi,
        }

def calculate_swing_fibonacci_levels(df: pd.DataFrame, left=5, right=5):
    if df is None or len(df) < 60:
        return {}, {"ok": False}

    high = df["High"]
    low = df["Low"]

    ph = _pivot_points(high, left=left, right=right, mode="high")
    pl = _pivot_points(low, left=left, right=right, mode="low")

    # Fallback إذا لم نجد قمم وقيعان واضحة
    if not ph or not pl:
        hh = float(high.tail(120).max())
        ll = float(low.tail(120).min())
        return (_fib_from_range(ll, hh, "up"), {"ok": True, "swing_low": ll, "swing_high": hh})

    last_hi_i, last_hi = ph[-1]
    last_lo_i, last_lo = pl[-1]

    if last_lo_i < last_hi_i:
        swing_low, swing_high, direction = last_lo, last_hi, "up"
    else:
        swing_low, swing_high, direction = last_lo, last_hi, "down"

    levels = _fib_from_range(swing_low, swing_high, direction=direction)
    return levels, {"ok": True, "direction": direction, "swing_low": swing_low, "swing_high": swing_high}

# ============================================================
# ✅ 4. نقاط الارتكاز (Pivots: Standard, Woodie, Camarilla)
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
    """استخراج شمعة الإغلاق المكتملة (يومي/أسبوعي/شهري)"""
    if df.empty: return None
    dfx = df.copy()

    if timeframe == "Daily":
        if len(dfx) < 2: return None
        use = dfx.iloc[-2] # الأمس
        return {"H": use["High"], "L": use["Low"], "C": use["Close"], "O": use["Open"], "ts": str(dfx.index[-2].date())}

    if timeframe == "Weekly":
        wk = dfx.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
        wk.dropna(inplace=True)
        if len(wk) < 2: return None
        use = wk.iloc[-2]
        return {"H": use["High"], "L": use["Low"], "C": use["Close"], "O": use["Open"], "ts": str(wk.index[-2].date())}

    if timeframe == "Monthly":
        mo = dfx.resample("M").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
        mo.dropna(inplace=True)
        if len(mo) < 2: return None
        use = mo.iloc[-2]
        return {"H": use["High"], "L": use["Low"], "C": use["Close"], "O": use["Open"], "ts": str(mo.index[-2].date())}

    return None

def _calc_pivots_for_tf(df: pd.DataFrame, tf: str, pivot_type: str):
    src = _get_last_completed_ohlc(df, tf)
    if not src: return {}, None
    H, L, C, O = src["H"], src["L"], src["C"], src["O"]
    
    if pivot_type == "Standard": res = pivot_standard(H, L, C)
    elif pivot_type == "Camarilla": res = pivot_camarilla(H, L, C)
    else: res = pivot_woodie(H, L, C, O)
    
    return res, src

# ============================================================
# ✅ 5. دعوم ومقاومات آلية (Clustering)
# ============================================================
def _cluster_levels(levels: list, tol: float):
    if not levels: return []
    lv = sorted([float(x) for x in levels if np.isfinite(x)])
    clusters, cur = [], [lv[0]]
    for x in lv[1:]:
        if abs(x - np.mean(cur)) <= tol: cur.append(x)
        else:
            clusters.append(float(np.mean(cur)))
            cur = [x]
    clusters.append(float(np.mean(cur)))
    return clusters

def auto_support_resistance_levels(df: pd.DataFrame, lookback=220, left=3, right=3):
    if len(df) < 100: return [], []
    d = df.tail(lookback).copy()
    ph = _pivot_points(d["High"], left, right, "high")
    pl = _pivot_points(d["Low"], left, right, "low")
    
    res = [p[1] for p in ph]
    sup = [p[1] for p in pl]
    
    atr = float(_atr(d).iloc[-1])
    tol = max(0.35 * atr, 0.004 * d["Close"].iloc[-1])
    
    return _cluster_levels(sup, tol)[-5:], _cluster_levels(res, tol)[-5:]

# ============================================================
# 🏛️ الواجهة الرئيسية (Render Logic)
# ============================================================
def render_classical_analysis(symbol: str):
    st.markdown("### 🏛️ التحليل الكلاسيكي المتقدم (Price Action + Scenarios)")

    # 1. جلب البيانات
    df = get_chart_history(symbol, period="2y", interval="1d")
    df = _ensure_ohlcv(df)
    
    if df.empty or len(df) < 100:
        st.error("⚠️ البيانات التاريخية غير كافية للتحليل الفني الدقيق.")
        return

    # 2. المؤشرات الأساسية
    df["SMA200"] = df["Close"].rolling(200).mean()
    df["ATR"] = _atr(df, 14)
    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])
    last_atr = float(df["ATR"].iloc[-1])
    last_sma = float(df["SMA200"].iloc[-1]) if not pd.isna(df["SMA200"].iloc[-1]) else 0

    # 3. لوحة التحكم (Controls)
    c1, c2, c3, c4 = st.columns(4)
    pivot_type = c1.selectbox("نوع الارتكاز", ["Standard", "Camarilla", "Woodie"])
    show_fib = c2.checkbox("فيبوناتشي", value=True)
    show_zones = c3.checkbox("عرض المناطق (Zones)", value=True)
    show_sr = c4.checkbox("دعوم آلية", value=True)

    c5, c6, c7 = st.columns(3)
    tf_daily = c5.checkbox("يومي", True)
    tf_weekly = c6.checkbox("أسبوعي", True)
    tf_monthly = c7.checkbox("شهري", False)

    # 4. الحسابات
    pivots_pack = []
    if tf_daily:
        p, src = _calc_pivots_for_tf(df, "Daily", pivot_type)
        if p: pivots_pack.append({"tf": "Daily", "p": p, "src": src})
    if tf_weekly:
        p, src = _calc_pivots_for_tf(df, "Weekly", pivot_type)
        if p: pivots_pack.append({"tf": "Weekly", "p": p, "src": src})
    if tf_monthly:
        p, src = _calc_pivots_for_tf(df, "Monthly", pivot_type)
        if p: pivots_pack.append({"tf": "Monthly", "p": p, "src": src})

    fibs, fib_meta = ({}, {})
    if show_fib:
        fibs, fib_meta = calculate_swing_fibonacci_levels(df)

    auto_sup, auto_res = ([], [])
    if show_sr:
        auto_sup, auto_res = auto_support_resistance_levels(df)

    # 5. الرسم البياني (Plotly)
    plot_df = df.tail(150)
    fig = go.Figure()

    # الشموع
    fig.add_trace(go.Candlestick(
        x=plot_df.index, open=plot_df["Open"], high=plot_df["High"],
        low=plot_df["Low"], close=plot_df["Close"], name="السعر"
    ))

    # SMA 200
    if last_sma > 0:
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["SMA200"], line=dict(color='blue', width=2), name="SMA 200"))

    # رسم الفيبوناتشي
    if show_fib and fibs:
        for k, v in fibs.items():
            col = "gold" if "61.8" in k else "gray"
            width = 2 if "61.8" in k else 1
            dash = "solid" if "61.8" in k else "dot"
            lo, hi, w = _zone_bounds(v, last_atr, last_close)
            
            if show_zones:
                fig.add_hrect(y0=lo, y1=hi, fillcolor=col, opacity=0.15, line_width=0, annotation_text=k)
            else:
                fig.add_hline(y=v, line_dash=dash, line_color=col, line_width=width, annotation_text=f"{k}: {v:.2f}")

    # رسم الارتكازات (Pivots)
    tf_colors = {"Daily": "gray", "Weekly": "purple", "Monthly": "black"}
    for pack in pivots_pack:
        tf = pack["tf"]
        p = pack["p"]
        col = tf_colors.get(tf, "black")
        
        for key in ["R2", "R1", "PP", "S1", "S2"]:
            if key not in p: continue
            val = float(p[key])
            lo, hi, w = _zone_bounds(val, last_atr, last_close)
            
            lvl_col = "red" if "R" in key else "green" if "S" in key else col
            label = f"{tf} {key}"
            
            if show_zones:
                fig.add_hrect(y0=lo, y1=hi, fillcolor=lvl_col, opacity=0.1, line_width=0, annotation_text=label)
            else:
                fig.add_hline(y=val, line_dash="dash", line_color=lvl_col, line_width=1, annotation_text=f"{label}: {val:.2f}")

    # رسم الدعوم الآلية
    if show_sr:
        for s in auto_sup:
            lo, hi, w = _zone_bounds(s, last_atr, last_close)
            fig.add_hrect(y0=lo, y1=hi, fillcolor="green", opacity=0.08, line_width=0)
        for r in auto_res:
            lo, hi, w = _zone_bounds(r, last_atr, last_close)
            fig.add_hrect(y0=lo, y1=hi, fillcolor="red", opacity=0.08, line_width=0)

    fig.update_layout(height=600, margin=dict(l=10, r=10, t=30, b=10), xaxis_rangeslider_visible=False, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # 6. بطاقات الملخص وسيناريوهات التداول
    # -----------------------------------------------------
    st.markdown("---")
    
    # تحديد أقرب مستويات
    primary_pivots = next((item["p"] for item in pivots_pack if item["tf"] == "Weekly"), 
                          next((item["p"] for item in pivots_pack if item["tf"] == "Daily"), {}))
    
    r1 = float(primary_pivots.get("R1", 0))
    s1 = float(primary_pivots.get("S1", 0))
    pp = float(primary_pivots.get("PP", 0))
    
    # تحسين اختيار مستويات السيناريو (دمج الفيبو والآلي)
    upside_levels = sorted([v for v in fibs.values() if v > last_close] + [r for r in auto_res if r > last_close] + ([r1] if r1 > last_close else []))
    downside_levels = sorted([v for v in fibs.values() if v < last_close] + [s for s in auto_sup if s < last_close] + ([s1] if s1 < last_close else []))
    
    resistance = upside_levels[0] if upside_levels else last_close * 1.05
    support = downside_levels[-1] if downside_levels else last_close * 0.95

    # فحص الاختراق
    vol_curr, vol_ma, vol_ok = _vol_confirm(df)
    break_up = _cross_up(last_close, prev_close, resistance)
    break_down = _cross_down(last_close, prev_close, support)

    # عرض السيناريوهات
    col_bull, col_bear = st.columns(2)
    
    with col_bull:
        st.success("🚀 سيناريو الاختراق (Bullish)")
        st.write(f"**شرط الدخول:** إغلاق يومي فوق **{resistance:.2f}**")
        if break_up:
            if vol_ok: st.caption("✅ اختراق حدث بحجم تداول عالي!")
            else: st.caption("⚠️ اختراق حدث لكن بحجم ضعيف (حذر).")
        else:
            st.caption(f"المسافة الحالية: {((resistance-last_close)/last_close)*100:.2f}%")
        
        target = upside_levels[1] if len(upside_levels) > 1 else resistance * 1.03
        st.metric("الهدف الأول", f"{target:.2f}")

    with col_bear:
        st.error("🔻 سيناريو الكسر (Bearish)")
        st.write(f"**شرط الخروج:** إغلاق يومي تحت **{support:.2f}**")
        if break_down:
            if vol_ok: st.caption("⛔ كسر حدث بحجم تداول عالي!")
            else: st.caption("⚠️ كسر حدث بحجم ضعيف.")
        else:
            st.caption(f"المسافة الحالية: {((last_close-support)/last_close)*100:.2f}%")
            
        target_down = downside_levels[-2] if len(downside_levels) > 1 else support * 0.97
        st.metric("دعم تالي", f"{target_down:.2f}")

    # 7. ملخص الاتجاه
    st.markdown("#### 🧭 حالة الاتجاه العام")
    trend_state = "صاعد 📈" if last_close > last_sma else "هابط 📉"
    atr_pct = (last_atr / last_close) * 100
    vol_state = "نشط 🔥" if vol_ok else "هادئ ❄️"
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("الاتجاه (SMA200)", trend_state)
    m2.metric("التذبذب (ATR)", f"{last_atr:.2f} ({atr_pct:.1f}%)")
    m3.metric("حالة السيولة", vol_state)
    m4.metric("موقع السعر", "فوق الارتكاز" if last_close > pp else "تحت الارتكاز")

    with st.expander("🔍 تفاصيل المستويات المحسوبة"):
        st.json({
            "Weekly Pivots": primary_pivots,
            "Fib Levels": fibs,
            "Auto Resistance": auto_res,
            "Auto Support": auto_sup
        })
