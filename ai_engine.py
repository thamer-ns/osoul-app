import json
import re
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from market_data import get_chart_history
from financial_analysis import get_advanced_fundamental_ratios

# ============================================================
# 🧠 AI Memory (DB Logging + Simple Online Learning)
# + Calibration + User Rules
# ============================================================

def _safe_import_db():
    try:
        from database import execute_query, fetch_table
        return execute_query, fetch_table
    except Exception:
        return None, None


# ----------------------------
# DB Utils (safe)
# ----------------------------
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


def _ensure_ai_tables():
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False

    # Base tables (كما عندك)
    ok1 = _try_exec("""
    CREATE TABLE IF NOT EXISTS ai_signals (
        id SERIAL PRIMARY KEY,
        created_at TIMESTAMP DEFAULT NOW(),
        symbol TEXT,
        timeframe TEXT,
        horizon_days INT DEFAULT 20,
        features_json TEXT,
        report_json TEXT,
        outcome_return_pct DOUBLE PRECISION,
        outcome_win INT
    )
    """, ())

    ok2 = _try_exec("""
    CREATE TABLE IF NOT EXISTS ai_weights (
        id SERIAL PRIMARY KEY,
        key TEXT UNIQUE,
        weight DOUBLE PRECISION DEFAULT 1.0,
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """, ())

    # ترقيات بدون كسر (Postgres)
    # (لو DB SQLite قد يفشل ونتجاهله)
    _try_exec("ALTER TABLE ai_signals ADD COLUMN IF NOT EXISTS sector TEXT", ())
    _try_exec("ALTER TABLE ai_signals ADD COLUMN IF NOT EXISTS strategy_name TEXT", ())
    _try_exec("ALTER TABLE ai_signals ADD COLUMN IF NOT EXISTS exit_features_json TEXT", ())

    return bool(ok1 and ok2)


def _ensure_user_rules_table():
    # استراتيجيات المستخدم المكتوبة نصياً
    ok = _try_exec("""
    CREATE TABLE IF NOT EXISTS ai_user_rules (
        id SERIAL PRIMARY KEY,
        created_at TIMESTAMP DEFAULT NOW(),
        title TEXT,
        rule_text TEXT,
        parsed_json TEXT,
        enabled INT DEFAULT 1
    )
    """, ())
    return bool(ok)


def log_ai_signal(symbol, timeframe, features: dict, report: dict, horizon_days=20, sector=None, strategy_name=None):
    """يسجل كل تقرير (features + report) للرجوع له لاحقاً وتطوير الذكاء."""
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False

    _ensure_ai_tables()
    try:
        # نحفظ أيضاً sector/strategy_name لو متوفرين
        _try_exec(
            "INSERT INTO ai_signals (symbol, timeframe, horizon_days, features_json, report_json, sector, strategy_name) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                str(symbol), str(timeframe), int(horizon_days),
                json.dumps(features, ensure_ascii=False),
                json.dumps(report, ensure_ascii=False),
                (str(sector) if sector is not None else None),
                (str(strategy_name) if strategy_name is not None else None),
            ),
        )
        return True
    except Exception:
        # fallback للنسخة القديمة لو DB ما يدعم الأعمدة
        try:
            execute_query(
                "INSERT INTO ai_signals (symbol, timeframe, horizon_days, features_json, report_json) VALUES (%s,%s,%s,%s,%s)",
                (
                    str(symbol), str(timeframe), int(horizon_days),
                    json.dumps(features, ensure_ascii=False),
                    json.dumps(report, ensure_ascii=False),
                ),
            )
            return True
        except Exception:
            return False


