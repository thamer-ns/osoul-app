# ai_engine.py
# ============================================================
# Osoli AI Engine (Stable)
# - Cross-DB tables (SQLite/Postgres)
# - Logging signals + online weights learning
# - User rules parsing + application
# - Generate readable AI report (score/confidence/entry/targets/scenarios)
# ============================================================

import json
import re
import uuid
import pandas as pd
import numpy as np
from datetime import datetime

AI_ENGINE_VERSION = "1.1.0"

# ============================================================
# Helpers
# ============================================================

def _normalize_symbol(sym: str) -> str:
    sym = (sym or "").strip().upper()
    if sym.isdigit():
        return f"{sym}.SR"
    sym = sym.replace(" ", "").replace("-", "")
    if sym.endswith("SR") and ".SR" not in sym:
        sym = sym.replace("SR", ".SR")
    return sym


def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_import_db():
    try:
        from database import execute_query, fetch_table
        return execute_query, fetch_table
    except Exception:
        return None, None


def _try_exec(sql: str, params=()):
    """
    Portable execute:
    - Postgres style placeholders: %s
    - SQLite style placeholders: ?
    نحاول أولاً كما هو، وإذا فشل نجرب استبدال %s بـ ?
    """
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    try:
        execute_query(sql, params)
        return True
    except Exception:
        try:
            sql2 = sql.replace("%s", "?")
            execute_query(sql2, params)
            return True
        except Exception:
            return False


def _safe_fetch_table(name: str):
    _, fetch_table = _safe_import_db()
    if not fetch_table:
        return None
    try:
        df = fetch_table(name)
        if isinstance(df, pd.DataFrame):
            return df
        return None
    except Exception:
        return None


def _ensure_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    يطبع أسماء الأعمدة إلى Open/High/Low/Close/Volume
    ويفك MultiIndex إذا موجود.
    """
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
    m_low  = pick("Low", "low", "LOW")
    m_close = pick("Close", "close", "Adj Close", "adjclose", "adj_close", "ADJ CLOSE")
    m_vol  = pick("Volume", "volume", "VOL", "vol")

    ren = {}
    if m_open and m_open != "Open": ren[m_open] = "Open"
    if m_high and m_high != "High": ren[m_high] = "High"
    if m_low and m_low != "Low": ren[m_low] = "Low"
    if m_close and m_close != "Close": ren[m_close] = "Close"
    if m_vol and m_vol != "Volume": ren[m_vol] = "Volume"
    if ren:
        df = df.rename(columns=ren)

    needed = ["Open", "High", "Low", "Close"]
    for c in needed:
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


# ============================================================
# ✅ Cross-DB table schemas (SQLite/Postgres)
# ============================================================

def _ensure_ai_tables():
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False

    ok1 = _try_exec("""
    CREATE TABLE IF NOT EXISTS ai_signals (
        id TEXT PRIMARY KEY,
        created_at TEXT,
        symbol TEXT,
        sector TEXT,
        timeframe TEXT,
        horizon_days INTEGER DEFAULT 20,
        strategy_name TEXT,
        features_json TEXT,
        exit_features_json TEXT,
        report_json TEXT,
        outcome_return_pct REAL,
        outcome_win INTEGER
    )
    """, ())

    ok2 = _try_exec("""
    CREATE TABLE IF NOT EXISTS ai_weights (
        key TEXT PRIMARY KEY,
        weight REAL DEFAULT 1.0,
        updated_at TEXT
    )
    """, ())

    return bool(ok1 and ok2)


def _ensure_user_rules_table():
    ok = _try_exec("""
    CREATE TABLE IF NOT EXISTS ai_user_rules (
        id TEXT PRIMARY KEY,
        created_at TEXT,
        title TEXT,
        rule_text TEXT,
        parsed_json TEXT,
        enabled INTEGER DEFAULT 1
    )
    """, ())
    return bool(ok)


# ============================================================
# Logging
# ============================================================

def log_ai_signal(symbol, timeframe, features: dict, report: dict, horizon_days=20, sector=None, strategy_name=None):
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return None

    _ensure_ai_tables()

    signal_id = str(uuid.uuid4())
    try:
        _try_exec(
            """
            INSERT INTO ai_signals
            (id, created_at, symbol, sector, timeframe, horizon_days, strategy_name, features_json, report_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                signal_id,
                _now_str(),
                str(symbol),
                (str(sector) if sector is not None else None),
                str(timeframe),
                int(horizon_days),
                (str(strategy_name) if strategy_name is not None else None),
                json.dumps(features or {}, ensure_ascii=False),
                json.dumps(report or {}, ensure_ascii=False),
            ),
        )
        return signal_id
    except Exception:
        return None


