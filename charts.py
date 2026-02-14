import streamlit as st
import plotly.graph_objects as go
import re

from data_normalizer import normalize_ohlcv
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd

from market_data import get_chart_history


# ============================================================
# ✅ Utils: Symbol + Datetime Index
# ============================================================
def _normalize_symbol(sym: str) -> str:
    s = (sym or "").strip().upper()
    if not s:
        return ""
    if s.isdigit():
        return f"{s}.SR"
    s = s.replace(" ", "").replace("-", "")
    if s.endswith("SR") and ".SR" not in s and not s.startswith("^"):
        s = s.replace("SR", ".SR")
    return s


def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    يضمن أن محور X تاريخ/وقت حقيقي:
    - لو فيه عمود date/Date/time... يحوله لإندكس
    - لو الإندكس غير DatetimeIndex يحاول تحويله
    - يحذف NaT والتكرارات ويرتب
    """
    if df is None or df.empty:
        return pd.DataFrame()

    d = df.copy()

    # لو يوجد عمود تاريخ
    for c in ["date", "Date", "datetime", "Datetime", "time", "Time", "timestamp", "Timestamp"]:
        if c in d.columns:
            d[c] = pd.to_datetime(d[c], errors="coerce")
            d = d.dropna(subset=[c])
            d = d.sort_values(c)
            d = d.set_index(c)
            break

    # لو الإندكس نفسه تاريخ
    if not isinstance(d.index, pd.DatetimeIndex):
        try:
            d.index = pd.to_datetime(d.index, errors="coerce")
        except Exception:
            pass

    # تنظيف
    d = d[~pd.isna(d.index)]
    d = d[~d.index.duplicated(keep="last")]
    try:
        d = d.sort_index()
    except Exception:
        pass

    return d


# ============================================================
# ✅ Data Normalizer (Fix Yahoo MultiIndex / lowercase / non-string cols)
# ============================================================
def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Backwards-compatible wrapper around shared normalizer."""
    return normalize_ohlcv(df)




def _plot_tail_bars(interval: str) -> int:
    itv = _norm_interval(interval)
    if itv in ["60m", "30m", "15m", "5m", "1m", "2m", "90m"]:
        return 520
    if itv == "1d":
        return 420
    if itv == "1wk":
        return 320
    if itv == "1mo":
        return 180
    return 420


def _default_period_for_interval(itv: str) -> str:
    """
    إذا period = None:
    - للفواصل الصغيرة: 6mo أو 1y
    - اليومي: 2y
    - الأسبوعي/الشهري: 5y أو max
    """
    itv = _norm_interval(itv)
    if itv in ["60m", "30m", "15m", "5m"]:
        return "6mo"
    if itv == "1d":
        return "2y"
    if itv in ["1wk", "1mo"]:
        return "5y"
    return "2y"


# ============================================================
# --- Support / Resistance ---
# ============================================================
def add_support_resistance(fig, df, sensitivity=3, max_levels=12):
    """
    دعم/مقاومة تلقائي:
    - اكتشاف قمم/قيعان محلية
    - فلترة تكرار المستويات ضمن 1%
    - تحديد حد أقصى للمستويات لتخفيف الزحمة
    """
    if df is None or df.empty or len(df) < (sensitivity * 2 + 10):
        return

    levels = []
    lows = df["Low"].values
    highs = df["High"].values

    for i in range(sensitivity, len(df) - sensitivity):
        # Support
        if lows[i] < np.min(lows[i - sensitivity:i]) and lows[i] < np.min(lows[i + 1:i + sensitivity + 1]):
            level = float(lows[i])
            if not any(abs(level - x[1]) <= max(level, 1e-9) * 0.01 for x in levels):
                levels.append((df.index[i], level, "Support"))

        # Resistance
        if highs[i] > np.max(highs[i - sensitivity:i]) and highs[i] > np.max(highs[i + 1:i + sensitivity + 1]):
            level = float(highs[i])
            if not any(abs(level - x[1]) <= max(level, 1e-9) * 0.01 for x in levels):
                levels.append((df.index[i], level, "Resistance"))

    last_close = float(df["Close"].iloc[-1])
    levels = sorted(levels, key=lambda x: abs(x[1] - last_close))[:max_levels]

    for dt, level, type_ in levels:
        color = "#00C853" if type_ == "Support" else "#D50000"
        fig.add_shape(
            type="line",
            x0=dt, y0=level, x1=df.index[-1], y1=level,
            line=dict(color=color, width=1, dash="dash"),
            xref="x", yref="y",
            row=1, col=1
        )


