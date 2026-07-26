from ai_engine_core.decision_policy_v3 import enrich_report


def _report(*, total=7.0, confidence=72, stop=96.0, reasons=None):
    return {
        "status": "ok",
        "total_score": total,
        "confidence": confidence,
        "features": {
            "close": 100.0,
            "atr14": 2.0,
            "adv_direction_score": 60.0 if total > 0 else -60.0,
            "adv_confidence": 70.0,
            "adv_agreement": 0.2,
        },
        "risk_plan": {"entry": 100.0, "stop": stop},
        "risk_gates": {"pass": True, "reasons": []},
        "tech_reasons": reasons or [],
        "engine_meta": {"interval_used": "1d", "last_bar": "2026-07-26", "rows": 250},
    }


def test_generic_watch_breakout_is_not_promoted_to_strong_breakout():
    result = enrich_report(
        _report(reasons=["السعر قرب سقف النطاق (مراقبة اختراق)"]),
        symbol="1120.SR",
        timeframe="1D",
    )

    assert result["opportunity_type"] == "STRUCTURE_SETUP"
    assert result["decision_engine"]["semantic_confirmation_policy"] == "explicit_close_evidence"


def test_explicit_candle_close_breakout_keeps_strong_classification():
    result = enrich_report(
        _report(reasons=["اختراق مقاومة بإغلاق الشمعة"]),
        symbol="1120.SR",
        timeframe="1D",
    )

    assert result["opportunity_type"] == "STRONG_BREAKOUT"


def test_extreme_sell_risk_is_blocked_instead_of_creating_zero_targets():
    result = enrich_report(
        _report(
            total=-7.0,
            stop=160.0,
            reasons=["كسر دعم بإغلاق الشمعة"],
        ),
        symbol="1120.SR",
        timeframe="1D",
    )

    assert result["lifecycle_status"] == "BLOCKED"
    assert result["risk_plan"]["target1"] is None
    assert result["risk_plan"]["target2"] is None
    assert result["risk_plan"]["target3"] is None
    assert result["targets"] == []
    assert result["decision_engine"]["blockers"]


def test_normal_sell_plan_remains_actionable_and_ordered():
    result = enrich_report(
        _report(
            total=-7.0,
            stop=104.0,
            reasons=["كسر دعم بإغلاق الشمعة"],
        ),
        symbol="1120.SR",
        timeframe="1D",
    )
    plan = result["risk_plan"]

    assert result["lifecycle_status"] == "ACTIONABLE"
    assert 0 < plan["target3"] < plan["target2"] < plan["target1"] < plan["entry"] < plan["stop"]
