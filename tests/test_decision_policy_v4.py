from __future__ import annotations

from ai_engine_core.decision_policy_v4 import audit_plan_geometry, build_school_consensus


def test_one_strong_actionable_school_qualifies_without_double_counting():
    report = {"features": {"liq_sweep_low": 1}}

    consensus = build_school_consensus(report)

    assert consensus["qualified"] is True
    assert consensus["strong_single_school"] is True
    assert consensus["direction"] == "buy"
    assert consensus["school_count"] == 1
    assert len(set(consensus["independent_axes"])) == consensus["school_count"]


def test_two_independent_aligned_schools_qualify():
    report = {
        "features": {
            "close": 110,
            "sma50": 100,
            "sma200": 90,
            "rsi14": 58,
            "macd": 2,
        },
        "tech_reasons": ["اتجاه صاعد فوق المتوسطات", "زخم صاعد MACD وRSI"],
    }

    consensus = build_school_consensus(report)

    assert consensus["qualified"] is True
    assert consensus["school_count"] >= 2
    assert {"trend", "momentum"}.issubset(set(consensus["independent_axes"]))


def test_same_axis_evidence_is_not_counted_as_multiple_schools():
    report = {
        "tech_reasons": [
            "RSI صاعد مؤكد",
            "MACD صاعد مؤكد",
            "زخم صاعد مؤكد بالإغلاق",
        ]
    }

    consensus = build_school_consensus(report)

    assert consensus["school_count"] <= 1
    assert consensus["qualified"] is False or consensus["strong_single_school"] is True


def test_geometry_requires_directional_order_and_timeframe_atr_limits():
    valid = {
        "direction": "buy",
        "features": {"atr14": 2.0},
        "risk_plan": {
            "entry": 100.0,
            "stop": 98.0,
            "target1": 102.0,
            "target2": 104.0,
            "target3": 106.0,
        },
    }
    audit = audit_plan_geometry(valid, "1d")
    assert audit["valid"] is True
    assert audit["target_r"] == [1.0, 2.0, 3.0]

    invalid = {
        "direction": "sell",
        "features": {"atr14": 1.0},
        "risk_plan": {
            "entry": 100.0,
            "stop": 99.0,
            "target1": 101.0,
            "target2": 102.0,
            "target3": 103.0,
        },
    }
    bad_audit = audit_plan_geometry(invalid, "15m")
    assert bad_audit["valid"] is False
    assert bad_audit["issues"]