def update_ai_outcome(signal_id: int, outcome_return_pct: float, exit_features: dict = None):
    """تحديث نتيجة إشارة قديمة (تستخدم لاحقاً للتعلّم)."""
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    _ensure_ai_tables()
    try:
        win = 1 if float(outcome_return_pct) > 0 else 0
        if exit_features is not None:
            # نحاول تحديث exit_features_json أيضاً
            try:
                execute_query(
                    "UPDATE ai_signals SET outcome_return_pct=%s, outcome_win=%s, exit_features_json=%s WHERE id=%s",
                    (float(outcome_return_pct), int(win), json.dumps(exit_features, ensure_ascii=False), int(signal_id)),
                )
            except Exception:
                execute_query(
                    "UPDATE ai_signals SET outcome_return_pct=%s, outcome_win=%s WHERE id=%s",
                    (float(outcome_return_pct), int(win), int(signal_id)),
                )
        else:
            execute_query(
                "UPDATE ai_signals SET outcome_return_pct=%s, outcome_win=%s WHERE id=%s",
                (float(outcome_return_pct), int(win), int(signal_id)),
            )
        return True
    except Exception:
        return False


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
    try:
        execute_query(
            """
            INSERT INTO ai_weights (key, weight) VALUES (%s,%s)
            ON CONFLICT (key) DO UPDATE SET weight=EXCLUDED.weight, updated_at=NOW()
            """,
            (str(key), float(weight)),
        )
        return True
    except Exception:
        # fallback بسيط لو DB لا يدعم ON CONFLICT
        try:
            _try_exec("DELETE FROM ai_weights WHERE key=%s", (str(key),))
            _try_exec("INSERT INTO ai_weights (key, weight) VALUES (%s,%s)", (str(key), float(weight)))
            return True
        except Exception:
            return False


