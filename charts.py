import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd

from market_data import get_chart_history


# ============================================================
# ✅ Data Normalizer (Fix Yahoo MultiIndex / lowercase / non-string cols)
# ============================================================
def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    يضمن وجود أعمدة OHLCV بأسماء:
    Open, High, Low, Close, Volume
    ويتعامل مع:
    - أعمدة lowercase (open/close...)
    - MultiIndex من yfinance
    - أعمدة غير نصية (تسبب title() error سابقاً)
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # Fix MultiIndex columns (sometimes from yfinance)
    if isinstance(df.columns, pd.MultiIndex):
        # Try to pick first level names
        # Often looks like ('Open', '2270.SR') etc
        df.columns = [c[0] if isinstance(c, tuple) and len(c) > 0 else str(c) for c in df.columns]

    # Make all columns strings safely
    df.columns = [str(c) for c in df.columns]

    # Normalize common variants
    col_map = {c.lower(): c for c in df.columns}

    def pick(name):
        # prefer exact match ignoring case
        for k in [name.lower(), name.lower().replace("_", ""), name.lower().replace("-", "")]:
            for cand in df.columns:
                if cand.lower().replace("_", "").replace("-", "") == k:
                    return cand
        return None

    o = pick("open")
    h = pick("high")
    l = pick("low")
    c = pick("close")
    v = pick("volume")

    # If "Adj Close" exists but no Close, fallback
    if c is None:
        adj = pick("adj close") or pick("adjclose")
        if adj is not None:
            c = adj

    # If open missing, fallback close
    if o is None and c is not None:
        df["Open"] = df[c]
        o = "Open"

    # If some are missing, return empty (chart can't be built)
    needed = [o, h, l, c, v]
    if any(x is None for x in needed):
        return pd.DataFrame()

    out = df.rename(columns={o: "Open", h: "High", l: "Low", c: "Close", v: "Volume"})
    # Ensure numeric
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    # Sort index if datetime-like
    try:
        out = out.sort_index()
    except Exception:
        pass

    out = out.dropna(subset=["Open", "High", "Low", "Close"])
    return out


# ============================================================
# --- دالة مساعدة لحساب ورسم الدعم والمقاومة ---
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

    # قلل العدد لأفضل مستويات (الأقرب للسعر الحالي)
    last_close = float(df["Close"].iloc[-1])
    levels = sorted(levels, key=lambda x: abs(x[1] - last_close))[:max_levels]

    # رسم
    for date, level, type_ in levels:
        color = "#00C853" if type_ == "Support" else "#D50000"
        fig.add_shape(
            type="line",
            x0=date, y0=level, x1=df.index[-1], y1=level,
            line=dict(color=color, width=1, dash="dash"),
            xref="x", yref="y",
            row=1, col=1
        )


