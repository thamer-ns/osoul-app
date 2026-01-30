import os
import json
import pandas as pd
import numpy as np
from datetime import datetime

from config import COMMISSION_RATE


# ============================================================
# Utils
# ============================================================
def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if isinstance(df.index, pd.DatetimeIndex):
        return df.sort_index()

    # لو فيه عمود Date/Datetime/date
    for c in ["Date", "Datetime", "date", "timestamp"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
            df = df.dropna(subset=[c]).set_index(c).sort_index()
            return df

    return df


def _safe_float(x, default=0.0):
    try:
        v = float(x)
        if np.isfinite(v):
            return v
        return default
    except Exception:
        return default


def _data_dir() -> str:
    # مجلد محلي لحفظ نتائج المختبر
    base = os.path.join(os.path.dirname(__file__), "lab_store")
    os.makedirs(base, exist_ok=True)
    return base


def _results_path() -> str:
    return os.path.join(_data_dir(), "backtest_results.csv")


def save_lab_result(payload: dict) -> None:
    """
    يسجل نتيجة Backtest في CSV لتغذية التعلم لاحقاً (ai_engine).
    """
    path = _results_path()
    row = payload.copy()
    row["ts"] = datetime.utcnow().isoformat()

    df_row = pd.DataFrame([row])
    if os.path.exists(path):
        try:
            old = pd.read_csv(path)
            out = pd.concat([old, df_row], ignore_index=True)
        except Exception:
            out = df_row
    else:
        out = df_row

    out.to_csv(path, index=False)


def list_strategies() -> list:
    return list(STRATEGY_CATALOG.keys())


# ============================================================
# Indicators
# ============================================================
def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = _ensure_datetime_index(df)

    # تحصين الأعمدة
    req = ["Open", "High", "Low", "Close", "Volume"]
    for c in req:
        if c not in df.columns:
            if c == "Open" and "Close" in df.columns:
                df["Open"] = df["Close"]
            else:
                df[c] = np.nan

    df = df.dropna(subset=["Close"]).copy()

    # SMA
    df["SMA_20"] = df["Close"].rolling(20).mean()
    df["SMA_50"] = df["Close"].rolling(50).mean()

    # RSI(14)
    delta = df["Close"].diff()
    avg_gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
    avg_loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss
    rs = rs.replace([np.inf, -np.inf], np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))
    df["RSI"] = df["RSI"].fillna(50)

    # ATR(14)
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR_14"] = tr.rolling(14).mean()

    # Ichimoku (9,26,52)
    # Tenkan
    period9_high = df["High"].rolling(9).max()
    period9_low = df["Low"].rolling(9).min()
    df["ICH_TENKAN"] = (period9_high + period9_low) / 2

    # Kijun
    period26_high = df["High"].rolling(26).max()
    period26_low = df["Low"].rolling(26).min()
    df["ICH_KIJUN"] = (period26_high + period26_low) / 2

    # Senkou A & B (Shifted 26)
    df["ICH_SENKOU_A"] = ((df["ICH_TENKAN"] + df["ICH_KIJUN"]) / 2).shift(26)

    period52_high = df["High"].rolling(52).max()
    period52_low = df["Low"].rolling(52).min()
    df["ICH_SENKOU_B"] = ((period52_high + period52_low) / 2).shift(26)

    # Chikou (Lagging 26)
    df["ICH_CHIKOU"] = df["Close"].shift(-26)

    # VSA helpers
    df["VOL_MA20"] = df["Volume"].rolling(20).mean()
    df["RANGE"] = (df["High"] - df["Low"])
    df["RANGE_MA20"] = df["RANGE"].rolling(20).mean()

    # نحذف أقل قدر لازم
    df = df.dropna(subset=["SMA_20", "SMA_50", "RSI"]).copy()
    return df


