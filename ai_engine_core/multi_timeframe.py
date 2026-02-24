from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


def _norm_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    d = df.copy()
    if not isinstance(d.index, pd.DatetimeIndex):
        if "Date" in d.columns:
            d["Date"] = pd.to_datetime(d["Date"], errors="coerce")
            d = d.set_index("Date")
        else:
            d.index = pd.to_datetime(d.index, errors="coerce")
    d = d[~pd.isna(d.index)].sort_index()
    return d


def resample_weekly_saudi(df_daily: pd.DataFrame) -> pd.DataFrame:
    d = _norm_ohlcv(df_daily)
    if d.empty or not {"Open", "High", "Low", "Close"}.issubset(set(d.columns)):
        return pd.DataFrame()
    out = pd.DataFrame(
        {
            "Open": pd.to_numeric(d["Open"], errors="coerce").resample("W-THU").first(),
            "High": pd.to_numeric(d["High"], errors="coerce").resample("W-THU").max(),
            "Low": pd.to_numeric(d["Low"], errors="coerce").resample("W-THU").min(),
            "Close": pd.to_numeric(d["Close"], errors="coerce").resample("W-THU").last(),
            "Volume": pd.to_numeric(d["Volume"], errors="coerce").fillna(0).resample("W-THU").sum() if "Volume" in d.columns else 0,
        }
    )
    return out.dropna(subset=["Open", "High", "Low", "Close"])


def _trend_from_close(close: pd.Series) -> str:
    c = pd.to_numeric(close, errors="coerce").dropna()
    if len(c) < 15:
        return "unknown"
    sma10 = c.rolling(10).mean()
    sma20 = c.rolling(20).mean()
    last = float(c.iloc[-1])
    s10 = float(sma10.iloc[-1]) if pd.notna(sma10.iloc[-1]) else last
    s20 = float(sma20.iloc[-1]) if pd.notna(sma20.iloc[-1]) else s10
    if last >= s10 >= s20:
        return "bull"
    if last <= s10 <= s20:
        return "bear"
    return "neutral"


def evaluate_daily_weekly_alignment(df_daily: pd.DataFrame, daily_bias: Optional[str] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "applied": True,
        "aligned": True,
        "daily_trend": "unknown",
        "weekly_trend": "unknown",
        "confidence_delta": 0.0,
        "reason": "",
    }
    try:
        d = _norm_ohlcv(df_daily)
        w = resample_weekly_saudi(d)
        if d.empty or w.empty:
            out.update({"applied": False, "reason": "MTF: بيانات غير كافية للتحقق الأسبوعي/اليومي"})
            return out
        out["daily_trend"] = _trend_from_close(d["Close"])
        out["weekly_trend"] = _trend_from_close(w["Close"])

        bias = (daily_bias or "").lower().strip()
        wt = out["weekly_trend"]
        if bias == "buy" and wt == "bear":
            out.update({"aligned": False, "confidence_delta": -12.0, "reason": "⚠️ اليومي إيجابي لكن الاتجاه الأسبوعي هابط (تم تخفيف التوصية)."})
        elif bias == "sell" and wt == "bull":
            out.update({"aligned": False, "confidence_delta": -12.0, "reason": "⚠️ اليومي سلبي لكن الاتجاه الأسبوعي صاعد (تحقق قبل قرار قوي)."})
        elif bias in {"buy", "sell"} and wt in {"bull", "bear"}:
            out.update({"aligned": True, "confidence_delta": 4.0, "reason": "✅ توافق جيد بين الاتجاه اليومي والأسبوعي."})
        else:
            out.update({"aligned": True, "confidence_delta": 0.0, "reason": "ℹ️ توافق متعدد الأطر محايد/غير حاسم."})
        return out
    except Exception as e:
        out.update({"applied": False, "reason": f"MTF error: {type(e).__name__}"})
        return out
