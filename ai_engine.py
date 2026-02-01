# ai_engine.py
import json
import re
import uuid
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from market_data import get_chart_history
from financial_analysis import get_advanced_fundamental_ratios


# ============================================================
# 🧠 AI Memory (DB Logging + Simple Online Learning)
# + Calibration + User Rules
# ============================================================

def _normalize_symbol(sym: str) -> str:
    sym = (sym or "").strip().upper()
    if sym.isdigit():
        return f"{sym}.SR"
    sym = sym.replace(" ", "").replace("-", "")
    if sym.endswith("SR") and ".SR" not in sym:
        sym = sym.replace("SR", ".SR")
    return sym


def _safe_import_db():
    try:
        from database import execute_query, fetch_table
        return execute_query, fetch_table
    except Exception:
        return None, None


def _safe_fetch_table(name: str):
    _, fetch_table = _safe_import_db()
    if not fetch_table:
        return None
    try:
        df = fetch_table(name)
        if df is None:
            return None
        if isinstance(df, pd.DataFrame):
            return df
        return None
    except Exception:
        return None


def _try_exec(sql: str, params=()):
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    try:
        execute_query(sql, params)
        return True
    except Exception:
        return False


def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# ✅ Cross-DB table schemas (SQLite/Postgres)
# ============================================================
def _ensure_ai_tables():
    """
    جداول Portable:
    - IDs نصية UUID بدل SERIAL (عشان Postgres + SQLite بدون تعارض)
    - created_at نص
    """
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
        return False

    _ensure_ai_tables()
    try:
        _try_exec(
            """
            INSERT INTO ai_signals
            (id, created_at, symbol, sector, timeframe, horizon_days, strategy_name, features_json, report_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                str(uuid.uuid4()),
                _now_str(),
                str(symbol), (str(sector) if sector is not None else None),
                str(timeframe), int(horizon_days),
                (str(strategy_name) if strategy_name is not None else None),
                json.dumps(features or {}, ensure_ascii=False),
                json.dumps(report or {}, ensure_ascii=False),
            ),
        )
        return True
    except Exception:
        return False


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
# Weights
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

    # SQLite/Postgres يدعمون UPSERT (لو كانت نسخة SQLite حديثة).
    # وإذا ما دعمت، عندنا fallback.
    try:
        execute_query(
            """
            INSERT INTO ai_weights (key, weight, updated_at)
            VALUES (%s,%s,%s)
            ON CONFLICT (key) DO UPDATE
            SET weight=EXCLUDED.weight, updated_at=EXCLUDED.updated_at
            """,
            (str(key), float(weight), _now_str()),
        )
        return True
    except Exception:
        try:
            _try_exec("DELETE FROM ai_weights WHERE key=%s", (str(key),))
            _try_exec("INSERT INTO ai_weights (key, weight, updated_at) VALUES (%s,%s,%s)", (str(key), float(weight), _now_str()))
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
# 🧠 User Rules: save/load/parse/evaluate
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

    if "فيبو" in t or "fibo" in t or "fib" in t:
        if "38" in t:
            if any(k in t for k in ["اختراق", "فوق", "اعلى"]):
                parsed["conditions"].append({"type": "fib_cross", "value": 38})
                parsed["tags"].append("FIB_38_UP")
            if any(k in t for k in ["كسر", "تحت", "اسفل"]):
                parsed["conditions"].append({"type": "fib_cross", "value": -38})
                parsed["tags"].append("FIB_38_DN")

    m = re.search(r"(?:boost|قوة|تأثير)\s*[:=]?\s*(\d+(?:\.\d+)?)", t)
    if m:
        parsed["boost"] = float(m.group(1))

    return parsed


# ============================================================
# ✅ Indicators (مطوّر بدون حذف القديم: SMA200/ATR/ADX/Stoch/OBV/Vol)
# ============================================================
def _compute_indicators(df: pd.DataFrame):
    out = {}
    if df is None or df.empty or len(df) < 60:
        return out

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    vol = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series([0] * len(df), index=df.index)

    # SMAs
    out["sma20"] = close.rolling(20).mean()
    out["sma50"] = close.rolling(50).mean()
    out["sma200"] = close.rolling(200).mean()

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    out["rsi14"] = rsi.bfill().fillna(50)

    # MACD(12,26,9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    out["macd"] = macd
    out["macd_signal"] = signal
    out["macd_hist"] = hist

    # ATR(14)
    try:
        prev_close = close.shift(1)
        tr = pd.concat(
            [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1
        ).max(axis=1)
        out["atr14"] = tr.rolling(14).mean()
    except Exception:
        pass

    # ADX(14) مبسط
    try:
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        prev_close = close.shift(1)
        tr = pd.concat(
            [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1
        ).max(axis=1)

        atr = tr.rolling(14).mean()
        plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(14).sum() / atr.replace(0, np.nan))
        minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(14).sum() / atr.replace(0, np.nan))
        dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
        out["adx14"] = dx.rolling(14).mean().bfill()
        out["plus_di14"] = plus_di.bfill()
        out["minus_di14"] = minus_di.bfill()
    except Exception:
        pass

    # Stochastic(14,3)
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

    # Volatility(20) - std لعوائد يومية
    try:
        ret = close.pct_change().fillna(0)
        out["vol20"] = ret.rolling(20).std().bfill()
    except Exception:
        pass

    # Fib 38.2 من نطاق آخر 120 يوم
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


def _eval_user_rule(parsed_rule: dict, df: pd.DataFrame, ind: dict):
    if not parsed_rule:
        return False, 0.0, "", {}

    conds = parsed_rule.get("conditions") or []
    if not conds:
        return False, 0.0, "", {}

    boost = float(parsed_rule.get("boost") or 1.5)
    direction = parsed_rule.get("direction")

    close = float(df["Close"].astype(float).iloc[-1])
    prev_close = float(df["Close"].astype(float).iloc[-2])

    rsi14 = float(ind.get("rsi14").iloc[-1]) if isinstance(ind.get("rsi14"), pd.Series) else None
    macd = float(ind.get("macd").iloc[-1]) if isinstance(ind.get("macd"), pd.Series) else None
    macd_prev = float(ind.get("macd").iloc[-2]) if isinstance(ind.get("macd"), pd.Series) else None
    sig = float(ind.get("macd_signal").iloc[-1]) if isinstance(ind.get("macd_signal"), pd.Series) else None
    sig_prev = float(ind.get("macd_signal").iloc[-2]) if isinstance(ind.get("macd_signal"), pd.Series) else None

    sma20 = float(ind.get("sma20").iloc[-1]) if isinstance(ind.get("sma20"), pd.Series) else None
    sma50 = float(ind.get("sma50").iloc[-1]) if isinstance(ind.get("sma50"), pd.Series) else None
    sma200 = float(ind.get("sma200").iloc[-1]) if isinstance(ind.get("sma200"), pd.Series) else None

    fib382 = ind.get("fib382", None)

    def _sma_by_n(n: int):
        if n == 20:
            return sma20
        if n == 50:
            return sma50
        if n == 200:
            return sma200
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
            if s is None:
                return False
            return close > s and prev_close <= s

        if t == "close_below_sma":
            n = int(v)
            s = _sma_by_n(n)
            if s is None:
                return False
            return close < s and prev_close >= s

        if t == "fib_cross" and fib382 is not None:
            if int(v) == 38:
                return close > float(fib382) and prev_close <= float(fib382)
            if int(v) == -38:
                return close < float(fib382) and prev_close >= float(fib382)

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
# 🕯️ Candles / Market Structure / SMC / Ichimoku / VSA / SR
# (كما عندك بدون تغيير منطقي)
# ============================================================

def _detect_advanced_patterns(df):
    if df is None or len(df) < 5:
        return 0, []

    score = 0
    patterns = []

    c1 = df.iloc[-3]
    c2 = df.iloc[-2]
    c3 = df.iloc[-1]

    body1 = abs(c1["Close"] - c1["Open"])
    body2 = abs(c2["Close"] - c2["Open"])

    is_c1_red = c1["Close"] < c1["Open"]
    is_c1_green = c1["Close"] > c1["Open"]
    is_c2_red = c2["Close"] < c2["Open"]
    is_c3_green = c3["Close"] > c3["Open"]
    is_c3_red = c3["Close"] < c3["Open"]

    if is_c1_red and body2 < body1 * 0.4 and is_c3_green:
        midpoint = c1["Open"] - (body1 / 2)
        if c3["Close"] > midpoint:
            score += 3
            patterns.append("✨ نجمة الصباح - انعكاس إيجابي قوي")

    if is_c1_green and body2 < body1 * 0.4 and is_c3_red:
        midpoint = c1["Open"] + (body1 / 2)
        if c3["Close"] < midpoint:
            score -= 3
            patterns.append("🌑 نجمة المساء - خروج/انعكاس سلبي")

    if is_c2_red and is_c3_green and c3["Open"] > c2["Close"] and c3["Close"] < c2["Open"]:
        score += 2
        patterns.append("🤰 الحرامي الشرائي - ضعف الزخم الهابط")

    if is_c2_red and is_c3_green and c3["Open"] < c2["Close"] and c3["Close"] > c2["Open"]:
        score += 2
        patterns.append("🔥 ابتلاع شرائي - سيطرة مشترين")

    return score, patterns


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


def _analyze_market_structure(df):
    if df is None or len(df) < 60:
        return 0, []

    score = 0
    obs = []

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    curr = float(close.iloc[-1])

    ph = _pivot_points(high, 3, 3, "high")
    pl = _pivot_points(low, 3, 3, "low")

    last_swing_high = ph[-1][1] if ph else float(high.iloc[-25:-2].max())
    last_swing_low = pl[-1][1] if pl else float(low.iloc[-25:-2].min())

    if curr > last_swing_high:
        score += 3
        obs.append(f"🚀 BMS: كسر قمة سوينغ ({last_swing_high:.2f})")
    elif curr < last_swing_low:
        score -= 3
        obs.append(f"⚠️ BMS: كسر قاع سوينغ ({last_swing_low:.2f})")
    else:
        rng = last_swing_high - last_swing_low
        if rng > 0:
            pos = (curr - last_swing_low) / rng
            if pos > 0.8:
                score += 1
                obs.append("السعر قرب سقف النطاق (مراقبة اختراق)")
            elif pos < 0.2:
                score -= 1
                obs.append("السعر قرب قاع النطاق (حذر)")
            else:
                score -= 1
                obs.append("مسار عرضي (تذبذب)")

    try:
        if len(ph) >= 1 and len(pl) >= 1:
            last_high_i, last_high = ph[-1]
            last_low_i, last_low = pl[-1]
            if last_low_i < last_high_i:
                impulse_low = last_low
                impulse_high = last_high
                fib50 = impulse_low + 0.5 * (impulse_high - impulse_low)
                if abs(curr - fib50) / max(curr, 1e-9) < 0.01:
                    score += 1
                    obs.append("🎯 OTE: السعر قريب 50% فيبو (منطقة دخول أفضل)")
            else:
                impulse_high = last_high
                impulse_low = last_low
                fib50 = impulse_high - 0.5 * (impulse_high - impulse_low)
                if abs(curr - fib50) / max(curr, 1e-9) < 0.01:
                    score -= 1
                    obs.append("🎯 OTE: السعر قريب 50% فيبو (منطقة بيع أفضل)")
    except Exception:
        pass

    return score, obs


def _detect_liquidity_sweep(df, lookback=30):
    if df is None or len(df) < lookback + 5:
        return 0, [], {}

    score = 0
    obs = []
    feats = {"liq_sweep_high": 0, "liq_sweep_low": 0}

    recent = df.iloc[-(lookback + 1):-1]
    prev_high = float(recent["High"].max())
    prev_low = float(recent["Low"].min())

    last = df.iloc[-1]
    h = float(last["High"])
    l = float(last["Low"])
    c = float(last["Close"])

    if h > prev_high and c < prev_high:
        score -= 2
        feats["liq_sweep_high"] = 1
        obs.append("🧲 صيد سيولة شرائية (اختراق زائف للأعلى)")

    if l < prev_low and c > prev_low:
        score += 2
        feats["liq_sweep_low"] = 1
        obs.append("🧲 صيد سيولة بيعية (اختراق زائف للأسفل)")

    return score, obs, feats


def _detect_order_block(df):
    if df is None or len(df) < 80:
        return 0, [], {}

    score = 0
    obs = []
    feats = {"bull_ob_retest": 0, "bear_ob_retest": 0}

    close = df["Close"].astype(float)
    open_ = df["Open"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    rng = (high - low)
    avg_rng = float(rng.iloc[-40:].mean()) if len(rng) >= 40 else float(rng.mean())

    window = df.iloc[-25:]
    idx_impulse_up = None
    for i in range(len(window) - 1, 1, -1):
        r = float(window["High"].iloc[i] - window["Low"].iloc[i])
        if r > avg_rng * 1.4 and float(window["Close"].iloc[i]) > float(window["Open"].iloc[i]):
            idx_impulse_up = window.index[i]
            break

    if idx_impulse_up is not None:
        sub = df.loc[:idx_impulse_up].tail(15)
        bears = sub[sub["Close"] < sub["Open"]]
        if not bears.empty:
            ob_idx = bears.index[-1]
            ob_low = float(low.loc[ob_idx])
            ob_high = float(high.loc[ob_idx])
            last_c = float(close.iloc[-1])
            last_l = float(low.iloc[-1])
            if (last_l <= ob_high) and (last_c >= ob_low):
                score += 2
                feats["bull_ob_retest"] = 1
                obs.append("🧱 Bullish Order Block retest (منطقة شراء محتملة)")

    idx_impulse_dn = None
    for i in range(len(window) - 1, 1, -1):
        r = float(window["High"].iloc[i] - window["Low"].iloc[i])
        if r > avg_rng * 1.4 and float(window["Close"].iloc[i]) < float(window["Open"].iloc[i]):
            idx_impulse_dn = window.index[i]
            break

    if idx_impulse_dn is not None:
        sub = df.loc[:idx_impulse_dn].tail(15)
        bulls = sub[sub["Close"] > sub["Open"]]
        if not bulls.empty:
            ob_idx = bulls.index[-1]
            ob_low = float(low.loc[ob_idx])
            ob_high = float(high.loc[ob_idx])
            last_c = float(close.iloc[-1])
            last_h = float(high.iloc[-1])
            if (last_h >= ob_low) and (last_c <= ob_high):
                score -= 2
                feats["bear_ob_retest"] = 1
                obs.append("🧱 Bearish Order Block retest (منطقة بيع محتملة)")

    return score, obs, feats


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


def _analyze_ichimoku(df):
    if df is None or len(df) < 120:
        return 0, [], {}

    score = 0
    obs = []
    feats = {
        "ichi_bull": 0,
        "ichi_bear": 0,
        "ichi_tk_cross_up": 0,
        "ichi_tk_cross_dn": 0,
    }

    tenkan, kijun, span_a, span_b, chikou = _ichimoku(df)
    close = df["Close"].astype(float)

    c = float(close.iloc[-1])
    sa = float(span_a.iloc[-1]) if not pd.isna(span_a.iloc[-1]) else np.nan
    sb = float(span_b.iloc[-1]) if not pd.isna(span_b.iloc[-1]) else np.nan
    if np.isnan(sa) or np.isnan(sb):
        return 0, [], feats

    cloud_top = max(sa, sb)
    cloud_bot = min(sa, sb)

    try:
        chik = float(chikou.iloc[-27])
        price_26 = float(close.iloc[-27])
    except Exception:
        chik = None
        price_26 = None

    if c > cloud_top:
        score += 1
        obs.append("☁️ السعر فوق سحابة الكومو (Bias شرائي)")
    elif c < cloud_bot:
        score -= 1
        obs.append("☁️ السعر تحت سحابة الكومو (Bias بيعي)")
    else:
        obs.append("☁️ السعر داخل السحابة (تذبذب/ضعف ترند)")

    if float(tenkan.iloc[-1]) > float(kijun.iloc[-1]) and float(tenkan.iloc[-2]) <= float(kijun.iloc[-2]):
        score += 1
        feats["ichi_tk_cross_up"] = 1
        obs.append("🔀 تقاطع تنكن فوق كيجن (إشارة دعم للشراء)")
    if float(tenkan.iloc[-1]) < float(kijun.iloc[-1]) and float(tenkan.iloc[-2]) >= float(kijun.iloc[-2]):
        score -= 1
        feats["ichi_tk_cross_dn"] = 1
        obs.append("🔀 تقاطع تنكن تحت كيجن (إشارة دعم للبيع)")

    if (c > cloud_top) and (float(span_a.iloc[-1]) > float(span_b.iloc[-1])) and (chik is not None) and (price_26 is not None) and (chik > price_26):
        score += 2
        feats["ichi_bull"] = 1
        obs.append("✅ Ichimoku صاعد قوي (شينكو+سحابة+سعر)")
    if (c < cloud_bot) and (float(span_a.iloc[-1]) < float(span_b.iloc[-1])) and (chik is not None) and (price_26 is not None) and (chik < price_26):
        score -= 2
        feats["ichi_bear"] = 1
        obs.append("⛔ Ichimoku هابط قوي (شينكو+سحابة+سعر)")

    return score, obs, feats


def _analyze_financial_golden_rules(symbol):
    try:
        metrics = get_advanced_fundamental_ratios(symbol)
    except Exception:
        return 0, [], {}

    score = 0
    obs = []
    feats = {
        "fund_strong_piotroski": 0,
        "fund_weak_piotroski": 0,
        "fund_graham_fair": 0,
        "fund_neg_ocf": 0,
    }

    try:
        piotroski = metrics.get("Piotroski_Score", 0)
        if piotroski >= 7:
            score += 3
            feats["fund_strong_piotroski"] = 1
            obs.append("💎 Piotroski مرتفع (ملاءة/جودة أرباح قوية)")
        elif piotroski <= 3:
            score -= 3
            feats["fund_weak_piotroski"] = 1
            obs.append("❌ Piotroski منخفض (هشاشة مالية)")

        fv = metrics.get("Fair_Value_Graham", 0)
        rating = metrics.get("Rating", "")
        if fv and fv > 0 and ("قوي" in str(rating) or "جيد" in str(rating)):
            score += 2
            feats["fund_graham_fair"] = 1
            obs.append("✅ تقييم جراهام جيد/عادل")

        ops_str = str(metrics.get("Opinions", ""))
        if ("سالب" in ops_str) and (("تشغيلي" in ops_str) or ("نقد" in ops_str)):
            score -= 4
            feats["fund_neg_ocf"] = 1
            obs.append("⚠️ التدفق النقدي التشغيلي سالب")
    except Exception:
        pass

    return score, obs, {**metrics, "_fund_features": feats}


def _analyze_vsa_art_of_trading(df):
    if df is None or len(df) < 50:
        return 0, [], {}

    score = 0
    obs = []
    feats = {"vsa_upthrust": 0, "vsa_stopping_volume": 0, "vsa_distribution": 0}

    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    open_ = df["Open"].astype(float)
    vol = df["Volume"].astype(float)

    curr = df.iloc[-1]
    avg_vol = float(vol.iloc[-20:].mean())
    rng = (high - low)
    avg_rng = float(rng.iloc[-20:].mean())

    r = float(curr["High"] - curr["Low"])
    if (float(curr["Close"]) > float(curr["Open"])) and (float(curr["Volume"]) > avg_vol * 1.5) and (r > avg_rng * 1.2):
        if float(curr["Close"]) <= float(curr["Low"]) + 0.25 * r:
            score -= 2
            feats["vsa_upthrust"] = 1
            obs.append("VSA: Upthrust (ضعف/تصريف محتمل)")

    if (float(curr["Close"]) < float(curr["Open"])) and (float(curr["Volume"]) > avg_vol * 1.5) and (r > avg_rng * 1.1):
        if float(curr["Close"]) >= float(curr["Low"]) + 0.5 * r:
            score += 2
            feats["vsa_stopping_volume"] = 1
            obs.append("VSA: Stopping Volume (امتصاص بيع/قوة)")

    if float(curr["Volume"]) > avg_vol * 1.7:
        if float(curr["Close"]) < float(curr["Low"]) + 0.55 * r and float(curr["Close"]) > float(curr["Open"]):
            score -= 1
            feats["vsa_distribution"] = 1
            obs.append("VSA: تفريغ محتمل (حجم عالي وإغلاق ليس على القمة)")

    return score, obs, feats


def _support_resistance_zones(df, lookback=120, max_levels=6):
    if df is None or len(df) < lookback:
        return [], []

    h = df["High"].astype(float)
    l = df["Low"].astype(float)

    ph = _pivot_points(h.tail(lookback), 3, 3, "high")
    pl = _pivot_points(l.tail(lookback), 3, 3, "low")

    highs = [p[1] for p in ph][-max_levels:]
    lows = [p[1] for p in pl][-max_levels:]

    return lows, highs


def _analyze_sr(df):
    if df is None or len(df) < 120:
        return 0, [], {}

    score = 0
    obs = []
    feats = {"near_support": 0, "near_resistance": 0, "broke_support_confirm": 0}

    close = float(df["Close"].astype(float).iloc[-1])
    lows, highs = _support_resistance_zones(df)

    if lows:
        sup = min(lows, key=lambda x: abs(close - x))
        if abs(close - sup) / max(close, 1e-9) < 0.01:
            score += 1
            feats["near_support"] = 1
            obs.append("🧩 قرب منطقة دعم (Zone)")

        try:
            c1 = float(df["Close"].iloc[-1])
            c2 = float(df["Close"].iloc[-2])
            if (c1 < sup) and (c2 < sup):
                score -= 2
                feats["broke_support_confirm"] = 1
                obs.append("🧨 كسر دعم مؤكد (إغلاق يومين تحت المنطقة)")
        except Exception:
            pass

    if highs:
        res = min(highs, key=lambda x: abs(close - x))
        if abs(close - res) / max(close, 1e-9) < 0.01:
            score -= 1
            feats["near_resistance"] = 1
            obs.append("🧩 قرب منطقة مقاومة (Zone)")

    return score, obs, feats


# ============================================================
# ✅ إضافات التحليل (MA Trend / Momentum / OBV / InsideBar / VSA Extended)
# ============================================================
def _analyze_ma_trend(df, ind):
    if df is None or df.empty or len(df) < 220:
        return 0, [], {}

    score = 0
    obs = []
    feats = {
        "ma_golden_cross": 0,
        "ma_death_cross": 0,
        "close_above_sma200": 0,
        "close_below_sma200": 0,
        "adx_strong_trend": 0,
    }

    close = float(df["Close"].astype(float).iloc[-1])
    close_prev = float(df["Close"].astype(float).iloc[-2])

    sma50 = ind.get("sma50")
    sma200 = ind.get("sma200")
    adx = ind.get("adx14")

    if isinstance(sma50, pd.Series) and isinstance(sma200, pd.Series) and not pd.isna(sma200.iloc[-1]):
        if float(sma50.iloc[-1]) > float(sma200.iloc[-1]) and float(sma50.iloc[-2]) <= float(sma200.iloc[-2]):
            score += 2
            feats["ma_golden_cross"] = 1
            obs.append("✨ Golden Cross (SMA50 فوق SMA200)")

        if float(sma50.iloc[-1]) < float(sma200.iloc[-1]) and float(sma50.iloc[-2]) >= float(sma200.iloc[-2]):
            score -= 2
            feats["ma_death_cross"] = 1
            obs.append("⚠️ Death Cross (SMA50 تحت SMA200)")

        if close > float(sma200.iloc[-1]) and close_prev <= float(sma200.iloc[-1]):
            score += 1
            feats["close_above_sma200"] = 1
            obs.append("✅ اختراق SMA200 للأعلى (تحسن اتجاه)")

        if close < float(sma200.iloc[-1]) and close_prev >= float(sma200.iloc[-1]):
            score -= 1
            feats["close_below_sma200"] = 1
            obs.append("⛔ كسر SMA200 للأسفل (ضعف اتجاه)")

    if isinstance(adx, pd.Series) and not pd.isna(adx.iloc[-1]):
        if float(adx.iloc[-1]) >= 20:
            feats["adx_strong_trend"] = 1
            obs.append("📈 ADX>=20 (ترند أوضح)")
            score += 1

    return score, obs, feats


def _analyze_momentum_pack(df, ind):
    if df is None or df.empty or len(df) < 60:
        return 0, [], {}

    score = 0
    obs = []
    feats = {
        "rsi_oversold": 0,
        "rsi_overbought": 0,
        "macd_hist_turn_up": 0,
        "macd_hist_turn_dn": 0,
        "stoch_buy_cross": 0,
        "stoch_sell_cross": 0,
    }

    rsi = ind.get("rsi14")
    hist = ind.get("macd_hist")
    k = ind.get("stoch_k")
    d = ind.get("stoch_d")

    if isinstance(rsi, pd.Series):
        rv = float(rsi.iloc[-1])
        if rv <= 30:
            score += 1
            feats["rsi_oversold"] = 1
            obs.append("🧊 RSI تحت 30 (تشبع بيع)")
        elif rv >= 70:
            score -= 1
            feats["rsi_overbought"] = 1
            obs.append("🔥 RSI فوق 70 (تشبع شراء)")

    if isinstance(hist, pd.Series) and len(hist) >= 3:
        if float(hist.iloc[-1]) > float(hist.iloc[-2]) and float(hist.iloc[-2]) <= float(hist.iloc[-3]):
            score += 1
            feats["macd_hist_turn_up"] = 1
            obs.append("📶 MACD Histogram انعطف للأعلى (زخم يتحسن)")
        if float(hist.iloc[-1]) < float(hist.iloc[-2]) and float(hist.iloc[-2]) >= float(hist.iloc[-3]):
            score -= 1
            feats["macd_hist_turn_dn"] = 1
            obs.append("📶 MACD Histogram انعطف للأسفل (زخم يضعف)")

    if isinstance(k, pd.Series) and isinstance(d, pd.Series) and len(k) >= 2:
        k1, k0 = float(k.iloc[-2]), float(k.iloc[-1])
        d1, d0 = float(d.iloc[-2]), float(d.iloc[-1])

        if (k1 < d1) and (k0 > d0) and (k0 < 20):
            score += 1
            feats["stoch_buy_cross"] = 1
            obs.append("🎯 Stochastic شراء (تقاطع تحت 20)")

        if (k1 > d1) and (k0 < d0) and (k0 > 80):
            score -= 1
            feats["stoch_sell_cross"] = 1
            obs.append("🎯 Stochastic بيع (تقاطع فوق 80)")

    return score, obs, feats


def _analyze_obv_pressure(df, ind, window=20):
    if df is None or df.empty or len(df) < window + 5:
        return 0, [], {}

    obv = ind.get("obv")
    if not isinstance(obv, pd.Series):
        return 0, [], {}

    score = 0
    obs = []
    feats = {"obv_accumulation": 0, "obv_distribution": 0}

    close = df["Close"].astype(float)

    try:
        price_slope = np.polyfit(range(window), close.tail(window), 1)[0]
        obv_slope = np.polyfit(range(window), obv.tail(window), 1)[0]

        if price_slope <= 0 and obv_slope > 0:
            score += 2
            feats["obv_accumulation"] = 1
            obs.append("💧 OBV تجميع ذكي (السيولة تدخل والسعر ما تحرك)")

        if price_slope > 0 and obv_slope < 0:
            score -= 2
            feats["obv_distribution"] = 1
            obs.append("🩸 OBV تصريف ذكي (السعر يصعد بسيولة خارجة)")
    except Exception:
        pass

    return score, obs, feats


def _detect_inside_bar(df):
    if df is None or len(df) < 3:
        return 0, [], {}
    prev = df.iloc[-2]
    curr = df.iloc[-1]

    score = 0
    obs = []
    feats = {"inside_bar": 0}

    if float(curr["High"]) < float(prev["High"]) and float(curr["Low"]) > float(prev["Low"]):
        score += 1
        feats["inside_bar"] = 1
        obs.append("🧷 Inside Bar (انضغاط — انفجار محتمل)")
    return score, obs, feats


def _analyze_vsa_extended(df):
    if df is None or len(df) < 60:
        return 0, [], {}

    score = 0
    obs = []
    feats = {
        "vsa_no_demand": 0,
        "vsa_no_supply": 0,
        "vsa_squat": 0,
        "vsa_end_rising": 0,
    }

    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    vol = df["Volume"].astype(float)

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    spread = float(curr["High"] - curr["Low"])
    avg_spread = float((high - low).iloc[-20:].mean())
    avg_vol = float(vol.iloc[-20:].mean())
    curr_vol = float(curr["Volume"])

    rng = float(curr["High"] - curr["Low"])
    close_pos = (float(curr["Close"]) - float(curr["Low"])) / rng if rng > 0 else 0.5

    if float(curr["Close"]) > float(prev["Close"]) and spread < avg_spread and curr_vol < avg_vol:
        score -= 1
        feats["vsa_no_demand"] = 1
        obs.append("VSA: No Demand (صعود بلا سيولة)")

    if float(curr["Close"]) < float(prev["Close"]) and spread < avg_spread and curr_vol < avg_vol:
        score += 1
        feats["vsa_no_supply"] = 1
        obs.append("VSA: No Supply (لا يوجد بائعين — دعم للصعود)")

    if (curr_vol > 1.3 * avg_vol) and (spread < 0.8 * avg_spread):
        score += 1
        feats["vsa_squat"] = 1
        obs.append("VSA: Squat (معركة سيولة — انفجار قريب)")

    gap_up = float(curr["Open"]) > float(prev["High"])
    bearish_close = float(curr["Close"]) < float(curr["Open"])
    close_near_low = close_pos < 0.25
    high_volume = curr_vol > (2.0 * avg_vol)
    if gap_up and bearish_close and close_near_low and high_volume:
        score -= 3
        feats["vsa_end_rising"] = 1
        obs.append("🚨 VSA: End of Rising Market (تصريف خطير)")

    return score, obs, feats


# ============================================================
# ✅ Risk Plan (ATR)
# ============================================================
def _risk_plan_from_atr_sr(df, ind):
    if df is None or df.empty:
        return {}

    close = float(df["Close"].astype(float).iloc[-1])
    atr = ind.get("atr14")
    atrv = float(atr.iloc[-1]) if isinstance(atr, pd.Series) and not pd.isna(atr.iloc[-1]) else None

    plan = {"entry": close, "stop": None, "target1": None, "rr": None}

    if atrv is None or atrv <= 0:
        return plan

    stop = close - 2.0 * atrv
    target1 = close + 3.0 * atrv

    plan["stop"] = round(float(stop), 4)
    plan["target1"] = round(float(target1), 4)

    risk = abs(close - stop)
    reward = abs(target1 - close)
    plan["rr"] = round((reward / risk) if risk > 0 else 0, 2)

    return plan


# ============================================================
# Confidence / Explainability / Strategy
# ============================================================
def _calc_confidence(tech_score, fund_score, df):
    quality = 5
    if df is not None and len(df) >= 220:
        quality = 30
    elif df is not None and len(df) >= 120:
        quality = 25
    elif df is not None and len(df) >= 60:
        quality = 15

    strength = min(abs(tech_score + fund_score) * 8, 45)
    alignment = 25 if ((tech_score >= 0 and fund_score >= 0) or (tech_score <= 0 and fund_score <= 0)) else 10

    conf = int(min(quality + strength + alignment, 100))
    if conf >= 75:
        label = "عالية"
    elif conf >= 50:
        label = "متوسطة"
    else:
        label = "منخفضة"
    return conf, label


def _build_explainability(tech_reasons, fund_reasons, total_score, tech_score, fund_score):
    positives, negatives, notes = [], [], []
    pos_keys = [
        "اختراق", "BMS", "OTE", "نجمة", "ابتلاع", "قوة", "Order Block",
        "Ichimoku صاعد", "Bias شرائي", "Stopping", "دعم", "✅", "💎", "🔀 تقاطع",
        "قاعدة مستخدم", "Golden Cross", "ADX", "OBV", "Inside Bar", "No Supply"
    ]

    for x in (tech_reasons or []):
        (positives if any(k in x for k in pos_keys) else negatives).append(x)

    for x in (fund_reasons or []):
        (positives if any(k in x for k in pos_keys) else negatives).append(x)

    notes.append(f"Tech={tech_score} | Fund={fund_score} | Total={total_score}")
    if tech_score > 3 and fund_score < 0:
        notes.append("تعارض: الفني قوي لكن المالي ضعيف — الأفضل مضاربة بإدارة مخاطر.")
    if fund_score > 3 and tech_score < 0:
        notes.append("تعارض: المالي قوي لكن السعر ضعيف — مناسب لاستثمار قيمة بصبر.")

    return {"positives": positives[:10], "negatives": negatives[:10], "notes": notes[:10]}


def _infer_strategy_hint(module_scores: dict):
    if not module_scores:
        return "Mixed"
    k = max(module_scores.keys(), key=lambda x: abs(module_scores.get(x, 0) or 0))
    return str(k)


# ============================================================
# Main Report
# ============================================================
def generate_ai_report(symbol, timeframe="1D"):
    """
    نفس منطقك، لكن:
    - يطبّع الرمز تلقائياً (1120 -> 1120.SR)
    - يسجل قواعد المستخدم فعلاً على SQLite
    - تمت إضافة محركات تحليل جديدة بدون حذف القديم
    """
    symbol = _normalize_symbol(symbol)

    try:
        df = get_chart_history(symbol, period="6mo")
        if df is None or df.empty:
            raise ValueError("no data")

        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in df.columns:
                raise ValueError(f"missing {col}")

        ind = _compute_indicators(df)

        # ====== محركاتك الأصلية ======
        s_candle, o_candle = _detect_advanced_patterns(df)
        s_struct, o_struct = _analyze_market_structure(df)
        s_liq, o_liq, f_liq = _detect_liquidity_sweep(df)
        s_ob, o_ob, f_ob = _detect_order_block(df)
        s_ichi, o_ichi, f_ichi = _analyze_ichimoku(df)
        s_vsa, o_vsa, f_vsa = _analyze_vsa_art_of_trading(df)
        s_sr, o_sr, f_sr = _analyze_sr(df)
        s_fund, o_fund, m_fund = _analyze_financial_golden_rules(symbol)

        # ====== الإضافات الجديدة ======
        s_ma, o_ma, f_ma = _analyze_ma_trend(df, ind)
        s_mom, o_mom, f_mom = _analyze_momentum_pack(df, ind)
        s_obv, o_obv, f_obv = _analyze_obv_pressure(df, ind)
        s_ib, o_ib, f_ib = _detect_inside_bar(df)
        s_vsa2, o_vsa2, f_vsa2 = _analyze_vsa_extended(df)

        base_tech = (
            s_candle + s_struct + s_vsa + s_ichi + s_ob + s_liq + s_sr
            + s_ma + s_mom + s_obv + s_ib + s_vsa2
        )

        tech_reasons = (
            (o_struct or []) + (o_candle or []) + (o_vsa or []) + (o_ichi or []) + (o_ob or []) + (o_liq or []) + (o_sr or [])
            + (o_ma or []) + (o_mom or []) + (o_obv or []) + (o_ib or []) + (o_vsa2 or [])
        )

        features = {}
        fund_feats = (m_fund or {}).get("_fund_features", {})
        for d in [f_liq, f_ob, f_ichi, f_vsa, f_sr, f_ma, f_mom, f_obv, f_ib, f_vsa2, fund_feats]:
            try:
                for k, v in (d or {}).items():
                    if isinstance(v, (bool, int)):
                        features[k] = int(v)
            except Exception:
                pass

        # إضافة قيم عددية (لا تدخل في weighted_bonus لأنها ليست 0/1)
        try:
            close_last = float(df["Close"].astype(float).iloc[-1])
            features["close"] = close_last

            if isinstance(ind.get("rsi14"), pd.Series):
                features["rsi14"] = float(ind["rsi14"].iloc[-1])
            if isinstance(ind.get("sma20"), pd.Series):
                features["sma20"] = float(ind["sma20"].iloc[-1])
            if isinstance(ind.get("sma50"), pd.Series):
                features["sma50"] = float(ind["sma50"].iloc[-1])
            if isinstance(ind.get("sma200"), pd.Series) and not pd.isna(ind["sma200"].iloc[-1]):
                features["sma200"] = float(ind["sma200"].iloc[-1])
            if isinstance(ind.get("atr14"), pd.Series) and not pd.isna(ind["atr14"].iloc[-1]):
                features["atr14"] = float(ind["atr14"].iloc[-1])
            if isinstance(ind.get("adx14"), pd.Series) and not pd.isna(ind["adx14"].iloc[-1]):
                features["adx14"] = float(ind["adx14"].iloc[-1])

            if ind.get("fib382") is not None:
                features["fib382"] = float(ind["fib382"])
        except Exception:
            pass

        # Weighted learning bonus (للعوامل الثنائية فقط)
        weighted_bonus = 0.0
        for k, v in features.items():
            if isinstance(v, (bool, int)) and int(v) == 1:
                weighted_bonus += (0.2 * (_get_weight(k, 1.0) - 1.0))

        tech_score = float(base_tech + weighted_bonus)
        fund_score = float(s_fund)
        total_score = float(tech_score + fund_score)

        # قواعد المستخدم
        try:
            rules = load_user_rules(enabled_only=True, max_rows=30)
        except Exception:
            rules = []

        user_delta = 0.0
        if rules:
            for rr in rules:
                parsed = rr.get("parsed") or {}
                hit, delta, reason, f_user = _eval_user_rule(parsed, df, ind)
                if hit:
                    user_delta += float(delta)
                    if reason:
                        tech_reasons.append(reason)
                    for kk, vv in (f_user or {}).items():
                        features[kk] = int(vv)

        if abs(user_delta) > 0:
            tech_score = float(tech_score + user_delta)
            total_score = float(tech_score + fund_score)

        # Sector
        sector = None
        try:
            from market_data import get_static_info
            info = get_static_info(symbol) or {}
            sector = info.get("sector") or info.get("Sector") or info.get("industry") or None
        except Exception:
            sector = None

        module_scores = {
            "MarketStructure": s_struct,
            "SmartMoney": (s_liq + s_ob),
            "Ichimoku": s_ichi,
            "VSA": s_vsa,
            "VSA_Ext": s_vsa2,
            "Candles": s_candle,
            "SupportResistance": s_sr,
            "MA_Trend": s_ma,
            "Momentum": s_mom,
            "OBV": s_obv,
            "InsideBar": s_ib,
            "Fundamental": s_fund,
            "UserRules": user_delta,
        }
        strategy_name = _infer_strategy_hint(module_scores)

        rec = "⚖️ محايد / مراقبة"
        clr = "#6c757d"
        strat = "السعر في منطقة حيرة. انتظر إشارة أوضح."

        if total_score >= 8:
            rec = "💎 فرصة ماسية (Strong Buy)"
            clr = "#198754"
            strat = "توافق قوي: هيكل + فلتر ترند + إشارات قوة."
        elif total_score >= 4:
            rec = "✅ شراء / تجميع"
            clr = "#28a745"
            strat = "الإشارات الإيجابية تغلب."
        elif total_score <= -5:
            rec = "⛔ خروج / وقف خسارة"
            clr = "#dc3545"
            strat = "إشارات ضعف/كسر دعم/هيكل سلبي."
        elif tech_score > 4 and fund_score < 0:
            rec = "⚡ مضاربة بحذر"
            clr = "#ffc107"
            strat = "فني قوي لكن المالي ضعيف — تقليل مخاطرة."
        elif fund_score >= 4 and tech_score < 0:
            rec = "📉 استثمار قيمة"
            clr = "#0d6efd"
            strat = "مالي قوي والسعر ضعيف — مناسب للصبر."

        fund_reasons = o_fund or []
        if not tech_reasons:
            tech_reasons = ["حركة السعر طبيعية"]
        if not fund_reasons:
            fund_reasons = ["المؤشرات المالية طبيعية"]

        confidence, confidence_label = _calc_confidence(tech_score, fund_score, df)
        explainability = _build_explainability(tech_reasons, fund_reasons, total_score, tech_score, fund_score)

        risk_plan = _risk_plan_from_atr_sr(df, ind)

        report = {
            "recommendation": rec,
            "color": clr,
            "strategy": strat,
            "tech_score": round(float(tech_score), 2),
            "fund_score": round(float(fund_score), 2),
            "tech_reasons": tech_reasons,
            "fund_reasons": fund_reasons,
            "trend": "صاعد" if float(tech_score) >= 0 else "هابط",
            "confidence": int(confidence),
            "confidence_label": confidence_label,
            "explainability": explainability,
            "features": features,
            "calibration": {},
            "strategy_name": strategy_name,
            "sector": sector,
            "risk_plan": risk_plan,  # ✅ إضافة بدون حذف أي مفتاح سابق
        }

        log_ai_signal(symbol, timeframe, features, report, horizon_days=20, sector=sector, strategy_name=strategy_name)
        return report

    except Exception:
        return {
            "recommendation": "غير متاح",
            "color": "#6c757d",
            "strategy": "نقص بيانات",
            "tech_reasons": [],
            "fund_reasons": [],
            "trend": "-",
            "confidence": 0,
            "confidence_label": "منخفضة",
            "explainability": {"positives": [], "negatives": [], "notes": ["AI Engine Error"]},
            "features": {},
            "calibration": {},
            "strategy_name": None,
            "sector": None,
            "risk_plan": {},  # ✅ حتى لا ينكسر العرض
        }


# ============================================================
# 🛡️ Portfolio Intelligence (كما عندك)
# ============================================================
def calculate_portfolio_risk_score(trades_df, cash_percent):
    try:
        if trades_df is None or trades_df.empty:
            return 0

        open_trades = trades_df[trades_df["status"] == "Open"]
        if open_trades.empty:
            return 0

        total_market_val = float(open_trades["market_value"].sum())
        if total_market_val == 0:
            return 0

        max_asset_weight = (float(open_trades["market_value"].max()) / total_market_val) * 100
        concentration_score = 30 if max_asset_weight > 50 else (15 if max_asset_weight > 25 else 0)

        liquidity_score = 25 if cash_percent < 5 else (10 if cash_percent < 15 else 0)

        strategy_score = 0
        try:
            spec_ratio = len(open_trades[open_trades["strategy"].astype(str).str.contains("مضاربة", na=False)]) / len(open_trades)
            strategy_score = spec_ratio * 30
        except Exception:
            pass

        return min(round(concentration_score + liquidity_score + strategy_score, 1), 100)
    except Exception:
        return 50


def run_stress_test(portfolio_value, open_positions_df):
    try:
        if open_positions_df is None or open_positions_df.empty:
            return {"scenarios": [], "insight": "المحفظة كاش."}

        weighted_beta = 0
        total_val = float(open_positions_df["market_value"].sum())
        if total_val == 0:
            return {"scenarios": [], "insight": "غير متاح"}

        for _, row in open_positions_df.iterrows():
            w = float(row["market_value"]) / total_val
            if row.get("asset_type") == "Sukuk":
                b = 0.1
            elif "مضاربة" in str(row.get("strategy", "")):
                b = 1.2
            else:
                b = 0.9
            weighted_beta += (w * b)

        scenarios = [
            {"name": "انهيار (-20%)", "market_chg": -0.20, "color": "#8B0000"},
            {"name": "تصحـيح (-10%)", "market_chg": -0.10, "color": "#DC2626"},
            {"name": "انتعـاش (+10%)", "market_chg": 0.10, "color": "#059669"},
            {"name": "طفرة (+20%)", "market_chg": 0.20, "color": "#047857"},
        ]

        results = []
        for s in scenarios:
            impact_pct = s["market_chg"] * weighted_beta
            results.append({"scenario": s["name"], "impact_pct": impact_pct * 100, "color": s["color"]})

        insight = "المحفظة عالية التذبذب" if weighted_beta > 1.1 else "المحفظة متوازنة"
        return {"scenarios": results, "insight": insight}
    except Exception:
        return {"scenarios": [], "insight": "غير متاح"}


def generate_rebalancing_suggestions(trades_df, cash_pct):
    suggestions = []
    try:
        if cash_pct < 5:
            suggestions.append(("priority", "🚨 السيولة منخفضة جداً (< 5%)"))

        if trades_df is not None and not trades_df.empty:
            open_trades = trades_df[trades_df["status"] == "Open"]
            for _, row in open_trades.iterrows():
                if float(row.get("gain_pct", 0) or 0) < -10:
                    suggestions.append(("danger", f"🛑 خسارة تجاوزت -10% في {row.get('symbol','-')}"))
    except Exception:
        pass

    return suggestions