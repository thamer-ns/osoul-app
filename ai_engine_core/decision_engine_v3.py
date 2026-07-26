"""Central decision layer for Osoli reports.

This module adapts the useful, transport-independent ideas from the market bot
into the Streamlit application: one final decision, close-confirmed plans,
opportunity classification, actionability gates, deterministic plan identity,
and explicit invalidation/expiry rules.

It intentionally consumes the already-computed report and never fetches market
data. This keeps UI reruns fast and avoids duplicating the technical engine.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from copy import deepcopy
from typing import Any, Iterable

DECISION_ENGINE_VERSION = "3.0"
LOGGER = logging.getLogger(__name__)

_ACTIONABLE_MIN_CONFIDENCE = 60.0
_DIRECTION_THRESHOLD = 15.0

_OPPORTUNITY_LABELS = {
    "ULTIMATE_BUY": "فرصة شراء فائقة التوافق",
    "ULTIMATE_SELL": "إشارة هابطة فائقة التوافق",
    "STRONG_BREAKOUT": "اختراق قوي مؤكد بالإغلاق",
    "STRONG_BREAKDOWN": "كسر قوي مؤكد بالإغلاق",
    "LIQUIDITY_RECLAIM": "استرداد سيولة بعد اختراق زائف",
    "LIQUIDITY_REJECTION": "رفض سيولة بعد اختراق زائف",
    "MOMENTUM_SHIFT": "تحول زخم",
    "STRUCTURE_SETUP": "فرصة هيكلية",
    "NO_SETUP": "لا توجد فرصة مكتملة",
}

_TIMEFRAME_EXPIRY_BARS = {
    "1m": 24,
    "5m": 18,
    "15m": 16,
    "30m": 14,
    "60m": 12,
    "1h": 12,
    "4h": 10,
    "1d": 10,
    "1w": 8,
    "1wk": 8,
    "1mo": 6,
}


def _finite(value: Any, default: float | None = None) -> float | None:
    """Return a finite float without treating NaN/inf as valid market data."""
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def _clip(value: Any, low: float, high: float, default: float = 0.0) -> float:
    number = _finite(value, default)
    return max(low, min(high, float(number if number is not None else default)))


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return bool(int(value))
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "pass", "passed", "ok", "aligned"}:
        return True
    if text in {"0", "false", "no", "fail", "failed", "blocked", "misaligned"}:
        return False
    return None


def _normalise_timeframe(value: Any) -> str:
    raw = str(value or "1d").strip().lower()
    aliases = {
        "d": "1d",
        "day": "1d",
        "daily": "1d",
        "1day": "1d",
        "w": "1wk",
        "week": "1wk",
        "weekly": "1wk",
        "1w": "1wk",
        "m": "1mo",
        "month": "1mo",
        "monthly": "1mo",
        "1mth": "1mo",
        "h": "1h",
    }
    return aliases.get(raw, raw)


def _text_items(*values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()

    def visit(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for item in value.values():
                visit(item)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)
            return
        text = str(value).strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)

    for value in values:
        visit(value)
    return output


def _contains_any(items: Iterable[str], needles: Iterable[str]) -> bool:
    haystack = " | ".join(str(item).casefold() for item in items)
    return any(str(needle).casefold() in haystack for needle in needles)


def _gate_snapshot(report: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
    calibration = report.get("calibration")
    calibration = calibration if isinstance(calibration, dict) else {}

    liquidity = calibration.get("liquidity_gate")
    liquidity = liquidity if isinstance(liquidity, dict) else {}
    mtf = calibration.get("multi_timeframe")
    mtf = mtf if isinstance(mtf, dict) else {}
    risk_gates = report.get("risk_gates")
    risk_gates = risk_gates if isinstance(risk_gates, dict) else {}

    liquidity_pass = _bool_or_none(liquidity.get("pass"))
    if liquidity_pass is None:
        liquidity_pass = _bool_or_none(features.get("liquidity_pass"))

    mtf_applied = _bool_or_none(mtf.get("applied"))
    if mtf_applied is None:
        mtf_applied = _bool_or_none(features.get("mtf_applied"))
    mtf_aligned = _bool_or_none(mtf.get("aligned"))
    if mtf_aligned is None and mtf_applied:
        mtf_aligned = _bool_or_none(features.get("mtf_aligned"))

    dq_pass = _bool_or_none(features.get("dq_pass"))
    risk_pass = _bool_or_none(risk_gates.get("pass"))
    if risk_pass is None:
        risk_pass = True

    return {
        "risk_pass": risk_pass,
        "risk_reasons": _text_items(risk_gates.get("reasons")),
        "liquidity_pass": liquidity_pass,
        "mtf_applied": bool(mtf_applied),
        "mtf_aligned": mtf_aligned,
        "data_quality_pass": dq_pass,
    }


def _direction(report: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
    total_score = _clip(report.get("total_score"), -20.0, 20.0)
    base_direction = _clip(total_score * 8.0, -100.0, 100.0)
    advanced_direction = _finite(features.get("adv_direction_score"))
    advanced_confidence = _clip(features.get("adv_confidence"), 0.0, 100.0, default=0.0)
    agreement = _clip(features.get("adv_agreement"), 0.0, 1.0, default=0.0)

    if advanced_direction is None or advanced_confidence <= 0:
        combined = base_direction
        advanced_weight = 0.0
    else:
        advanced_weight = 0.15 + 0.15 * (advanced_confidence / 100.0)
        combined = (1.0 - advanced_weight) * base_direction + advanced_weight * advanced_direction

    contradiction = (
        abs(base_direction) >= _DIRECTION_THRESHOLD
        and advanced_direction is not None
        and abs(advanced_direction) >= _DIRECTION_THRESHOLD
        and base_direction * advanced_direction < 0
    )

    combined = _clip(combined, -100.0, 100.0)
    direction = "buy" if combined >= _DIRECTION_THRESHOLD else "sell" if combined <= -_DIRECTION_THRESHOLD else "neutral"
    return {
        "direction": direction,
        "direction_score": round(combined, 2),
        "base_direction_score": round(base_direction, 2),
        "advanced_direction_score": round(advanced_direction, 2) if advanced_direction is not None else None,
        "advanced_weight": round(advanced_weight, 3),
        "agreement": round(agreement, 3),
        "contradiction": contradiction,
    }


def _classify_opportunity(
    direction: str,
    confidence: float,
    direction_info: dict[str, Any],
    gates: dict[str, Any],
    features: dict[str, Any],
    evidence: list[str],
) -> str:
    if direction == "neutral":
        return "NO_SETUP"

    mtf_ok = not gates["mtf_applied"] or gates["mtf_aligned"] is not False
    execution_ok = (
        gates["risk_pass"] is not False
        and gates["liquidity_pass"] is not False
        and gates["data_quality_pass"] is not False
        and mtf_ok
        and not direction_info["contradiction"]
    )
    agreement = _finite(direction_info.get("agreement"), 0.0) or 0.0

    if confidence >= 78 and execution_ok and agreement >= 0.45:
        return "ULTIMATE_BUY" if direction == "buy" else "ULTIMATE_SELL"

    if direction == "buy" and int(_finite(features.get("liq_sweep_low"), 0.0) or 0) == 1:
        return "LIQUIDITY_RECLAIM"
    if direction == "sell" and int(_finite(features.get("liq_sweep_high"), 0.0) or 0) == 1:
        return "LIQUIDITY_REJECTION"

    breakout_words = ("اختراق", "breakout", "bms", "close_above", "مقاومة")
    breakdown_words = ("كسر", "breakdown", "close_below", "دعم")
    if direction == "buy" and _contains_any(evidence, breakout_words):
        return "STRONG_BREAKOUT"
    if direction == "sell" and _contains_any(evidence, breakdown_words):
        return "STRONG_BREAKDOWN"

    momentum_words = (
        "macd",
        "rsi",
        "زخم",
        "momentum",
        "divergence",
        "دايفرجنس",
        "golden cross",
        "death cross",
        "sma cross",
    )
    if _contains_any(evidence, momentum_words):
        return "MOMENTUM_SHIFT"
    return "STRUCTURE_SETUP"


def _calibrate_confidence(
    report: dict[str, Any],
    direction_info: dict[str, Any],
    gates: dict[str, Any],
) -> tuple[float, list[str]]:
    confidence = _clip(report.get("confidence"), 0.0, 100.0)
    penalties: list[str] = []

    if direction_info["direction"] == "neutral":
        confidence = min(confidence, 54.0)
        penalties.append("اتجاه المحركات غير حاسم")
    if direction_info["contradiction"]:
        confidence -= 18.0
        penalties.append("تعارض اتجاه المحرك الأساسي مع المؤشرات المتقدمة")
    if gates["risk_pass"] is False:
        confidence -= 18.0
        penalties.append("بوابات المخاطر لم تجتز")
    if gates["liquidity_pass"] is False:
        confidence -= 20.0
        penalties.append("السيولة لا تسمح بتنفيذ موثوق")
    if gates["mtf_applied"] and gates["mtf_aligned"] is False:
        confidence -= 12.0
        penalties.append("تعارض الفاصل الحالي مع الفاصل الأعلى")
    if gates["data_quality_pass"] is False:
        confidence -= 10.0
        penalties.append("جودة البيانات المالية غير كافية")

    context = report.get("learning_context")
    context = context if isinstance(context, dict) else {}
    market = str(context.get("market_trend") or "").strip().lower()
    direction = direction_info["direction"]
    if (direction == "buy" and market in {"bear", "bearish"}) or (
        direction == "sell" and market in {"bull", "bullish"}
    ):
        confidence -= 8.0
        penalties.append("اتجاه الفرصة يعاكس اتجاه السوق العام")

    rows = _finite((report.get("engine_meta") or {}).get("rows") if isinstance(report.get("engine_meta"), dict) else None)
    if rows is not None and rows < 120:
        confidence -= 6.0
        penalties.append("التغطية التاريخية محدودة")

    return round(_clip(confidence, 0.0, 100.0), 2), penalties


def _valid_directional_level(direction: str, entry: float, stop: float | None) -> bool:
    if stop is None or stop <= 0:
        return False
    return stop < entry if direction == "buy" else stop > entry


def _build_plan(
    report: dict[str, Any],
    symbol: str,
    timeframe: str,
    direction: str,
    opportunity_type: str,
    confidence: float,
    status: str,
) -> dict[str, Any]:
    features = report.get("features")
    features = features if isinstance(features, dict) else {}
    existing = report.get("risk_plan")
    existing = existing if isinstance(existing, dict) else {}

    entry = _finite(existing.get("entry"))
    if entry is None:
        entry = _finite(features.get("close"))
    if entry is None or entry <= 0 or direction == "neutral":
        return {
            "plan_id": None,
            "direction": direction,
            "status": status,
            "entry": None,
            "entry_low": None,
            "entry_high": None,
            "stop": None,
            "target1": None,
            "target2": None,
            "target3": None,
            "rr": None,
            "invalidation": "لا توجد خطة اتجاهية مكتملة",
            "expiry_bars": _TIMEFRAME_EXPIRY_BARS.get(timeframe, 10),
            "confirmation": "candle_close",
        }

    atr = _finite(features.get("atr14"))
    if atr is None or atr <= 0:
        existing_stop = _finite(existing.get("stop"))
        atr = abs(entry - existing_stop) / 2.0 if existing_stop is not None else entry * 0.015
    atr = max(float(atr), entry * 0.0025)

    stop = _finite(existing.get("stop"))
    if not _valid_directional_level(direction, entry, stop):
        stop = entry - 1.8 * atr if direction == "buy" else entry + 1.8 * atr
    stop = max(stop, entry * 0.01)

    risk = abs(entry - stop)
    zone_half_width = max(0.15 * atr, entry * 0.0015)
    entry_low = max(0.01, entry - zone_half_width)
    entry_high = entry + zone_half_width

    if direction == "buy":
        target1 = entry + 1.5 * risk
        target2 = entry + 2.2 * risk
        target3 = entry + 3.0 * risk
        invalidation = f"إغلاق شمعة مؤكدة دون {stop:.4f}"
    else:
        target1 = max(0.01, entry - 1.5 * risk)
        target2 = max(0.01, entry - 2.2 * risk)
        target3 = max(0.01, entry - 3.0 * risk)
        invalidation = f"إغلاق شمعة مؤكدة فوق {stop:.4f}"

    last_bar = ""
    engine_meta = report.get("engine_meta")
    if isinstance(engine_meta, dict):
        last_bar = str(engine_meta.get("last_bar") or "")

    fingerprint_payload = {
        "symbol": str(symbol or ""),
        "timeframe": timeframe,
        "direction": direction,
        "opportunity_type": opportunity_type,
        "entry": round(entry, 4),
        "stop": round(stop, 4),
        "last_bar": last_bar,
        "engine": DECISION_ENGINE_VERSION,
    }
    fingerprint = json.dumps(fingerprint_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    plan_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:20]

    return {
        "plan_id": plan_id,
        "direction": direction,
        "status": status,
        "entry": round(entry, 4),
        "entry_low": round(entry_low, 4),
        "entry_high": round(entry_high, 4),
        "stop": round(stop, 4),
        "target1": round(target1, 4),
        "target2": round(target2, 4),
        "target3": round(target3, 4),
        "rr": 3.0,
        "risk_per_unit": round(risk, 4),
        "invalidation": invalidation,
        "expiry_bars": _TIMEFRAME_EXPIRY_BARS.get(timeframe, 10),
        "confirmation": "candle_close",
        "confidence": round(confidence, 2),
    }


def _lifecycle_status(
    direction: str,
    confidence: float,
    gates: dict[str, Any],
    opportunity_type: str,
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if direction == "neutral" or opportunity_type == "NO_SETUP":
        return "NO_SETUP", ["لا يوجد اتجاه حاسم"]
    if gates["risk_pass"] is False:
        blockers.extend(gates["risk_reasons"] or ["بوابات المخاطر رفضت الخطة"])
    if gates["liquidity_pass"] is False:
        blockers.append("السيولة غير كافية")
    if gates["data_quality_pass"] is False and opportunity_type in {"ULTIMATE_BUY", "ULTIMATE_SELL"}:
        blockers.append("جودة البيانات لا تسمح بتصنيف فائق")
    if blockers:
        return "BLOCKED", blockers
    if confidence >= _ACTIONABLE_MIN_CONFIDENCE:
        return "ACTIONABLE", []
    return "HEADS_UP", ["الثقة دون حد التنفيذ؛ الخطة للمراقبة فقط"]


def _recommendation(direction: str, status: str, opportunity_type: str) -> tuple[str, str, str]:
    label = _OPPORTUNITY_LABELS.get(opportunity_type, opportunity_type)
    if status == "ACTIONABLE" and direction == "buy":
        return f"✅ {label}", "#198754", "خطة اتجاهية مؤكدة بالإغلاق واجتازت بوابات التنفيذ."
    if status == "ACTIONABLE" and direction == "sell":
        return f"⛔ {label}", "#dc3545", "إشارة هابطة مؤكدة بالإغلاق؛ تستخدم للخروج أو التحوط وفق السوق."
    if status == "HEADS_UP":
        direction_text = "صاعدة" if direction == "buy" else "هابطة"
        return f"👀 مراقبة فرصة {direction_text}", "#f59e0b", "الفرصة غير قابلة للتنفيذ بعد؛ انتظر ارتفاع الثقة أو اكتمال التأكيد."
    if status == "BLOCKED":
        return "⚠️ إشارة موجودة لكن التنفيذ محظور", "#f59e0b", "ظهرت إشارة اتجاهية، لكن إحدى بوابات المخاطر أو السيولة منعتها."
    return "⚖️ لا توجد فرصة مكتملة", "#6c757d", "لا يوجد توافق اتجاهي كافٍ لبناء خطة قابلة للتنفيذ."


def _safe_error_report(report: dict[str, Any], symbol: str, timeframe: str) -> dict[str, Any]:
    internal_error = report.get("__error__")
    internal_trace = report.get("__trace__")
    error_id = hashlib.sha256(
        f"{symbol}|{timeframe}|{type(internal_error).__name__}|{internal_error}".encode("utf-8", errors="replace")
    ).hexdigest()[:12]
    if internal_error or internal_trace:
        LOGGER.error(
            "AI report failure id=%s symbol=%s timeframe=%s error=%r",
            error_id,
            symbol,
            timeframe,
            internal_error,
        )
    safe = {
        key: deepcopy(value)
        for key, value in report.items()
        if key not in {"__trace__", "__error__"}
    }
    safe.update(
        {
            "status": "error",
            "__error__": f"تعذر إكمال التحليل بأمان. رقم التتبع: {error_id}",
            "error_id": error_id,
            "recommendation": "غير متاح",
            "strategy": "حدث خطأ داخلي وسُجل للتشخيص دون عرض تفاصيل حساسة.",
            "confidence": 0,
            "decision_engine": {
                "version": DECISION_ENGINE_VERSION,
                "status": "ERROR",
                "confirmation": "candle_close",
            },
        }
    )
    return safe


def enrich_report(
    report: Any,
    *,
    symbol: str = "",
    timeframe: str = "1D",
) -> dict[str, Any]:
    """Return one sanitized, execution-aware decision for all presentation layers."""
    if not isinstance(report, dict):
        report = {"status": "error", "__error__": "invalid_report_type"}

    if report.get("__error__") or report.get("__trace__") or str(report.get("status") or "").lower() == "error":
        return _safe_error_report(report, str(symbol), str(timeframe))

    enriched: dict[str, Any] = deepcopy(report)
    features = enriched.get("features")
    features = features if isinstance(features, dict) else {}
    enriched["features"] = features

    tf = _normalise_timeframe(
        (enriched.get("engine_meta") or {}).get("interval_used")
        if isinstance(enriched.get("engine_meta"), dict)
        else timeframe
    )
    if not tf:
        tf = _normalise_timeframe(timeframe)

    gates = _gate_snapshot(enriched, features)
    direction_info = _direction(enriched, features)
    confidence, penalties = _calibrate_confidence(enriched, direction_info, gates)

    evidence = _text_items(
        enriched.get("tech_reasons"),
        enriched.get("fund_reasons"),
        enriched.get("signal_events"),
        (enriched.get("explainability") or {}).get("positives")
        if isinstance(enriched.get("explainability"), dict)
        else None,
    )
    opportunity_type = _classify_opportunity(
        direction_info["direction"],
        confidence,
        direction_info,
        gates,
        features,
        evidence,
    )
    status, blockers = _lifecycle_status(
        direction_info["direction"],
        confidence,
        gates,
        opportunity_type,
    )
    plan = _build_plan(
        enriched,
        str(symbol or enriched.get("symbol") or ""),
        tf,
        direction_info["direction"],
        opportunity_type,
        confidence,
        status,
    )

    recommendation, color, strategy = _recommendation(
        direction_info["direction"],
        status,
        opportunity_type,
    )
    enriched["recommendation"] = recommendation
    enriched["color"] = color
    enriched["strategy"] = strategy
    enriched["confidence"] = int(round(confidence))
    enriched["confidence_label"] = (
        "مرتفعة" if confidence >= 75 else "متوسطة" if confidence >= 55 else "منخفضة"
    )
    enriched["direction"] = direction_info["direction"]
    enriched["direction_score"] = direction_info["direction_score"]
    enriched["opportunity_type"] = opportunity_type
    enriched["opportunity_label"] = _OPPORTUNITY_LABELS[opportunity_type]
    enriched["lifecycle_status"] = status
    enriched["risk_plan"] = plan

    if plan.get("entry") is not None:
        enriched["entry"] = {
            "entry_zone": f"{plan['entry_low']:.4f} – {plan['entry_high']:.4f}",
            "price": plan["entry"],
            "confirmation": "إغلاق الشمعة",
        }
        enriched["risk"] = {
            "stop": plan["stop"],
            "invalidation": plan["stop"],
            "invalidation_rule": plan["invalidation"],
            "rr": plan["rr"],
            "stop_confirmation": "إغلاق الشمعة",
        }
        enriched["targets"] = [
            {"name": "T1", "price": plan["target1"], "note": "1.5R"},
            {"name": "T2", "price": plan["target2"], "note": "2.2R"},
            {"name": "T3", "price": plan["target3"], "note": "3.0R"},
        ]

    decision_evidence = [
        f"تصنيف الفرصة: {_OPPORTUNITY_LABELS[opportunity_type]}",
        f"حالة الخطة: {status}",
        f"درجة الاتجاه: {direction_info['direction_score']:.2f}/100",
        "الاختراق والكسر والوقف لا تُعتمد إلا بعد إغلاق الشمعة.",
    ]
    top_evidence = _text_items(decision_evidence, enriched.get("top_evidence"), evidence)
    top_risks = _text_items(blockers, penalties, enriched.get("top_risks"))
    enriched["top_evidence"] = top_evidence[:12]
    enriched["top_risks"] = top_risks[:12]

    decision_payload = {
        "version": DECISION_ENGINE_VERSION,
        "status": status,
        "opportunity_type": opportunity_type,
        "opportunity_label": _OPPORTUNITY_LABELS[opportunity_type],
        "direction": direction_info["direction"],
        "direction_score": direction_info["direction_score"],
        "core_direction_score": direction_info["base_direction_score"],
        "advanced_direction_score": direction_info["advanced_direction_score"],
        "contradiction": direction_info["contradiction"],
        "confidence": round(confidence, 2),
        "confidence_penalties": penalties,
        "blockers": blockers,
        "gates": gates,
        "plan": plan,
        "confirmation": "candle_close",
        "future_transitions": {
            "T1": "عند إغلاق/تداول السعر عند الهدف الأول وفق بيانات المتابعة",
            "T2": "بعد تحقق T1 ثم الوصول للهدف الثاني",
            "T3": "اكتمال الخطة عند الهدف الثالث",
            "INVALIDATED": plan.get("invalidation"),
            "EXPIRED": f"بعد {plan.get('expiry_bars')} شمعة دون تفعيل/تقدم",
        },
        "source_policy": "single_pass_existing_report",
    }
    enriched["decision_engine"] = decision_payload

    meta = enriched.get("engine_meta")
    meta = dict(meta) if isinstance(meta, dict) else {}
    meta["decision_engine_version"] = DECISION_ENGINE_VERSION
    meta["decision_confirmation"] = "candle_close"
    meta["decision_status"] = status
    meta["plan_id"] = plan.get("plan_id")
    enriched["engine_meta"] = meta
    return enriched
