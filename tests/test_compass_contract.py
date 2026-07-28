from __future__ import annotations

import json
import time

import pytest

from ai_engine_core.compass_contract import compare_compass_with_report, parse_compass_payload
from ai_engine_core.timeframe_contract import CANONICAL_TIMEFRAMES, canonical_timeframe


def _payload(**overrides):
    value = {
        "v": 1,
        "s": "SC-V90-D",
        "e": "NL",
        "x": "TADAWUL:1120",
        "y": "stock",
        "f": "1d",
        "t": int(time.time() * 1000) - 1_000,
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


def test_current_sc_v90_payload_is_normalized_and_geometry_audited():
    result = parse_compass_payload(json.dumps(_payload()))
    assert result["source"] == "SC-V90-D"
    assert result["source_generation"] == "current"
    assert result["timeframe"] == "1d"
    assert result["event"] == "NL"
    assert result["direction"] == "buy"
    assert result["confidence"] == 80.0
    assert result["geometry"]["valid"] is True
    assert result["geometry"]["target_r"] == [1.0, 2.0, 3.0]


def test_minute_week_and_month_wires_are_unambiguous():
    assert canonical_timeframe("5m") == "5m"
    assert canonical_timeframe("1wk") == "1wk"
    assert canonical_timeframe("1mo") == "1mo"
    assert "5m" in CANONICAL_TIMEFRAMES
    assert "1wk" in CANONICAL_TIMEFRAMES
    assert "1mo" in CANONICAL_TIMEFRAMES


def test_intraday_and_daily_source_timeframe_rules():
    assert parse_compass_payload(_payload(s="SC-V90-I", f="5m"))["timeframe"] == "5m"
    with pytest.raises(ValueError):
        parse_compass_payload(_payload(s="SC-V90-I", f="1d"))
    with pytest.raises(ValueError):
        parse_compass_payload(_payload(s="SC-V90-D", f="5m"))


def test_nan_future_time_unknown_source_and_bad_targets_are_rejected():
    with pytest.raises(ValueError):
        parse_compass_payload(_payload(p="NaN"))
    with pytest.raises(ValueError):
        parse_compass_payload(_payload(t=int(time.time() * 1000) + 600_000))
    with pytest.raises(ValueError):
        parse_compass_payload(_payload(s="UNTRUSTED"))
    with pytest.raises(ValueError):
        parse_compass_payload(_payload(n=2))


def test_reversed_plan_is_rejected_not_saved_as_weak_evidence():
    with pytest.raises(ValueError):
        parse_compass_payload(
            _payload(d=-1, e="NS", en=100, sl=98, t1=102, t2=104, t3=106)
        )


def test_legacy_entry_alias_is_migration_compatible():
    result = parse_compass_payload(_payload(s="SC-V88-D", e="ENTRY_LONG"))
    assert result["event"] == "NL"
    assert result["source_generation"] == "legacy"


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
