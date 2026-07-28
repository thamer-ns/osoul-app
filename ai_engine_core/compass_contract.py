"""Strict parser for current SC-V90 / SC-FXM compact events.

External events are comparison evidence only.  This module validates source,
timeframe, event chronology primitives, instrument compatibility and plan
geometry before any persistence or forwarding occurs.
"""
from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime, timezone
from itertools import pairwise
from typing import Any

from .timeframe_contract import canonical_timeframe, timeframe_minutes

COMPASS_SCHEMA_VERSION = 1
_MAX_PAYLOAD_CHARS = 16_384
_CURRENT_SOURCES = frozenset({"SC-V90-I", "SC-V90-D", "SC-FXM-V14"})
_LEGACY_SOURCES = frozenset({"SC-V88-I", "SC-V88-D", "SC-FXM-V12", "SC-V84-I", "SC-V84-D", "SC-FXM-V8"})
_ALLOWED_SOURCES = _CURRENT_SOURCES | _LEGACY_SOURCES
_STOCK_TYPES = frozenset({"stock", "fund", "dr"})
_OTHER_TYPES = frozenset({"forex", "index", "futures", "cfd", "crypto", "bond", "commodity", "spot"})
_EVENT_ALIASES = {
    "ENTRY_LONG": "NL", "NEW_LONG": "NL", "LONG": "NL",
    "ENTRY_SHORT": "NS", "NEW_SHORT": "NS", "SHORT": "NS",
    "TARGET_1": "T1", "TARGET_2": "T2", "TARGET_3": "T3",
    "STOP": "SL", "STOP_LOSS": "SL", "CANCEL": "C", "FAKEOUT": "FO",
}
_ALLOWED_EVENTS = frozenset({"NL", "NS", "T1", "T2", "T3", "SL", "C", "FO"})
_TARGET_RANK = {"T1": 1, "T2": 2, "T3": 3}


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
    if not text or len(text) > maximum or any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ValueError(f"{name} غير صالح")
    return text


def _event(value: Any) -> str:
    raw = _text(value, name="رمز الحدث", maximum=40).upper()
    event = _EVENT_ALIASES.get(raw, raw)
    if event not in _ALLOWED_EVENTS:
        raise ValueError("حدث SC غير مدعوم")
    return event


def _source(value: Any) -> str:
    source = _text(value, name="المصدر", maximum=40).upper()
    if source not in _ALLOWED_SOURCES:
        raise ValueError("مصدر المؤشر غير معتمد")
    return source


def _symbol(value: Any) -> str:
    symbol = _text(value, name="الرمز", maximum=80).upper()
    if re.fullmatch(r"[A-Z0-9.^=_:/-]{1,80}", symbol) is None:
        raise ValueError("الرمز غير صالح")
    return symbol


def _geometry(direction: int, entry: float | None, stop: float | None, targets: list[float | None], target_count: int) -> dict[str, Any]:
    issues: list[str] = []
    if direction not in (-1, 1):
        return {"valid": False, "issues": ["الاتجاه مطلوب للخطة"], "target_r": []}
    if entry is None or stop is None or entry <= 0 or stop <= 0:
        return {"valid": False, "issues": ["الدخول أو الوقف مفقود"], "target_r": []}
    active = targets[:target_count]
    if any(value is None or value <= 0 for value in active):
        return {"valid": False, "issues": ["الأهداف المعلنة غير مكتملة"], "target_r": []}
    numeric_targets = [float(value) for value in active if value is not None]
    risk = abs(entry - stop)
    if risk <= 0:
        issues.append("مسافة الوقف صفرية")
    if direction > 0:
        if stop >= entry:
            issues.append("وقف الصفقة الصاعدة يجب أن يكون تحت الدخول")
        if not all(target > entry for target in numeric_targets):
            issues.append("أهداف الصفقة الصاعدة يجب أن تكون فوق الدخول")
        if any(right <= left for left, right in pairwise(numeric_targets)):
            issues.append("أهداف الصفقة الصاعدة غير مرتبة")
    else:
        if stop <= entry:
            issues.append("وقف الصفقة الهابطة يجب أن يكون فوق الدخول")
        if not all(target < entry for target in numeric_targets):
            issues.append("أهداف الصفقة الهابطة يجب أن تكون تحت الدخول")
        if any(right >= left for left, right in pairwise(numeric_targets)):
            issues.append("أهداف الصفقة الهابطة غير مرتبة")
    ratios = [round(abs(target - entry) / risk, 3) if risk > 0 else None for target in numeric_targets]
    return {"valid": not issues, "issues": issues, "target_r": ratios, "risk_per_unit": round(risk, 8)}


