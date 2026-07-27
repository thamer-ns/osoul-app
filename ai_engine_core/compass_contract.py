"""Safe parser for SC-V88 / SC-FXM TradingView webhook evidence.

The compass is an external evidence source, not an authority that silently
replaces Osoli's native calculation.  Parsed payloads may be compared with the
native report and displayed to the user, while the application decision remains
inside decision_policy_v4.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

COMPASS_SCHEMA_VERSION = 1
_MAX_PAYLOAD_CHARS = 16_384


def _finite(value: Any, *, required: bool = False) -> float | None:
    if value is None or value == "":
        if required:
            raise ValueError("قيمة رقمية مطلوبة مفقودة")
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("قيمة رقمية غير صالحة") from exc
    if not math.isfinite(number):
        raise ValueError("NaN وInfinity غير مسموحين")
    return number


def _integer(value: Any, *, minimum: int, maximum: int, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} غير صالح") from exc
    if not minimum <= number <= maximum:
        raise ValueError(f"{name} خارج النطاق")
    return number


def _text(value: Any, *, name: str, maximum: int = 120) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} مطلوب")
    if len(text) > maximum or any(ord(char) < 32 for char in text):
        raise ValueError(f"{name} غير صالح")
    return text


def _normalise_timeframe(value: str) -> str:
    raw = value.strip().lower()
    aliases = {
        "1": "1m", "1m": "1m", "5": "5m", "5m": "5m",
        "15": "15m", "15m": "15m", "30": "30m", "30m": "30m",
        "60": "1h", "60m": "1h", "1h": "1h", "240": "4h", "4h": "4h",
        "d": "1d", "1d": "1d", "w": "1wk", "1w": "1wk", "1wk": "1wk",
        "m": "1mo", "1mo": "1mo",
    }
    return aliases.get(raw, raw)


def _geometry(direction: int, entry: float | None, stop: float | None, targets: list[float | None]) -> dict[str, Any]:
    issues: list[str] = []
    ratios: list[float | None] = []
    if direction == 0:
        return {"valid": entry is None and stop is None, "issues": [] if entry is None and stop is None else ["خطة محايدة تحتوي مستويات اتجاهية"], "target_r": []}
    if entry is None or stop is None or entry <= 0 or stop <= 0:
        return {"valid": False, "issues": ["الدخول أو الوقف مفقود"], "target_r": []}
    if (direction > 0 and stop >= entry) or (direction < 0 and stop <= entry):
        issues.append("الوقف في الجهة الخاطئة")
    risk = abs(entry - stop)
    previous = 0.0
    for index, target in enumerate(targets, start=1):
        if target is None:
            ratios.append(None)
            continue
        if target <= 0 or (direction > 0 and target <= entry) or (direction < 0 and target >= entry):
            issues.append(f"الهدف {index} في الجهة الخاطئة")
        ratio = abs(target - entry) / risk if risk > 0 else 0.0
        ratios.append(round(ratio, 3))
        if ratio <= previous:
            issues.append("الأهداف غير مرتبة")
        previous = ratio
    return {"valid": not issues, "issues": issues, "target_r": ratios, "risk_per_unit": round(risk, 8)}


def parse_compass_payload(payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one compact TradingView alert payload."""
    if isinstance(payload, bytes):
        if len(payload) > _MAX_PAYLOAD_CHARS:
            raise ValueError("حجم الرسالة أكبر من المسموح")
        try:
            raw = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("JSON غير صالح") from exc
    elif isinstance(payload, str):
        if len(payload) > _MAX_PAYLOAD_CHARS:
            raise ValueError("حجم الرسالة أكبر من المسموح")
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("JSON غير صالح") from exc
    elif isinstance(payload, dict):
        raw = dict(payload)
    else:
        raise ValueError("نوع الرسالة غير مدعوم")

    version = _integer(raw.get("v", 1), minimum=1, maximum=COMPASS_SCHEMA_VERSION, name="الإصدار")
    source = _text(raw.get("s"), name="المصدر", maximum=40)
    event = _text(raw.get("e"), name="رمز الحدث", maximum=80)
    symbol = _text(raw.get("x"), name="الرمز", maximum=80).upper()
    asset_type = _text(raw.get("y", "unknown"), name="نوع الأصل", maximum=30).lower()
    timeframe = _normalise_timeframe(_text(raw.get("f"), name="الفاصل", maximum=12))
    timestamp_ms = _integer(raw.get("t"), minimum=1, maximum=9_999_999_999_999, name="وقت الحدث")
    direction = _integer(raw.get("d", 0), minimum=-1, maximum=1, name="الاتجاه")
    event_price = _finite(raw.get("p"), required=True)
    entry = _finite(raw.get("en"))
    stop = _finite(raw.get("sl"))
    targets = [_finite(raw.get(key)) for key in ("t1", "t2", "t3")]
    target_count = _integer(raw.get("n", sum(value is not None for value in targets)), minimum=0, maximum=3, name="عدد الأهداف")
    score = _integer(raw.get("q", 0), minimum=0, maximum=1_000_000, name="درجة التوافق")
    score_maximum = _integer(raw.get("qm", 0), minimum=0, maximum=1_000_000, name="أقصى درجة")
    counter_trend = bool(raw.get("ct", False))

    if event_price is None or event_price <= 0:
        raise ValueError("سعر الحدث يجب أن يكون موجبًا")
    present_targets = sum(value is not None for value in targets)
    if present_targets != target_count:
        raise ValueError("عدد الأهداف لا يطابق المستويات المرسلة")
    if score_maximum and score > score_maximum:
        raise ValueError("درجة التوافق أعلى من الحد الأقصى")

    geometry = _geometry(direction, entry, stop, targets)
    confidence = round(score / score_maximum * 100.0, 2) if score_maximum > 0 else None
    event_time = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
    return {
        "schema_version": version,
        "source": source,
        "event": event,
        "symbol": symbol,
        "asset_type": asset_type,
        "timeframe": timeframe,
        "event_time": event_time.replace(microsecond=0).isoformat(),
        "event_timestamp_ms": timestamp_ms,
        "event_price": event_price,
        "direction": "buy" if direction > 0 else "sell" if direction < 0 else "neutral",
        "direction_code": direction,
        "entry": entry,
        "stop": stop,
        "targets": targets[:target_count],
        "target_count": target_count,
        "score": score,
        "score_maximum": score_maximum,
        "confidence": confidence,
        "counter_trend": counter_trend,
        "geometry": geometry,
        "policy": "external_evidence_compare_only",
    }


