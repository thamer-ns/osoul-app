# classical_analysis.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from market_data import get_chart_history

# ============================================================
# ✅ أدوات مساعدة: تنظيف ومعالجة البيانات
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
        # تحويل الكل لنسق موحد (Open, High, Low, Close, Volume)
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
    """حساب متوسط المدى الحقيقي (ATR) لقياس التذبذب"""
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

def _calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """حساب مؤشر القوة النسبية RSI"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def _calculate_macd(series: pd.Series, fast=12, slow=26, signal=9):
    """حساب MACD"""
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

# ============================================================
# ✅ المنطق: القمم والقيعان (Pivot Points & Fib)
# ============================================================
def _pivot_points(series: pd.Series, left=3, right=3, mode="high"):
    """تحديد القمم والقيعان المحلية"""
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

def _fib_from_range(swing_low: float, swing_high: float, direction="up"):
    """حساب مستويات فيبوناتشي"""
    lo, hi = float(swing_low), float(swing_high)
    diff = hi - lo
    if diff == 0: return {}

    if direction == "up":
        return {
            "Fib 100% (قمة)": hi,
            "Fib 61.8% (ذهبي)": hi - (0.382 * diff),
            "Fib 50%": hi - (0.5 * diff),
            "Fib 38.2%": hi - (0.618 * diff),
            "Fib 0% (قاع)": lo,
        }
    else:
        return {
            "Fib 100% (قاع)": lo,
            "Fib 61.8% (ذهبي)": lo + (0.382 * (hi - lo)),
            "Fib 50%": lo + (0.5 * (hi - lo)),
            "Fib 38.2%": lo + (0.618 * (hi - lo)),
            "Fib 0% (قمة)": hi,
        }

def calculate_swing_fibonacci_levels(df: pd.DataFrame, left=3, right=3):
    """تحديد آخر موجة ورسم الفيبوناتشي عليها"""
    if df is None or len(df) < 60:
        return {}, {"ok": False}

    high = df["High"]
    low = df["Low"]

    ph = _pivot_points(high, left=left, right=right, mode="high")
    pl = _pivot_points(low, left=left, right=right, mode="low")

    if not ph or not pl:
        return {}, {"ok": False}

    last_hi_i, last_hi = ph[-1]
    last_lo_i, last_lo = pl[-1]

    # تحديد الاتجاه بناءً على أيهما حدث أخيراً
    if last_lo_i < last_hi_i: # القمة جاءت بعد القاع (اتجاه صاعد)
        swing_low, swing_high, direction = last_lo, last_hi, "up"
    else: # القاع جاء بعد القمة (اتجاه هابط)
        swing_low, swing_high, direction = last_lo, last_hi, "down"

    levels = _fib_from_range(swing_low, swing_high, direction=direction)
    return levels, {"direction": direction, "low": swing_low, "high": swing_high}

# ============================================================
# ✅ المنطق: نقاط الارتكاز (Pivot Points)
# ============================================================
def pivot_standard(H, L, C):
    PP = (H + L + C) / 3
    return {
        "R2": PP + (H - L), "R1": (2 * PP) - L,
        "PP": PP,
        "S1": (2 * PP) - H, "S2": PP - (H - L)
    }

def pivot_woodie(H, L, C, O):
    PP = (H + L + 2 * O) / 4
    return {
        "R2": PP + (H - L), "R1": (2 * PP) - L,
        "PP": PP,
        "S1": (2 * PP) - H, "S2": PP - (H - L)
    }

def pivot_camarilla(H, L, C):
    rng = (H - L)
    return {
        "R4": C + (rng * 1.1 / 2), "R3": C + (rng * 1.1 / 4),
        "PP": C,
        "S3": C - (rng * 1.1 / 4), "S4": C - (rng * 1.1 / 2)
    }

def _calc_pivots_for_tf(df: pd.DataFrame, tf: str, pivot_type: str):
    """حساب الارتكاز بناءً على الفاصل الزمني (يومي، أسبوعي، شهري)"""
    if df.empty: return {}, None
    
    use_df = df.copy()
    src = {}
    
    if tf == "Daily":
        if len(use_df) < 2: return {}, None
        last = use_df.iloc[-2] # الأمس
        src = {"H": last["High"], "L": last["Low"], "C": last["Close"], "O": last["Open"]}
        
    elif tf == "Weekly":
        wk = use_df.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
        if len(wk) < 2: return {}, None
        last = wk.iloc[-2] # الأسبوع الماضي
        src = {"H": last["High"], "L": last["Low"], "C": last["Close"], "O": last["Open"]}
        
    elif tf == "Monthly":
        mo = use_df.resample("M").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
        if len(mo) < 2: return {}, None
        last = mo.iloc[-2] # الشهر الماضي
        src = {"H": last["High"], "L": last["Low"], "C": last["Close"], "O": last["Open"]}

    if not src: return {}, None
    
    H, L, C, O = src["H"], src["L"], src["C"], src["O"]
    if pivot_type == "Standard": return pivot_standard(H, L, C), src
    if pivot_type == "Camarilla": return pivot_camarilla(H, L, C), src
    return pivot_woodie(H, L, C, O), src

# ============================================================
# ✅ المنطق: الدعوم والمقاومات التلقائية
# ============================================================
def _cluster_levels(levels: list[float], tol: float):
    """تجميع المستويات المتقاربة"""
    if not levels: return []
    lv = sorted([float(x) for x in levels if np.isfinite(x)])
    clusters, cur = [], [lv[0]]
    for x in lv[1:]:
        if abs(x - np.mean(cur)) <= tol:
            cur.append(x)
        else:
            clusters.append(float(np.mean(cur)))
            cur = [x]
    clusters.append(float(np.mean(cur)))
    return clusters

def auto_support_resistance_levels(df: pd.DataFrame, lookback=200):
    """استخراج الدعوم والمقاومات من الشارت تلقائياً"""
    if len(df) < 100: return [], []
    
    d = df.tail(lookback).copy()
    ph = _pivot_points(d["High"], 3, 3, "high")
    pl = _pivot_points(d["Low"], 3, 3, "low")
    
    res = [p[1] for p in ph]
    sup = [p[1] for p in pl]
    
    # التسامح (Tolerance) يعتمد على السعر
    tol = d["Close"].mean() * 0.015 
    
    return _cluster_levels(sup, tol)[-5:], _cluster_levels(res, tol)[-5:]

# ============================================================
# 🏛️ الواجهة الرئيسية (Main Render)
# ============================================================
def render_classical_analysis(symbol: str):
    st.markdown("### 🏛️ التحليل الفني المتقدم (Technical Analysis)")

    # 1. جلب البيانات
    df = get_chart_history(symbol, period="2y", interval="1d")
    df = _ensure_ohlcv(df)

    if df.empty or len(df) < 100:
        st.error("⚠️ بيانات السهم غير كافية للتحليل الفني الدقيق.")
        return

    # 2. حساب المؤشرات
    df["SMA200"] = df["Close"].rolling(200).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    df["ATR"] = _atr(df, 14)
    df["RSI"] = _calculate_rsi(df["Close"])
    df["MACD"], df["MACD_Signal"], df["MACD_Hist"] = _calculate_macd(df["Close"])

    last_close = df["Close"].iloc[-1]
    last_atr = df["ATR"].iloc[-1]

    # 3. لوحة التحكم
    c1, c2, c3, c4 = st.columns(4)
    pivot_type = c1.selectbox("نوع الارتكاز", ["Standard", "Camarilla", "Woodie"])
    show_fib = c2.checkbox("فيبوناتشي (Swing)", value=True)
    show_sr = c3.checkbox("دعوم/مقاومات تلقائية", value=True)
    indicator_select = c4.selectbox("المؤشر السفلي", ["Volume", "RSI", "MACD"])

    # 4. الحسابات (Pivots, Fib, AutoSR)
    pivots_daily, _ = _calc_pivots_for_tf(df, "Daily", pivot_type)
    pivots_weekly, _ = _calc_pivots_for_tf(df, "Weekly", pivot_type)
    
    fibs, _ = calculate_swing_fibonacci_levels(df, 5, 5) if show_fib else ({}, {})
    auto_sup, auto_res = auto_support_resistance_levels(df) if show_sr else ([], [])

    # 5. الرسم البياني (Subplots)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.05, row_heights=[0.7, 0.3])

    # -- الشارت الرئيسي (شموع) --
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name="السعر"
    ), row=1, col=1)

    # المتوسطات
    fig.add_trace(go.Scatter(x=df.index, y=df["SMA200"], line=dict(color='blue', width=1), name="SMA 200"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["EMA50"], line=dict(color='orange', width=1), name="EMA 50"), row=1, col=1)

    # رسم المستويات (Pivots)
    def _draw_level(val, name, color, dash="dash"):
        fig.add_hline(y=val, line_dash=dash, line_color=color, line_width=1, 
                      annotation_text=f"{name} {val:.2f}", row=1, col=1)

    if pivots_weekly:
        _draw_level(pivots_weekly.get("PP", 0), "W-Pivot", "black", "solid")
        _draw_level(pivots_weekly.get("R1", 0), "W-R1", "red")
        _draw_level(pivots_weekly.get("S1", 0), "W-S1", "green")

    # رسم فيبوناتشي
    if show_fib and fibs:
        for k, v in fibs.items():
            col = "gold" if "61.8" in k else "gray"
            _draw_level(v, k, col, "dot")

    # رسم Auto S/R (مناطق مظللة)
    if show_sr:
        for s in auto_sup:
            fig.add_hrect(y0=s, y1=s+last_atr*0.2, fillcolor="green", opacity=0.1, line_width=0, row=1, col=1)
        for r in auto_res:
            fig.add_hrect(y0=r-last_atr*0.2, y1=r, fillcolor="red", opacity=0.1, line_width=0, row=1, col=1)

    # -- المؤشر السفلي --
    if indicator_select == "Volume":
        colors = ['red' if c < o else 'green' for c, o in zip(df['Close'], df['Open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name="Volume"), row=2, col=1)
    
    elif indicator_select == "RSI":
        fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple'), name="RSI"), row=2, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="green", row=2, col=1)
        
    elif indicator_select == "MACD":
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='blue'), name="MACD"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD_Signal'], line=dict(color='orange'), name="Signal"), row=2, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], name="Hist"), row=2, col=1)

    fig.update_layout(height=600, margin=dict(l=10, r=10, t=30, b=10), xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    # 6. بطاقات الملخص (Trend Check)
    st.markdown("#### 🧭 قراءة الاتجاه")
    c1, c2, c3 = st.columns(3)
    
    # حالة الترند
    trend = "صاعد 🟢" if last_close > df["SMA200"].iloc[-1] else "هابط 🔴"
    c1.metric("الاتجاه العام (SMA200)", trend)
    
    # حالة الزخم (RSI)
    last_rsi = df["RSI"].iloc[-1]
    rsi_state = "تشبع شرائي ⚠️" if last_rsi > 70 else "تشبع بيعي ✅" if last_rsi < 30 else "محايد"
    c2.metric("مؤشر الزخم (RSI)", f"{last_rsi:.1f}", rsi_state)
    
    # أقرب المستويات
    nearest_res = min([r for r in auto_res if r > last_close], default=pivots_weekly.get("R1", 0))
    nearest_sup = max([s for s in auto_sup if s < last_close], default=pivots_weekly.get("S1", 0))
    
    c3.metric("المجال السعري المتوقع", f"{nearest_sup:.1f} - {nearest_res:.1f}")

    # 7. التوصية الفنية الآلية
    st.info(f"""
    💡 **الخلاصة الفنية:**
    السهم يتداول بسعر **{last_close:.2f}**. 
    - أقرب مقاومة قوية: **{nearest_res:.2f}**
    - أقرب دعم قوي: **{nearest_sup:.2f}**
    - إذا اخترق المقاومة بحجم عالي، الهدف التالي قد يكون عند **{pivots_weekly.get('R2', nearest_res*1.05):.2f}**.
    """)
