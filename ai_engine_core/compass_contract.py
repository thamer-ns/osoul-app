"""Strict SC-V90 / SC-FXM compact-contract validation.

The parser is shared by the journal, the Streamlit UI and the market-bot bridge.
It normalises every accepted timeframe to one unambiguous internal vocabulary,
validates source/instrument/frame compatibility, rejects impossible timestamps
and plan geometry, and rebuilds the exact compact wire payload sent to the bot.
External evidence never overrides Osoli's native decision automatically.
"""
from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime, timezone
from itertools import pairwise
from typing import Any

COMPASS_SCHEMA_VERSION = 1
_MAX_PAYLOAD_CHARS = 16_384
_MIN_EVENT_TIMESTAMP_MS = 946_684_800_000  # 2000-01-01 UTC
_MAX_FUTURE_SKEW_MS = 5 * 60_000

CURRENT_STOCK_SOURCES = frozenset({"SC-V90-I", "SC-V90-D"})
LEGACY_STOCK_SOURCES = frozenset({"SC-V84-I", "SC-V84-D"})
CURRENT_OTHER_SOURCES = frozenset({"SC-FXM-V14"})
LEGACY_OTHER_SOURCES = frozenset({"SC-FXM-V8"})
STRICT_SOURCES = (
    CURRENT_STOCK_SOURCES
    | LEGACY_STOCK_SOURCES
    | CURRENT_OTHER_SOURCES
    | LEGACY_OTHER_SOURCES
)
INTRADAY_STOCK_SOURCES = frozenset({"SC-V90-I", "SC-V84-I"})
DAILY_STOCK_SOURCES = frozenset({"SC-V90-D", "SC-V84-D"})
OTHER_SOURCES = CURRENT_OTHER_SOURCES | LEGACY_OTHER_SOURCES
STOCK_TYPES = frozenset({"stock", "fund", "dr"})
OTHER_TYPES = frozenset(
    {
        "forex",
        "index",
        "futures",
        "cfd",
        "crypto",
        "bond",
        "spread",
        "economic",
        "commodity",
        "spot",
        "swap",
        "forward",
    }
)
SUPPORTED_TIMEFRAMES = (
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "4h",
    "1d",
    "1w",
    "1mo",
)
_TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1_440,
    "1w": 10_080,
    "1mo": 43_200,
}
_EVENT_ALIASES = {
    "NL": "NL",
    "NEW_LONG": "NL",
    "NEW_PLAN_LONG": "NL",
    "ENTRY_LONG": "NL",
    "NS": "NS",
    "NEW_SHORT": "NS",
    "NEW_PLAN_SHORT": "NS",
    "ENTRY_SHORT": "NS",
    "T1": "T1",
    "TARGET_1": "T1",
    "T2": "T2",
    "TARGET_2": "T2",
    "T3": "T3",
    "TARGET_3": "T3",
    "SL": "SL",
    "STOP": "SL",
    "C": "C",
    "CANCELLED": "C",
    "FO": "FO",
    "FAKEOUT": "FO",
}
_TARGET_EVENT_RANK = {"T1": 1, "T2": 2, "T3": 3}


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
    if len(text) > maximum or any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ValueError(f"{name} غير صالح")
    return text


def normalise_timeframe(value: Any) -> str:
    """Return the one canonical frame vocabulary shared with the bot.

    Lower-case ``m`` means minutes; upper-case TradingView ``M`` means month.
    Numeric TradingView values mean minutes.  ``1wk`` is accepted only as a
    migration alias and normalised to ``1w``.
    """
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("الفاصل مطلوب")
    if raw.isdigit():
        aliases = {"1": "1m", "5": "5m", "15": "15m", "30": "30m", "60": "1h", "240": "4h"}
        result = aliases.get(raw)
    elif raw == "M":
        result = "1mo"
    else:
        lowered = raw.lower()
        aliases = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "60m": "1h",
            "1h": "1h",
            "240m": "4h",
            "4h": "4h",
            "d": "1d",
            "1d": "1d",
            "day": "1d",
            "daily": "1d",
            "w": "1w",
            "1w": "1w",
            "1wk": "1w",
            "week": "1w",
            "weekly": "1w",
            "mo": "1mo",
            "1mo": "1mo",
            "month": "1mo",
            "monthly": "1mo",
        }
        result = aliases.get(lowered)
    if result not in SUPPORTED_TIMEFRAMES:
        raise ValueError("الفاصل غير مدعوم")
    return str(result)


def _canonical_event(value: Any) -> str:
    text = _text(value, name="رمز الحدث", maximum=40).upper()
    event = _EVENT_ALIASES.get(text)
    if event is None:
        raise ValueError("رمز الحدث غير مدعوم")
    return event


