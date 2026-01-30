# backtester.py
import json
import uuid
import pandas as pd
import numpy as np
from datetime import datetime

from config import COMMISSION_RATE

# DB (Fail-safe)
try:
    from database import execute_query, fetch_table
except Exception:
    execute_query = None
    fetch_table = None


# ============================================================
# 🧠 Strategy Catalog (قابل للتوسع)
# ============================================================
STRATEGY_CATALOG = {
    "Trend": {
        "name_ar": "📈 تتبع الاتجاه (Trend)",
        "family": "Trend",
        "timeframes": ["1D", "1W"],
        "notes": "سعر فوق SMA50 + RSI>50 للدخول. خروج بكسر SMA50."
    },
    "Sniper": {
        "name_ar": "🎯 قناص المتوسط (Sniper)",
        "family": "Pullback",
        "timeframes": ["1D", "4H"],
        "notes": "اختراق SMA20 بعد لمسة. خروج بكسر SMA20."
    },

    # موجودة في الكاتالوج وجاهزة لتفعيل خوارزمياتها لاحقاً
    "Ichimoku": {"name_ar": "☁️ إشيموكو", "family": "Trend", "timeframes": ["1D", "4H"], "notes": "يُفعل لاحقاً."},
    "VSA": {"name_ar": "📊 VSA (حجم/سبريد)", "family": "Volume", "timeframes": ["1D", "1H"], "notes": "يُفعل لاحقاً."},
    "SMC": {"name_ar": "🏛️ SMC / هيكل السوق", "family": "Structure", "timeframes": ["1D", "4H"], "notes": "يُفعل لاحقاً."},
    "SupplyDemand": {"name_ar": "🧲 العرض والطلب", "family": "Zones", "timeframes": ["1D", "4H"], "notes": "يُفعل لاحقاً."},
}


def list_strategies():
    return list(STRATEGY_CATALOG.keys())


# ============================================================
# 🧱 DB: إنشاء الجداول تلقائياً
# ============================================================
def ensure_lab_tables():
    if not execute_query:
        return False

    # صيغة عامة غالباً تنجح على Postgres/SQLite
    ddl = [
        """
        CREATE TABLE IF NOT EXISTS lab_runs (
            run_id TEXT PRIMARY KEY,
            created_at TEXT,
            symbol TEXT,
            sector TEXT,
            strategy_key TEXT,
            strategy_name_ar TEXT,
            timeframe TEXT,
            capital REAL,
            commission REAL,
            bars_count INTEGER,
            start_date TEXT,
            end_date TEXT,
            return_pct REAL,
            final_value REAL,
            trades_count INTEGER,
            params_json TEXT,
            notes TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS lab_trades (
            trade_id TEXT PRIMARY KEY,
            run_id TEXT,
            ts TEXT,
            side TEXT,
            price REAL,
            qty REAL,
            cash REAL,
            value REAL,
            close_price REAL,
            portfolio_value REAL,
            features_json TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS lab_equity (
            row_id TEXT PRIMARY KEY,
            run_id TEXT,
            ts TEXT,
            close_price REAL,
            portfolio_value REAL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ai_decisions (
            decision_id TEXT PRIMARY KEY,
            created_at TEXT,
            symbol TEXT,
            sector TEXT,
            recommendation TEXT,
            strategy_key TEXT,
            confidence INTEGER,
            price REAL,
            explainability_json TEXT,
            features_json TEXT,
            linked_run_id TEXT,
            outcome_return_pct REAL,
            outcome_notes TEXT
        )
        """
    ]

    ok = True
    for q in ddl:
        try:
            execute_query(q, ())
        except Exception:
            ok = False
    return ok


# ============================================================
# 📌 Indicators
# ============================================================
def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if isinstance(df.index, pd.DatetimeIndex):
        df = df.sort_index()

    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c not in df.columns:
            if c == "Open" and "Close" in df.columns:
                df["Open"] = df["Close"]
            else:
                df[c] = np.nan

    df["SMA_20"] = df["Close"].rolling(20).mean()
    df["SMA_50"] = df["Close"].rolling(50).mean()

    delta = df["Close"].diff()
    avg_gain = delta.where(delta > 0, 0).ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = (-delta.where(delta < 0, 0)).ewm(alpha=1 / 14, adjust=False).mean()

    rs = avg_gain / avg_loss
    rs = rs.replace([np.inf, -np.inf], np.nan)

    df["RSI"] = 100 - (100 / (1 + rs))
    df["RSI"] = df["RSI"].fillna(50)

    df.dropna(subset=["SMA_20", "SMA_50", "RSI"], inplace=True)
    return df


def _safe_ts(idx) -> str:
    try:
        return idx.strftime("%Y-%m-%d")
    except Exception:
        return str(idx)


def _features_snapshot(row) -> dict:
    """نسجل مؤشرات لحظة التنفيذ (مرجع للتعلم لاحقاً)."""
    out = {}
    for k in ["RSI", "SMA_20", "SMA_50", "Close", "Open", "High", "Low", "Volume"]:
        try:
            v = float(row.get(k)) if pd.notna(row.get(k)) else None
        except Exception:
            v = None
        out[k] = v
    return out


