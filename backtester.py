# backtester.py
import json
import pandas as pd
import numpy as np
from config import COMMISSION_RATE


# ============================================================
# ✅ Strategy Catalog (مختبر الاستراتيجيات)
# ============================================================

STRATEGY_CATALOG = [
    {
        "key": "TREND",
        "name": "Trend (اتجاه)",
        "category": "Trend",
        "desc": "شراء مع اتجاه عام: فوق SMA50 و RSI>50. خروج بكسر SMA50.",
        "params": {"use_atr_sl": False, "sl_atr": 2.0, "use_atr_tp": False, "tp_atr": 3.0},
    },
    {
        "key": "SNIPER",
        "name": "Sniper (قنّاص)",
        "category": "Swing/Mean",
        "desc": "اختراق SMA20 للأعلى كدخول. خروج بكسر SMA20.",
        "params": {"use_atr_sl": False, "sl_atr": 1.8, "use_atr_tp": False, "tp_atr": 2.8},
    },
    {
        "key": "ICHIMOKU_TREND",
        "name": "Ichimoku Trend",
        "category": "Trend",
        "desc": "شراء: السعر فوق السحابة + تنكن>كيجن. خروج: كسر كيجن أو دخول السحابة.",
        "params": {"use_atr_sl": True, "sl_atr": 2.2, "use_atr_tp": False, "tp_atr": 0},
    },
    {
        "key": "SMC_LIQSWEEP_REV",
        "name": "SMC Liquidity Sweep Reversal",
        "category": "SMC",
        "desc": "شراء بعد صيد سيولة للأسفل (اختراق زائف للقاع) ثم رجوع الإغلاق فوق القاع السابق.",
        "params": {"use_atr_sl": True, "sl_atr": 2.0, "use_atr_tp": True, "tp_atr": 3.0},
    },
    {
        "key": "SMC_ORDERBLOCK",
        "name": "SMC Order Block Retest",
        "category": "SMC",
        "desc": "شراء عند إعادة اختبار Bullish Order Block (آخر شمعة هابطة قبل اندفاع صاعد قوي).",
        "params": {"use_atr_sl": True, "sl_atr": 2.2, "use_atr_tp": True, "tp_atr": 3.4},
    },
    {
        "key": "MS_BMS_RETEST",
        "name": "Market Structure BMS + Retest",
        "category": "Structure",
        "desc": "شراء بعد كسر قمة سوينغ ثم إعادة اختبار (Retest) للمستوى.",
        "params": {"use_atr_sl": True, "sl_atr": 2.0, "use_atr_tp": True, "tp_atr": 3.2},
    },
    {
        "key": "OTE_50",
        "name": "OTE / Fib 50% Pullback",
        "category": "Structure",
        "desc": "بعد موجة واضحة، شراء عند قرب 50% فيبو مع شمعة تأكيد.",
        "params": {"use_atr_sl": True, "sl_atr": 2.0, "use_atr_tp": True, "tp_atr": 3.0},
    },
    {
        "key": "VSA_STOPPING_VOL",
        "name": "VSA Stopping Volume",
        "category": "VSA",
        "desc": "شراء عند Stopping Volume (شمعة هابطة + فوليوم عالي + إغلاق في النصف الأعلى).",
        "params": {"use_atr_sl": True, "sl_atr": 2.0, "use_atr_tp": True, "tp_atr": 3.0},
    },
    {
        "key": "RANGE_BREAKOUT",
        "name": "Range Breakout (سكالب/اختراق)",
        "category": "Breakout",
        "desc": "اختراق أعلى 20 يوم مع فوليوم أعلى من المتوسط. خروج عند كسر SMA20 أو وقف ATR.",
        "params": {"use_atr_sl": True, "sl_atr": 1.6, "use_atr_tp": True, "tp_atr": 2.4},
    },
]


def list_strategies_df():
    rows = []
    for s in STRATEGY_CATALOG:
        rows.append({
            "key": s["key"],
            "name": s["name"],
            "category": s.get("category", ""),
            "desc": s.get("desc", ""),
        })
    return pd.DataFrame(rows)


# ============================================================
# 🧱 DB تسجيل استراتيجيات المختبر (اختياري – Fail-safe)
# ============================================================

