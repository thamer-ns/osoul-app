"""Final Osoli decision policy aligned with SC-V94.7 / SC-FXM-V18.8.

Osoli's native schools remain the decision authority.  The current SC feature
pack is the execution-consistency gate and supplies side-safe cluster-first
stop/target geometry only when directions agree.
"""
from __future__ import annotations

import copy
import math
from typing import Any

from .decision_policy_v4 import enrich_report as _v4_enrich_report
from .decision_policy_v5 import (
    _advisor_intelligence,
    _attach_external_context,
    _attach_financial_lineage,
    _data_reliability,
)
from .decision_policy_v5 import enrich_report as _v5_enrich_report
from .sc_feature_pack_v925 import SC_INDICATOR_CONTRACT

DECISION_ENGINE_VERSION = "6.1"
ANALYSIS_CONTRACT_VERSION = "6.1"
_CURRENT_INDICATOR_CONTRACT = SC_INDICATOR_CONTRACT
_COMPATIBLE_INDICATOR_CONTRACTS = {
    SC_INDICATOR_CONTRACT,
    "SC-V92.5/SC-FXM-V16",
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _current_pack(report: Any) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    value = report.get("sc_feature_pack")
    pack = value if isinstance(value, dict) else {}
    return (
        pack
        if pack.get("ok")
        and str(pack.get("indicator_contract") or "")
        in _COMPATIBLE_INDICATOR_CONTRACTS
        else {}
    )


def _base_enrich(
    report: Any,
    *,
    symbol: str,
    timeframe: str,
) -> dict[str, Any]:
    """Run one decision path; do not mix old and current SC contracts."""
    if not _current_pack(report):
        return _v5_enrich_report(report, symbol=symbol, timeframe=timeframe)

    enriched = _v4_enrich_report(report, symbol=symbol, timeframe=timeframe)
    if str(enriched.get("status") or "").lower() == "error" or enriched.get(
        "error"
    ):
        return enriched
    _attach_external_context(enriched, symbol, timeframe)
    _attach_financial_lineage(enriched, symbol)
    enriched["data_reliability"] = _data_reliability(enriched)
    enriched["advisor_intelligence"] = _advisor_intelligence(enriched)
    meta = dict(enriched.get("engine_meta") or {})
    meta["legacy_sc_v91_skipped"] = True
    meta["legacy_sc_v91_reason"] = "superseded_by_sc_v947_feature_pack"
    enriched["engine_meta"] = meta
    return enriched


def _native_direction(report: dict[str, Any]) -> int:
    candidates = [
        report.get("direction"),
        (report.get("risk_plan") or {}).get("direction")
        if isinstance(report.get("risk_plan"), dict)
        else None,
        (report.get("decision_engine") or {}).get("direction")
        if isinstance(report.get("decision_engine"), dict)
        else None,
        (report.get("school_consensus") or {}).get("direction")
        if isinstance(report.get("school_consensus"), dict)
        else None,
    ]
    for value in candidates:
        if isinstance(value, (int, float)) and int(value) in {-1, 1}:
            return int(value)
        text = str(value or "").strip().lower()
        if text in {"buy", "long", "bullish", "شراء", "صاعد"}:
            return 1
        if text in {"sell", "short", "bearish", "بيع", "هابط"}:
            return -1
    return 0


def _downgrade(report: dict[str, Any], reason: str) -> None:
    if str(report.get("lifecycle_status") or "") != "ACTIONABLE":
        return
    report["lifecycle_status"] = "HEADS_UP"
    report["analysis_stage"] = "قرب الدخول"
    report["recommendation"] = "👀 مراقبة — تعارض مع عقد SC‑V94.7"
    report["color"] = "#f59e0b"
    plan = report.get("risk_plan")
    if isinstance(plan, dict):
        plan["status"] = "HEADS_UP"
    decision = report.get("decision_engine")
    if isinstance(decision, dict):
        decision["status"] = "HEADS_UP"
        blockers = decision.setdefault("blockers", [])
        if reason not in blockers:
            blockers.append(reason)
    risks = list(report.get("top_risks") or [])
    if reason not in risks:
        risks.insert(0, reason)
    report["top_risks"] = risks[:12]
    report["strategy"] = reason


def _sc_geometry(plan: dict[str, Any]) -> dict[str, Any]:
    entry = _finite(plan.get("entry"))
    stop = _finite(plan.get("stop"))
    targets = [_finite(value) for value in plan.get("targets") or []]
    direction = (
        1
        if entry is not None and stop is not None and stop < entry
        else -1
        if entry is not None and stop is not None and stop > entry
        else 0
    )
    issues: list[str] = []
    ratios: list[float] = []
    if entry is None or stop is None or direction == 0:
        issues.append("خطة SC تفتقد دخولًا أو وقفًا صحيحًا")
        return {
            "valid": False,
            "complete": False,
            "issues": issues,
            "target_r": [],
        }
    risk = abs(entry - stop)
    for index, target in enumerate(targets, start=1):
        if target is None or (
            direction > 0 and target <= entry
        ) or (
            direction < 0 and target >= entry
        ):
            issues.append(f"هدف SC رقم {index} في جهة غير صحيحة")
            continue
        ratios.append(round(abs(target - entry) / risk, 3))
    if len(targets) not in {1, 2, 3}:
        issues.append("عدد أهداف SC يجب أن يكون بين 1 و3")
    if ratios and ratios[0] < (
        0.75 if plan.get("short_plan") else 1.0
    ) - 1e-9:
        issues.append("العائد الأول أقل من حد خطة SC")
    return {
        "valid": not issues,
        "complete": not issues,
        "issues": issues,
        "risk_per_unit": round(risk, 8),
        "risk_pct": round(risk / entry * 100.0, 4),
        "risk_atr": plan.get("risk_atr"),
        "target_r": ratios,
        "target_count": len(targets),
        "short_plan": bool(plan.get("short_plan")),
        "method": plan.get("method"),
    }


def _apply_sc_plan(
    report: dict[str, Any],
    sc_plan: dict[str, Any],
    direction: int,
) -> None:
    targets = [_finite(item) for item in sc_plan.get("targets") or []]
    targets = [item for item in targets if item is not None]
    plan = report.get("risk_plan")
    if not isinstance(plan, dict):
        plan = {}
    plan.update(
        {
            "direction": "buy" if direction > 0 else "sell",
            "entry": _finite(sc_plan.get("entry")),
            "stop": _finite(sc_plan.get("stop")),
            "target1": targets[0] if len(targets) >= 1 else None,
            "target2": targets[1] if len(targets) >= 2 else None,
            "target3": targets[2] if len(targets) >= 3 else None,
            "target_count": len(targets),
            "target_sources": list(sc_plan.get("target_sources") or []),
            "stop_source": sc_plan.get("stop_source"),
            "short_plan": bool(sc_plan.get("short_plan")),
            "risk_atr": sc_plan.get("risk_atr"),
            "first_rr": sc_plan.get("first_rr"),
            "method": sc_plan.get("method"),
            "post_target1_trail": copy.deepcopy(
                sc_plan.get("post_target1_trail") or {}
            ),
            "status": report.get("lifecycle_status"),
        }
    )
    report["risk_plan"] = plan
    report["plan_geometry"] = _sc_geometry(sc_plan)
    decision = report.get("decision_engine")
    if isinstance(decision, dict):
        decision["plan_geometry"] = report["plan_geometry"]
        decision["risk_plan"] = copy.deepcopy(plan)


def _support_resistance_integrity(pack: dict[str, Any]) -> tuple[bool, str]:
    integrity = pack.get("integrity")
    if not isinstance(integrity, dict):
        return False, "عقد SC لا يحتوي فحص سلامة المستويات"
    if not integrity.get("ok"):
        issues = ", ".join(str(item) for item in integrity.get("issues") or [])
        return False, f"فشل فحص سلامة الدعم والمقاومة: {issues or 'غير محدد'}"
    return True, ""


def enrich_report(
    report: Any,
    *,
    symbol: str = "",
    timeframe: str = "1D",
) -> dict[str, Any]:
    enriched = _base_enrich(report, symbol=symbol, timeframe=timeframe)
    if str(enriched.get("status") or "").lower() == "error" or enriched.get(
        "error"
    ):
        return enriched
    pack_value = enriched.get("sc_feature_pack")
    pack = pack_value if isinstance(pack_value, dict) else {}
    decision_summary: dict[str, Any] = {
        "available": bool(pack.get("ok")),
        "contract": _CURRENT_INDICATOR_CONTRACT,
        "native_decision_authority": True,
        "plan_replaced": False,
        "blocker": "",
    }
    if pack.get("ok"):
        native = _native_direction(enriched)
        sc_direction = int(pack.get("direction") or 0)
        veto_value = pack.get("opposition_veto")
        veto = veto_value if isinstance(veto_value, dict) else {}
        plan_value = pack.get("risk_plan")
        sc_plan = plan_value if isinstance(plan_value, dict) else {}
        lifecycle = str(enriched.get("lifecycle_status") or "")
        integrity_ok, integrity_reason = _support_resistance_integrity(pack)
        blocker = ""
        if lifecycle == "ACTIONABLE" and not integrity_ok:
            blocker = integrity_reason
        elif lifecycle == "ACTIONABLE" and veto.get("blocked"):
            blocker = (
                "كلاستر دعم/مقاومة حالي يعارض الخطة حتى كسره "
                "بإغلاق وتحول دوره"
            )
        elif lifecycle == "ACTIONABLE" and not pack.get("qualified"):
            blocker = "لم يكتمل توافق SC‑V94.7 على إغلاق الشمعة"
        elif (
            lifecycle == "ACTIONABLE"
            and native
            and sc_direction
            and native != sc_direction
        ):
            blocker = "اتجاه أصولي يخالف اتجاه SC‑V94.7 المؤكد"
        elif lifecycle == "ACTIONABLE" and not sc_plan.get("valid"):
            blocker = "هندسة SC‑V94.7 للوقف والأهداف غير قابلة للتنفيذ"
        if blocker:
            _downgrade(enriched, blocker)
            decision_summary["blocker"] = blocker
        elif (
            lifecycle == "ACTIONABLE"
            and native == sc_direction
            and sc_plan.get("valid")
            and integrity_ok
        ):
            _apply_sc_plan(enriched, sc_plan, native)
            decision_summary["plan_replaced"] = True
        decision_summary.update(
            {
                "native_direction": native,
                "sc_direction": sc_direction,
                "qualified": bool(pack.get("qualified")),
                "event": pack.get("event_code"),
                "confidence": int(pack.get("confidence") or 0),
                "opposition_veto": bool(veto.get("blocked")),
                "integrity_ok": integrity_ok,
                "priority": list(pack.get("priority_order") or []),
            }
        )
    enriched["sc_v947_decision"] = decision_summary
    enriched["sc_v925_decision"] = copy.deepcopy(decision_summary)
    contract = dict(enriched.get("analysis_contract") or {})
    contract.update(
        {
            "schema_version": ANALYSIS_CONTRACT_VERSION,
            "decision_version": DECISION_ENGINE_VERSION,
            "indicator_contract": _CURRENT_INDICATOR_CONTRACT,
            "level_priority": (
                "current_role_sr_cluster_then_confirmed_pivot_then_secondary"
            ),
            "support_definition": "nearest_valid_level_below_closed_price",
            "resistance_definition": "nearest_valid_level_above_closed_price",
            "role_reversal": "broken_resistance_becomes_support_and_inverse",
            "break_confirmation": "closed_candle",
            "role_reversal_failure": "close_back_through_cluster",
            "target_count": "one_to_three",
            "cluster_opposition_veto": True,
            "higher_timeframe_source": "last_completed_bar",
            "legacy_sc_v91_decision_influence": False,
        }
    )
    enriched["analysis_contract"] = contract
    decision = enriched.get("decision_engine")
    if isinstance(decision, dict):
        decision["version"] = DECISION_ENGINE_VERSION
        decision["sc_v947"] = copy.deepcopy(decision_summary)
        decision["sc_v925"] = copy.deepcopy(decision_summary)
    meta = dict(enriched.get("engine_meta") or {})
    meta["decision_engine_version"] = DECISION_ENGINE_VERSION
    meta["analysis_contract_version"] = ANALYSIS_CONTRACT_VERSION
    meta["sc_indicator_contract"] = _CURRENT_INDICATOR_CONTRACT
    enriched["engine_meta"] = meta
    return enriched


__all__ = [
    "ANALYSIS_CONTRACT_VERSION",
    "DECISION_ENGINE_VERSION",
    "enrich_report",
]