# ============================================================
# 🧪 Backtest Core + DB logging
# ============================================================
def run_backtest(
    df: pd.DataFrame,
    strategy: str,
    capital: float = 100000,
    symbol: str = None,
    sector: str = None,
    timeframe: str = "1D",
    notes: str = "",
) -> dict | None:

    if df is None or len(df) < 60:
        return None

    required_cols = {"Open", "Close", "High", "Low", "Volume"}
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        if "Open" in missing and "Close" in df.columns:
            df = df.copy()
            df["Open"] = df["Close"]
            missing.remove("Open")
        if missing:
            return None

    strategy = str(strategy or "").strip()
    if strategy not in STRATEGY_CATALOG:
        return None

    df = calculate_indicators(df)
    if df.empty or len(df) < 10:
        return None

    df["Signal"] = 0

    # إشارات مفعلة فعلياً
    if strategy == "Trend":
        buy = (df["Close"] > df["SMA_50"]) & (df["RSI"] > 50)
        sell = (df["Close"] < df["SMA_50"])
    elif strategy == "Sniper":
        buy = (df["Close"] > df["SMA_20"]) & (df["Close"].shift(1) <= df["SMA_20"].shift(1))
        sell = (df["Close"] < df["SMA_20"])
    else:
        return None

    df.loc[buy, "Signal"] = 1
    df.loc[sell, "Signal"] = -1

    # منع التحيز للمستقبل
    df["Trade_Signal"] = df["Signal"].shift(1).fillna(0)

    cash = float(capital)
    shares = 0
    log_rows = []
    equity_rows = []

    COMM = float(COMMISSION_RATE or 0.0)

    # run_id ثابت مرجعي
    run_id = str(uuid.uuid4())
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for i, (idx, row) in enumerate(df.iterrows()):
        p_open = float(row["Open"]) if row.get("Open") and row["Open"] > 0 else float(row["Close"])
        sig = float(row.get("Trade_Signal", 0))
        ts = _safe_ts(idx)

        # تنفيذ
        if sig == 1 and shares == 0:
            invest = cash / (1 + COMM)
            qty = int(invest / p_open)
            if qty > 0:
                cost = qty * p_open * (1 + COMM)
                cash -= cost
                shares = qty

                log_rows.append({
                    "ts": ts, "side": "Buy", "price": p_open, "qty": qty,
                    "cash": cash, "value": cost,
                    "close_price": float(row["Close"]),
                    "portfolio_value": None,
                    "features": _features_snapshot(row)
                })

        elif sig == -1 and shares > 0:
            revenue = shares * p_open * (1 - COMM)
            cash += revenue

            log_rows.append({
                "ts": ts, "side": "Sell", "price": p_open, "qty": shares,
                "cash": cash, "value": revenue,
                "close_price": float(row["Close"]),
                "portfolio_value": None,
                "features": _features_snapshot(row)
            })

            shares = 0

        # Mark-to-market على Close
        port_val = cash + shares * float(row["Close"])
        equity_rows.append({"ts": ts, "close_price": float(row["Close"]), "portfolio_value": float(port_val)})

        # تحديث آخر عملية بالـ portfolio_value (لتوثيق الحالة وقت التنفيذ)
        if log_rows and log_rows[-1]["ts"] == ts and log_rows[-1]["portfolio_value"] is None:
            log_rows[-1]["portfolio_value"] = float(port_val)

    # إرجاع النتائج
    final_val = float(equity_rows[-1]["portfolio_value"]) if equity_rows else float(capital)
    ret_pct = ((final_val - float(capital)) / float(capital)) * 100

    result = {
        "run_id": run_id,
        "created_at": created_at,
        "strategy_key": strategy,
        "strategy_name_ar": STRATEGY_CATALOG[strategy]["name_ar"],
        "return_pct": float(ret_pct),
        "final_value": float(final_val),
        "trades_log": pd.DataFrame([{
            "Date": x["ts"], "Type": x["side"], "Price": x["price"], "Qty": x["qty"],
            "Cash": x["cash"], "Value": x["value"]
        } for x in log_rows]),
        "df": df.assign(Portfolio_Value=[x["portfolio_value"] for x in equity_rows]),
    }

    # ✅ DB Logging (Run + Trades + Equity) + ربط آخر AI decision
    _persist_run_to_db(
        run_id=run_id,
        created_at=created_at,
        symbol=symbol,
        sector=sector,
        strategy=strategy,
        timeframe=timeframe,
        capital=capital,
        commission=COMM,
        df=df,
        ret_pct=ret_pct,
        final_val=final_val,
        trades=log_rows,
        equity=equity_rows,
        notes=notes,
    )

    return result