def update_ai_outcome(signal_id: str, outcome_return_pct: float, exit_features: dict = None):
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    _ensure_ai_tables()
    try:
        win = 1 if float(outcome_return_pct) > 0 else 0
        if exit_features is not None:
            _try_exec(
                "UPDATE ai_signals SET outcome_return_pct=%s, outcome_win=%s, exit_features_json=%s WHERE id=%s",
                (float(outcome_return_pct), int(win), json.dumps(exit_features, ensure_ascii=False), str(signal_id)),
            )
        else:
            _try_exec(
                "UPDATE ai_signals SET outcome_return_pct=%s, outcome_win=%s WHERE id=%s",
                (float(outcome_return_pct), int(win), str(signal_id)),
            )
        return True
    except Exception:
        return False


# ============================================================
# Weights (simple online learning)
# ============================================================

def _get_weight(key: str, default=1.0):
    execute_query, fetch_table = _safe_import_db()
    if not execute_query or not fetch_table:
        return float(default)
    _ensure_ai_tables()
    try:
        df = fetch_table("ai_weights")
        if df is None or df.empty or "key" not in df.columns:
            return float(default)
        row = df[df["key"] == key]
        if row.empty:
            return float(default)
        return float(row.iloc[0].get("weight", default))
    except Exception:
        return float(default)


def _set_weight(key: str, weight: float):
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    _ensure_ai_tables()

    ok = _try_exec(
        """
        INSERT INTO ai_weights (key, weight, updated_at)
        VALUES (%s,%s,%s)
        ON CONFLICT(key) DO UPDATE
        SET weight=EXCLUDED.weight, updated_at=EXCLUDED.updated_at
        """,
        (str(key), float(weight), _now_str()),
    )
    if ok:
        return True

    try:
        _try_exec("DELETE FROM ai_weights WHERE key=%s", (str(key),))
        _try_exec(
            "INSERT INTO ai_weights (key, weight, updated_at) VALUES (%s,%s,%s)",
            (str(key), float(weight), _now_str())
        )
        return True
    except Exception:
        return False


def learn_from_history(max_rows=400):
    execute_query, fetch_table = _safe_import_db()
    if not execute_query or not fetch_table:
        return {"ok": False, "reason": "DB not available"}

    _ensure_ai_tables()
    try:
        df = fetch_table("ai_signals")
        if df is None or df.empty:
            return {"ok": True, "updated": 0}

        if "outcome_win" not in df.columns:
            return {"ok": True, "updated": 0}

        df = df.dropna(subset=["outcome_win"])
        if df.empty:
            return {"ok": True, "updated": 0}

        if "created_at" in df.columns:
            df = df.sort_values("created_at", ascending=False)

        df = df.head(int(max_rows))

        stats = {}
        for _, r in df.iterrows():
            try:
                feats = json.loads(r.get("features_json") or "{}")
                win = int(r.get("outcome_win") or 0)
                for k, v in feats.items():
                    if isinstance(v, (bool, int)) and int(v) in (0, 1):
                        stats.setdefault(k, {"wins": 0, "n": 0})
                        stats[k]["wins"] += win
                        stats[k]["n"] += 1
            except Exception:
                pass

        updated = 0
        for k, s in stats.items():
            if s["n"] < 20:
                continue
            win_rate = s["wins"] / s["n"]
            w = _get_weight(k, 1.0)

            if win_rate >= 0.58:
                w = min(w + 0.05, 2.0)
            elif win_rate <= 0.42:
                w = max(w - 0.05, 0.3)

            if _set_weight(k, w):
                updated += 1

        return {"ok": True, "updated": updated, "features": len(stats)}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


# ============================================================
# 🧠 User Rules
# ============================================================

