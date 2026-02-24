# ai_engine_core/indicators.py

import pandas as pd
import numpy as np


def _ffill_no_lookahead(s, fallback=None):
    """Forward-fill only to avoid lookahead bias from backfilling future values."""
    try:
        x = pd.Series(s).copy().ffill()
        if fallback is not None:
            x = x.fillna(fallback)
        return x
    except Exception:
        return s


def _compute_indicators(df: pd.DataFrame):
    """
    يرجع dict بنفس المفاتيح التي تعتمد عليها بقية الملفات.
    تحسينات:
    - RSI Wilder (أثبت)
    - ATR Wilder
    - ADX أقرب للمعيار (DI/ADX)
    - حماية من الأعمدة الناقصة والقسمة على صفر
    """
    out = {}
    if df is None or df.empty or len(df) < 60:
        return out

    # Required columns
    for c in ("Close", "High", "Low"):
        if c not in df.columns:
            return out

    close = pd.to_numeric(df["Close"], errors="coerce").astype(float)
    high = pd.to_numeric(df["High"], errors="coerce").astype(float)
    low = pd.to_numeric(df["Low"], errors="coerce").astype(float)

    # Volume optional
    if "Volume" in df.columns:
        vol = pd.to_numeric(df["Volume"], errors="coerce").fillna(0).astype(float)
    else:
        vol = pd.Series([0.0] * len(df), index=df.index)

    # SMAs
    out["sma20"] = close.rolling(20).mean()
    out["sma50"] = close.rolling(50).mean()
    out["sma200"] = close.rolling(200).mean()

    # =========================================================
    # RSI (Wilder)
    # =========================================================
    try:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)

        # Wilder smoothing via ewm(alpha=1/14)
        avg_gain = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        out["rsi14"] = _ffill_no_lookahead(rsi, fallback=50)
    except Exception:
        out["rsi14"] = pd.Series([50] * len(df), index=df.index)

    # =========================================================
    # MACD
    # =========================================================
    try:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal
        out["macd"] = macd
        out["macd_signal"] = signal
        out["macd_hist"] = hist
    except Exception:
        pass

    # =========================================================
    # ATR (Wilder)
    # =========================================================
    try:
        prev_close = close.shift(1)
        tr = pd.concat(
            [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1
        ).max(axis=1)

        atr14 = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
        out["atr14"] = atr14
    except Exception:
        pass

    # =========================================================
    # ADX (14) + DI
    # =========================================================
    try:
        up_move = high.diff()
        down_move = -low.diff()

        plus_dm = pd.Series(
            np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
            index=df.index
        )
        minus_dm = pd.Series(
            np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
            index=df.index
        )

        prev_close = close.shift(1)
        tr = pd.concat(
            [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1
        ).max(axis=1)

        atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()

        plus_di = 100 * (plus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / atr.replace(0, np.nan))
        minus_di = 100 * (minus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / atr.replace(0, np.nan))

        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.ewm(alpha=1/14, adjust=False, min_periods=14).mean()

        out["adx14"] = _ffill_no_lookahead(adx)
        out["plus_di14"] = _ffill_no_lookahead(plus_di)
        out["minus_di14"] = _ffill_no_lookahead(minus_di)
    except Exception:
        pass

    # =========================================================
    # Stochastic (14,3)
    # =========================================================
    try:
        ll14 = low.rolling(14).min()
        hh14 = high.rolling(14).max()
        k = 100 * (close - ll14) / (hh14 - ll14).replace(0, np.nan)
        d = k.rolling(3).mean()
        out["stoch_k"] = _ffill_no_lookahead(k)
        out["stoch_d"] = _ffill_no_lookahead(d)
    except Exception:
        pass

    # =========================================================
    # OBV
    # =========================================================
    try:
        direction = np.sign(close.diff()).fillna(0.0)
        obv = (direction * vol).fillna(0.0).cumsum()
        out["obv"] = obv
    except Exception:
        pass

    # =========================================================
    # Volatility (20)
    # =========================================================
    try:
        ret = close.pct_change().replace([np.inf, -np.inf], 0).fillna(0)
        out["vol20"] = _ffill_no_lookahead(ret.rolling(20).std(), fallback=0)
    except Exception:
        pass

    # =========================================================
    # Fib + Range (120 lookback)
    # =========================================================
    try:
        look = 120 if len(df) >= 120 else len(df)
        hh = float(pd.to_numeric(high.iloc[-look:], errors="coerce").max())
        ll = float(pd.to_numeric(low.iloc[-look:], errors="coerce").min())
        rng = hh - ll
        if rng > 0 and np.isfinite(rng):
            out["fib382"] = ll + 0.382 * rng
            out["range_high"] = hh
            out["range_low"] = ll
    except Exception:
        pass

    return out