# ============================================================
# 💾 Persist to DB + Link with AI decisions
# ============================================================
def _persist_run_to_db(
    run_id: str,
    created_at: str,
    symbol: str,
    sector: str,
    strategy: str,
    timeframe: str,
    capital: float,
    commission: float,
    df: pd.DataFrame,
    ret_pct: float,
    final_val: float,
    trades: list,
    equity: list,
    notes: str = "",
):
    if not execute_query:
        return

    ensure_lab_tables()

    bars_count = int(len(df))
    start_date = _safe_ts(df.index.min()) if isinstance(df.index, pd.DatetimeIndex) else (str(df.index.min()) if len(df) else "")
    end_date = _safe_ts(df.index.max()) if isinstance(df.index, pd.DatetimeIndex) else (str(df.index.max()) if len(df) else "")

    params = {
        "commission": commission,
        "capital": float(capital),
        "timeframe": timeframe,
        "strategy_key": strategy,
    }

    # 1) run header
    try:
        execute_query(
            """
            INSERT INTO lab_runs
            (run_id, created_at, symbol, sector, strategy_key, strategy_name_ar, timeframe,
             capital, commission, bars_count, start_date, end_date, return_pct, final_value, trades_count,
             params_json, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                run_id, created_at,
                symbol or "", sector or "",
                strategy, STRATEGY_CATALOG.get(strategy, {}).get("name_ar", strategy),
                timeframe,
                float(capital), float(commission),
                bars_count, start_date, end_date,
                float(ret_pct), float(final_val),
                int(len(trades)),
                json.dumps(params, ensure_ascii=False),
                notes or "",
            )
        )
    except Exception:
        # إذا صار تعارض run_id أو مشكلة، لا نكسر التطبيق
        pass

    # 2) trades
    for j, t in enumerate(trades):
        trade_id = f"{run_id}_{j}"
        try:
            execute_query(
                """
                INSERT INTO lab_trades
                (trade_id, run_id, ts, side, price, qty, cash, value, close_price, portfolio_value, features_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    trade_id, run_id,
                    t.get("ts", ""),
                    t.get("side", ""),
                    float(t.get("price", 0) or 0),
                    float(t.get("qty", 0) or 0),
                    float(t.get("cash", 0) or 0),
                    float(t.get("value", 0) or 0),
                    float(t.get("close_price", 0) or 0),
                    float(t.get("portfolio_value", 0) or 0),
                    json.dumps(t.get("features", {}) or {}, ensure_ascii=False),
                )
            )
        except Exception:
            pass

    # 3) equity curve (downsample لتقليل حجم DB)
    try:
        step = max(len(equity) // 500, 1)  # نخزن بحد أقصى ~500 نقطة
    except Exception:
        step = 1

    for k in range(0, len(equity), step):
        e = equity[k]
        row_id = f"{run_id}_e_{k}"
        try:
            execute_query(
                """
                INSERT INTO lab_equity (row_id, run_id, ts, close_price, portfolio_value)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (
                    row_id, run_id,
                    e.get("ts", ""),
                    float(e.get("close_price", 0) or 0),
                    float(e.get("portfolio_value", 0) or 0),
                )
            )
        except Exception:
            pass

    # 4) ربط آخر قرار AI لنفس السهم (إذا موجود) وتسجيل Outcome
    _link_latest_ai_decision_to_run(symbol=symbol, sector=sector, run_id=run_id, outcome_return_pct=float(ret_pct))


def _link_latest_ai_decision_to_run(symbol: str, sector: str, run_id: str, outcome_return_pct: float):
    if not (execute_query and fetch_table and symbol):
        return

    try:
        ensure_lab_tables()

        # نحاول نجيب آخر قرار AI لهذا السهم وغير مربوط بعد
        dec = fetch_table("ai_decisions")
        if dec is None or dec.empty:
            return

        sub = dec[dec["symbol"].astype(str) == str(symbol)]
        if "linked_run_id" in sub.columns:
            sub = sub[sub["linked_run_id"].isna() | (sub["linked_run_id"].astype(str) == "")]
        if sub.empty:
            return

        # أحدث قرار حسب created_at
        if "created_at" in sub.columns:
            sub = sub.sort_values("created_at", ascending=False)

        decision_id = str(sub.iloc[0]["decision_id"])

        execute_query(
            """
            UPDATE ai_decisions
            SET linked_run_id=%s, outcome_return_pct=%s, outcome_notes=%s
            WHERE decision_id=%s
            """,
            (run_id, float(outcome_return_pct), "Linked with latest lab run", decision_id)
        )

    except Exception:
        pass


# ============================================================
# 📚 Helpers for AI / UI (اختياري)
# ============================================================
def get_lab_runs(symbol: str = None, limit: int = 50) -> pd.DataFrame:
    if not fetch_table:
        return pd.DataFrame()
    try:
        ensure_lab_tables()
        df = fetch_table("lab_runs")
        if df is None or df.empty:
            return pd.DataFrame()
        if symbol:
            df = df[df["symbol"].astype(str) == str(symbol)]
        if "created_at" in df.columns:
            df = df.sort_values("created_at", ascending=False)
        return df.head(limit)
    except Exception:
        return pd.DataFrame()