def save_user_rule(rule_text: str, title: str = None, enabled: int = 1):
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return {"ok": False, "reason": "DB not available"}

    _ensure_user_rules_table()
    rule_text = (rule_text or "").strip()
    if not rule_text:
        return {"ok": False, "reason": "empty"}

    parsed = _parse_user_rule(rule_text)
    try:
        _try_exec(
            "INSERT INTO ai_user_rules (id, created_at, title, rule_text, parsed_json, enabled) VALUES (%s,%s,%s,%s,%s,%s)",
            (
                str(uuid.uuid4()),
                _now_str(),
                (title or "قاعدة مستخدم"),
                rule_text,
                json.dumps(parsed, ensure_ascii=False),
                int(enabled),
            ),
        )
        return {"ok": True, "parsed": parsed}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def load_user_rules(enabled_only=True, max_rows=50):
    _ensure_user_rules_table()
    df = _safe_fetch_table("ai_user_rules")
    if df is None or df.empty:
        return []
    try:
        if enabled_only and "enabled" in df.columns:
            df = df[df["enabled"].astype(int) == 1]
        if "created_at" in df.columns:
            df = df.sort_values("created_at", ascending=False)
        df = df.head(int(max_rows))
        rules = []
        for _, r in df.iterrows():
            pj = r.get("parsed_json")
            try:
                parsed = json.loads(pj) if pj else _parse_user_rule(str(r.get("rule_text") or ""))
            except Exception:
                parsed = _parse_user_rule(str(r.get("rule_text") or ""))
            rules.append({
                "id": r.get("id"),
                "title": r.get("title") or "قاعدة مستخدم",
                "rule_text": r.get("rule_text") or "",
                "parsed": parsed,
            })
        return rules
    except Exception:
        return []


def _parse_user_rule(text: str):
    t = (text or "").strip().lower()

    parsed = {
        "raw": text,
        "conditions": [],
        "direction": None,
        "boost": 1.5,
        "tags": [],
    }

    if any(k in t for k in ["شراء", "تجميع", "صعود", "buy"]):
        parsed["direction"] = "buy"
    if any(k in t for k in ["بيع", "خروج", "هبوط", "sell"]):
        parsed["direction"] = "sell"

    if "ماكد" in t or "macd" in t:
        if any(k in t for k in ["تقاطع", "cross"]) and any(k in t for k in ["صعود", "ايجابي", "up"]):
            parsed["conditions"].append({"type": "macd_cross", "value": "up"})
            parsed["tags"].append("MACD_CROSS_UP")
        if any(k in t for k in ["تقاطع", "cross"]) and any(k in t for k in ["هبوط", "سلبي", "down"]):
            parsed["conditions"].append({"type": "macd_cross", "value": "down"})
            parsed["tags"].append("MACD_CROSS_DN")

        if any(k in t for k in ["خط الصفر", "zero"]):
            if any(k in t for k in ["فوق", "اختراق", "up", "اعلى"]):
                parsed["conditions"].append({"type": "macd_zero", "value": "above"})
                parsed["tags"].append("MACD_ABOVE_ZERO")
            if any(k in t for k in ["تحت", "down", "اسفل"]):
                parsed["conditions"].append({"type": "macd_zero", "value": "below"})
                parsed["tags"].append("MACD_BELOW_ZERO")

    if "rsi" in t or "مؤشر القوة النسبية" in t or "القوة النسبية" in t:
        m = re.search(r"(?:rsi|القوة)\s*(?:فوق|اعلى|>)\s*(\d+)", t)
        if m:
            parsed["conditions"].append({"type": "rsi_gt", "value": float(m.group(1))})
            parsed["tags"].append("RSI_GT")
        m = re.search(r"(?:rsi|القوة)\s*(?:تحت|اقل|<)\s*(\d+)", t)
        if m:
            parsed["conditions"].append({"type": "rsi_lt", "value": float(m.group(1))})
            parsed["tags"].append("RSI_LT")
        if "فوق 70" in t:
            parsed["conditions"].append({"type": "rsi_gt", "value": 70.0})
            parsed["tags"].append("RSI_GT_70")
        if "تحت 30" in t:
            parsed["conditions"].append({"type": "rsi_lt", "value": 30.0})
            parsed["tags"].append("RSI_LT_30")

    if "sma" in t or "متوسط" in t or "موفينج" in t:
        m = re.search(r"(?:sma|متوسط)\s*(\d+)", t)
        if m:
            n = int(m.group(1))
            if any(k in t for k in ["اختراق", "فوق", "اعلى"]):
                parsed["conditions"].append({"type": "close_above_sma", "value": n})
                parsed["tags"].append(f"CLOSE_ABOVE_SMA{n}")
            if any(k in t for k in ["كسر", "تحت", "اسفل"]):
                parsed["conditions"].append({"type": "close_below_sma", "value": n})
                parsed["tags"].append(f"CLOSE_BELOW_SMA{n}")

    m = re.search(r"(?:boost|قوة|تأثير)\s*[:=]?\s*(\d+(?:\.\d+)?)", t)
    if m:
        parsed["boost"] = float(m.group(1))

    return parsed