def _geometry(
    direction: int,
    entry: float | None,
    stop: float | None,
    targets: list[float | None],
) -> dict[str, Any]:
    issues: list[str] = []
    ratios: list[float | None] = []
    if direction == 0:
        return {
            "valid": entry is None and stop is None,
            "issues": [] if entry is None and stop is None else ["خطة محايدة تحتوي مستويات اتجاهية"],
            "target_r": [],
        }
    if entry is None or stop is None or entry <= 0 or stop <= 0:
        return {"valid": False, "issues": ["الدخول أو الوقف مفقود"], "target_r": []}
    if (direction > 0 and stop >= entry) or (direction < 0 and stop <= entry):
        issues.append("الوقف في الجهة الخاطئة")
    risk = abs(entry - stop)
    if risk <= 0:
        issues.append("المخاطرة لكل وحدة غير صالحة")
    present = [target for target in targets if target is not None]
    for index, target in enumerate(present, start=1):
        assert target is not None
        if target <= 0 or (direction > 0 and target <= entry) or (direction < 0 and target >= entry):
            issues.append(f"الهدف {index} في الجهة الخاطئة")
        ratio = abs(target - entry) / risk if risk > 0 else 0.0
        ratios.append(round(ratio, 3))
    if direction > 0 and any(right <= left for left, right in pairwise(present)):
        issues.append("أهداف الصعود غير مرتبة تصاعديًا")
    if direction < 0 and any(right >= left for left, right in pairwise(present)):
        issues.append("أهداف الهبوط غير مرتبة تنازليًا")
    return {
        "valid": not issues,
        "issues": issues,
        "target_r": ratios,
        "risk_per_unit": round(risk, 8),
    }


def _validate_source_frame(source: str, asset_type: str, timeframe: str) -> None:
    minutes = _TIMEFRAME_MINUTES[timeframe]
    if source in INTRADAY_STOCK_SOURCES:
        if asset_type not in STOCK_TYPES or minutes >= 1_440:
            raise ValueError("مصدر الأسهم اللحظي يتطلب سهمًا وفاصلًا أقل من اليومي")
        return
    if source in DAILY_STOCK_SOURCES:
        if asset_type not in STOCK_TYPES or timeframe not in {"1d", "1w", "1mo"}:
            raise ValueError("مصدر الأسهم اليومي يتطلب سهمًا وفاصلًا يوميًا أو أعلى")
        return
    if source in OTHER_SOURCES:
        if asset_type not in OTHER_TYPES or minutes > 1_440:
            raise ValueError("مصدر الأسواق الأخرى يتطلب أصلًا غير سهمي من الدقيقة إلى اليومي")
        return
    raise ValueError("مصدر المؤشر غير معتمد")


def _decode_payload(payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, bytes):
        if len(payload) > _MAX_PAYLOAD_CHARS:
            raise ValueError("حجم الرسالة أكبر من المسموح")
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("JSON غير صالح") from exc
    elif isinstance(payload, str):
        if len(payload) > _MAX_PAYLOAD_CHARS:
            raise ValueError("حجم الرسالة أكبر من المسموح")
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("JSON غير صالح") from exc
    elif isinstance(payload, dict):
        decoded = dict(payload)
    else:
        raise ValueError("نوع الرسالة غير مدعوم")
    if not isinstance(decoded, dict):
        raise ValueError("جذر JSON يجب أن يكون كائنًا")
    return decoded


