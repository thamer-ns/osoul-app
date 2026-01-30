# backtester.py
import pandas as pd

# ============================
# ✅ Strategy Normalizer
# ============================
def normalize_strategy(strategy) -> str:
    """
    يحول أي شكل للاستراتيجية إلى string:
    - "Trend"
    - ("Trend","ترند")
    - {"key":"Trend","name":"ترند"}
    """
    if strategy is None:
        return "Trend"

    # tuple/list -> خذ أول عنصر كـ key
    if isinstance(strategy, (tuple, list)):
        if len(strategy) == 0:
            return "Trend"
        return str(strategy[0])

    # dict -> خذ key/id/value/name
    if isinstance(strategy, dict):
        return str(strategy.get("key") or strategy.get("id") or strategy.get("value") or strategy.get("name") or "Trend")

    # string/other
    return str(strategy)


def list_strategies():
    """
    ✅ ترجع قائمة نصوص فقط (strings) لتجنب مشاكل tuples في الواجهة.
    إذا تحتاج أسماء عربية للعرض، استخدم STRATEGY_META داخل الملف.
    """
    return list(STRATEGY_META.keys())


# ============================
# Strategy Metadata (AR names)
# ============================
STRATEGY_META = {
    "Trend": {"name_ar": "ترند (Trend)"},
    "Sniper": {"name_ar": "قناص (Sniper)"},
}


# ============================
# Helpers
# ============================
def _ensure_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    # توحيد أسماء الأعمدة
    cols = {c: c.strip() for c in df.columns}
    df = df.rename(columns=cols)

    # بعض المصادر تكون lower-case
    if "Close" not in df.columns and "close" in df.columns:
        df = df.rename(columns={"close": "Close"})
    if "Open" not in df.columns and "open" in df.columns:
        df = df.rename(columns={"open": "Open"})
    if "High" not in df.columns and "high" in df.columns:
        df = df.rename(columns={"high": "High"})
    if "Low" not in df.columns and "low" in df.columns:
        df = df.rename(columns={"low": "Low"})
    if "Volume" not in df.columns and "volume" in df.columns:
        df = df.rename(columns={"volume": "Volume"})

    if "Close" not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"]).copy()

    # تأكد من index تاريخي إن أمكن
    if "Date" in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        try:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.set_index("Date")
        except Exception:
            pass

    return df


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(0)


# ============================
# Simple Strategies (safe)
# ============================
def _run_trend(df: pd.DataFrame):
    """
    Trend: تقاطع SMA20 فوق SMA50 شراء، والعكس بيع.
    """
    out = df.copy()
    out["SMA20"] = _sma(out["Close"], 20)
    out["SMA50"] = _sma(out["Close"], 50)
    out["signal"] = 0
    out.loc[out["SMA20"] > out["SMA50"], "signal"] = 1
    out.loc[out["SMA20"] < out["SMA50"], "signal"] = -1
    return out


def _run_sniper(df: pd.DataFrame):
    """
    Sniper: RSI<30 شراء، RSI>70 بيع.
    """
    out = df.copy()
    out["RSI"] = _rsi(out["Close"], 14)
    out["signal"] = 0
    out.loc[out["RSI"] < 30, "signal"] = 1
    out.loc[out["RSI"] > 70, "signal"] = -1
    return out


STRATEGY_RUNNERS = {
    "Trend": _run_trend,
    "Sniper": _run_sniper,
}


# ============================
# ✅ Main Backtest
# ============================
def run_backtest(data, strategy, initial_capital: float = 100000.0, symbol=None, sector=None):
    """
    يرجع dict:
      - return_pct
      - df (Portfolio_Value)
      - trades_log (DataFrame)
      - strategy_name_ar
    """
    # ✅ fix جوهري: ضمان string
    strategy_key = normalize_strategy(strategy).strip()
    if not strategy_key:
        strategy_key = "Trend"

    # بعض الأكواد القديمة تسوي .title() -> خليه دايم string
    try:
        strategy_key_title = str(strategy_key).title()
    except Exception:
        strategy_key_title = "Trend"

    if strategy_key not in STRATEGY_RUNNERS:
        # جرّب نسخة title لو كانت "trend" etc
        if strategy_key_title in STRATEGY_RUNNERS:
            strategy_key = strategy_key_title
        else:
            strategy_key = "Trend"

    df = _ensure_ohlc(data)
    if df.empty or len(df) < 50:
        return None

    runner = STRATEGY_RUNNERS[strategy_key]
    bt = runner(df)

    # محاكاة بسيطة: دخول عند signal=1 وخروج عند signal=-1
    cash = float(initial_capital)
    position = 0.0
    entry_price = 0.0
    trades = []

    port_vals = []
    in_pos = False

    for idx, row in bt.iterrows():
        price = float(row["Close"])
        sig = int(row.get("signal", 0))

        # شراء
        if (not in_pos) and sig == 1 and cash > 0:
            position = cash / price
            entry_price = price
            cash = 0.0
            in_pos = True
            trades.append({"date": idx, "type": "BUY", "price": price})

        # بيع
        elif in_pos and sig == -1 and position > 0:
            cash = position * price
            pnl = (price - entry_price) * position
            trades.append({"date": idx, "type": "SELL", "price": price, "pnl": pnl})
            position = 0.0
            entry_price = 0.0
            in_pos = False

        # قيمة المحفظة
        port = cash + (position * price)
        port_vals.append(port)

    bt = bt.copy()
    bt["Portfolio_Value"] = port_vals

    final_val = float(bt["Portfolio_Value"].iloc[-1]) if not bt.empty else float(initial_capital)
    ret_pct = ((final_val - float(initial_capital)) / float(initial_capital) * 100.0) if initial_capital else 0.0

    trades_df = pd.DataFrame(trades)
    if not trades_df.empty and "date" in trades_df.columns:
        try:
            trades_df["date"] = pd.to_datetime(trades_df["date"])
        except Exception:
            pass

    return {
        "symbol": symbol,
        "sector": sector,
        "strategy_id": strategy_key,
        "strategy_name_ar": STRATEGY_META.get(strategy_key, {}).get("name_ar", strategy_key),
        "return_pct": float(ret_pct),
        "final_value": float(final_val),
        "df": bt,
        "trades_log": trades_df,
    }