def _eval_user_rule(parsed_rule: dict, df: pd.DataFrame, ind: dict):
    if not parsed_rule:
        return False, 0.0, "", {}

    conds = parsed_rule.get("conditions") or []
    if not conds:
        return False, 0.0, "", {}

    if df is None or df.empty or len(df) < 3:
        return False, 0.0, "", {}

    boost = float(parsed_rule.get("boost") or 1.5)
    direction = parsed_rule.get("direction")

    close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])

    rsi14 = float(ind.get("rsi14").iloc[-1]) if isinstance(ind.get("rsi14"), pd.Series) else None
    macd = float(ind.get("macd").iloc[-1]) if isinstance(ind.get("macd"), pd.Series) else None
    macd_prev = float(ind.get("macd").iloc[-2]) if isinstance(ind.get("macd"), pd.Series) else None
    sig = float(ind.get("macd_signal").iloc[-1]) if isinstance(ind.get("macd_signal"), pd.Series) else None
    sig_prev = float(ind.get("macd_signal").iloc[-2]) if isinstance(ind.get("macd_signal"), pd.Series) else None

    sma20 = float(ind.get("sma20").iloc[-1]) if isinstance(ind.get("sma20"), pd.Series) else None
    sma50 = float(ind.get("sma50").iloc[-1]) if isinstance(ind.get("sma50"), pd.Series) else None
    sma200 = float(ind.get("sma200").iloc[-1]) if isinstance(ind.get("sma200"), pd.Series) else None

    def _sma_by_n(n: int):
        if n == 20: return sma20
        if n == 50: return sma50
        if n == 200: return sma200
        return None

    def ok_one(c):
        t = c.get("type")
        v = c.get("value")

        if t == "macd_cross" and macd is not None and sig is not None and macd_prev is not None and sig_prev is not None:
            if v == "up":
                return (macd > sig) and (macd_prev <= sig_prev)
            if v == "down":
                return (macd < sig) and (macd_prev >= sig_prev)

        if t == "macd_zero" and macd is not None:
            if v == "above":
                return macd > 0
            if v == "below":
                return macd < 0

        if t == "rsi_gt" and rsi14 is not None:
            return rsi14 > float(v)
        if t == "rsi_lt" and rsi14 is not None:
            return rsi14 < float(v)

        if t == "close_above_sma":
            n = int(v)
            s = _sma_by_n(n)
            if s is None: return False
            return close > s and prev_close <= s

        if t == "close_below_sma":
            n = int(v)
            s = _sma_by_n(n)
            if s is None: return False
            return close < s and prev_close >= s

        return False

    hits = [ok_one(c) for c in conds]
    if not all(hits):
        return False, 0.0, "", {}

    delta = boost
    if direction == "sell":
        delta = -abs(boost)
    elif direction == "buy":
        delta = abs(boost)

    reason = f"📌 قاعدة مستخدم مطبقة: {parsed_rule.get('raw','')}"
    feats = {}
    for tag in (parsed_rule.get("tags") or []):
        feats[f"user_rule_{str(tag).lower()}"] = 1

    return True, float(delta), reason, feats


# ============================================================
# Indicators + Utilities
# ============================================================

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

    # ATR(14)
    tr1 = (high - low).abs()
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14).mean().bfill()

    # OBV
    obv = (np.sign(close.diff()).fillna(0) * vol).cumsum()
    out["obv"] = obv.fillna(method="bfill").fillna(0)

    return out


def _swing_support_resistance(df: pd.DataFrame, lookback=60):
    if df is None or df.empty:
        return None, None
    d = df.tail(int(lookback)).copy()
    sup = float(d["Low"].min())
    res = float(d["High"].max())
    return sup, res


def _clamp(x, lo, hi):
    try:
        x = float(x)
    except Exception:
        x = lo
    return max(lo, min(hi, x))


# ============================================================
# Portfolio risk & stress tools (simple)
# ============================================================