def parse_compass_payload(
    payload: str | bytes | dict[str, Any],
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Validate and normalize one current or migration compact alert."""
    raw = _decode_payload(payload)
    version = _integer(raw.get("v"), minimum=1, maximum=COMPASS_SCHEMA_VERSION, name="الإصدار")
    source = _text(raw.get("s"), name="المصدر", maximum=40).upper()
    if source not in STRICT_SOURCES:
        raise ValueError("مصدر المؤشر غير معتمد")
    event = _canonical_event(raw.get("e"))
    symbol = _text(raw.get("x"), name="الرمز", maximum=80).upper()
    if re.fullmatch(r"[A-Z0-9.^=_:/-]{1,80}", symbol) is None:
        raise ValueError("الرمز غير صالح")
    asset_type = _text(raw.get("y"), name="نوع الأصل", maximum=30).lower()
    timeframe = normalise_timeframe(raw.get("f"))
    _validate_source_frame(source, asset_type, timeframe)

    timestamp_ms = _integer(
        raw.get("t"),
        minimum=_MIN_EVENT_TIMESTAMP_MS,
        maximum=9_999_999_999_999,
        name="وقت الحدث",
    )
    clock_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    if timestamp_ms > clock_ms + _MAX_FUTURE_SKEW_MS:
        raise ValueError("وقت الحدث في المستقبل خارج هامش السماح")

    direction = _integer(raw.get("d"), minimum=-1, maximum=1, name="الاتجاه")
    if event == "NL" and direction != 1:
        raise ValueError("NL يتطلب اتجاهًا صاعدًا")
    if event == "NS" and direction != -1:
        raise ValueError("NS يتطلب اتجاهًا هابطًا")
    if event != "FO" and direction not in {-1, 1}:
        raise ValueError("الحدث يتطلب اتجاهًا صريحًا")

    event_price = _finite(raw.get("p"), required=True)
    if event_price is None or event_price <= 0 or event_price > 1_000_000_000:
        raise ValueError("سعر الحدث غير صالح")
    entry = _finite(raw.get("en"))
    stop = _finite(raw.get("sl"))
    targets = [_finite(raw.get(key)) for key in ("t1", "t2", "t3")]
    target_count = _integer(raw.get("n"), minimum=1, maximum=3, name="عدد الأهداف")
    score = _integer(raw.get("q"), minimum=0, maximum=100_000, name="درجة التوافق")
    score_maximum = _integer(raw.get("qm"), minimum=1, maximum=100_000, name="أقصى درجة")
    if score > score_maximum:
        raise ValueError("درجة التوافق أعلى من الحد الأقصى")

    if event == "FO":
        if target_count != 1:
            raise ValueError("FO يتطلب عدد أهداف يساوي 1")
        geometry = _geometry(direction, entry, stop, [])
    else:
        required = [entry, stop, targets[0]]
        if target_count >= 2:
            required.append(targets[1])
        if target_count >= 3:
            required.append(targets[2])
        if any(value is None for value in required):
            raise ValueError("الحدث يفتقد مستويات الخطة النشطة")
        if any(value is not None for value in targets[target_count:]):
            raise ValueError("توجد أهداف زائدة عن العدد المعلن")
        rank = _TARGET_EVENT_RANK.get(event)
        if rank is not None and rank > target_count:
            raise ValueError("حدث الهدف يتجاوز عدد الأهداف المعلن")
        geometry = _geometry(direction, entry, stop, targets[:target_count])
        if not geometry.get("valid"):
            raise ValueError("هندسة الخطة غير صالحة")

    confidence = round(score / score_maximum * 100.0, 2)
    event_time = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
    age_seconds = max(0.0, (clock_ms - timestamp_ms) / 1000.0)
    return {
        "schema_version": version,
        "source": source,
        "legacy_source": source not in (CURRENT_STOCK_SOURCES | CURRENT_OTHER_SOURCES),
        "event": event,
        "symbol": symbol,
        "asset_type": asset_type,
        "timeframe": timeframe,
        "event_time": event_time.replace(microsecond=0).isoformat(),
        "event_timestamp_ms": timestamp_ms,
        "event_age_seconds": round(age_seconds, 3),
        "replay_event": age_seconds > 7 * 86_400,
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
        "counter_trend": bool(raw.get("ct", False)),
        "geometry": geometry,
        "policy": "external_evidence_compare_only",
    }


def to_bot_wire_payload(parsed_or_payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
    """Rebuild the exact compact contract accepted by the bot."""
    parsed = (
        parsed_or_payload
        if isinstance(parsed_or_payload, dict)
        and "schema_version" in parsed_or_payload
        and "event_timestamp_ms" in parsed_or_payload
        else parse_compass_payload(parsed_or_payload)
    )
    targets = list(parsed.get("targets") or [])[:3]
    targets += [None] * (3 - len(targets))
    return {
        "v": int(parsed["schema_version"]),
        "s": str(parsed["source"]),
        "e": str(parsed["event"]),
        "x": str(parsed["symbol"]),
        "y": str(parsed["asset_type"]),
        "f": normalise_timeframe(parsed["timeframe"]),
        "t": int(parsed["event_timestamp_ms"]),
        "p": float(parsed["event_price"]),
        "d": int(parsed["direction_code"]),
        "en": parsed.get("entry"),
        "sl": parsed.get("stop"),
        "t1": targets[0],
        "t2": targets[1],
        "t3": targets[2],
        "n": int(parsed["target_count"]),
        "q": int(parsed["score"]),
        "qm": int(parsed["score_maximum"]),
        "ct": bool(parsed.get("counter_trend", False)),
    }


def compare_compass_with_report(compass: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Compare external evidence with Osoli without changing either decision."""
    native_direction = str(report.get("direction") or "neutral").lower()
    external_direction = str(compass.get("direction") or "neutral").lower()
    external_symbol = str(compass.get("symbol") or "").split(":")[-1].replace(".SR", "")
    native_symbol = str(report.get("symbol") or "").split(":")[-1].replace(".SR", "")
    same_symbol = external_symbol == native_symbol if native_symbol else True
    native_frame_raw = str(
        (report.get("analysis_contract") or {}).get("timeframe")
        or (report.get("engine_meta") or {}).get("interval_used")
        or ""
    )
    try:
        same_frame = normalise_timeframe(compass.get("timeframe")) == normalise_timeframe(native_frame_raw)
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
    if compass.get("event") != "FO" and not (compass.get("geometry") or {}).get("valid", False):
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


__all__ = [
    "COMPASS_SCHEMA_VERSION",
    "CURRENT_OTHER_SOURCES",
    "CURRENT_STOCK_SOURCES",
    "STRICT_SOURCES",
    "SUPPORTED_TIMEFRAMES",
    "compare_compass_with_report",
    "normalise_timeframe",
    "parse_compass_payload",
    "to_bot_wire_payload",
]
