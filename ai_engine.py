# ai_engine.py
# Minimal, stable AI Engine for Osoli (no external ML deps)
# Provides required functions expected by ui/pages/analysis and views_impl.
# - generate_ai_report
# - calculate_portfolio_risk_score
# - run_stress_test
# - generate_rebalancing_suggestions
# - save_user_rule
# - load_user_rules

from __future__ import annotations

import math
import traceback
from typing import Any, Dict, List, Optional

import pandas as pd

AI_ENGINE_VERSION = "0.3.0-min-stable"


# --------------------------------------------------------
# DB (Fail-safe)
# --------------------------------------------------------
_db_ok = True
_db_err = ""
try:
    from database import execute_query, fetch_table
except Exception as e:
    _db_ok = False
    _db_err = repr(e)

    def execute_query(*args, **kwargs):  # type: ignore
        raise RuntimeError(f"database module missing: {_db_err}")

    def fetch_table(*args, **kwargs):  # type: ignore
        return pd.DataFrame()


def _ensure_rules_table():
    """
    Creates user_rules table if missing.
    Works with Postgres/SQLite in most setups.
    """
    if not _db_ok:
        return
    try:
        execute_query(
            """
            CREATE TABLE IF NOT EXISTS user_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                rule_text TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception:
        # Some Postgres setups need SERIAL instead of AUTOINCREMENT;
        # ignore if already exists or dialect differs.
        try:
            execute_query(
                """
                CREATE TABLE IF NOT EXISTS user_rules (
                    id SERIAL PRIMARY KEY,
                    title TEXT,
                    rule_text TEXT,
                    enabled INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        except Exception:
            pass


# --------------------------------------------------------
# Market data (Fail-safe)
# --------------------------------------------------------
_md_ok = True
_md_err = ""
try:
    from market_data import get_chart_history
except Exception as e:
    _md_ok = False
    _md_err = repr(e)

    def get_chart_history(*args, **kwargs):  # type: ignore
        return pd.DataFrame()


# --------------------------------------------------------
# Helpers: indicators
# --------------------------------------------------------
def _col_pick(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    cols = {str(c).lower(): c for c in df.columns}
    for n in names:
        if n.lower() in cols:
            return cols[n.lower()]
    return None


def _safe_df(data: Any) -> pd.DataFrame:
    if data is None:
        return pd.DataFrame()
    if isinstance(data, pd.DataFrame):
        return data.copy()
    try:
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=max(2, n // 3)).mean()


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    rs = _ema(up, n) / (_ema(down, n) + 1e-9)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h = df[_col_pick(df, ["high", "High"]) or df.columns[0]].astype(float)
    l = df[_col_pick(df, ["low", "Low"]) or df.columns[0]].astype(float)
    c = df[_col_pick(df, ["close", "Close"]) or df.columns[0]].astype(float)
    prev_c = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=max(2, n // 3)).mean()


def _pct(a: float, b: float) -> float:
    return 0.0 if b == 0 else (a / b) * 100.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _tf_to_period_interval(tf: str) -> Dict[str, str]:
    """
    Convert UI timeframe to suitable market_data call.
    We keep it conservative: 1d -> 6mo/1d, 1wk -> 3y/1d, 1mo -> 10y/1wk
    """
    t = (tf or "1d").strip().lower()
    if t in ("1wk", "1w", "week"):
        return {"period": "3y", "interval": "1d"}
    if t in ("1mo", "1m", "month"):
        return {"period": "10y", "interval": "1wk"}
    return {"period": "6mo", "interval": "1d"}


# --------------------------------------------------------
# Required API
# --------------------------------------------------------
def generate_ai_report(symbol: str, timeframe: str = "1d") -> Dict[str, Any]:
    """
    Generates a lightweight "Osoli-style" report without external ML.
    Returns dict compatible with the UI renderer.
    """
    sym = (symbol or "").strip().upper()
    tf = (timeframe or "1d").strip().lower()

    if not sym:
        return {
            "__error__": "symbol missing",
            "__trace__": "",
            "recommendation": "تعذر توليد التقرير",
            "strategy": "Fallback",
            "color": "#b42318",
            "score": 0,
            "confidence": 0,
            "confidence_label": "منخفضة",
            "summary_text": "رمز السهم غير صحيح.",
            "risk_gates": {"pass": False, "reasons": ["رمز السهم غير صحيح"]},
            "scenarios": [],
            "top_evidence": [],
            "top_risks": ["رمز السهم غير صحيح"],
        }

    if not _md_ok:
        return {
            "__error__": "market_data missing",
            "__trace__": _md_err,
            "recommendation": "تعذر توليد التقرير",
            "strategy": "Fallback",
            "color": "#b42318",
            "score": 0,
            "confidence": 0,
            "confidence_label": "منخفضة",
            "summary_text": "تعذر جلب بيانات السوق: market_data غير متاح.",
            "risk_gates": {"pass": False, "reasons": ["market_data غير متاح"]},
            "scenarios": [],
            "top_evidence": [],
            "top_risks": ["تعذر جلب بيانات السوق"],
        }

    try:
        cfg = _tf_to_period_interval(tf)
        df = _safe_df(get_chart_history(sym, period=cfg["period"], interval=cfg["interval"]))
        if df.empty:
            # try older signature
            df = _safe_df(get_chart_history(sym, cfg["period"]))

        if df.empty:
            return {
                "__error__": "empty price data",
                "__trace__": "",
                "recommendation": "تعذر توليد التقرير",
                "strategy": "Fallback",
                "color": "#b42318",
                "score": 0,
                "confidence": 0,
                "confidence_label": "منخفضة",
                "summary_text": "لم أستطع جلب بيانات سعرية لهذا الرمز.",
                "risk_gates": {"pass": False, "reasons": ["بيانات سعرية غير متاحة"]},
                "scenarios": [],
                "top_evidence": [],
                "top_risks": ["بيانات سعرية غير متاحة"],
            }

        close_col = _col_pick(df, ["close", "Close"]) or df.columns[-1]
        c = pd.to_numeric(df[close_col], errors="coerce").dropna()
        if c.empty:
            raise ValueError("close series empty")

        last = float(c.iloc[-1])
        sma50 = float(_sma(c, 50).iloc[-1]) if len(c) >= 10 else last
        sma200 = float(_sma(c, 200).iloc[-1]) if len(c) >= 30 else sma50
        rsi14 = float(_rsi(c, 14).iloc[-1]) if len(c) >= 20 else 50.0

        # Trend score (0..60)
        trend = 0.0
        trend += 25.0 if last > sma50 else 8.0
        trend += 25.0 if sma50 > sma200 else 8.0
        trend += 10.0 if (last / (sma50 + 1e-9)) > 1.02 else 0.0
        trend = _clamp(trend, 0, 60)

        # Momentum score (0..40)
        mom = 0.0
        if rsi14 >= 60:
            mom = 35.0
        elif rsi14 >= 50:
            mom = 25.0
        elif rsi14 >= 40:
            mom = 15.0
        else:
            mom = 8.0
        # penalize extreme overbought a bit
        if rsi14 >= 75:
            mom -= 8.0
        mom = _clamp(mom, 0, 40)

        score = int(round(_clamp(trend + mom, 0, 100)))

        # Confidence
        confidence = 40
        if len(c) >= 120:
            confidence += 25
        elif len(c) >= 60:
            confidence += 15
        if (abs(last - sma50) / (sma50 + 1e-9)) >= 0.03:
            confidence += 10
        confidence = int(_clamp(confidence, 10, 90))

        conf_label = "مرتفعة" if confidence >= 70 else "متوسطة" if confidence >= 40 else "منخفضة"

        # Recommendation
        if score >= 75:
            rec = "شراء / تعزيز"
            color = "#16a34a"
        elif score >= 55:
            rec = "مراقبة إيجابية"
            color = "#f59e0b"
        else:
            rec = "تجنب / انتظار"
            color = "#ef4444"

        # Risk gates
        reasons = []
        passed = True

        # Basic gates
        if score < 45:
            passed = False
            reasons.append("السكور منخفض (ضعف اتجاه/زخم).")

        if rsi14 >= 75:
            passed = False
            reasons.append("تشبع شرائي مرتفع (RSI>=75) يزيد احتمال التصحيح.")

        # Entry / Stop via ATR
        # Build atr only if OHLC exists
        entry_zone = last
        stop = None
        inv = None
        rr = None
        support = None
        resistance = None
        targets = []

        try:
            hi = _col_pick(df, ["high", "High"])
            lo = _col_pick(df, ["low", "Low"])
            if hi and lo:
                atr14 = float(_atr(df, 14).iloc[-1])
                stop = max(0.0, last - 2.0 * atr14)
                inv = max(0.0, last - 2.5 * atr14)
                t1 = last + 2.0 * atr14
                t2 = last + 3.5 * atr14
                rr = (t1 - last) / max(1e-9, (last - stop))
                targets = [
                    {"name": "هدف 1", "price": float(t1), "note": "مستهدف ATR"},
                    {"name": "هدف 2", "price": float(t2), "note": "مستهدف ATR"},
                ]
                support = float(last - 1.5 * atr14)
                resistance = float(last + 1.5 * atr14)
        except Exception:
            pass

        # Evidence / Risks bullets
        top_evidence = []
        if last > sma50:
            top_evidence.append("السعر أعلى من متوسط 50 يوم.")
        else:
            top_evidence.append("السعر أسفل متوسط 50 يوم.")

        if sma50 > sma200:
            top_evidence.append("ترند متوسط/طويل إيجابي (MA50 أعلى MA200).")
        else:
            top_evidence.append("ترند متوسط/طويل سلبي (MA50 أسفل MA200).")

        top_evidence.append(f"RSI تقريباً {rsi14:.1f}.")

        top_risks = []
        if score < 55:
            top_risks.append("الزخم/الاتجاه غير كافٍ لإشارة قوية.")
        if rsi14 >= 70:
            top_risks.append("قريب من تشبع شرائي.")
        if rsi14 <= 35:
            top_risks.append("ضعف واضح/تشبع بيعي محتمل.")
        if not targets:
            top_risks.append("تعذر حساب ATR/مستويات بسبب نقص بيانات OHLC.")

        # Scenarios
        scenarios = []
        if targets and stop is not None:
            scenarios.append(
                {
                    "name": "سيناريو اختراق/استمرار",
                    "trigger": "ثبات أعلى MA50 مع زخم RSI > 55",
                    "entry": float(entry_zone),
                    "stop": float(stop),
                    "target1": float(targets[0]["price"]),
                    "target2": float(targets[1]["price"]),
                    "note": "تقوية الصفقة عند الإغلاق الإيجابي.",
                }
            )
            scenarios.append(
                {
                    "name": "سيناريو ارتداد دعم",
                    "trigger": "هبوط باتجاه الدعم ثم شمعة انعكاس",
                    "entry": float(support) if support else float(entry_zone),
                    "stop": float(inv) if inv else float(stop),
                    "target1": float(entry_zone),
                    "target2": float(targets[0]["price"]),
                    "note": "مناسب إذا السوق العام داعم.",
                }
            )

        summary_text = (
            f"السكور {score}/100 على فاصل {tf}. "
            f"الاتجاه: {'إيجابي' if sma50 > sma200 else 'سلبي'} | "
            f"RSI: {rsi14:.1f}."
        )

        return {
            "symbol": sym,
            "timeframe": tf,
            "recommendation": rec,
            "strategy": "Tech+Rules (Light)",
            "color": color,
            "score": score,
            "confidence": confidence,
            "confidence_label": conf_label,
            "summary_text": summary_text,
            "entry": {"entry_zone": float(entry_zone)},
            "risk": {
                "stop": float(stop) if stop is not None else None,
                "invalidation": float(inv) if inv is not None else None,
                "rr": float(rr) if rr is not None else None,
            },
            "levels": {
                "support": float(support) if support is not None else None,
                "resistance": float(resistance) if resistance is not None else None,
            },
            "targets": targets,
            "top_evidence": top_evidence,
            "top_risks": top_risks,
            "risk_gates": {"pass": bool(passed), "reasons": reasons},
            "scenarios": scenarios,
            "explainability": {"positives": top_evidence, "negatives": top_risks, "notes": []},
        }

    except Exception as e:
        return {
            "__error__": f"AI report exception: {e}",
            "__trace__": traceback.format_exc(),
            "recommendation": "تعذر توليد التقرير",
            "strategy": "Fallback",
            "color": "#b42318",
            "score": 0,
            "confidence": 0,
            "confidence_label": "منخفضة",
            "summary_text": "حدث خطأ أثناء توليد التقرير.",
            "risk_gates": {"pass": False, "reasons": ["استثناء أثناء توليد التقرير"]},
            "scenarios": [],
            "top_evidence": [],
            "top_risks": ["استثناء أثناء توليد التقرير"],
        }


def calculate_portfolio_risk_score(df_positions: pd.DataFrame, config: Optional[dict] = None) -> int:
    """
    Simple risk score (0..100). Higher = riskier.
    Uses concentration + drawdown proxy (volatility).
    """
    d = _safe_df(df_positions)
    if d.empty:
        return 50

    qty_col = _col_pick(d, ["quantity", "qty"])
    price_col = _col_pick(d, ["price", "entry_price", "avg_price", "last_price"])
    if not qty_col or not price_col:
        return 55

    qty = pd.to_numeric(d[qty_col], errors="coerce").fillna(0.0)
    price = pd.to_numeric(d[price_col], errors="coerce").fillna(0.0)
    value = (qty * price).clip(lower=0.0)
    total = float(value.sum())
    if total <= 0:
        return 55

    weights = (value / total).fillna(0.0)
    concentration = float((weights ** 2).sum())  # Herfindahl
    # map concentration to 0..40
    conc_score = _clamp((concentration * 100.0), 5.0, 40.0)

    # basic: more positions => less risk
    npos = int((value > 0).sum())
    diversity_bonus = _clamp(20 - npos * 2.0, 0, 20)

    risk = int(_clamp(60 + conc_score - diversity_bonus, 0, 100))
    return risk


def run_stress_test(portfolio_value: float, open_positions: pd.DataFrame) -> Dict[str, Any]:
    """
    Simple stress scenarios based on portfolio value and position concentration.
    """
    pv = float(portfolio_value or 0.0)
    d = _safe_df(open_positions)

    scenarios = [
        {"scenario": "هبوط السوق -5%", "impact_pct": -5.0},
        {"scenario": "هبوط السوق -10%", "impact_pct": -10.0},
        {"scenario": "صدمة قوية -20%", "impact_pct": -20.0},
    ]

    insight = ""
    if pv > 0:
        risk = calculate_portfolio_risk_score(d, {})
        if risk >= 75:
            insight = "المحفظة عالية المخاطر (تركّز مرتفع). خفف الحجم أو وزّع القطاعات."
        elif risk >= 55:
            insight = "مخاطر متوسطة. راقب التركز وفعّل وقف خسارة للمراكز."
        else:
            insight = "مخاطر منخفضة نسبياً. استمر بإدارة المخاطر."

    return {"scenarios": scenarios, "insight": insight}


def generate_rebalancing_suggestions(df_positions: pd.DataFrame, config: Optional[dict] = None) -> List[Dict[str, Any]]:
    """
    Minimal rebalancing suggestions based on concentration.
    """
    d = _safe_df(df_positions)
    if d.empty:
        return []

    sym_col = _col_pick(d, ["symbol", "ticker"])
    qty_col = _col_pick(d, ["quantity", "qty"])
    price_col = _col_pick(d, ["price", "entry_price", "avg_price", "last_price"])
    if not sym_col or not qty_col or not price_col:
        return []

    qty = pd.to_numeric(d[qty_col], errors="coerce").fillna(0.0)
    price = pd.to_numeric(d[price_col], errors="coerce").fillna(0.0)
    value = (qty * price).clip(lower=0.0)
    total = float(value.sum())
    if total <= 0:
        return []

    weights = (value / total).fillna(0.0)
    d2 = d.copy()
    d2["_w"] = weights
    d2["_v"] = value

    d2 = d2.sort_values("_w", ascending=False)
    top = d2.head(3)

    suggestions = []
    for _, r in top.iterrows():
        if float(r["_w"]) >= 0.35:
            suggestions.append(
                {
                    "symbol": str(r[sym_col]),
                    "suggestion": "تقليل التركز",
                    "reason": f"الوزن الحالي تقريباً {_pct(float(r['_v']), total):.1f}%.",
                    "action": "فكر بتخفيف جزء من المركز أو إضافة مراكز أخرى لتوزيع المخاطر.",
                }
            )

    return suggestions


def save_user_rule(rule_text: str, title: str = None, enabled: int = 1) -> Dict[str, Any]:
    """
    Save a user strategy rule to DB (user_rules).
    """
    txt = (rule_text or "").strip()
    if not txt:
        return {"ok": False, "reason": "rule_text empty"}

    if not _db_ok:
        return {"ok": False, "reason": "database missing", "trace": _db_err}

    try:
        _ensure_rules_table()
        t = (title or "قاعدة من المستخدم").strip()
        en = 1 if int(enabled or 0) else 0
        execute_query(
            "INSERT INTO user_rules (title, rule_text, enabled) VALUES (%s,%s,%s)",
            (t, txt, en),
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "reason": str(e), "trace": traceback.format_exc()}


def load_user_rules(enabled_only: bool = True, max_rows: int = 50) -> List[Dict[str, Any]]:
    """
    Load last saved rules from DB.
    """
    if not _db_ok:
        return []

    try:
        _ensure_rules_table()
        df = fetch_table("user_rules")
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return []

        if enabled_only and "enabled" in df.columns:
            df = df[df["enabled"].astype(str).isin(["1", "True", "true"])]

        if "created_at" in df.columns:
            df = df.sort_values("created_at", ascending=False)
        elif "id" in df.columns:
            df = df.sort_values("id", ascending=False)

        df = df.head(int(max_rows or 50))

        out = []
        for _, r in df.iterrows():
            out.append(
                {
                    "id": int(r["id"]) if "id" in df.columns and pd.notna(r["id"]) else None,
                    "title": str(r.get("title", "") or "قاعدة"),
                    "rule_text": str(r.get("rule_text", "") or ""),
                    "enabled": int(r.get("enabled", 1)) if "enabled" in df.columns else 1,
                    "created_at": str(r.get("created_at", "") or ""),
                }
            )
        return out

    except Exception:
        return []


# Optional: external diagnostics if you want to call it later
def self_test() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": AI_ENGINE_VERSION,
        "db_ok": _db_ok,
        "db_err": "" if _db_ok else _db_err,
        "market_data_ok": _md_ok,
        "market_data_err": "" if _md_ok else _md_err,
        "functions": [
            "generate_ai_report",
            "calculate_portfolio_risk_score",
            "run_stress_test",
            "generate_rebalancing_suggestions",
            "save_user_rule",
            "load_user_rules",
        ],
    }
