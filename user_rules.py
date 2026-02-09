# ai_engine_core/user_rules.py

import json
import re
import uuid
import pandas as pd

from .db import _safe_import_db, _try_exec, _safe_fetch_table, _ensure_user_rules_table
from .core import _now_str

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

            rules.append(
                {
                    "id": r.get("id"),
                    "title": r.get("title") or "قاعدة مستخدم",
                    "rule_text": r.get("rule_text") or "",
                    "parsed": parsed,
                }
            )
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