def _safe_import_db():
    try:
        from database import execute_query, fetch_table
        return execute_query, fetch_table
    except Exception:
        return None, None


def ensure_lab_tables():
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    try:
        execute_query("""
        CREATE TABLE IF NOT EXISTS lab_strategies (
            id SERIAL PRIMARY KEY,
            key TEXT UNIQUE,
            name TEXT,
            category TEXT,
            description TEXT,
            rules_json TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """, ())
        return True
    except Exception:
        return False


def seed_lab_strategies():
    """
    يسجل جميع الاستراتيجيات داخل المختبر (DB) إن كانت متاحة.
    """
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return {"ok": False, "reason": "DB not available"}

    ensure_lab_tables()
    updated = 0
    for s in STRATEGY_CATALOG:
        try:
            rules = {"desc": s.get("desc", ""), "params": s.get("params", {})}
            execute_query(
                """
                INSERT INTO lab_strategies (key, name, category, description, rules_json)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (key)
                DO UPDATE SET
                    name=EXCLUDED.name,
                    category=EXCLUDED.category,
                    description=EXCLUDED.description,
                    rules_json=EXCLUDED.rules_json,
                    updated_at=NOW()
                """,
                (s["key"], s["name"], s.get("category", ""), s.get("desc", ""), json.dumps(rules, ensure_ascii=False)),
            )
            updated += 1
        except Exception:
            pass

    return {"ok": True, "updated": updated}


# ============================================================
# 📌 Indicators
# ============================================================

def _atr(df, n=14):
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1/n, adjust=False).mean()
    return atr


def _ichimoku(df):
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    chikou = close.shift(-26)
    return tenkan, kijun, span_a, span_b, chikou


def _pivot_points(series, left=3, right=3, mode="high"):
    if series is None or len(series) < left + right + 3:
        return []
    pivots = []
    arr = series.values
    for i in range(left, len(arr) - right):
        window = arr[i - left : i + right + 1]
        if mode == "high":
            if arr[i] == np.max(window):
                pivots.append((i, float(arr[i])))
        else:
            if arr[i] == np.min(window):
                pivots.append((i, float(arr[i])))
    return pivots


def calculate_indicators(df):
    df = df.copy()

    # ترتيب زمني
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.sort_index()

    # SMA
    df["SMA_20"] = df["Close"].rolling(20).mean()
    df["SMA_50"] = df["Close"].rolling(50).mean()

    # RSI
    delta = df["Close"].diff()
    avg_gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
    avg_loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = (avg_gain / avg_loss).replace([np.inf, -np.inf], np.nan)
    df["RSI"] = (100 - (100 / (1 + rs))).fillna(50)

    # ATR
    df["ATR_14"] = _atr(df, 14)

    # Ichimoku
    tenkan, kijun, span_a, span_b, chikou = _ichimoku(df)
    df["TENKAN"] = tenkan
    df["KIJUN"] = kijun
    df["SPAN_A"] = span_a
    df["SPAN_B"] = span_b
    df["CHIKOU"] = chikou

    # Volume features
    df["VOL_AVG20"] = df["Volume"].astype(float).rolling(20).mean()
    df["RANGE"] = (df["High"].astype(float) - df["Low"].astype(float))
    df["RANGE_AVG20"] = df["RANGE"].rolling(20).mean()

    # تنظيف: لا نحذف كل شيء، نحذف فقط ما يلزم لتشغيل معظم الاستراتيجيات
    df.dropna(subset=["SMA_20", "SMA_50", "RSI", "ATR_14"], inplace=True)

    return df


# ============================================================
# 🔍 Signals Builders
# ============================================================

def _signal_trend(df):
    buy = (df["Close"] > df["SMA_50"]) & (df["RSI"] > 50)
    sell = (df["Close"] < df["SMA_50"])
    return buy, sell


def _signal_sniper(df):
    buy = (df["Close"] > df["SMA_20"]) & (df["Close"].shift(1) <= df["SMA_20"].shift(1))
    sell = (df["Close"] < df["SMA_20"])
    return buy, sell


