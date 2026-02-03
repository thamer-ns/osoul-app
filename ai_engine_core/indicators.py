# ai_engine_core/indicators.py

import pandas as pd
import numpy as np

def _ensure_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    # ✅ انسخ نفس دالتك كما هي من الملف الأصلي
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    try:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [str(c[-1]) for c in df.columns]
    except Exception:
        pass

    cols = {c: c for c in df.columns}
    lower = {str(c).lower(): c for c in df.columns}

    def pick(*names):
        for n in names:
            if n in cols:
                return cols[n]
            if n.lower() in lower:
                return lower[n.lower()]
        return None

    m_open = pick("Open", "open", "OPEN")
    m_high = pick("High", "high", "HIGH")
    m_low = pick("Low", "low", "LOW")
    m_close = pick("Close", "close", "Adj Close", "adjclose", "adj_close", "ADJ CLOSE")
    m_vol = pick("Volume", "volume", "VOL", "vol")

    ren = {}
    if m_open and m_open != "Open": ren[m_open] = "Open"
    if m_high and m_high != "High": ren[m_high] = "High"
    if m_low and m_low != "Low": ren[m_low] = "Low"
    if m_close and m_close != "Close": ren[m_close] = "Close"
    if m_vol and m_vol != "Volume": ren[m_vol] = "Volume"
    if ren:
        df = df.rename(columns=ren)

    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            raise ValueError(f"missing {c}")

    if "Volume" not in df.columns:
        df["Volume"] = 0.0

    for c in ["Open", "High", "Low", "Close", "Volume"]:
        try:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        except Exception:
            pass

    df = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    return df

def _compute_indicators(df: pd.DataFrame):
    # ✅ انسخ نفس دالتك كما هي
    out = {}
    if df is None or df.empty or len(df) < 60:
        return out

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    vol = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series([0] * len(df), index=df.index)

    out["sma20"] = close.rolling(20).mean()
    out["sma50"] = close.rolling(50).mean()
    out["sma200"] = close.rolling(200).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    out["rsi14"] = rsi.bfill().fillna(50)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    out["macd"] = macd
    out["macd_signal"] = signal
    out["macd_hist"] = hist

    try:
        prev_close = close.shift(1)
        tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        out["atr14"] = tr.rolling(14).mean()
    except Exception:
        pass

    # ... باقي المؤشرات عندك (ADX/Stoch/OBV/vol/fib) انسخها كما هي إن رغبت
    # (أنا تركتها مختصرة هنا لتجنب تكرار ضخم - لكن الأفضل نقلها كاملة من ملفك)

    # Fib + Range
    try:
        look = 120 if len(df) >= 120 else len(df)
        hh = float(high.iloc[-look:].max())
        ll = float(low.iloc[-look:].min())
        rng = hh - ll
        if rng > 0:
            out["fib382"] = ll + 0.382 * rng
            out["range_high"] = hh
            out["range_low"] = ll
    except Exception:
        pass

    return out