# ============================================================
# ✅ Safe fetch wrapper (handles signature differences)
# ============================================================
def _fetch_history(symbol: str, period: str, interval: str):
    """
    يحاول استدعاء get_chart_history بعدة توقيعات لتفادي اختلاف النسخ.
    """
    # الأكثر شيوعاً في مشروعك (period/interval)
    try:
        return get_chart_history(symbol, period=period, interval=interval)
    except TypeError:
        pass
    except Exception:
        pass

    # بعض النسخ: (symbol, period, interval)
    try:
        return get_chart_history(symbol, period, interval)
    except TypeError:
        pass
    except Exception:
        pass

    # بعض النسخ: (symbol, period)
    try:
        return get_chart_history(symbol, period)
    except TypeError:
        pass
    except Exception:
        pass

    # fallback أخير
    try:
        return get_chart_history(symbol)
    except Exception:
        return pd.DataFrame()


# ============================================================
# --- Main ---
# ============================================================
def render_technical_chart(symbol, period=None, interval="1d"):
    """
    شارت احترافي داخل Streamlit:
    - Candlestick + SMA + Bollinger
    - RSI + MACD
    - Zoom/Scroll + Pan + RangeSlider + RangeSelector
    - أدوات رسم (line/rect/circle) + eraser
    """

    itv = _norm_interval(interval)
    sym = _normalize_symbol(symbol)
    if not sym:
        st.warning("الرجاء إدخال رمز صحيح.")
        return

    if period is None or str(period).strip() == "":
        period = _default_period_for_interval(itv)

    raw = _fetch_history(sym, period=period, interval=itv)

    # normalize + ensure datetime axis
    df = _normalize_ohlcv(raw)
    df = _ensure_datetime_index(df)

    if df is None or df.empty or len(df) < 30:
        st.warning("البيانات التاريخية غير كافية أو غير صالحة لهذا الفاصل الزمني.")
        return

    n = len(df)

    # ========================================================
    # Indicators
    # ========================================================
    # SMA
    df["SMA_50"] = df["Close"].rolling(window=50).mean() if n >= 50 else np.nan
    df["SMA_200"] = df["Close"].rolling(window=200).mean() if n >= 200 else np.nan

    # Bollinger Bands (20)
    if n >= 20:
        ma20 = df["Close"].rolling(20).mean()
        std20 = df["Close"].rolling(20).std()
        df["BB_Upper"] = ma20 + (std20 * 2)
        df["BB_Lower"] = ma20 - (std20 * 2)
        df["BB_Width"] = (df["BB_Upper"] - df["BB_Lower"]) / ma20.replace(0, np.nan)
    else:
        df["BB_Upper"] = np.nan
        df["BB_Lower"] = np.nan
        df["BB_Width"] = np.nan

    # RSI (14) - EWM
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = (100 - (100 / (1 + rs))).fillna(50)

    # MACD
    exp12 = df["Close"].ewm(span=12, adjust=False).mean()
    exp26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = exp12 - exp26
    df["Signal_Line"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["Signal_Line"]

    # Notes
    notes = []
    if n < 50:
        notes.append("لا توجد شموع كافية لحساب SMA50 بدقة.")
    if n < 200:
        notes.append("لا توجد شموع كافية لحساب SMA200 (الاتجاه الطويل) لهذا الفاصل.")
    if n < 60 and itv == "1mo":
        notes.append("الفاصل الشهري غالبًا يعطي شموع أقل — نعتمد أكثر على RSI/MACD والمستويات.")
    for msg in notes:
        st.info(f"ملاحظة: {msg}")

    # ========================================================
    # Plot Window
    # ========================================================
    tail_n = _plot_tail_bars(itv)
    plot_df = df.tail(tail_n).copy()

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.62, 0.18, 0.20],
        subplot_titles=(f"السعر: {sym} ({itv})", "RSI", "MACD")
    )

    # Candles
    fig.add_trace(
        go.Candlestick(
            x=plot_df.index,
            open=plot_df["Open"],
            high=plot_df["High"],
            low=plot_df["Low"],
            close=plot_df["Close"],
            name="السعر"
        ),
        row=1, col=1
    )

    # SMA lines
    if "SMA_50" in plot_df.columns and not plot_df["SMA_50"].isna().all():
        fig.add_trace(
            go.Scatter(x=plot_df.index, y=plot_df["SMA_50"], line=dict(color="orange", width=1.5), name="متوسط 50 (SMA)"),
            row=1, col=1
        )
    if "SMA_200" in plot_df.columns and not plot_df["SMA_200"].isna().all():
        fig.add_trace(
            go.Scatter(x=plot_df.index, y=plot_df["SMA_200"], line=dict(color="#2962FF", width=2), name="متوسط 200 (SMA)"),
            row=1, col=1
        )

    # Bollinger
    if "BB_Upper" in plot_df.columns and not plot_df["BB_Upper"].isna().all():
        fig.add_trace(
            go.Scatter(x=plot_df.index, y=plot_df["BB_Upper"], line=dict(color="gray", width=1, dash="dot"),
                       name="BB Upper", showlegend=False),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=plot_df.index, y=plot_df["BB_Lower"],
                line=dict(color="gray", width=1, dash="dot"),
                fill="tonexty", fillcolor="rgba(0,0,255,0.05)",
                name="BB Lower", showlegend=False
            ),
            row=1, col=1
        )

    # RSI
    fig.add_trace(
        go.Scatter(x=plot_df.index, y=plot_df["RSI"], line=dict(color="purple"), name="القوة النسبية (RSI)"),
        row=2, col=1
    )
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    # MACD
    colors = np.where(plot_df["MACD_Hist"] >= 0, "#26a69a", "#ef5350")
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df["MACD_Hist"], marker_color=colors, name="الهيستوجرام"), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["MACD"], line=dict(color="blue"), name="MACD (الماكد)"), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["Signal_Line"], line=dict(color="orange"), name="خط الإشارة"), row=3, col=1)

    # ========================================================
    # ✅ Professional interaction (TradingView-like)
    # ========================================================
    rangeselector_buttons = [
        dict(count=7, label="7D", step="day", stepmode="backward"),
        dict(count=1, label="1M", step="month", stepmode="backward"),
        dict(count=3, label="3M", step="month", stepmode="backward"),
        dict(count=6, label="6M", step="month", stepmode="backward"),
        dict(count=1, label="1Y", step="year", stepmode="backward"),
        dict(step="all", label="All"),
    ]

    fig.update_layout(
        height=860,
        hovermode="x unified",
        dragmode="pan",
        margin=dict(t=40, b=10, l=10, r=10),
        xaxis=dict(
            type="date",
            rangeselector=dict(buttons=rangeselector_buttons),
            rangeslider=dict(visible=True, thickness=0.08),
        ),
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    # تحسين قراءة المؤشر (Spikes مثل الكروس هير)
    fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor", showgrid=True, gridwidth=0.5)
    fig.update_yaxes(showspikes=True, spikemode="across", spikesnap="cursor", showgrid=True, gridwidth=0.5)

    # إخفاء ticklabels في الأعلى للاحترافية
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_xaxes(showticklabels=False, row=2, col=1)

    # دعم/مقاومة
    sr_key = f"sr_{sym}_{itv}"
    if st.checkbox("🎯 إظهار مستويات الدعم والمقاومة (Auto S&R)", value=False, key=sr_key):
        add_support_resistance(fig, plot_df, sensitivity=3)

    config = {
        "displayModeBar": True,
        "scrollZoom": True,
        "displaylogo": False,
        "modeBarButtonsToAdd": ["drawline", "drawrect", "drawcircle", "eraseshape"],
    }

    st.plotly_chart(fig, width="stretch", config=config)

    # ========================================================
    # ✅ التقرير الفني
    # ========================================================
    st.markdown("### 📋 التقرير الفني الذكي")

    last_close = float(df["Close"].iloc[-1])
    last_sma50 = float(df["SMA_50"].iloc[-1]) if ("SMA_50" in df.columns and not pd.isna(df["SMA_50"].iloc[-1])) else np.nan
    last_sma200 = float(df["SMA_200"].iloc[-1]) if ("SMA_200" in df.columns and not pd.isna(df["SMA_200"].iloc[-1])) else np.nan
    last_rsi = float(df["RSI"].iloc[-1])
    last_macd = float(df["MACD"].iloc[-1])
    last_signal = float(df["Signal_Line"].iloc[-1])

    is_bull_market = (not np.isnan(last_sma200)) and (last_close > last_sma200)
    is_golden_cross = (not np.isnan(last_sma50)) and (not np.isnan(last_sma200)) and (last_sma50 > last_sma200)

    rsi_status = "neutral"
    if last_rsi > 70:
        rsi_status = "overbought"
    elif last_rsi < 30:
        rsi_status = "oversold"

    st.markdown("##### 1️⃣ حالة الاتجاه (Trend):")
    col_t1, col_t2 = st.columns(2)

    with col_t1:
        if np.isnan(last_sma200):
            st.info("لا يوجد SMA200 لهذا الفاصل — سيتم الاعتماد أكثر على الزخم والمستويات.")
        elif is_bull_market:
            st.success(f"**إيجابي:** السعر ({last_close:.2f}) فوق **SMA200** ({last_sma200:.2f}) → اتجاه صاعد طويل.")
        else:
            st.error(f"**سلبي:** السعر ({last_close:.2f}) تحت **SMA200** ({last_sma200:.2f}) → اتجاه عام ضعيف.")

    with col_t2:
        if np.isnan(last_sma50) or np.isnan(last_sma200):
            st.info("لا يوجد بيانات كافية لتقييم Golden Cross.")
        elif is_golden_cross:
            st.info("**الترتيب إيجابي:** SMA50 فوق SMA200 → يدعم استمرار الصعود.")
        else:
            st.warning("**الترتيب سلبي:** SMA50 تحت SMA200 → ضغط هابط محتمل.")

    st.markdown("##### 2️⃣ الزخم والمؤشرات (Momentum):")
    col_m1, col_m2 = st.columns(2)

    with col_m1:
        st.write(f"**RSI: {last_rsi:.1f}**")
        if rsi_status == "overbought":
            st.warning("⚠️ تشبع شرائي: احتمالية تصحيح أعلى — الحذر من الشراء المتأخر.")
        elif rsi_status == "oversold":
            st.success("💎 تشبع بيعي: قد تكون منطقة ارتداد للمضاربين (مع إدارة مخاطر).")
        else:
            st.info("⚖️ حيادي: الزخم طبيعي — القرار يعتمد على كسر/اختراق.")

    with col_m2:
        st.write("**MACD:**")
        if last_macd > last_signal:
            st.success("🟢 إيجابي: MACD فوق Signal → زخم صاعد.")
        else:
            st.error("🔴 سلبي: MACD تحت Signal → ضعف في الزخم.")

    st.markdown("---")
    st.markdown("##### 💡 الخلاصة الفنية:")

    score = 0.0

    # Trend
    if not np.isnan(last_sma200) and is_bull_market:
        score += 1.0
    if not np.isnan(last_sma50) and not np.isnan(last_sma200) and is_golden_cross:
        score += 1.0

    # Momentum
    if last_macd > last_signal:
        score += 1.0

    if 30 < last_rsi < 70:
        score += 0.5
    elif last_rsi < 30:
        score += 1.0

    if itv == "1mo" and np.isnan(last_sma200):
        score += 0.25

    if score >= 3.5:
        st.success("### ✅ النظرة العامة: إيجابية قوية (Strong Buy Area)")
        st.write("الاتجاه/الزخم داعم. راقب مناطق المقاومة لإدارة دخول أفضل.")
    elif score <= 1.0:
        st.error("### ⛔ النظرة العامة: سلبية (Sell / Avoid)")
        st.write("الإشارات تميل للضعف. الأفضل الانتظار أو الالتزام بإدارة مخاطر صارمة.")
    else:
        st.warning("### ✋ النظرة العامة: حذر / ترقب (Hold)")
        st.write("الإشارات متضاربة. انتظر كسر مقاومة/دعم أو تحسن الزخم قبل قرار قوي.")