def _signal_ichimoku_trend(df):
    close = df["Close"].astype(float)
    sa = df["SPAN_A"].astype(float)
    sb = df["SPAN_B"].astype(float)

    cloud_top = pd.concat([sa, sb], axis=1).max(axis=1)
    cloud_bot = pd.concat([sa, sb], axis=1).min(axis=1)

    buy = (close > cloud_top) & (df["TENKAN"] > df["KIJUN"])
    sell = (close < df["KIJUN"]) | (close < cloud_bot)
    return buy, sell


def _signal_liqsweep_reversal(df, lookback=30):
    """
    Sweep Low: low < prev_low and close > prev_low
    """
    prev = df.shift(1)
    prev_low = prev["Low"].rolling(lookback).min()
    sweep_low = (df["Low"] < prev_low) & (df["Close"] > prev_low)

    # فلتر بسيط: RSI ليس ضعيف جداً
    buy = sweep_low & (df["RSI"] > 40)
    sell = (df["Close"] < df["SMA_20"]) | (df["RSI"] < 45)
    return buy, sell


def _find_bullish_order_block(df):
    """
    تبسيط: نحدد اندفاع صاعد قوي ثم نأخذ آخر شمعة هابطة قبل الاندفاع كمنطقة OB.
    """
    if len(df) < 80:
        return None

    rng = df["RANGE"].astype(float)
    avg_rng = float(rng.iloc[-40:].mean()) if len(rng) >= 40 else float(rng.mean())

    window = df.iloc[-25:]
    idx_impulse_up = None
    for i in range(len(window) - 1, 1, -1):
        r = float(window["RANGE"].iloc[i])
        if r > avg_rng * 1.4 and float(window["Close"].iloc[i]) > float(window["Open"].iloc[i]):
            idx_impulse_up = window.index[i]
            break

    if idx_impulse_up is None:
        return None

    sub = df.loc[:idx_impulse_up].tail(15)
    bears = sub[sub["Close"] < sub["Open"]]
    if bears.empty:
        return None

    ob_idx = bears.index[-1]
    ob_low = float(df.loc[ob_idx, "Low"])
    ob_high = float(df.loc[ob_idx, "High"])
    return {"low": ob_low, "high": ob_high}


def _signal_orderblock_retest(df):
    ob = _find_bullish_order_block(df)
    if not ob:
        buy = pd.Series(False, index=df.index)
        sell = pd.Series(False, index=df.index)
        return buy, sell

    ob_low, ob_high = ob["low"], ob["high"]
    # retest: low <= ob_high and close >= ob_low
    buy = (df["Low"].astype(float) <= ob_high) & (df["Close"].astype(float) >= ob_low)
    sell = (df["Close"] < df["SMA_20"]) | (df["RSI"] < 45)
    return buy, sell


def _signal_bms_retest(df, lookback=80):
    """
    BMS: كسر قمة سوينغ ثم retest
    """
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    ph = _pivot_points(high.tail(lookback), 3, 3, "high")
    if not ph:
        buy = pd.Series(False, index=df.index)
        sell = pd.Series(False, index=df.index)
        return buy, sell

    last_swing_high = ph[-1][1]
    breakout = close > last_swing_high
    retest = (low <= last_swing_high) & (close >= last_swing_high)

    buy = retest & breakout.shift(1).fillna(False)
    sell = (close < df["SMA_20"]) | (df["RSI"] < 45)
    return buy, sell


def _signal_ote50(df, lookback=120):
    """
    موجة low->high ثم انتظار قرب 50% (±1%) مع شمعة خضراء تأكيد.
    """
    if len(df) < lookback:
        buy = pd.Series(False, index=df.index)
        sell = pd.Series(False, index=df.index)
        return buy, sell

    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    open_ = df["Open"].astype(float)

    # نلتقط آخر موجة: آخر قاع سوينغ ثم آخر قمة سوينغ بعدها
    ph = _pivot_points(high.tail(lookback), 3, 3, "high")
    pl = _pivot_points(low.tail(lookback), 3, 3, "low")

    if not ph or not pl:
        buy = pd.Series(False, index=df.index)
        sell = pd.Series(False, index=df.index)
        return buy, sell

    # آخر قاع ثم آخر قمة بعده
    # (تبسيط)
    last_low_i, last_low = pl[-1]
    last_high_i, last_high = ph[-1]
    if last_low_i >= last_high_i:
        buy = pd.Series(False, index=df.index)
        sell = pd.Series(False, index=df.index)
        return buy, sell

    fib50 = last_low + 0.5 * (last_high - last_low)

    near_50 = (abs(close - fib50) / close.replace(0, np.nan)) < 0.01
    confirm = close > open_
    buy = near_50 & confirm & (df["RSI"] > 45)
    sell = (close < df["SMA_20"]) | (df["RSI"] < 45)
    return buy, sell


