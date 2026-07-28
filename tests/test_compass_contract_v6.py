from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_engine_core.compass_contract import (
    normalise_timeframe,
    parse_compass_payload,
    to_bot_wire_payload,
)

VECTORS = Path(__file__).parent / "contracts" / "sc_v90_v1_vectors.json"
NOW_MS = 1_800_000_000_000


def _vectors():
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def test_shared_contract_vectors_normalize_exactly_for_the_bot():
    for vector in _vectors():
        parsed = parse_compass_payload(vector["payload"], now_ms=NOW_MS)
        assert parsed["timeframe"] == vector["expected_frame"]
        wire = to_bot_wire_payload(parsed)
        assert wire["f"] == vector["expected_frame"]
        assert wire["s"] == vector["payload"]["s"]
        assert wire["e"] in {"NL", "NS"}


def test_minutes_weekly_and_monthly_are_unambiguous():
    assert normalise_timeframe("5m") == "5m"
    assert normalise_timeframe("5") == "5m"
    assert normalise_timeframe("1wk") == "1w"
    assert normalise_timeframe("1w") == "1w"
    assert normalise_timeframe("M") == "1mo"
    assert normalise_timeframe("1mo") == "1mo"


def test_strict_contract_rejects_unknown_source_future_time_and_bad_geometry():
    payload = _vectors()[0]["payload"]

    with pytest.raises(ValueError):
        parse_compass_payload({**payload, "s": "SC-UNKNOWN"}, now_ms=NOW_MS)

    with pytest.raises(ValueError):
        parse_compass_payload({**payload, "t": NOW_MS + 300_001}, now_ms=NOW_MS)

    with pytest.raises(ValueError):
        parse_compass_payload({**payload, "sl": 101.0}, now_ms=NOW_MS)

    with pytest.raises(ValueError):
        parse_compass_payload({**payload, "s": "SC-V90-I", "f": "1d"}, now_ms=NOW_MS)


def test_replay_events_can_be_audited_locally_but_are_marked_historical():
    parsed = parse_compass_payload(_vectors()[0]["payload"], now_ms=NOW_MS)
    assert parsed["replay_event"] is True
    assert parsed["event_age_seconds"] > 7 * 86_400