def calculate_portfolio_risk_score(trades_df: pd.DataFrame, cash_pct: float) -> int:
    """
    0..100 (Higher = riskier)
    - cash reduces risk
    - concentrated portfolio increases risk
    """
    cash_pct = _clamp(cash_pct, 0, 100)
    score = 55.0 - 0.35 * cash_pct

    if trades_df is None or trades_df.empty:
        return int(_clamp(score, 0, 100))

    df = trades_df.copy()
    if "status" in df.columns:
        stt = df["status"].astype(str).str.lower().str.strip()
        df = df[stt == "open"].copy()

    if df.empty:
        return int(_clamp(score, 0, 100))

    # concentration by market_value
    if "market_value" in df.columns:
        mv = pd.to_numeric(df["market_value"], errors="coerce").fillna(0)
        tot = float(mv.sum()) if mv.sum() else 0
        if tot > 0:
            w = (mv / tot).clip(0, 1)
            hhi = float((w ** 2).sum())  # 1/n .. 1
            score += (hhi * 70.0)  # up to +70
    else:
        score += 10

    return int(_clamp(score, 0, 100))


def run_stress_test(portfolio_value: float, open_positions_df: pd.DataFrame):
    """
    scenarios: simple shocks
    """
    pv = float(portfolio_value or 0)
    if pv <= 0:
        return {"scenarios": [], "insight": "لا توجد قيمة محفظة لاختبار التحمل."}

    shocks = [
        ("هبوط -5%", -5),
        ("هبوط -10%", -10),
        ("هبوط -15%", -15),
        ("هبوط -25%", -25),
    ]
    scenarios = []
    for name, pct in shocks:
        impact = pv * (pct / 100.0)
        scenarios.append({"scenario": name, "impact_pct": pct, "impact_value": impact})

    insight = "اختبار بسيط: كلما زادت الصفقات/التركيز قلّت القدرة على تحمل الهبوط."
    return {"scenarios": scenarios, "insight": insight}


def generate_rebalancing_suggestions(trades_df: pd.DataFrame, cash_pct: float):
    """
    Suggestions to reduce concentration.
    """
    if trades_df is None or trades_df.empty:
        return []

    df = trades_df.copy()
    if "status" in df.columns:
        stt = df["status"].astype(str).str.lower().str.strip()
        df = df[stt == "open"].copy()

    if df.empty or "market_value" not in df.columns or "symbol" not in df.columns:
        return []

    mv = pd.to_numeric(df["market_value"], errors="coerce").fillna(0)
    tot = float(mv.sum()) if mv.sum() else 0
    if tot <= 0:
        return []

    df["weight"] = (mv / tot) * 100.0
    df = df.sort_values("weight", ascending=False)

    sug = []
    top = df.head(5)
    for _, r in top.iterrows():
        w = float(r["weight"])
        if w >= 25:
            sug.append({"symbol": r.get("symbol"), "suggestion": f"وزن مرتفع ({w:.1f}%)—فكر بتخفيف جزء لإدارة المخاطر."})

    if float(cash_pct or 0) < 5:
        sug.append({"symbol": "-", "suggestion": "الكاش منخفض جدًا (<5%)—رفع الكاش يزيد المرونة."})

    return sug


# ============================================================
# Main: Generate AI report
# ============================================================

