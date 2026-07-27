"""Unified analysis policy v4.

This layer keeps the proven v3 close-confirmed decision, then adds the useful
transport-independent ideas shared by the Telegram bot and the SC-V88 compass:
independent evidence schools, a one-strong-or-two-independent qualification
rule, opposition vetoes, timeframe-aware risk geometry, and one presentation
contract for every UI.

The module never fetches data.  It only audits an existing report, preventing
extra network calls and duplicated indicator calculations on Streamlit reruns.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .decision_policy_v3 import enrich_report as _v3_enrich_report

DECISION_ENGINE_VERSION = "4.0"
ANALYSIS_CONTRACT_VERSION = "4.0"


@dataclass(frozen=True, slots=True)
class EvidenceSchool:
    axis: str
    school: str
    direction: int
    strength: int
    actionable: bool
    reason: str


_SCHOOL_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("structure", "داو والبنية السعرية", ("bos", "choch", "هيكل", "بنية", "قمة", "قاع", "اختراق مقاومة", "كسر دعم")),
    ("trend", "الاتجاه والمتوسطات", ("trend", "ترند", "اتجاه", "sma", "ema", "ichimoku", "إيشيموكو", "قناة")),
    ("momentum", "الزخم", ("rsi", "macd", "زخم", "momentum", "دايفرجنس", "divergence", "cross")),
    ("participation", "الحجم والمشاركة", ("vsa", "حجم", "volume", "سيولة", "liquidity", "امتصاص", "effort")),
    ("location", "الموقع والمستويات", ("دعم", "مقاومة", "منطقة", "order block", "طلب", "عرض", "fib", "فيبوناتشي", "premium", "discount")),
    ("behavior", "السلوك السعري والشموع", ("شمعة", "ابتلاع", "مطرقة", "شهاب", "inside", "انسايد", "gap", "fvg", "sweep", "spring", "utad", "كسر وهمي")),
    ("volatility", "التذبذب والنظام", ("atr", "adx", "تذبذب", "volatility", "regime", "بولنجر", "bollinger", "squeeze")),
    ("fundamental", "الجودة المالية", ("مالي", "fund", "تدفق نقدي", "ربحية", "ديون", "piotroski", "جودة البيانات")),
)

_POSITIVE = (
    "صاعد", "صعود", "إيجابي", "شراء", "تجميع", "اختراق مقاومة", "فوق", "استرداد", "ارتداد صاعد",
    "bull", "buy", "long", "golden", "close_above", "طلب", "spring", "امتصاص بيع",
)
_NEGATIVE = (
    "هابط", "هبوط", "سلبي", "بيع", "خروج", "كسر دعم", "تحت", "رفض", "ارتداد هابط",
    "bear", "sell", "short", "death", "close_below", "عرض", "utad", "امتصاص شراء",
)
_ACTIONABLE = (
    "مؤكد", "بإغلاق", "إغلاق", "breakout", "breakdown", "bos", "choch", "spring", "utad",
    "استرداد", "رفض سعري", "ابتلاع", "مطرقة", "شهاب", "sweep",
)

_STOP_ATR_LIMITS = {
    "1m": (0.45, 1.80),
    "2m": (0.48, 1.90),
    "5m": (0.50, 2.00),
    "15m": (0.55, 2.20),
    "30m": (0.60, 2.40),
    "60m": (0.65, 2.70),
    "1h": (0.65, 2.70),
    "4h": (0.75, 3.10),
    "1d": (0.85, 3.50),
    "1wk": (0.85, 3.50),
    "1w": (0.85, 3.50),
    "1mo": (0.85, 3.50),
}


def _finite(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _normalise_timeframe(value: Any) -> str:
    raw = str(value or "1d").strip().lower()
    return {
        "d": "1d", "day": "1d", "daily": "1d", "1day": "1d",
        "w": "1wk", "week": "1wk", "weekly": "1wk", "1w": "1wk",
        "m": "1mo", "month": "1mo", "monthly": "1mo",
        "h": "1h", "60min": "60m", "60minut": "60m",
    }.get(raw, raw)


def _flatten(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()

    def visit(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            # Preserve complete event/reason objects rather than counting every
            # scalar as an independent piece of evidence.
            preferred = value.get("reason") or value.get("event") or value.get("summary") or value.get("note")
            if preferred:
                visit(preferred)
            else:
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

    visit(values)
    return output


def _contains(text: str, words: Iterable[str]) -> bool:
    lowered = text.casefold()
    return any(word.casefold() in lowered for word in words)


def _direction_from_text(items: list[str]) -> tuple[int, int, int]:
    positive = sum(1 for item in items if _contains(item, _POSITIVE))
    negative = sum(1 for item in items if _contains(item, _NEGATIVE))
    if positive == negative:
        return 0, positive, negative
    return (1 if positive > negative else -1), positive, negative


def _numeric_school_signals(report: dict[str, Any]) -> list[EvidenceSchool]:
    features = report.get("features") if isinstance(report.get("features"), dict) else {}
    signals: list[EvidenceSchool] = []
    close = _finite(features.get("close"))
    sma50 = _finite(features.get("sma50"))
    sma200 = _finite(features.get("sma200"))
    if close and sma50:
        direction = 1 if close > sma50 else -1
        strength = 70
        reason = "السعر فوق SMA50" if direction > 0 else "السعر تحت SMA50"
        if sma200:
            aligned = (direction > 0 and sma50 > sma200) or (direction < 0 and sma50 < sma200)
            if aligned:
                strength = 78
                reason += " مع توافق SMA200"
        signals.append(EvidenceSchool("trend", "الاتجاه والمتوسطات", direction, strength, False, reason))

    rsi = _finite(features.get("rsi14"))
    macd = _finite(features.get("macd"))
    if rsi is not None:
        direction = 1 if rsi >= 55 else -1 if rsi <= 45 else 0
        if direction:
            macd_aligned = macd is not None and ((direction > 0 and macd > 0) or (direction < 0 and macd < 0))
            strength = 78 if macd_aligned else 64
            reason = f"RSI={rsi:.1f}" + (" وMACD متوافق" if macd_aligned else "")
            signals.append(EvidenceSchool("momentum", "الزخم", direction, strength, macd_aligned, reason))

    for key, direction, reason in (
        ("liq_sweep_low", 1, "استرداد قاع بعد سحب سيولة"),
        ("liq_sweep_high", -1, "رفض قمة بعد سحب سيولة"),
        ("broke_support_confirm", -1, "كسر دعم مؤكد"),
    ):
        if int(_finite(features.get(key), 0.0) or 0) == 1:
            signals.append(EvidenceSchool("behavior" if "sweep" in key else "structure", "السلوك السعري والشموع" if "sweep" in key else "داو والبنية السعرية", direction, 88, True, reason))

    fund_score = _finite(report.get("fund_score"), 0.0) or 0.0
    if abs(fund_score) >= 2:
        direction = 1 if fund_score > 0 else -1
        strength = min(84, 58 + int(abs(fund_score) * 4))
        signals.append(EvidenceSchool("fundamental", "الجودة المالية", direction, strength, False, f"درجة التحليل المالي {fund_score:+.1f}"))
    return signals


def _text_school_signals(report: dict[str, Any]) -> list[EvidenceSchool]:
    evidence = _flatten(
        [
            report.get("tech_reasons"),
            report.get("fund_reasons"),
            report.get("signal_events"),
            report.get("top_evidence"),
            (report.get("explainability") or {}).get("positives") if isinstance(report.get("explainability"), dict) else None,
        ]
    )
    signals: list[EvidenceSchool] = []
    for axis, school, keywords in _SCHOOL_RULES:
        matched = [item for item in evidence if _contains(item, keywords)]
        direction, positive, negative = _direction_from_text(matched)
        if not matched or direction == 0:
            continue
        actionable = any(_contains(item, _ACTIONABLE) for item in matched)
        dominant = max(positive, negative)
        opposition = min(positive, negative)
        strength = 56 + min(18, dominant * 6) + (10 if actionable else 0) - min(10, opposition * 4)
        strength = max(55, min(92, strength))
        reason = matched[0]
        if len(matched) > 1:
            reason += f" (+{len(matched) - 1} دليل)"
        signals.append(EvidenceSchool(axis, school, direction, strength, actionable, reason))
    return signals


def _strongest_per_axis(signals: list[EvidenceSchool]) -> list[EvidenceSchool]:
    strongest: dict[tuple[str, int], EvidenceSchool] = {}
    for signal in signals:
        key = (signal.axis, signal.direction)
        previous = strongest.get(key)
        if previous is None or signal.strength > previous.strength:
            strongest[key] = signal
    return list(strongest.values())


def build_school_consensus(report: dict[str, Any]) -> dict[str, Any]:
    """Build independent-school consensus without double-counting one axis."""
    signals = _strongest_per_axis(_numeric_school_signals(report) + _text_school_signals(report))
    long_signals = sorted((item for item in signals if item.direction > 0), key=lambda item: item.strength, reverse=True)
    short_signals = sorted((item for item in signals if item.direction < 0), key=lambda item: item.strength, reverse=True)
    long_total = sum(item.strength for item in long_signals)
    short_total = sum(item.strength for item in short_signals)
    if long_total == short_total:
        aligned: list[EvidenceSchool] = []
        opposing = sorted(signals, key=lambda item: item.strength, reverse=True)
        direction = 0
    else:
        direction = 1 if long_total > short_total else -1
        aligned = long_signals if direction > 0 else short_signals
        opposing = short_signals if direction > 0 else long_signals

    strongest = aligned[0] if aligned else None
    strong_single = bool(len(aligned) == 1 and strongest and strongest.strength >= 84 and strongest.actionable)
    independent = len({item.axis for item in aligned[:4]})
    multi = bool(len(aligned) >= 2 and independent >= 2 and aligned[0].strength >= 60 and aligned[1].strength >= 58)
    opposing_veto = bool(
        opposing
        and (
            opposing[0].strength >= 84
            or (
                len(opposing) >= 2
                and sum(item.strength for item in opposing[:2])
                >= sum(item.strength for item in aligned[:2]) * 0.85
            )
        )
    )
    qualified = bool(direction and (strong_single or multi) and not opposing_veto)
    selected = aligned[:4] if qualified else aligned[:2]
    strength = round(sum(item.strength for item in selected) / len(selected)) if selected else 0
    strength = min(96, strength + (6 if len(selected) >= 3 else 3 if len(selected) == 2 else 0))
    return {
        "qualified": qualified,
        "direction": "buy" if direction > 0 else "sell" if direction < 0 else "neutral",
        "strength": strength,
        "school_count": len(selected),
        "school_names": [item.school for item in selected],
        "independent_axes": [item.axis for item in selected],
        "strong_single_school": strong_single,
        "opposition_veto": opposing_veto,
        "signals": [asdict(item) for item in selected],
        "opposing": [asdict(item) for item in opposing[:3]],
        "rule": "one_strong_actionable_or_two_independent_aligned",
    }


def audit_plan_geometry(report: dict[str, Any], timeframe: str) -> dict[str, Any]:
    plan = report.get("risk_plan") if isinstance(report.get("risk_plan"), dict) else {}
    direction = str(report.get("direction") or plan.get("direction") or "neutral").lower()
    entry = _finite(plan.get("entry"))
    stop = _finite(plan.get("stop"))
    targets = [_finite(plan.get(f"target{index}")) for index in (1, 2, 3)]
    features = report.get("features") if isinstance(report.get("features"), dict) else {}
    atr = _finite(features.get("atr14"))
    issues: list[str] = []
    target_r: list[float | None] = []

    if direction not in {"buy", "sell"} or entry is None:
        return {"valid": False, "complete": False, "issues": ["لا توجد خطة اتجاهية مكتملة"], "target_r": [], "stop_atr": None}
    if entry <= 0 or stop is None or stop <= 0:
        issues.append("الدخول أو الوقف غير صالح")
        return {"valid": False, "complete": False, "issues": issues, "target_r": [], "stop_atr": None}

    risk = abs(entry - stop)
    correct_stop = stop < entry if direction == "buy" else stop > entry
    if not correct_stop or risk <= 0:
        issues.append("الوقف ليس خلف نقطة الإبطال في جهة الصفقة")

    previous_r = 0.0
    for index, target in enumerate(targets, start=1):
        if target is None:
            target_r.append(None)
            issues.append(f"الهدف {index} غير متاح")
            continue
        correct_target = target > entry if direction == "buy" else target < entry
        ratio = abs(target - entry) / risk if risk > 0 else 0.0
        target_r.append(round(ratio, 2))
        if target <= 0 or not correct_target:
            issues.append(f"الهدف {index} في جهة غير صحيحة")
        if ratio <= previous_r:
            issues.append("الأهداف غير مرتبة تصاعديًا بوحدة R")
        previous_r = ratio

    short_plan = bool(plan.get("short_plan") or plan.get("obstacle_target"))
    minimum_t1 = 0.65 if short_plan else 1.0
    if target_r and target_r[0] is not None and float(target_r[0]) < minimum_t1:
        issues.append(f"الهدف الأول أقل من الحد الأدنى {minimum_t1:.2f}R")

    stop_atr = risk / atr if atr and atr > 0 else None
    limits = _STOP_ATR_LIMITS.get(_normalise_timeframe(timeframe), (0.85, 3.50))
    if stop_atr is not None and not limits[0] <= stop_atr <= limits[1]:
        issues.append(f"مسافة الوقف {stop_atr:.2f} ATR خارج نطاق الفاصل {limits[0]:.2f}–{limits[1]:.2f}")

    complete = all(value is not None for value in (entry, stop, *targets))
    return {
        "valid": not issues,
        "complete": complete,
        "issues": issues,
        "risk_per_unit": round(risk, 6),
        "risk_pct": round(risk / entry * 100.0, 3) if entry > 0 else None,
        "stop_atr": round(stop_atr, 3) if stop_atr is not None else None,
        "stop_atr_limits": list(limits),
        "target_r": target_r,
        "short_plan": short_plan,
    }


def _downgrade(report: dict[str, Any], reason: str) -> None:
    status = str(report.get("lifecycle_status") or "NO_SETUP")
    if status != "ACTIONABLE":
        return
    report["lifecycle_status"] = "HEADS_UP"
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
    report["recommendation"] = "👀 مراقبة — التوافق لم يكتمل"
    report["color"] = "#f59e0b"
    report["strategy"] = reason


def enrich_report(report: Any, *, symbol: str = "", timeframe: str = "1D") -> dict[str, Any]:
    """Return a v4 report with one auditable contract for every presentation."""
    enriched = _v3_enrich_report(report, symbol=symbol, timeframe=timeframe)
    if str(enriched.get("status") or "").lower() == "error":
        return enriched

    meta = enriched.get("engine_meta") if isinstance(enriched.get("engine_meta"), dict) else {}
    actual_tf = _normalise_timeframe(meta.get("interval_used") or timeframe)
    consensus = build_school_consensus(enriched)
    geometry = audit_plan_geometry(enriched, actual_tf)

    if str(enriched.get("lifecycle_status") or "") == "ACTIONABLE" and not consensus["qualified"]:
        _downgrade(enriched, "لم يتحقق شرط مدرسة واحدة قوية قابلة للتنفيذ أو مدرستين مستقلتين متوافقتين")
    if str(enriched.get("lifecycle_status") or "") == "ACTIONABLE" and not geometry["valid"]:
        _downgrade(enriched, "هندسة الدخول والوقف والأهداف لم تجتز التدقيق")

    status = str(enriched.get("lifecycle_status") or "NO_SETUP")
    stage = {
        "NO_SETUP": "راقب",
        "HEADS_UP": "قرب الدخول",
        "ACTIONABLE": "دخول مؤكد",
        "BLOCKED": "محظورة",
        "ERROR": "غير متاح",
    }.get(status, "راقب")

    enriched["school_consensus"] = consensus
    enriched["plan_geometry"] = geometry
    enriched["analysis_stage"] = stage
    enriched["analysis_contract"] = {
        "schema_version": ANALYSIS_CONTRACT_VERSION,
        "decision_version": DECISION_ENGINE_VERSION,
        "closed_candles_only": True,
        "break_stop_confirmation": "candle_close",
        "target_monitoring": "touch_with_close_audit",
        "school_rule": consensus["rule"],
        "timeframe": actual_tf,
        "stage": stage,
        "lifecycle": status,
        "external_evidence_policy": "compare_never_override_automatically",
    }

    decision = enriched.get("decision_engine")
    if isinstance(decision, dict):
        decision["version"] = DECISION_ENGINE_VERSION
        decision["school_consensus"] = consensus
        decision["plan_geometry"] = geometry
        decision["stage"] = stage
    meta = dict(meta)
    meta["decision_engine_version"] = DECISION_ENGINE_VERSION
    meta["analysis_contract_version"] = ANALYSIS_CONTRACT_VERSION
    enriched["engine_meta"] = meta
    return enriched