def _signal_vsa_stopping_volume(df):
    """
    Stopping Volume: شمعة هابطة + فوليوم عالي + إغلاق في النصف الأعلى من المدى
    """
    vol = df["Volume"].astype(float)
    avg_vol = df["VOL_AVG20"].astype(float)

    r = df["RANGE"].astype(float)
    close = df["Close"].astype(float)
    open_ = df["Open"].astype(float)
    low = df["Low"].astype(float)

    down = close < open_
    high_vol = vol > (avg_vol * 1.5)
    strong_range = r > (df["RANGE_AVG20"] * 1.1)

    in_upper_half = close >= (low + 0.5 * r)

    buy = down & high_vol & strong_range & in_upper_half
    sell = (close < df["SMA_20"]) | (df["RSI"] < 45)
    return buy, sell


def _signal_range_breakout(df, lookback=20):
    close = df["Close"].astype(float)
    high = df["High"].astype(float)

    prev_high = high.shift(1).rolling(lookback).max()
    breakout = close > prev_high

    vol = df["Volume"].astype(float)
    vol_ok = vol > (df["VOL_AVG20"] * 1.3)

    buy = breakout & vol_ok
    sell = (close < df["SMA_20"]) | (df["RSI"] < 45)
    return buy, sell


def _resolve_strategy_key(strategy):
    s = str(strategy or "").strip().upper()
    if s in [x["key"] for x in STRATEGY_CATALOG]:
        return s

    # backward compatible (Trend / Sniper)
    if "TREND" in s:
        return "TREND"
    if "SNIPER" in s:
        return "SNIPER"

    # عربي
    if "اتجاه" in str(strategy):
        return "TREND"
    if "قن" in str(strategy) or "مضاربة" in str(strategy):
        return "SNIPER"

    return None


def _get_strategy_signals(df, strategy_key):
    if strategy_key == "TREND":
        return _signal_trend(df)
    if strategy_key == "SNIPER":
        return _signal_sniper(df)
    if strategy_key == "ICHIMOKU_TREND":
        return _signal_ichimoku_trend(df)
    if strategy_key == "SMC_LIQSWEEP_REV":
        return _signal_liqsweep_reversal(df)
    if strategy_key == "SMC_ORDERBLOCK":
        return _signal_orderblock_retest(df)
    if strategy_key == "MS_BMS_RETEST":
        return _signal_bms_retest(df)
    if strategy_key == "OTE_50":
        return _signal_ote50(df)
    if strategy_key == "VSA_STOPPING_VOL":
        return _signal_vsa_stopping_volume(df)
    if strategy_key == "RANGE_BREAKOUT":
        return _signal_range_breakout(df)

    return None, None


# ============================================================
# 🧪 Backtest Engine
# ============================================================