def learn_from_history(max_rows=400):
    """
    تعلّم بسيط على مستوى feature_key (كما عندك).
    """
    execute_query, fetch_table = _safe_import_db()
    if not execute_query or not fetch_table:
        return {"ok": False, "reason": "DB not available"}

    _ensure_ai_tables()
    try:
        df = fetch_table("ai_signals")
        if df is None or df.empty:
            return {"ok": True, "updated": 0}

        df = df.dropna(subset=["outcome_win"])
        if df.empty:
            return {"ok": True, "updated": 0}

        df = df.sort_values("created_at", ascending=False).head(int(max_rows))

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
            "INSERT INTO ai_user_rules (title, rule_text, parsed_json, enabled) VALUES (%s,%s,%s,%s)",
            (
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
    """
    Parsing بسيط ومستقر (بدون ML):
    يحاول اكتشاف قواعد مثل:
    - "تقاطع الماكد صعودا واختراق خط الصفر"
    - "RSI فوق 70"
    - "اختراق مستوى 38 فيبو"
    """
    t = (text or "").strip().lower()

    parsed = {
        "raw": text,
        "conditions": [],
        "direction": None,      # buy/sell
        "boost": 1.5,           # تأثير افتراضي
        "tags": [],
    }

    # اتجاه (تقريبي)
    if any(k in t for k in ["شراء", "تجميع", "صعود", "شراءً", "buy"]):
        parsed["direction"] = "buy"
    if any(k in t for k in ["بيع", "خروج", "هبوط", "sell"]):
        parsed["direction"] = "sell"

    # MACD
    if "ماكد" in t or "macd" in t:
        # تقاطع صعود/هبوط
        if any(k in t for k in ["تقاطع", "cross"]) and any(k in t for k in ["صعود", "ايجابي", "up"]):
            parsed["conditions"].append({"type": "macd_cross", "value": "up"})
            parsed["tags"].append("MACD_CROSS_UP")
        if any(k in t for k in ["تقاطع", "cross"]) and any(k in t for k in ["هبوط", "سلبي", "down"]):
            parsed["conditions"].append({"type": "macd_cross", "value": "down"})
            parsed["tags"].append("MACD_CROSS_DN")

        # اختراق خط الصفر
        if any(k in t for k in ["خط الصفر", "zero"]):
            if any(k in t for k in ["فوق", "اختراق", "up", "اعلى"]):
                parsed["conditions"].append({"type": "macd_zero", "value": "above"})
                parsed["tags"].append("MACD_ABOVE_ZERO")
            if any(k in t for k in ["تحت", "down", "اسفل"]):
                parsed["conditions"].append({"type": "macd_zero", "value": "below"})
                parsed["tags"].append("MACD_BELOW_ZERO")

    # RSI thresholds
    if "rsi" in t or "مؤشر القوة النسبية" in t or "القوة النسبية" in t:
        m = re.search(r"(?:rsi|القوة)\s*(?:فوق|اعلى|>)\s*(\d+)", t)
        if m:
            parsed["conditions"].append({"type": "rsi_gt", "value": float(m.group(1))})
            parsed["tags"].append("RSI_GT")
        m = re.search(r"(?:rsi|القوة)\s*(?:تحت|اقل|<)\s*(\d+)", t)
        if m:
            parsed["conditions"].append({"type": "rsi_lt", "value": float(m.group(1))})
            parsed["tags"].append("RSI_LT")

        # شائع
        if "فوق 70" in t:
            parsed["conditions"].append({"type": "rsi_gt", "value": 70.0})
            parsed["tags"].append("RSI_GT_70")
        if "تحت 30" in t:
            parsed["conditions"].append({"type": "rsi_lt", "value": 30.0})
            parsed["tags"].append("RSI_LT_30")

    # SMA break
    if "sma" in t or "متوسط" in t or "موفينج" in t:
        # SMA 20 / 50
        m = re.search(r"(?:sma|متوسط)\s*(\d+)", t)
        if m:
            n = int(m.group(1))
            if any(k in t for k in ["اختراق", "فوق", "اعلى"]):
                parsed["conditions"].append({"type": "close_above_sma", "value": n})
                parsed["tags"].append(f"CLOSE_ABOVE_SMA{n}")
            if any(k in t for k in ["كسر", "تحت", "اسفل"]):
                parsed["conditions"].append({"type": "close_below_sma", "value": n})
                parsed["tags"].append(f"CLOSE_BELOW_SMA{n}")

    # Fibonacci 38
    if "فيبو" in t or "fibo" in t or "fib" in t:
        if "38" in t:
            # اختراق 38
            if any(k in t for k in ["اختراق", "فوق", "اعلى"]):
                parsed["conditions"].append({"type": "fib_cross", "value": 38})
                parsed["tags"].append("FIB_38_UP")
            if any(k in t for k in ["كسر", "تحت", "اسفل"]):
                parsed["conditions"].append({"type": "fib_cross", "value": -38})
                parsed["tags"].append("FIB_38_DN")

    # تأثير rule (اختياري)
    m = re.search(r"(?:boost|قوة|تأثير)\s*[:=]?\s*(\d+(?:\.\d+)?)", t)
    if m:
        parsed["boost"] = float(m.group(1))

    # لو ما قدر يفهم شيء: نخليه نصي فقط
    return parsed


def _compute_indicators(df: pd.DataFrame):
    """
    مؤشرات خفيفة لتقييم قواعد المستخدم + أسباب الفشل.
    - RSI14
    - MACD (12,26,9)
    - SMA20/50
    - Fib 38.2 من آخر موجة سوينغ مبسطة
    """
    out = {}
    if df is None or df.empty or len(df) < 60:
        return out

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    # SMA
    out["sma20"] = close.rolling(20).mean()
    out["sma50"] = close.rolling(50).mean()

    # RSI14
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    out["rsi14"] = rsi.fillna(method="bfill").fillna(50)

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    out["macd"] = macd
    out["macd_signal"] = signal
    out["macd_hist"] = hist

    # Fib 38.2 مبسط: آخر 120 شمعة، نأخذ أعلى قمة وأدنى قاع ونحسب 38.2
    try:
        look = 120 if len(df) >= 120 else len(df)
        hh = float(high.iloc[-look:].max())
        ll = float(low.iloc[-look:].min())
        rng = hh - ll
        if rng > 0:
            fib382 = ll + 0.382 * rng
            out["fib382"] = fib382
            out["range_high"] = hh
            out["range_low"] = ll
    except Exception:
        pass

    return out


def _eval_user_rule(parsed_rule: dict, df: pd.DataFrame, ind: dict):
    """
    يرجع: (hit:bool, score_delta:float, reason:str, features:dict)
    """
    if not parsed_rule:
        return False, 0.0, "", {}

    conds = parsed_rule.get("conditions") or []
    if not conds:
        return False, 0.0, "", {}

    boost = float(parsed_rule.get("boost") or 1.5)
    direction = parsed_rule.get("direction")  # buy/sell/None

    close = float(df["Close"].astype(float).iloc[-1])
    prev_close = float(df["Close"].astype(float).iloc[-2])

    # Latest indicator values
    rsi14 = float(ind.get("rsi14").iloc[-1]) if isinstance(ind.get("rsi14"), pd.Series) else None
    macd = float(ind.get("macd").iloc[-1]) if isinstance(ind.get("macd"), pd.Series) else None
    macd_prev = float(ind.get("macd").iloc[-2]) if isinstance(ind.get("macd"), pd.Series) else None
    sig = float(ind.get("macd_signal").iloc[-1]) if isinstance(ind.get("macd_signal"), pd.Series) else None
    sig_prev = float(ind.get("macd_signal").iloc[-2]) if isinstance(ind.get("macd_signal"), pd.Series) else None
    sma20 = float(ind.get("sma20").iloc[-1]) if isinstance(ind.get("sma20"), pd.Series) else None
    sma50 = float(ind.get("sma50").iloc[-1]) if isinstance(ind.get("sma50"), pd.Series) else None
    fib382 = ind.get("fib382", None)

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
            s = sma20 if n == 20 else (sma50 if n == 50 else None)
            if s is None:
                return False
            return close > s and prev_close <= s
        if t == "close_below_sma":
            n = int(v)
            s = sma20 if n == 20 else (sma50 if n == 50 else None)
            if s is None:
                return False
            return close < s and prev_close >= s
        if t == "fib_cross" and fib382 is not None:
            # value=38 => اختراق للأعلى، value=-38 => كسر للأسفل
            if int(v) == 38:
                return close > float(fib382) and prev_close <= float(fib382)
            if int(v) == -38:
                return close < float(fib382) and prev_close >= float(fib382)
        return False

    hits = [ok_one(c) for c in conds]
    if not all(hits):
        return False, 0.0, "", {}

    # score delta بحسب الاتجاه
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
# 🕯️ 1) Advanced Candlestick Patterns (موجود + ثابت)
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

    # Morning Star
    if is_c1_red and body2 < body1 * 0.4 and is_c3_green:
        midpoint = c1["Open"] - (body1 / 2)
        if c3["Close"] > midpoint:
            score += 3
            patterns.append("✨ نجمة الصباح - انعكاس إيجابي قوي")

    # Evening Star
    if is_c1_green and body2 < body1 * 0.4 and is_c3_red:
        midpoint = c1["Open"] + (body1 / 2)
        if c3["Close"] < midpoint:
            score -= 3
            patterns.append("🌑 نجمة المساء - خروج/انعكاس سلبي")

    # Bullish Harami
    if is_c2_red and is_c3_green and c3["Open"] > c2["Close"] and c3["Close"] < c2["Open"]:
        score += 2
        patterns.append("🤰 الحرامي الشرائي - ضعف الزخم الهابط")

    # Bullish Engulfing
    if is_c2_red and is_c3_green and c3["Open"] < c2["Close"] and c3["Close"] > c2["Open"]:
        score += 2
        patterns.append("🔥 ابتلاع شرائي - سيطرة مشترين")

    return score, patterns


# ============================================================
# 📈 2) Market Structure + BMS/Retest/OTE (مطوّر)
# ============================================================

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

    # Retest + OTE (قرب 50%)
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


# ============================================================
# 🧩 3) Smart Money: Liquidity Sweep + Order Block + AMD (مطوّر)
# ============================================================

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


# ============================================================
# ☁️ 4) Ichimoku Trend Filter (مطوّر)
# ============================================================

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


# ============================================================
# 💰 5) Fundamental Golden Rules (موجود + ثابت)
# ============================================================

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


# ============================================================
# 📊 6) VSA (مطوّر أكثر)
# ============================================================

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


# ============================================================
# 🧱 7) Support/Resistance Zones (مبسطة)
# ============================================================

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
# ✅ Confidence + Explainability (كما عندك)
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
    pos_keys = ["اختراق", "BMS", "OTE", "نجمة", "ابتلاع", "قوة", "Order Block", "Ichimoku صاعد", "Bias شرائي", "Stopping", "دعم", "✅", "💎", "🔀 تقاطع", "قاعدة مستخدم"]

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


# ============================================================
# 🎛️ Calibration: Learned Bias from ai_decisions + lab_*
# ============================================================

def _normalize_cols(df: pd.DataFrame):
    # يحاول توحيد أسماء الأعمدة الشائعة
    if df is None or df.empty:
        return df
    df = df.copy()
    cols = {c: c.lower() for c in df.columns}
    df.rename(columns=cols, inplace=True)
    return df


def _parse_json_safe(x):
    try:
        if x is None:
            return {}
        if isinstance(x, dict):
            return x
        s = str(x)
        if not s.strip():
            return {}
        return json.loads(s)
    except Exception:
        return {}


def _extract_failure_tokens(features: dict):
    """
    يحول features_snapshot إلى أسباب مفهومة:
    - rsi_high/low
    - close_below_sma / broke_support_confirm
    - liq sweep
    - ichimoku bear
    - vsa upthrust
    """
    toks = []
    if not isinstance(features, dict):
        return toks

    # RSI numeric
    rsi = features.get("rsi") or features.get("rsi14") or features.get("RSI") or features.get("rsi_14")
    try:
        rsi = float(rsi) if rsi is not None else None
    except Exception:
        rsi = None

    if rsi is not None:
        if rsi >= 70:
            toks.append("RSI عالي (تشبع شراء)")
        elif rsi <= 30:
            toks.append("RSI منخفض (تشبع بيع)")

    # Flags
    flag_map = {
        "broke_support_confirm": "كسر دعم مؤكد",
        "near_resistance": "قرب مقاومة",
        "liq_sweep_high": "صيد سيولة شرائية (انعكاس سلبي محتمل)",
        "liq_sweep_low": "صيد سيولة بيعية (انعكاس إيجابي محتمل)",
        "bear_ob_retest": "Bearish OB retest",
        "bull_ob_retest": "Bullish OB retest",
        "ichi_bear": "Ichimoku هابط قوي",
        "ichi_bull": "Ichimoku صاعد قوي",
        "vsa_upthrust": "VSA Upthrust (ضعف)",
        "vsa_distribution": "VSA توزيع",
        "vsa_stopping_volume": "VSA Stopping (قوة)",
    }
    for k, label in flag_map.items():
        try:
            if int(features.get(k, 0)) == 1:
                toks.append(label)
        except Exception:
            pass

    # SMA numeric if present
    try:
        close = features.get("close")
        sma20 = features.get("sma20")
        sma50 = features.get("sma50")
        if close is not None and sma20 is not None:
            if float(close) < float(sma20):
                toks.append("السعر تحت SMA20")
        if close is not None and sma50 is not None:
            if float(close) < float(sma50):
                toks.append("السعر تحت SMA50")
    except Exception:
        pass

    return toks


def _best_strategy_from_rows(rows: pd.DataFrame, strategy_col="strategy_name"):
    """
    يتوقع الأعمدة (حسب المتوفر):
    - outcome_win / outcome_return_pct
    أو
    - return_pct / pnl_pct / gain_pct
    """
    if rows is None or rows.empty:
        return None

    df = rows.copy()
    df = _normalize_cols(df)

    # strategy column normalization
    if strategy_col.lower() not in df.columns:
        # نحاول بدائل
        for alt in ["strategy", "strategyname", "strat", "model_strategy"]:
            if alt in df.columns:
                strategy_col = alt
                break

    if strategy_col.lower() not in df.columns:
        return None

    # return column
    ret_col = None
    for c in ["outcome_return_pct", "return_pct", "pnl_pct", "gain_pct", "ret_pct"]:
        if c in df.columns:
            ret_col = c
            break

    win_col = "outcome_win" if "outcome_win" in df.columns else None

    # derive win from returns if needed
    if win_col is None and ret_col is not None:
        df["__win"] = df[ret_col].astype(float).apply(lambda x: 1 if x > 0 else 0)
        win_col = "__win"

    if ret_col is None or win_col is None:
        return None

    # group
    g = df.groupby(strategy_col.lower()).agg(
        n=(win_col, "count"),
        win_rate=(win_col, "mean"),
        avg_return=(ret_col, "mean"),
    ).reset_index()

    g = g[g["n"] >= 5]  # حد أدنى بسيط
    if g.empty:
        # لو أقل من 5، نأخذ أفضل الموجود
        g = df.groupby(strategy_col.lower()).agg(
            n=(win_col, "count"),
            win_rate=(win_col, "mean"),
            avg_return=(ret_col, "mean"),
        ).reset_index()

    g = g.sort_values(["win_rate", "avg_return", "n"], ascending=[False, False, False])
    best = g.iloc[0]
    return {
        "strategy": str(best[strategy_col.lower()]),
        "win_rate": float(best["win_rate"]),
        "avg_return": float(best["avg_return"]),
        "n": int(best["n"]),
        "table": g.head(10),
    }


def _collect_recent_ai_history(symbol: str, sector: str = None, limit=100):
    """
    يجمع تاريخ القرارات من:
    1) ai_decisions (لو موجود)
    2) ai_signals (fallback)
    ثم يحاول إلحاق نتائج من lab_trades / lab_runs / lab_equity بشكل مرن.
    """
    symbol = str(symbol)
    sector = (str(sector) if sector else None)

    df_dec = _safe_fetch_table("ai_decisions")
    if df_dec is not None and not df_dec.empty:
        df_dec = _normalize_cols(df_dec)
        # filter symbol/sector if columns exist
        if "symbol" in df_dec.columns:
            df_dec = df_dec[df_dec["symbol"].astype(str) == symbol]
        if sector and "sector" in df_dec.columns:
            df_dec = df_dec[df_dec["sector"].astype(str) == sector]
        if "created_at" in df_dec.columns:
            df_dec = df_dec.sort_values("created_at", ascending=False)
        df_dec = df_dec.head(int(limit))
        return df_dec, "ai_decisions"

    # fallback: ai_signals
    df_sig = _safe_fetch_table("ai_signals")
    if df_sig is None or df_sig.empty:
        return None, None

    df_sig = _normalize_cols(df_sig)
    if "symbol" in df_sig.columns:
        df_sig = df_sig[df_sig["symbol"].astype(str) == symbol]
    if sector and "sector" in df_sig.columns:
        df_sig = df_sig[df_sig["sector"].astype(str) == sector]
    if "created_at" in df_sig.columns:
        df_sig = df_sig.sort_values("created_at", ascending=False)
    df_sig = df_sig.head(int(limit))
    return df_sig, "ai_signals"


def get_learned_bias(symbol: str, sector: str = None, limit=100):
    """
    ✅ المطلوب منك:
    ترجع:
    - أفضل استراتيجية تاريخياً لهذا السهم/القطاع
    - win_rate + avg_return
    - أشهر أسباب الفشل (من features_snapshot وقت الدخول/الخروج)
    """
    rows, src = _collect_recent_ai_history(symbol, sector, limit=limit)
    if rows is None or rows.empty:
        return {
            "ok": True,
            "source": None,
            "symbol": str(symbol),
            "sector": sector,
            "best_strategy": None,
            "win_rate": None,
            "avg_return": None,
            "n": 0,
            "top_fail_reasons": [],
        }

    df = _normalize_cols(rows)

    # محاولة إيجاد strategy_name
    best = _best_strategy_from_rows(df, strategy_col="strategy_name")
    if best is None:
        # fallback: strategy موجود في report_json؟
        # نجرب استخراج "strategy" من report_json
        if "report_json" in df.columns:
            tmp = []
            for _, r in df.iterrows():
                rep = _parse_json_safe(r.get("report_json"))
                tmp.append(rep.get("strategy") or rep.get("strategy_name") or rep.get("recommendation") or "Unknown")
            df["strategy_name"] = tmp
            best = _best_strategy_from_rows(df, strategy_col="strategy_name")

    # استخراج أسباب الفشل من features_json + exit_features_json إذا موجود
    fail_tokens = []
    # نحدد صفوف خاسرة
    ret_col = None
    for c in ["outcome_return_pct", "return_pct", "pnl_pct", "gain_pct", "ret_pct"]:
        if c in df.columns:
            ret_col = c
            break

    if "outcome_win" in df.columns:
        losers = df[df["outcome_win"].astype(float) == 0]
    elif ret_col is not None:
        losers = df[df[ret_col].astype(float) <= 0]
    else:
        losers = df.iloc[0:0]

    if not losers.empty:
        for _, r in losers.iterrows():
            feats = _parse_json_safe(r.get("features_json"))
            exit_feats = _parse_json_safe(r.get("exit_features_json"))
            fail_tokens += _extract_failure_tokens(feats)
            fail_tokens += _extract_failure_tokens(exit_feats)

    # top reasons
    top_fail = []
    if fail_tokens:
        s = pd.Series(fail_tokens).value_counts().head(7)
        top_fail = [f"{idx} ({int(val)})" for idx, val in s.items()]

    if best is None:
        return {
            "ok": True,
            "source": src,
            "symbol": str(symbol),
            "sector": sector,
            "best_strategy": None,
            "win_rate": None,
            "avg_return": None,
            "n": int(len(df)),
            "top_fail_reasons": top_fail,
        }

    return {
        "ok": True,
        "source": src,
        "symbol": str(symbol),
        "sector": sector,
        "best_strategy": best["strategy"],
        "win_rate": round(best["win_rate"], 4),
        "avg_return": round(best["avg_return"], 4),
        "n": int(best["n"]),
        "top_fail_reasons": top_fail,
    }


# ============================================================
# 🧠 Master Brain (مطوّر: Calibration + User Rules)
# ============================================================

def _infer_strategy_hint(module_scores: dict):
    """
    يعطي اسم استراتيجية/مدرسة مسيطرة من مكونات التحليل.
    """
    if not module_scores:
        return "Mixed"
    # الأعلى مطلقاً
    k = max(module_scores.keys(), key=lambda x: abs(module_scores.get(x, 0) or 0))
    return str(k)


def generate_ai_report(symbol, timeframe="1D"):
    """
    نفس مفاتيحك الأساسية + إضافات:
    - Calibration: learned bias
    - User rules: text strategies that affect score/reasons (بدون كسر)
    """
    try:
        df = get_chart_history(symbol, period="6mo")
        if df is None or df.empty:
            raise ValueError("no data")

        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in df.columns:
                raise ValueError(f"missing {col}")

        # مؤشرات مساعدة (للقواعد + أسباب الفشل)
        ind = _compute_indicators(df)

        # 1) Candles
        s_candle, o_candle = _detect_advanced_patterns(df)

        # 2) Market Structure
        s_struct, o_struct = _analyze_market_structure(df)

        # 3) SMC
        s_liq, o_liq, f_liq = _detect_liquidity_sweep(df)
        s_ob, o_ob, f_ob = _detect_order_block(df)

        # 4) Ichimoku
        s_ichi, o_ichi, f_ichi = _analyze_ichimoku(df)

        # 5) VSA
        s_vsa, o_vsa, f_vsa = _analyze_vsa_art_of_trading(df)

        # 6) SR Zones
        s_sr, o_sr, f_sr = _analyze_sr(df)

        # 7) Fundamentals
        s_fund, o_fund, m_fund = _analyze_financial_golden_rules(symbol)

        # ------------------------------------------
        # 🔧 Weighted Tech Score (كما عندك)
        # ------------------------------------------
        base_tech = s_candle + s_struct + s_vsa + s_ichi + s_ob + s_liq + s_sr
        tech_reasons = (o_struct or []) + (o_candle or []) + (o_vsa or []) + (o_ichi or []) + (o_ob or []) + (o_liq or []) + (o_sr or [])

        # Features 0/1
        features = {}
        fund_feats = (m_fund or {}).get("_fund_features", {})
        for d in [f_liq, f_ob, f_ichi, f_vsa, f_sr, fund_feats]:
            try:
                for k, v in (d or {}).items():
                    if isinstance(v, (bool, int)):
                        features[k] = int(v)
            except Exception:
                pass

        # أضف لقطة رقمية مفيدة للتعلّم/الفشل (لا تغير مزاياك، فقط إثراء)
        try:
            close_last = float(df["Close"].astype(float).iloc[-1])
            features["close"] = close_last
            if isinstance(ind.get("rsi14"), pd.Series):
                features["rsi14"] = float(ind["rsi14"].iloc[-1])
            if isinstance(ind.get("sma20"), pd.Series):
                features["sma20"] = float(ind["sma20"].iloc[-1])
            if isinstance(ind.get("sma50"), pd.Series):
                features["sma50"] = float(ind["sma50"].iloc[-1])
            if ind.get("fib382") is not None:
                features["fib382"] = float(ind["fib382"])
        except Exception:
            pass

        # weights bonus
        weighted_bonus = 0.0
        for k, v in features.items():
            if isinstance(v, (bool, int)) and int(v) == 1:
                weighted_bonus += (0.2 * (_get_weight(k, 1.0) - 1.0))

        tech_score = float(base_tech + weighted_bonus)
        fund_score = float(s_fund)
        total_score = float(tech_score + fund_score)

        # ------------------------------------------
        # ✅ User Rules Integration (بدون كسر)
        # ------------------------------------------
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
                    # سجل features
                    for kk, vv in (f_user or {}).items():
                        features[kk] = int(vv)

        if abs(user_delta) > 0:
            tech_score = float(tech_score + user_delta)
            total_score = float(tech_score + fund_score)

        # ------------------------------------------
        # 🔥 Calibration / Learned Bias
        # ------------------------------------------
        sector = None
        try:
            # لو عندك get_static_info موجود، خذه بدون ما نكسر لو غير متوفر
            from market_data import get_static_info
            info = get_static_info(symbol) or {}
            sector = info.get("sector") or info.get("Sector") or info.get("industry") or None
        except Exception:
            sector = None

        learned = get_learned_bias(symbol, sector, limit=100)

        # Hint strategy name من مكونات التحليل (للتسجيل/المقارنة)
        module_scores = {
            "MarketStructure": s_struct,
            "SmartMoney": (s_liq + s_ob),
            "Ichimoku": s_ichi,
            "VSA": s_vsa,
            "Candles": s_candle,
            "SupportResistance": s_sr,
            "Fundamental": s_fund,
            "UserRules": user_delta,
        }
        strategy_name = _infer_strategy_hint(module_scores)

        # تأثير learned bias على الثقة/التوصية
        calib_note = None
        calib_conf_delta = 0
        if learned and learned.get("best_strategy"):
            wr = learned.get("win_rate")
            ar = learned.get("avg_return")
            n = learned.get("n", 0)
            if wr is not None and n >= 10:
                if float(wr) >= 0.60:
                    calib_conf_delta = +6
                    calib_note = f"🎯 Calibration: تاريخياً للسهم/القطاع أفضل أداء ({learned['best_strategy']}) | WinRate={wr:.0%} | AvgRet={ar:.2f}%"
                elif float(wr) <= 0.45:
                    calib_conf_delta = -6
                    calib_note = f"⚠️ Calibration: تاريخياً أداء ضعيف للاستراتيجيات على هذا السهم/القطاع | WinRate={wr:.0%} | راقب أسباب الفشل"
            # ارفع وزن strategy المسيطرة لهذا السهم/القطاع (لطيف)
            try:
                if wr is not None:
                    key = f"STRAT::{sector or 'NA'}::{symbol}::{learned['best_strategy']}"
                    w0 = _get_weight(key, 1.0)
                    if float(wr) >= 0.60:
                        _set_weight(key, min(w0 + 0.08, 2.0))
                    elif float(wr) <= 0.45:
                        _set_weight(key, max(w0 - 0.08, 0.3))
            except Exception:
                pass

        # ------------------------------------------
        # القرار (نفس منطقك)
        # ------------------------------------------
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

        # تطبيق Calibration على الثقة
        if calib_conf_delta != 0:
            confidence = int(max(0, min(100, confidence + calib_conf_delta)))
            if calib_note:
                tech_reasons.append(calib_note)

        # أسباب الفشل الشائعة من learned
        if learned and learned.get("top_fail_reasons"):
            # ضفها كـ Notes في explainability
            pass

        explainability = _build_explainability(tech_reasons, fund_reasons, total_score, tech_score, fund_score)

        if learned and learned.get("top_fail_reasons"):
            explainability["notes"] = (explainability.get("notes") or []) + [f"أشهر أسباب الفشل: {', '.join(learned['top_fail_reasons'][:4])}"]

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
            # إضافات جديدة (لا تكسر العرض)
            "calibration": learned,
            "strategy_name": strategy_name,
            "sector": sector,
        }

        # ✅ يسجّل ذاكرة
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
