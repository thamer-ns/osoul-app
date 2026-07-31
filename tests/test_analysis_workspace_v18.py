from __future__ import annotations

import pandas as pd

from views.analysis.workspace_v18 import (
    _advisor_action,
    _decision,
    _levels,
    _position_size,
    _targets,
)


def _report(direction: str = "buy", lifecycle: str = "ACTIONABLE") -> dict:
    return {
        "direction": direction,
        "lifecycle_status": lifecycle,
        "confidence": 82,
        "risk_plan": {
            "entry": 100.0,
            "stop": 98.0,
            "target1": 104.0,
            "target2": 108.0,
            "target3": 112.0,
            "expiry_bars": 6,
        },
        "plan_geometry": {"valid": True, "target_r": [2.0, 4.0, 6.0]},
        "sc_feature_pack": {
            "sr": {
                "support": {"level": 98.5},
                "resistance": {"level": 103.0},
            }
        },
    }


def test_actionable_long_is_presented_as_upside_plan() -> None:
    decision = _decision(_report())
    assert decision["actionable"] is True
    assert decision["direction"] == 1
    assert decision["action"] == "دخول صاعد مشروط"
    assert _targets(decision["plan"]) == [104.0, 108.0, 112.0]


def test_actionable_short_is_presented_as_downside_plan() -> None:
    report = _report(direction="sell")
    report["risk_plan"] = {
        "entry": 100.0,
        "stop": 102.0,
        "targets": [96.0, 92.0],
    }
    decision = _decision(report)
    assert decision["actionable"] is True
    assert decision["direction"] == -1
    assert decision["action"] == "دخول هابط مشروط"


def test_non_actionable_report_is_monitoring_not_a_trade() -> None:
    report = _report(direction="neutral", lifecycle="NO_SETUP")
    report["risk_plan"] = {}
    decision = _decision(report)
    assert decision["actionable"] is False
    assert decision["action"] == "مراقبة"
    assert _levels(report) == (98.5, 103.0)


def test_advisor_uses_open_position_context() -> None:
    finance = {
        "portfolio_value": 100_000.0,
        "all_trades": pd.DataFrame(
            [
                {
                    "symbol": "2222.SR",
                    "status": "open",
                    "quantity": 100,
                    "entry_price": 95.0,
                }
            ]
        ),
    }
    advice = _advisor_action(_report(), finance, "2222.SR")
    assert advice["position"]["has_position"] is True
    assert advice["position"]["average_entry"] == 95.0
    assert "احتفاظ مشروط" in advice["title"]


def test_position_size_is_capped_by_risk_and_concentration() -> None:
    finance = {"portfolio_value": 100_000.0, "all_trades": pd.DataFrame()}
    size = _position_size(_report(), finance)
    assert size["risk_budget"] == 1_000.0
    assert size["risk_per_unit"] == 2.0
    assert size["units"] == 200
    assert size["position_value"] == 20_000.0