def run_backtest(df, strategy, capital=100000, params=None):
    """
    يحافظ على نفس المخرجات القديمة + يدعم استراتيجيات جديدة.
    params (اختياري):
      - use_atr_sl: bool
      - sl_atr: float
      - use_atr_tp: bool
      - tp_atr: float
      - max_hold_bars: int (0 = تعطيل)
    """
    if df is None or len(df) < 80:
        return None

    # تحصين الأعمدة
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
    if df.empty or len(df) < 30:
        return None

    strategy_key = _resolve_strategy_key(strategy)
    if not strategy_key:
        return None

    # default params from catalog then override
    base_params = {}
    for s in STRATEGY_CATALOG:
        if s["key"] == strategy_key:
            base_params = dict(s.get("params", {}))
            break

    params = params or {}
    for k, v in params.items():
        base_params[k] = v

    use_atr_sl = bool(base_params.get("use_atr_sl", False))
    sl_atr = float(base_params.get("sl_atr", 2.0) or 2.0)

    use_atr_tp = bool(base_params.get("use_atr_tp", False))
    tp_atr = float(base_params.get("tp_atr", 3.0) or 3.0)

    max_hold = int(base_params.get("max_hold_bars", 0) or 0)

    buy_cond, sell_cond = _get_strategy_signals(df, strategy_key)
    if buy_cond is None:
        return None

    df["Signal"] = 0
    df.loc[buy_cond, "Signal"] = 1
    df.loc[sell_cond, "Signal"] = -1

    # ✅ تصحيح التحيز للمستقبل
    df["Trade_Signal"] = df["Signal"].shift(1).fillna(0)

    cash = float(capital)
    shares = 0
    entry_price = 0.0
    entry_i = None
    log = []
    hist = []

    COMM = float(COMMISSION_RATE or 0.0)

    for i, r in enumerate(df.itertuples()):
        # تنفيذ على Open (واقعي)
        p = float(getattr(r, "Open", getattr(r, "Close")))
        close_p = float(getattr(r, "Close"))
        sig = float(getattr(r, "Trade_Signal", 0))
        atr = float(getattr(r, "ATR_14", 0) or 0)

        d = r.Index.strftime("%Y-%m-%d") if hasattr(r.Index, "strftime") else str(r.Index)

        if p <= 0:
            hist.append(cash + (shares * close_p))
            continue

        # Risk exits (SL/TP/max hold) قبل إشارة البيع
        if shares > 0 and entry_price > 0:
            # max hold
            if max_hold > 0 and entry_i is not None and (i - entry_i) >= max_hold:
                revenue = shares * p * (1 - COMM)
                cash += revenue
                log.append({"Date": d, "Type": "Sell(MaxHold)", "Price": p, "Qty": shares, "Cash": cash, "Value": revenue})
                shares = 0
                entry_price = 0.0
                entry_i = None

            # ATR SL/TP
            if shares > 0 and atr > 0:
                if use_atr_sl:
                    sl = entry_price - (sl_atr * atr)
                    if close_p <= sl:
                        revenue = shares * p * (1 - COMM)
                        cash += revenue
                        log.append({"Date": d, "Type": "Sell(SL)", "Price": p, "Qty": shares, "Cash": cash, "Value": revenue})
                        shares = 0
                        entry_price = 0.0
                        entry_i = None

                if shares > 0 and use_atr_tp:
                    tp = entry_price + (tp_atr * atr)
                    if close_p >= tp:
                        revenue = shares * p * (1 - COMM)
                        cash += revenue
                        log.append({"Date": d, "Type": "Sell(TP)", "Price": p, "Qty": shares, "Cash": cash, "Value": revenue})
                        shares = 0
                        entry_price = 0.0
                        entry_i = None

        # شراء
        if sig == 1 and shares == 0:
            invest = cash / (1 + COMM)
            qty = int(invest / p)

            if qty > 0:
                cost = qty * p * (1 + COMM)
                cash -= cost
                shares = qty
                entry_price = p
                entry_i = i
                log.append({"Date": d, "Type": "Buy", "Price": p, "Qty": shares, "Cash": cash, "Value": cost, "Strategy": strategy_key})

        # بيع
        elif sig == -1 and shares > 0:
            revenue = shares * p * (1 - COMM)
            cash += revenue
            log.append({"Date": d, "Type": "Sell", "Price": p, "Qty": shares, "Cash": cash, "Value": revenue, "Strategy": strategy_key})
            shares = 0
            entry_price = 0.0
            entry_i = None

        # Mark-to-market
        hist.append(cash + (shares * close_p))

    df["Portfolio_Value"] = hist

    final_val = float(hist[-1]) if hist else float(capital)
    ret_pct = ((final_val - float(capital)) / float(capital)) * 100

    return {
        "strategy_key": strategy_key,
        "return_pct": ret_pct,
        "final_value": final_val,
        "trades_log": pd.DataFrame(log),
        "df": df,
    }