# ============================================================
# --- الدالة الرئيسية ---
# ============================================================
def render_technical_chart(symbol, period="2y", interval="1d"):
    # 1) جلب البيانات
    raw = get_chart_history(symbol, period, interval)
    df = _normalize_ohlcv(raw)

    if df is None or df.empty or len(df) < 80:
        st.warning("البيانات التاريخية غير كافية أو غير صالحة للرسم الفني.")
        return

    # 2) الحسابات الفنية
    df["SMA_50"] = df["Close"].rolling(window=50).mean()
    df["SMA_200"] = df["Close"].rolling(window=200).mean()

    # Bollinger Bands
    ma20 = df["Close"].rolling(20).mean()
    std20 = df["Close"].rolling(20).std()
    df["BB_Upper"] = ma20 + (std20 * 2)
    df["BB_Lower"] = ma20 - (std20 * 2)
    df["BB_Width"] = (df["BB_Upper"] - df["BB_Lower"]) / ma20.replace(0, np.nan)

    # RSI (EWMA)
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

    # تأكد من وجود SMA200 (لو بيانات قليلة)
    if df["SMA_200"].isna().all():
        st.info("ملاحظة: لا توجد 200 شمعة كافية لحساب SMA 200 بدقة.")

    # 3) تجهيز الرسم (آخر 300 شمعة أو أقل)
    plot_df = df.tail(320).copy()

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=(f"السعر: {symbol}", "RSI", "MACD")
    )

    # شموع
    fig.add_trace(
        go.Candlestick(
            x=plot_df.index,
            open=plot_df["Open"], high=plot_df["High"],
            low=plot_df["Low"], close=plot_df["Close"],
            name="السعر"
        ),
        row=1, col=1
    )

    # متوسطات
    fig.add_trace(
        go.Scatter(x=plot_df.index, y=plot_df["SMA_50"], line=dict(color="orange", width=1.5), name="SMA 50"),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=plot_df.index, y=plot_df["SMA_200"], line=dict(color="#2962FF", width=2), name="SMA 200"),
        row=1, col=1
    )

    # Bollinger
    fig.add_trace(
        go.Scatter(x=plot_df.index, y=plot_df["BB_Upper"], line=dict(color="gray", width=1, dash="dot"), showlegend=False),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=plot_df.index, y=plot_df["BB_Lower"],
            line=dict(color="gray", width=1, dash="dot"),
            fill="tonexty", fillcolor="rgba(0,0,255,0.05)",
            showlegend=False
        ),
        row=1, col=1
    )

    # RSI
    fig.add_trace(
        go.Scatter(x=plot_df.index, y=plot_df["RSI"], line=dict(color="purple"), name="RSI"),
        row=2, col=1
    )
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    # MACD
    colors = np.where(plot_df["MACD_Hist"] >= 0, "#26a69a", "#ef5350")
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df["MACD_Hist"], marker_color=colors, name="Hist"), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["MACD"], line=dict(color="blue"), name="MACD"), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["Signal_Line"], line=dict(color="orange"), name="Signal"), row=3, col=1)

    fig.update_layout(
        height=820,
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        margin=dict(t=30, b=10, l=10, r=10),
    )
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_xaxes(showticklabels=False, row=2, col=1)

    # دعم/مقاومة
    if st.checkbox("🎯 إظهار مستويات الدعم والمقاومة (Auto S&R)", value=False, key=f"sr_{symbol}_{period}_{interval}"):
        add_support_resistance(fig, plot_df, sensitivity=3)

    st.plotly_chart(fig, use_container_width=True)

    # 4) التقرير الفني
    st.markdown("### 📋 التقرير الفني الذكي")

    # قيم أخيرة
    last_close = float(df["Close"].iloc[-1])
    last_sma50 = float(df["SMA_50"].iloc[-1]) if not pd.isna(df["SMA_50"].iloc[-1]) else np.nan
    last_sma200 = float(df["SMA_200"].iloc[-1]) if not pd.isna(df["SMA_200"].iloc[-1]) else np.nan
    last_rsi = float(df["RSI"].iloc[-1])
    last_macd = float(df["MACD"].iloc[-1])
    last_signal = float(df["Signal_Line"].iloc[-1])

    # منطق
    is_bull_market = (not np.isnan(last_sma200)) and (last_close > last_sma200)
    is_golden_cross = (not np.isnan(last_sma50)) and (not np.isnan(last_sma200)) and (last_sma50 > last_sma200)

    rsi_status = "neutral"
    if last_rsi > 70:
        rsi_status = "overbought"
    elif last_rsi < 30:
        rsi_status = "oversold"

    # 1) Trend
    st.markdown("##### 1️⃣ حالة الاتجاه (Trend):")
    col_t1, col_t2 = st.columns(2)

    with col_t1:
        if np.isnan(last_sma200):
            st.info("لا يوجد بيانات كافية لحساب SMA200 — سيتم الاعتماد على مؤشرات أخرى.")
        elif is_bull_market:
            st.success(
                f"**إيجابي:** السعر ({last_close:.2f}) فوق **SMA200** ({last_sma200:.2f}) → اتجاه صاعد طويل."
            )
        else:
            st.error(
                f"**سلبي:** السعر ({last_close:.2f}) تحت **SMA200** ({last_sma200:.2f}) → اتجاه عام ضعيف."
            )

    with col_t2:
        if np.isnan(last_sma50) or np.isnan(last_sma200):
            st.info("لا يوجد بيانات كافية لتقييم Golden Cross.")
        elif is_golden_cross:
            st.info("**الترتيب إيجابي:** SMA50 فوق SMA200 → يدعم استمرار الصعود.")
        else:
            st.warning("**الترتيب سلبي:** SMA50 تحت SMA200 → ضغط هابط محتمل.")

    # 2) Momentum
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

    # 3) Verdict
    st.markdown("---")
    st.markdown("##### 💡 الخلاصة الفنية:")

    score = 0.0
    if is_bull_market:
        score += 1
    if is_golden_cross:
        score += 1
    if last_macd > last_signal:
        score += 1
    if 30 < last_rsi < 70:
        score += 0.5
    elif last_rsi < 30:
        score += 1

    if score >= 3.5:
        st.success("### ✅ النظرة العامة: إيجابية قوية (Strong Buy Area)")
        st.write("الاتجاه العام جيد والزخم داعم. راقب مناطق المقاومة لإدارة دخول أفضل.")
    elif score <= 1:
        st.error("### ⛔ النظرة العامة: سلبية (Sell / Avoid)")
        st.write("الإشارات تميل للضعف. الأفضل الانتظار أو الالتزام بإدارة مخاطر صارمة.")
    else:
        st.warning("### ✋ النظرة العامة: حذر / ترقب (Hold)")
        st.write("الإشارات متضاربة. انتظر كسر مقاومة/دعم أو تحسن الزخم قبل قرار قوي.")