def _validate_source_context(source: str, asset_type: str, timeframe: str) -> None:
    minutes = timeframe_minutes(timeframe)
    if source.endswith("-I"):
        if asset_type not in _STOCK_TYPES or minutes >= 1_440:
            raise ValueError("نسخة الأسهم اللحظية تتطلب سهمًا وفاصلًا أقل من اليومي")
    elif source.endswith("-D"):
        if asset_type not in _STOCK_TYPES or not 1_440 <= minutes <= 3 * 43_200:
            raise ValueError("نسخة الأسهم اليومية تتطلب فاصلًا من اليومي إلى ثلاثة أشهر")
    elif source.startswith("SC-FXM"):
        if asset_type not in _OTHER_TYPES or minutes > 1_440:
            raise ValueError("نسخة الأسواق الأخرى تتطلب أصلًا مدعومًا وفاصلًا حتى اليومي")


def parse_compass_payload(payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
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

    required_keys = {"v", "s", "e", "x", "y", "f", "t", "p", "d", "en", "sl", "t1", "t2", "t3", "n", "q", "qm", "ct"}
    missing = sorted(key for key in required_keys if key not in raw)
    if missing:
        raise ValueError("عقد SC ناقص: " + ",".join(missing))

    version = _integer(raw["v"], minimum=1, maximum=COMPASS_SCHEMA_VERSION, name="الإصدار")
    source = _source(raw["s"])
    event = _event(raw["e"])
    symbol = _symbol(raw["x"])
    asset_type = _text(raw["y"], name="نوع الأصل", maximum=30).lower()
    timeframe = canonical_timeframe(raw["f"])
    timestamp_ms = _integer(raw["t"], minimum=946_684_800_000, maximum=9_999_999_999_999, name="وقت الحدث")
    now_ms = int(time.time() * 1000)
    if timestamp_ms > now_ms + 5 * 60_000:
        raise ValueError("وقت الحدث في المستقبل")
    direction = _integer(raw["d"], minimum=-1, maximum=1, name="الاتجاه")
    event_price = _finite(raw["p"], required=True)
    entry = _finite(raw["en"])
    stop = _finite(raw["sl"])
    targets = [_finite(raw[key]) for key in ("t1", "t2", "t3")]
    target_count = _integer(raw["n"], minimum=1, maximum=3, name="عدد الأهداف")
    score = _integer(raw["q"], minimum=0, maximum=100_000, name="درجة التوافق")
    score_maximum = _integer(raw["qm"], minimum=1, maximum=100_000, name="أقصى درجة")
    counter_trend = bool(raw["ct"])

    if event_price is None or event_price <= 0 or event_price > 1_000_000_000:
        raise ValueError("سعر الحدث غير صالح")
    if score > score_maximum:
        raise ValueError("درجة التوافق أعلى من الحد الأقصى")
    if event == "NL" and direction != 1:
        raise ValueError("NL يتطلب اتجاهًا صاعدًا")
    if event == "NS" and direction != -1:
        raise ValueError("NS يتطلب اتجاهًا هابطًا")
    if event != "FO" and direction not in (-1, 1):
        raise ValueError("الحدث يتطلب اتجاهًا صريحًا")
    rank = _TARGET_RANK.get(event)
    if rank is not None and rank > target_count:
        raise ValueError("حدث الهدف يتجاوز عدد الأهداف المعلن")
    if sum(value is not None for value in targets) != target_count:
        raise ValueError("عدد الأهداف لا يطابق المستويات المرسلة")

    _validate_source_context(source, asset_type, timeframe)
    geometry = _geometry(direction, entry, stop, targets, target_count)
    if event != "FO" and not geometry["valid"]:
        raise ValueError("هندسة الخطة غير صالحة")
    confidence = round(score / score_maximum * 100.0, 2)
    event_time = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
    return {
        "schema_version": version,
        "source": source,
        "source_generation": "current" if source in _CURRENT_SOURCES else "legacy",
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
    native_direction = str(report.get("direction") or "neutral").lower()
    external_direction = str(compass.get("direction") or "neutral").lower()
    external_symbol = str(compass.get("symbol") or "").split(":")[-1].replace(".SR", "")
    native_symbol = str(report.get("symbol") or "").split(":")[-1].replace(".SR", "")
    same_symbol = external_symbol == native_symbol if native_symbol else True
    native_frame_raw = (report.get("analysis_contract") or {}).get("timeframe") or (report.get("engine_meta") or {}).get("interval_used") or ""
    try:
        same_frame = canonical_timeframe(compass.get("timeframe")) == canonical_timeframe(native_frame_raw)
    except ValueError:
        same_frame = False
    aligned = native_direction == external_direction and native_direction in {"buy", "sell"}
    conflicts: list[str] = []
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
