# ai_engine_core/rules.py

import uuid
import json
import re
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
    # ✅ انسخ دالتك كما هي بالكامل (هي طويلة ومنطقها ممتاز)
    # (ضع هنا نفس محتوى _parse_user_rule من ملفك الأصلي)
    t = (text or "").strip().lower()
    parsed = {"raw": text, "conditions": [], "direction": None, "boost": 1.5, "tags": []}

    if any(k in t for k in ["شراء", "تجميع", "صعود", "buy"]):
        parsed["direction"] = "buy"
    if any(k in t for k in ["بيع", "خروج", "هبوط", "sell"]):
        parsed["direction"] = "sell"

    # ... أكمل بقية منطقك من الملف الأصلي كما هو
    return parsed

def _eval_user_rule(parsed_rule: dict, df: pd.DataFrame, ind: dict):
    # ✅ انسخ دالتك كما هي بالكامل (هي الأساس لتطبيق القواعد)
    # (ضع هنا نفس محتوى _eval_user_rule من ملفك الأصلي)
    if not parsed_rule:
        return False, 0.0, "", {}
    # ...
    return False, 0.0, "", {}
