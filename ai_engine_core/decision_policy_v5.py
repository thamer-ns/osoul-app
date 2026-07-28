"""Final Osoli decision policy v5.

V5 augments the raw report with the Python SC-V90 breakout engine *before* the
proven v4 qualification and geometry gates run.  It then attaches provider
lineage, financial source quality and the latest validated indicator/bot event
as explainable context.  External events never override the native decision.
"""
from __future__ import annotations

import copy
import json
import logging
import math
from typing import Any

import pandas as pd

from .breakout_patterns_v90 import ENGINE_VERSION as BREAKOUT_VERSION
from .breakout_patterns_v90 import analyze_breakout_patterns
from .compass_contract import compare_compass_with_report
from .decision_policy_v4 import enrich_report as _v4_enrich_report
from .reporting_policy_v5 import timeframe_to_interval

LOGGER = logging.getLogger(__name__)
DECISION_ENGINE_VERSION = "5.0"
ANALYSIS_CONTRACT_VERSION = "5.0"


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def _augment_breakouts(
    report: dict[str, Any],
    *,
    symbol: str,
    timeframe: str,
) -> dict[str, Any]:
    output = copy.deepcopy(report)
    if str(output.get("status") or "").lower() == "error" or output.get("error"):
        return output
    interval = timeframe_to_interval(
        str((output.get("engine_meta") or {}).get("interval_used") or timeframe)
    )
    try:
        from market_data import get_chart_history

        frame = get_chart_history(symbol, period=None, interval=interval, years=15 if interval in {"1wk", "1mo"} else 5)
    except Exception:
        LOGGER.exception("Unable to fetch candles for SC-V90 engine")
        frame = pd.DataFrame()
    breakout = analyze_breakout_patterns(
        frame if isinstance(frame, pd.DataFrame) else pd.DataFrame(),
        symbol=symbol,
        timeframe=interval,
    )
    output["breakout_engine"] = breakout
    if not breakout.get("ok"):
        return output

    features = dict(output.get("features") or {})
    features.update(dict(breakout.get("features") or {}))
    output["features"] = features
    reasons = list(output.get("tech_reasons") or [])
    for evidence in breakout.get("evidence") or []:
        text = str(evidence).strip()
        if text and text not in reasons:
            reasons.append(text)
    output["tech_reasons"] = reasons[:20]
    events = list(output.get("signal_events") or [])
    for signal in breakout.get("signals") or []:
        events.append(
            {
                "type": "SC-V90",
                "event": signal.get("kind"),
                "direction": signal.get("direction"),
                "level": signal.get("level"),
                "at": breakout.get("last_closed_bar"),
            }
        )
    output["signal_events"] = events[:20]

    confirmed_count = int((breakout.get("features") or {}).get("breakout_confirmed_count") or 0)
    score = _finite(breakout.get("direction_score"))
    delta = max(-2.5, min(2.5, score / 100.0 * min(2.5, confirmed_count * 1.25)))
    output["tech_score"] = _finite(output.get("tech_score")) + delta
    output["total_score"] = _finite(output.get("tech_score")) + _finite(output.get("fund_score"))
    output["breakout_score_delta"] = round(delta, 3)
    return output


def _attach_external_context(report: dict[str, Any], symbol: str, timeframe: str) -> None:
    try:
        from .external_signal_journal_v5 import latest_external_event, lifecycle_snapshot

        interval = str((report.get("analysis_contract") or {}).get("timeframe") or timeframe).lower()
        snapshot = lifecycle_snapshot(symbol, interval)
        report["external_signal_lifecycle"] = snapshot
        row = latest_external_event(symbol, interval)
        if row and row.get("payload_json"):
            parsed = json.loads(str(row["payload_json"]))
            comparison = compare_compass_with_report(parsed, report)
            report["external_signal_comparison"] = comparison
            report["external_signal_latest"] = parsed
    except Exception:
        LOGGER.debug("External signal context unavailable", exc_info=True)
        report.setdefault("external_signal_lifecycle", {"available": False, "events": 0})


def _attach_financial_lineage(report: dict[str, Any], symbol: str) -> None:
    try:
        from financial_analysis.store import get_stored_financials_df

        frame = get_stored_financials_df(symbol, "Annual")
        attrs = dict(getattr(frame, "attrs", {}) or {}) if isinstance(frame, pd.DataFrame) else {}
        lineage = dict(attrs.get("financial_lineage") or {})
        if lineage:
            report["financial_data_lineage"] = lineage
    except Exception:
        LOGGER.debug("Financial lineage unavailable", exc_info=True)


