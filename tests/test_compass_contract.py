from __future__ import annotations

import json

import pytest

from ai_engine_core.compass_contract import compare_compass_with_report, parse_compass_payload


def _payload(**overrides):
    value = {
        "v": 1,
        "s": "SC-V88-D",
        "e": "ENTRY_LONG",
        "x": "TADAWUL:1120",
        "y": "stock",
        "f": "D",
        "t": 1_800_000_000_000,
        "p": 100,
        "d": 1,
        "en": 100,
        "sl": 98,
        "t1": 102,
        "t2": 104,
        "t3": 106,
        "n": 3,
        "q": 8,
        "qm": 10,
        "ct": False,
    }
    value.update(overrides)
    return value


def test_valid_compass_payload_is_normalized_and_geometry_audited():
    result = parse_compass_payload(json.dumps(_payload()))

    assert result["timeframe"] == "1d"
    assert result["direction"] == "buy"
    assert result["confidence"] == 80.0
    assert result["geometry"]["valid"] is True
    assert result["geometry"]["target_r"] == [1.0, 2.0, 3.0]


def test_nan_and_mismatched_targets_are_rejected():
    with pytest.raises(ValueError):
        parse_compass_payload(_payload(p="NaN"))
    with pytest.raises(ValueError):
        parse_compass_payload(_payload(n=2))


def test_reversed_plan_is_retained_as_evidence_but_marked_invalid():
    result = parse_compass_payload(_payload(d=-1, en=100, sl=98, t1=102, t2=104, t3=106))
    assert result["geometry"]["valid"] is False


def test_compass_comparison_never_changes_native_decision():
    external = parse_compass_payload(_payload())
    native = {
        "symbol": "1120.SR",
        "direction": "sell",
        "analysis_contract": {"timeframe": "1d"},
    }
    comparison = compare_compass_with_report(external, native)
    assert comparison["aligned"] is False
    assert comparison["decision_effect"] == "none"
    assert "اتجاه البوصلة يعاكس اتجاه أصولي" in comparison["conflicts"]