def compare_compass_with_report(compass: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Compare external compass evidence with Osoli without changing either."""
    native_direction = str(report.get("direction") or "neutral").lower()
    external_direction = str(compass.get("direction") or "neutral").lower()
    same_symbol = str(compass.get("symbol") or "").split(":")[-1].replace(".SR", "") == str(report.get("symbol") or "").split(":")[-1].replace(".SR", "") if report.get("symbol") else True
    same_frame = _normalise_timeframe(str(compass.get("timeframe") or "")) == _normalise_timeframe(str((report.get("analysis_contract") or {}).get("timeframe") or (report.get("engine_meta") or {}).get("interval_used") or ""))
    aligned = native_direction == external_direction and native_direction in {"buy", "sell"}
    conflicts = []
    if not same_symbol:
        conflicts.append("الرمز لا يطابق التحليل الحالي")
    if not same_frame:
        conflicts.append("الفاصل لا يطابق التحليل الحالي")
    if native_direction in {"buy", "sell"} and external_direction in {"buy", "sell"} and not aligned:
        conflicts.append("اتجاه البوصلة يعاكس اتجاه أصولي")
    if not (compass.get("geometry") or {}).get("valid", False) and external_direction != "neutral":
        conflicts.append("هندسة خطة البوصلة غير صالحة")
    return {
        "aligned": aligned and not conflicts,
        "same_symbol": same_symbol,
        "same_timeframe": same_frame,
        "native_direction": native_direction,
        "external_direction": external_direction,
        "conflicts": conflicts,
        "decision_effect": "none",
    }
