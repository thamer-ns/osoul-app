"""Final semantic and risk-integrity policy for decision engine v3.

The base decision engine builds the unified plan. This final policy is deliberately
small and conservative: it prevents generic words such as "watch breakout" or
"near support" from being labelled as a confirmed strong break, and it blocks
plans whose stop distance cannot produce economically meaningful positive levels.
"""
from __future__ import annotations

import math
from typing import Any

from .decision_engine_v3 import (
    _OPPORTUNITY_LABELS,
    _recommendation,
    enrich_report as _base_enrich_report,
)

DECISION_ENGINE_VERSION = "3.1"
_MAX_RISK_TO_ENTRY = 0.35


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _flatten_text(value: Any) -> list[str]:
    output: list[str] = []
    if value is None:
        return output
    if isinstance(value, dict):
        for item in value.values():
            output.extend(_flatten_text(item))
        return output
    if isinstance(value, (list, tuple, set)):
        for item in value:
            output.extend(_flatten_text(item))
        return output
    text = str(value).strip()
    return [text] if text else []


def _evidence(report: dict[str, Any]) -> list[str]:
    return _flatten_text(
        [
            report.get("tech_reasons"),
            report.get("signal_events"),
            report.get("top_evidence"),
        ]
    )


def _contains_any(evidence: list[str], phrases: tuple[str, ...]) -> bool:
    text = " | ".join(evidence).casefold()
    return any(phrase.casefold() in text for phrase in phrases)


def _has_close_confirmed_break(direction: str, evidence: list[str]) -> bool:
    if direction == "buy":
        phrases = (
            "اختراق مقاومة بإغلاق الشمعة",
            "اختراق مؤكد بالإغلاق",
            "bms: كسر قمة",
            "confirmed breakout",
            "close_above",
            "breakout_resistance",
        )
    else:
        phrases = (
            "كسر دعم بإغلاق الشمعة",
            "كسر مؤكد بالإغلاق",
            "bms: كسر قاع",
            "confirmed breakdown",
            "close_below",
            "breakdown_support",
        )
    return _contains_any(evidence, phrases)


def _fallback_opportunity(evidence: list[str]) -> str:
    if _contains_any(
        evidence,
        (
            "macd",
            "rsi",
            "زخم",
            "momentum",
            "divergence",
            "دايفرجنس",
            "golden cross",
            "death cross",
            "sma cross",
        ),
    ):
        return "MOMENTUM_SHIFT"
    return "STRUCTURE_SETUP"


def _apply_opportunity_integrity(report: dict[str, Any]) -> None:
    opportunity = str(report.get("opportunity_type") or "")
    if opportunity not in {"STRONG_BREAKOUT", "STRONG_BREAKDOWN"}:
        return

    direction = str(report.get("direction") or "neutral").lower()
    evidence = _evidence(report)
    if _has_close_confirmed_break(direction, evidence):
        return

    replacement = _fallback_opportunity(evidence)
    label = _OPPORTUNITY_LABELS[replacement]
    report["opportunity_type"] = replacement
    report["opportunity_label"] = label

    decision = report.get("decision_engine")
    if isinstance(decision, dict):
        decision["opportunity_type"] = replacement
        decision["opportunity_label"] = label
        decision.setdefault("integrity_notes", []).append(
            "خُفّض تصنيف الاختراق/الكسر لعدم وجود دليل صريح على تأكيد الإغلاق."
        )

    status = str(report.get("lifecycle_status") or "NO_SETUP")
    recommendation, color, strategy = _recommendation(direction, status, replacement)
    report["recommendation"] = recommendation
    report["color"] = color
    report["strategy"] = strategy


def _plan_is_extreme(plan: dict[str, Any], direction: str) -> bool:
    entry = _finite(plan.get("entry"))
    stop = _finite(plan.get("stop"))
    if entry is None or stop is None or entry <= 0 or stop <= 0:
        return False

    risk = abs(entry - stop)
    if risk <= 0:
        return True
    if risk / entry > _MAX_RISK_TO_ENTRY:
        return True

    if direction == "sell":
        target1 = _finite(plan.get("target1"))
        target2 = _finite(plan.get("target2"))
        target3 = _finite(plan.get("target3"))
        if None in {target1, target2, target3}:
            return True
        if not (0 < target3 < target2 < target1 < entry < stop):
            return True
    elif direction == "buy":
        target1 = _finite(plan.get("target1"))
        target2 = _finite(plan.get("target2"))
        target3 = _finite(plan.get("target3"))
        if None in {target1, target2, target3}:
            return True
        if not (0 < stop < entry < target1 < target2 < target3):
            return True
    return False


def _apply_plan_integrity(report: dict[str, Any]) -> None:
    plan = report.get("risk_plan")
    if not isinstance(plan, dict) or plan.get("entry") is None:
        return

    direction = str(report.get("direction") or plan.get("direction") or "neutral").lower()
    if direction not in {"buy", "sell"} or not _plan_is_extreme(plan, direction):
        return

    reason = "مسافة الوقف أو ترتيب الأهداف غير صالح اقتصاديًا؛ أوقفت الخطة بدل تضييق الوقف أو اختراع أهداف."
    report["lifecycle_status"] = "BLOCKED"
    plan["status"] = "BLOCKED"
    plan["target1"] = None
    plan["target2"] = None
    plan["target3"] = None
    plan["rr"] = None
    report["targets"] = []

    decision = report.get("decision_engine")
    if isinstance(decision, dict):
        decision["status"] = "BLOCKED"
        blockers = decision.setdefault("blockers", [])
        if reason not in blockers:
            blockers.append(reason)
        decision["plan"] = plan
        decision.setdefault("integrity_notes", []).append(reason)

    top_risks = report.get("top_risks")
    top_risks = list(top_risks) if isinstance(top_risks, list) else []
    if reason not in top_risks:
        top_risks.insert(0, reason)
    report["top_risks"] = top_risks[:12]

    opportunity = str(report.get("opportunity_type") or "STRUCTURE_SETUP")
    recommendation, color, _ = _recommendation(direction, "BLOCKED", opportunity)
    report["recommendation"] = recommendation
    report["color"] = color
    report["strategy"] = reason


def enrich_report(
    report: Any,
    *,
    symbol: str = "",
    timeframe: str = "1D",
) -> dict[str, Any]:
    """Build the base decision and enforce final semantic/risk integrity."""
    enriched = _base_enrich_report(report, symbol=symbol, timeframe=timeframe)
    if str(enriched.get("status") or "").lower() == "error":
        return enriched

    _apply_opportunity_integrity(enriched)
    _apply_plan_integrity(enriched)

    decision = enriched.get("decision_engine")
    if isinstance(decision, dict):
        decision["version"] = DECISION_ENGINE_VERSION
        decision["semantic_confirmation_policy"] = "explicit_close_evidence"
    meta = enriched.get("engine_meta")
    meta = dict(meta) if isinstance(meta, dict) else {}
    meta["decision_engine_version"] = DECISION_ENGINE_VERSION
    enriched["engine_meta"] = meta
    return enriched
