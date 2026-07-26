from ai_engine_core.decision_engine_v3 import enrich_report


def _report(
    *,
    total=8.0,
    confidence=82,
    adv_direction=72,
    adv_confidence=80,
    agreement=0.8,
    direction_market="bull",
    risk_pass=True,
    liquidity_pass=True,
    mtf_aligned=True,
    dq_pass=True,
    close=100.0,
    atr=2.0,
    reasons=None,
):
    return {
        "status": "ok",
        "total_score": total,
        "tech_score": total,
        "fund_score": 0,
        "confidence": confidence,
        "recommendation": "raw",
        "strategy": "raw",
        "features": {
            "close": close,
            "atr14": atr,
            "adv_direction_score": adv_direction,
            "adv_confidence": adv_confidence,
            "adv_agreement": agreement,
            "dq_pass": 1 if dq_pass else 0,
            "liquidity_pass": 1 if liquidity_pass else 0,
            "mtf_applied": 1,
            "mtf_aligned": 1 if mtf_aligned else 0,
        },
        "risk_plan": {
            "entry": close,
            "stop": close - 2 * atr if total > 0 else close + 2 * atr,
        },
        "risk_gates": {"pass": risk_pass, "reasons": [] if risk_pass else ["blocked"]},
        "calibration": {
            "liquidity_gate": {"pass": liquidity_pass},
            "multi_timeframe": {"applied": True, "aligned": mtf_aligned},
        },
        "learning_context": {"market_trend": direction_market, "regime": "trend"},
        "tech_reasons": reasons or ["اختراق مقاومة بإغلاق الشمعة", "MACD bullish cross"],
        "engine_meta": {"interval_used": "1d", "last_bar": "2026-07-26", "rows": 250},
    }


def test_actionable_buy_plan_is_monotonic_and_close_confirmed():
    result = enrich_report(_report(), symbol="1120.SR", timeframe="1D")
    plan = result["decision_engine"]["plan"]

    assert result["lifecycle_status"] == "ACTIONABLE"
    assert result["direction"] == "buy"
    assert result["opportunity_type"] in {"ULTIMATE_BUY", "STRONG_BREAKOUT"}
    assert plan["stop"] < plan["entry"] < plan["target1"] < plan["target2"] < plan["target3"]
    assert plan["confirmation"] == "candle_close"
    assert result["decision_engine"]["confirmation"] == "candle_close"


def test_actionable_sell_plan_has_direction_safe_levels():
    result = enrich_report(
        _report(
            total=-8.0,
            adv_direction=-70,
            direction_market="bear",
            reasons=["كسر دعم بإغلاق الشمعة", "MACD bearish cross"],
        ),
        symbol="1120.SR",
        timeframe="1D",
    )
    plan = result["risk_plan"]

    assert result["lifecycle_status"] == "ACTIONABLE"
    assert result["direction"] == "sell"
    assert plan["target3"] < plan["target2"] < plan["target1"] < plan["entry"] < plan["stop"]


def test_contradiction_penalises_confidence_and_prevents_false_ultimate_signal():
    result = enrich_report(
        _report(total=7.0, confidence=75, adv_direction=-80, agreement=0.9),
        symbol="1120.SR",
        timeframe="1D",
    )

    assert result["decision_engine"]["contradiction"] is True
    assert result["confidence"] < 75
    assert result["opportunity_type"] not in {"ULTIMATE_BUY", "ULTIMATE_SELL"}


def test_failed_risk_gate_blocks_execution():
    result = enrich_report(
        _report(risk_pass=False),
        symbol="1120.SR",
        timeframe="1D",
    )

    assert result["lifecycle_status"] == "BLOCKED"
    assert result["decision_engine"]["blockers"]
    assert "محظور" in result["recommendation"]


def test_neutral_report_does_not_invent_a_plan():
    result = enrich_report(
        _report(total=0.2, confidence=70, adv_direction=0, agreement=0),
        symbol="1120.SR",
        timeframe="1D",
    )

    assert result["lifecycle_status"] == "NO_SETUP"
    assert result["risk_plan"]["entry"] is None
    assert "targets" not in result


def test_internal_trace_is_never_returned_to_ui():
    secret = "database-password-and-private-stack"
    result = enrich_report(
        {"status": "error", "__error__": secret, "__trace__": secret},
        symbol="1120.SR",
        timeframe="1D",
    )

    serialized = repr(result)
    assert "__trace__" not in result
    assert secret not in serialized
    assert result["status"] == "error"
    assert result["error_id"]


def test_plan_id_is_deterministic_for_same_closed_bar():
    report = _report()
    first = enrich_report(report, symbol="1120.SR", timeframe="1D")
    second = enrich_report(report, symbol="1120.SR", timeframe="1D")

    assert first["risk_plan"]["plan_id"] == second["risk_plan"]["plan_id"]


def test_liquidity_reclaim_classification():
    report = _report(confidence=70, agreement=0.2, reasons=["صيد سيولة بيعية"])
    report["features"]["liq_sweep_low"] = 1

    result = enrich_report(report, symbol="1120.SR", timeframe="1D")

    assert result["opportunity_type"] == "LIQUIDITY_RECLAIM"