# ============================================================
# Strategy Signals (return Series with 1 buy, -1 sell, 0 hold)
# ============================================================
def sig_trend(df: pd.DataFrame) -> pd.Series:
    # Trend: فوق SMA50 + RSI>50 / خروج تحت SMA50
    buy = (df["Close"] > df["SMA_50"]) & (df["RSI"] > 50)
    sell = (df["Close"] < df["SMA_50"])
    s = pd.Series(0, index=df.index)
    s.loc[buy] = 1
    s.loc[sell] = -1
    return s


def sig_sniper(df: pd.DataFrame) -> pd.Series:
    # Sniper: اختراق SMA20 يومها (تقاطع) / خروج تحت SMA20
    buy = (df["Close"] > df["SMA_20"]) & (df["Close"].shift(1) <= df["SMA_20"].shift(1))
    sell = (df["Close"] < df["SMA_20"])
    s = pd.Series(0, index=df.index)
    s.loc[buy] = 1
    s.loc[sell] = -1
    return s


def sig_rsi_meanrev(df: pd.DataFrame) -> pd.Series:
    # Mean Reversion: RSI<30 دخول، خروج RSI>55 أو كسر SMA20
    buy = (df["RSI"] < 30)
    sell = (df["RSI"] > 55) | (df["Close"] < df["SMA_20"])
    s = pd.Series(0, index=df.index)
    s.loc[buy] = 1
    s.loc[sell] = -1
    return s


def sig_ichimoku_break(df: pd.DataFrame) -> pd.Series:
    # Ichimoku Breakout (مبسطة):
    # دخول: Close فوق السحابة + Tenkan فوق Kijun
    # خروج: Close تحت Kijun أو تحت السحابة
    cloud_top = np.maximum(df["ICH_SENKOU_A"], df["ICH_SENKOU_B"])
    cloud_bot = np.minimum(df["ICH_SENKOU_A"], df["ICH_SENKOU_B"])

    buy = (df["Close"] > cloud_top) & (df["ICH_TENKAN"] > df["ICH_KIJUN"])
    sell = (df["Close"] < df["ICH_KIJUN"]) | (df["Close"] < cloud_bot)

    s = pd.Series(0, index=df.index)
    s.loc[buy] = 1
    s.loc[sell] = -1
    return s


def sig_vsa_spring(df: pd.DataFrame) -> pd.Series:
    # VSA "Spring" مبسط:
    # دخول: Low يكسر قاع 20 يوم ثم إغلاق أعلى (رفض) + Volume أعلى من متوسطه
    # خروج: Close تحت SMA20
    prev_low20 = df["Low"].shift(1).rolling(20).min()
    spring = (df["Low"] < prev_low20) & (df["Close"] > df["Open"])
    vol_ok = (df["Volume"] > (df["VOL_MA20"] * 1.2))
    buy = spring & vol_ok
    sell = (df["Close"] < df["SMA_20"])

    s = pd.Series(0, index=df.index)
    s.loc[buy] = 1
    s.loc[sell] = -1
    return s


# ============================================================
# Strategy Catalog
# ============================================================
STRATEGY_CATALOG = {
    "Trend": {
        "name_ar": "ترند (SMA50 + RSI)",
        "signal_fn": sig_trend,
        "min_bars": 60,
    },
    "Sniper": {
        "name_ar": "سنايبر (SMA20 Break)",
        "signal_fn": sig_sniper,
        "min_bars": 60,
    },
    "RSI_MeanReversion": {
        "name_ar": "ارتداد RSI (Mean Reversion)",
        "signal_fn": sig_rsi_meanrev,
        "min_bars": 60,
    },
    "Ichimoku_Breakout": {
        "name_ar": "إيشيموكو (اختراق السحابة)",
        "signal_fn": sig_ichimoku_break,
        "min_bars": 120,
    },
    "VSA_Spring": {
        "name_ar": "VSA (Spring)",
        "signal_fn": sig_vsa_spring,
        "min_bars": 80,
    },
}


