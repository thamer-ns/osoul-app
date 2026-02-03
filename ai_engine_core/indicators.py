# ai_engine_core/indicators.py

import pandas as pd
import numpy as np

def _compute_indicators(df: pd.DataFrame):
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

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    out["rsi14"] = rsi.bfill().fillna(50)

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    out["macd"] = macd
    out["macd_signal"] = signal
    out["macd_hist"] = hist

    # ATR
    try:
        prev_close = close.shift(1)
        tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        out["atr14"] = tr.rolling(14).mean()
    except Exception:
        pass

    # ADX
    try:
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        prev_close = close.shift(1)
        tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)

        atr = tr.rolling(14).mean()
        plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(14).sum() / atr.replace(0, np.nan))
        minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(14).sum() / atr.replace(0, np.nan))
        dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
        out["adx14"] = dx.rolling(14).mean().bfill()
        out["plus_di14"] = plus_di.bfill()
        out["minus_di14"] = minus_di.bfill()
    except Exception:
        pass

    # Stochastic
    try:
        ll14 = low.rolling(14).min()
        hh14 = high.rolling(14).max()
        k = 100 * (close - ll14) / (hh14 - ll14).replace(0, np.nan)
        d = k.rolling(3).mean()
        out["stoch_k"] = k.bfill()
        out["stoch_d"] = d.bfill()
    except Exception:
        pass

    # OBV
    try:
        direction = np.sign(close.diff()).fillna(0)
        obv = (direction * vol).fillna(0).cumsum()
        out["obv"] = obv
    except Exception:
        pass

    # Volatility
    try:
        ret = close.pct_change().fillna(0)
        out["vol20"] = ret.rolling(20).std().bfill()
    except Exception:
        pass

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
