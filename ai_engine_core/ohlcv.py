# ai_engine_core/ohlcv.py

import pandas as pd

def _ensure_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    يطبع أسماء الأعمدة إلى Open/High/Low/Close/Volume
    ويفك MultiIndex إذا موجود.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    # فك MultiIndex الأعمدة (أحياناً من yfinance)
    try:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [str(c[-1]) for c in df.columns]
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/ohlcv.py:17')

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
    if m_open and m_open != "Open":
        ren[m_open] = "Open"
    if m_high and m_high != "High":
        ren[m_high] = "High"
    if m_low and m_low != "Low":
        ren[m_low] = "Low"
    if m_close and m_close != "Close":
        ren[m_close] = "Close"
    if m_vol and m_vol != "Volume":
        ren[m_vol] = "Volume"

    if ren:
        df = df.rename(columns=ren)

    # تأكد الأعمدة الأساسية موجودة
    needed = ["Open", "High", "Low", "Close"]
    for c in needed:
        if c not in df.columns:
            raise ValueError(f"missing {c}")

    if "Volume" not in df.columns:
        df["Volume"] = 0.0

    # تنظيف أنواع البيانات
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        try:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/ohlcv.py:65')

    df = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    return df