def _resolve_strategy_key(strategy: str) -> str | None:
    if not strategy:
        return None
    s = str(strategy).strip()

    # Exact match
    if s in STRATEGY_CATALOG:
        return s

    # Contains match (مرن مع نصوص الواجهة)
    s_low = s.lower()
    for k in STRATEGY_CATALOG:
        if k.lower() in s_low:
            return k

    # بعض المرادفات
    if "mean" in s_low or "reversion" in s_low:
        return "RSI_MeanReversion"
    if "ichi" in s_low or "سحابة" in s or "ايشيموكو" in s:
        return "Ichimoku_Breakout"
    if "vsa" in s_low:
        return "VSA_Spring"

    return None


# ============================================================
# Backtest Core
# ============================================================
def run_backtest(df: pd.DataFrame, strategy: str, capital: float = 100000, symbol: str = "", sector: str = ""):
    if df is None or len(df) < 60:
        return None

    df = _ensure_datetime_index(df)

    # تحصين الأعمدة الأساسية
    required_cols = {"Open", "Close", "High", "Low", "Volume"}
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        if "Open" in missing and "Close" in df.columns:
            df = df.copy()
            df["Open"] = df["Close"]
            missing.remove("Open")
        if missing:
            return None

    df = calculate_indicators(df)
    if df.empty:
        return None

    key = _resolve_strategy_key(strategy)
    if not key:
        return None

    spec = STRATEGY_CATALOG[key]
    if len(df) < int(spec.get("min_bars", 60)):
        return None

    # إشارات
    sig = spec["signal_fn"](df).fillna(0)
    df["Signal"] = sig.astype(int)

    # ✅ منع التحيز للمستقبل: تنفيذ إشارة اليوم على افتتاح الغد
    df["Trade_Signal"] = df["Signal"].shift(1).fillna(0)

    cash = float(capital)
    shares = 0
    log = []
    hist = []

    comm = float(COMMISSION_RATE or 0.0)

    for r in df.itertuples():
        open_p = _safe_float(getattr(r, "Open", getattr(r, "Close", 0)), 0)
        close_p = _safe_float(getattr(r, "Close", 0), 0)
        sigv = _safe_float(getattr(r, "Trade_Signal", 0), 0)

        d = r.Index.strftime("%Y-%m-%d") if hasattr(r.Index, "strftime") else str(r.Index)

        # Mark-to-market لو السعر غير صالح
        if open_p <= 0 or close_p <= 0:
            hist.append(cash + shares * close_p)
            continue

        # شراء
        if sigv == 1 and shares == 0:
            invest = cash / (1 + comm)
            qty = int(invest / open_p)
            if qty > 0:
                cost = qty * open_p * (1 + comm)
                cash -= cost
                shares = qty
                log.append({"Date": d, "Type": "Buy", "Price": open_p, "Qty": qty, "Cash": cash, "Value": cost})

        # بيع
        elif sigv == -1 and shares > 0:
            revenue = shares * open_p * (1 - comm)
            cash += revenue
            log.append({"Date": d, "Type": "Sell", "Price": open_p, "Qty": shares, "Cash": cash, "Value": revenue})
            shares = 0

        hist.append(cash + shares * close_p)

    df["Portfolio_Value"] = hist
    final_val = float(hist[-1]) if hist else float(capital)
    ret_pct = ((final_val - float(capital)) / float(capital)) * 100.0

    trades_df = pd.DataFrame(log)

    # ✅ سجل النتيجة للمختبر
    try:
        save_lab_result({
            "symbol": symbol or "",
            "sector": sector or "",
            "strategy_key": key,
            "strategy_name_ar": spec.get("name_ar", key),
            "capital": float(capital),
            "final_value": final_val,
            "return_pct": ret_pct,
            "trades_count": int(len(trades_df) // 2) if not trades_df.empty else 0,
        })
    except Exception:
        pass

    return {
        "strategy_key": key,
        "strategy_name_ar": spec.get("name_ar", key),
        "return_pct": ret_pct,
        "final_value": final_val,
        "trades_log": trades_df,
        "df": df,
    }