def _data_reliability(report: dict[str, Any]) -> dict[str, Any]:
    meta = report.get("engine_meta") if isinstance(report.get("engine_meta"), dict) else {}
    price_lineage = meta.get("data_lineage") if isinstance(meta.get("data_lineage"), dict) else {}
    financial_lineage = report.get("financial_data_lineage") if isinstance(report.get("financial_data_lineage"), dict) else {}
    price_score = int(_finite(price_lineage.get("quality_score"), 75 if price_lineage.get("source") else 35))
    financial_quality = financial_lineage.get("quality") if isinstance(financial_lineage.get("quality"), dict) else {}
    financial_score = int(_finite(financial_quality.get("score"), 0))
    fund_reasons = list(report.get("fund_reasons") or [])
    financial_available = bool(financial_lineage) or bool(fund_reasons)
    weights = [(price_score, 0.65)]
    if financial_available:
        weights.append((financial_score, 0.35))
    combined = round(sum(value * weight for value, weight in weights) / sum(weight for _, weight in weights))
    issues: list[str] = []
    if price_score < 60:
        issues.append("جودة بيانات السعر منخفضة")
    if financial_available and financial_score < 55:
        issues.append("القوائم المالية جزئية أو غير مكتملة")
    if bool(price_lineage.get("is_stale")):
        issues.append("بيانات السعر قديمة")
    return {
        "score": max(0, min(100, combined)),
        "price_score": price_score,
        "financial_score": financial_score if financial_available else None,
        "price_source": price_lineage.get("source") or "unknown",
        "financial_source": financial_lineage.get("source") or "unavailable",
        "issues": issues,
        "pass": combined >= 60 and not bool(price_lineage.get("is_stale")),
    }


def _advisor_intelligence(report: dict[str, Any]) -> dict[str, Any]:
    breakout = report.get("breakout_engine") if isinstance(report.get("breakout_engine"), dict) else {}
    external = report.get("external_signal_comparison") if isinstance(report.get("external_signal_comparison"), dict) else {}
    lifecycle = report.get("external_signal_lifecycle") if isinstance(report.get("external_signal_lifecycle"), dict) else {}
    reliability = report.get("data_reliability") if isinstance(report.get("data_reliability"), dict) else {}
    insights: list[str] = []
    cautions: list[str] = []
    confirmed = int((breakout.get("features") or {}).get("breakout_confirmed_count") or 0)
    forming = int((breakout.get("features") or {}).get("breakout_forming_count") or 0)
    if confirmed:
        insights.append(f"محرك SC-V90 داخل أصولي أكد {confirmed} نموذج على إغلاق الشمعة")
    elif forming:
        insights.append(f"يوجد {forming} نموذج اختراق تحت التكوين ولم يتحول إلى دخول")
    if external.get("aligned"):
        insights.append("آخر حدث من المؤشر والبوت متوافق مع اتجاه أصولي")
    for conflict in external.get("conflicts") or []:
        cautions.append(str(conflict))
    if lifecycle.get("available"):
        insights.append(
            f"دورة المؤشر الخارجية: {lifecycle.get('status')} — الحدث {lifecycle.get('event')}"
        )
    cautions.extend(str(item) for item in reliability.get("issues") or [])
    return {
        "headline": str(report.get("recommendation") or "لا توجد توصية"),
        "stage": report.get("analysis_stage"),
        "insights": insights[:8],
        "cautions": cautions[:8],
        "external_decision_effect": "none",
        "native_decision_authority": True,
        "plain_language": True,
    }


def enrich_report(report: Any, *, symbol: str = "", timeframe: str = "1D") -> dict[str, Any]:
    raw = report if isinstance(report, dict) else {}
    augmented = _augment_breakouts(raw, symbol=symbol, timeframe=timeframe)
    enriched = _v4_enrich_report(augmented, symbol=symbol, timeframe=timeframe)
    if str(enriched.get("status") or "").lower() == "error" or enriched.get("error"):
        return enriched

    _attach_external_context(enriched, symbol, timeframe)
    _attach_financial_lineage(enriched, symbol)
    enriched["data_reliability"] = _data_reliability(enriched)
    enriched["advisor_intelligence"] = _advisor_intelligence(enriched)

    contract = dict(enriched.get("analysis_contract") or {})
    contract.update(
        {
            "schema_version": ANALYSIS_CONTRACT_VERSION,
            "decision_version": DECISION_ENGINE_VERSION,
            "breakout_engine": BREAKOUT_VERSION,
            "indicator_integration": "persistent_lifecycle_compare_only",
            "bot_integration": "explicit_secure_forwarding",
            "provider_fusion": "5.0",
            "external_evidence_policy": "compare_never_override_automatically",
        }
    )
    enriched["analysis_contract"] = contract
    decision = enriched.get("decision_engine")
    if isinstance(decision, dict):
        decision["version"] = DECISION_ENGINE_VERSION
        decision["breakout_engine"] = enriched.get("breakout_engine")
        decision["data_reliability"] = enriched.get("data_reliability")
        decision["external_signal_comparison"] = enriched.get("external_signal_comparison")
    meta = dict(enriched.get("engine_meta") or {})
    meta["decision_engine_version"] = DECISION_ENGINE_VERSION
    meta["analysis_contract_version"] = ANALYSIS_CONTRACT_VERSION
    meta["breakout_engine_version"] = BREAKOUT_VERSION
    enriched["engine_meta"] = meta
    return enriched


__all__ = [
    "ANALYSIS_CONTRACT_VERSION",
    "DECISION_ENGINE_VERSION",
    "enrich_report",
]