def generate_ai_report(symbol: str, timeframe: str = "1d"):
    """
    Returns dict with:
    recommendation, strategy, color, score, confidence, confidence_label,
    summary_text, entry, risk, levels, targets, explainability, top_evidence/top_risks,
    risk_gates, scenarios
    """
    symbol = _normalize_symbol(symbol)
    timeframe = (timeframe or "1d").strip()

    # safe imports
    try:
        from market_data import get_chart_history
    except Exception:
        return {"__error__": "market_data.get_chart_history missing"}

    # fundamentals optional
    fundamentals = {}
    try:
        from financial_analysis import get_advanced_fundamental_ratios
        fundamentals = get_advanced_fundamental_ratios(symbol) or {}
    except Exception:
        fundamentals = {}

    # get history
    period = "2y" if timeframe in ("1d", "1wk", "1mo") else "1y"
    try:
        df = get_chart_history(symbol, period=period, interval=timeframe)
    except TypeError:
        df = get_chart_history(symbol, period)

    if df is None:
        return {"__error__": "No data"}
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if df.empty or len(df) < 80:
        return {"__error__": "Not enough OHLCV data"}

    df = _ensure_ohlcv_columns(df)

    ind = _compute_indicators(df)
    if not ind:
        return {"__error__": "Indicators not ready"}

    close = float(df["Close"].iloc[-1])
    sma20 = float(ind["sma20"].iloc[-1]) if isinstance(ind.get("sma20"), pd.Series) else close
    sma50 = float(ind["sma50"].iloc[-1]) if isinstance(ind.get("sma50"), pd.Series) else close
    sma200 = float(ind["sma200"].iloc[-1]) if isinstance(ind.get("sma200"), pd.Series) else close
    rsi14 = float(ind["rsi14"].iloc[-1]) if isinstance(ind.get("rsi14"), pd.Series) else 50.0
    macd = float(ind["macd"].iloc[-1]) if isinstance(ind.get("macd"), pd.Series) else 0.0
    sig = float(ind["macd_signal"].iloc[-1]) if isinstance(ind.get("macd_signal"), pd.Series) else 0.0
    atr = float(ind["atr14"].iloc[-1]) if isinstance(ind.get("atr14"), pd.Series) else 0.0

    sup, res = _swing_support_resistance(df, lookback=60)
    sup = float(sup) if sup is not None else close * 0.95
    res = float(res) if res is not None else close * 1.05

    # Features (binary) + weighted score
    feats = {}
    positives, negatives, notes = [], [], []

    # trend
    feats["close_above_sma50"] = 1 if close > sma50 else 0
    feats["sma50_above_sma200"] = 1 if sma50 > sma200 else 0
    feats["close_above_sma20"] = 1 if close > sma20 else 0

    # momentum
    feats["rsi_ok_45_70"] = 1 if (45 <= rsi14 <= 70) else 0
    feats["rsi_overbought"] = 1 if rsi14 >= 72 else 0
    feats["rsi_oversold"] = 1 if rsi14 <= 30 else 0

    feats["macd_bullish"] = 1 if macd > sig else 0

    # simple risk gates
    gate_reasons = []
    gate_pass = True

    if atr <= 0:
        gate_pass = False
        gate_reasons.append("لا يمكن حساب ATR (بيانات غير كافية).")

    # scoring
    base = 50.0
    score = base

    def add_feat(k, good_text=None, bad_text=None, pos=4.0):
        nonlocal score
        w = _get_weight(k, 1.0)
        if feats.get(k, 0) == 1:
            score += pos * w
            if good_text:
                positives.append(good_text)
        else:
            score -= (pos * 0.7) * w
            if bad_text:
                negatives.append(bad_text)

    add_feat("close_above_sma20", "السعر فوق SMA20 (زخم قصير)", "السعر تحت SMA20 (ضعف قصير)", pos=3.0)
    add_feat("close_above_sma50", "السعر فوق SMA50 (اتجاه جيد)", "السعر تحت SMA50 (اتجاه ضعيف)", pos=5.0)
    add_feat("sma50_above_sma200", "SMA50 فوق SMA200 (اتجاه صاعد)", "SMA50 تحت SMA200 (اتجاه هابط)", pos=6.0)
    add_feat("macd_bullish", "MACD أعلى من الإشارة (زخم إيجابي)", "MACD سلبي مقابل الإشارة", pos=4.0)

    if feats["rsi_overbought"] == 1:
        score -= 4
        negatives.append("RSI مرتفع (تشبع شراء محتمل)")
    elif feats["rsi_oversold"] == 1:
        score += 3
        positives.append("RSI منخفض (تشبع بيع قد يمنح ارتداد)")
    else:
        if feats["rsi_ok_45_70"] == 1:
            score += 2
            positives.append("RSI ضمن نطاق صحي (45-70)")
        else:
            score -= 1

    # apply user rules
    rules = load_user_rules(enabled_only=True, max_rows=20) or []
    user_delta_total = 0.0
    user_feats = {}
    for r in rules:
        parsed = r.get("parsed") or {}
        ok, delta, reason, uf = _eval_user_rule(parsed, df, ind)
        if ok:
            user_delta_total += float(delta)
            if reason:
                notes.append(reason)
            if isinstance(uf, dict):
                user_feats.update(uf)

    score += user_delta_total
    feats.update(user_feats)

    # fundamentals hint (optional)
    if isinstance(fundamentals, dict) and fundamentals:
        fscore = fundamentals.get("Piotroski_Score")
        try:
            fscore = float(fscore)
        except Exception:
            fscore = None
        if fscore is not None:
            if fscore >= 7:
                score += 3
                positives.append("F-Score قوي (ماليًا)")
            elif fscore <= 3:
                score -= 3
                negatives.append("F-Score ضعيف (ماليًا)")

    score = int(_clamp(score, 0, 100))

    # confidence from signal agreement
    conf = 45
    agree = 0
    agree += 1 if feats["close_above_sma50"] else 0
    agree += 1 if feats["sma50_above_sma200"] else 0
    agree += 1 if feats["macd_bullish"] else 0
    agree += 1 if feats["rsi_ok_45_70"] else 0
    conf = int(_clamp(30 + agree * 15 + (abs(user_delta_total) * 3), 0, 95))

    confidence_label = "مرتفعة" if conf >= 70 else "متوسطة" if conf >= 40 else "منخفضة"

    # recommendation
    if score >= 70 and gate_pass:
        rec = "شراء / مراقبة دخول"
        color = "#0f7a3c"
    elif score >= 55 and gate_pass:
        rec = "مراقبة"
        color = "#8a5a00"
    else:
        rec = "تجنب / انتظار"
        color = "#a40e26"

    # build plan
    entry_zone = close  # simple
    stop = max(sup - (atr * 0.8), close - (atr * 1.8))
    invalidation = sup - (atr * 0.2)

    # targets
    t1 = max(res, close + (atr * 2.0))
    t2 = max(t1 * 1.02, close + (atr * 3.5))

    # risk: rr
    rr = None
    try:
        rr = (t1 - entry_zone) / (entry_zone - stop) if (entry_zone - stop) != 0 else None
    except Exception:
        rr = None

    if rr is not None and rr < 0.9:
        gate_pass = False
        gate_reasons.append("نسبة العائد للمخاطرة منخفضة (R:R < 0.9).")

    risk_gates = {"pass": bool(gate_pass), "reasons": gate_reasons}

    # scenarios
    scenarios = [
        {
            "name": "اختراق مقاومة",
            "trigger": f"إغلاق فوق {res:.2f}",
            "entry": float(max(entry_zone, res * 1.002)),
            "stop": float(stop),
            "target1": float(t1),
            "target2": float(t2),
            "note": "يفضل حجم أعلى/ثبات يومين للتأكيد."
        },
        {
            "name": "ارتداد من دعم",
            "trigger": f"ثبات فوق الدعم {sup:.2f}",
            "entry": float(max(sup * 1.01, entry_zone * 0.99)),
            "stop": float(stop),
            "target1": float(min(res, t1)),
            "target2": float(t1),
            "note": "راقب سلوك الشموع/الفوليوم."
        }
    ]

    summary = (
        f"Score={score}/100 | ثقة={conf}% | "
        f"الاتجاه={'صاعد' if (feats['close_above_sma50'] and feats['sma50_above_sma200']) else 'متذبذب/ضعيف'} | "
        f"RSI={rsi14:.1f} | MACD={'إيجابي' if feats['macd_bullish'] else 'سلبي'}"
    )

    report = {
        "symbol": symbol,
        "timeframe": timeframe,
        "recommendation": rec,
        "strategy": "Osoli AI (Tech+Rules)",
        "color": color,

        "score": score,
        "confidence": conf,
        "confidence_label": confidence_label,
        "summary_text": summary,

        "entry": {"entry_zone": float(entry_zone), "entry_note": "منطقة دخول مبدئية حول الإغلاق الحالي."},
        "risk": {"stop": float(stop), "invalidation": float(invalidation), "rr": float(rr) if rr is not None else None},
        "levels": {"support": float(sup), "resistance": float(res)},
        "targets": [
            {"name": "Target 1", "price": float(t1), "note": "هدف أول"},
            {"name": "Target 2", "price": float(t2), "note": "هدف ثاني"},
        ],

        "explainability": {
            "positives": positives[:20],
            "negatives": negatives[:20],
            "notes": notes[:20],
        },
        "top_evidence": positives[:12],
        "top_risks": negatives[:12],
        "risk_gates": risk_gates,
        "scenarios": scenarios,
    }

    # optional log
    try:
        log_ai_signal(symbol=symbol, timeframe=timeframe, features=feats, report=report, horizon_days=20)
    except Exception:
        pass

    return report