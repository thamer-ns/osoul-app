from __future__ import annotations

import copy

from ai_engine_core import decision_policy_v6 as decision
import live_market_report_v15 as live_report


def _current_pack() -> dict:
    return {
        "ok": True,
        "indicator_contract": "SC-V92.5/SC-FXM-V16",
        "qualified": False,
        "direction": 0,
        "confidence": 60,
        "event_code": "WATCH",
        "opposition_veto": {"blocked": False},
        "risk_plan": {"valid": False},
        "priority_order": [
            "sr_cluster",
            "confirmed_pivot",
            "secondary_tools",
        ],
    }


def test_current_sc_pack_skips_legacy_v91_decision_path(monkeypatch) -> None:
    raw = {
        "status": "ok",
        "tech_score": 71.0,
        "total_score": 71.0,
        "lifecycle_status": "HEADS_UP",
        "sc_feature_pack": _current_pack(),
        "engine_meta": {},
    }
    calls: list[str] = []

    def v4(report, *, symbol, timeframe):
        calls.append(f"v4:{symbol}:{timeframe}")
        return copy.deepcopy(report)

    def forbidden_v5(*_args, **_kwargs):
        raise AssertionError("SC-V91/V5 must not run beside a current V92.5 pack")

    monkeypatch.setattr(decision, "_v4_enrich_report", v4)
    monkeypatch.setattr(decision, "_v5_enrich_report", forbidden_v5)
    monkeypatch.setattr(decision, "_attach_external_context", lambda *_args: None)
    monkeypatch.setattr(decision, "_attach_financial_lineage", lambda *_args: None)
    monkeypatch.setattr(decision, "_data_reliability", lambda _report: {"pass": True})
    monkeypatch.setattr(decision, "_advisor_intelligence", lambda _report: {})

    result = decision.enrich_report(raw, symbol="2222", timeframe="1D")

    assert calls == ["v4:2222:1D"]
    assert result["tech_score"] == 71.0
    assert result["total_score"] == 71.0
    assert result["engine_meta"]["legacy_sc_v91_skipped"] is True
    assert result["analysis_contract"]["legacy_sc_v91_decision_influence"] is False


def test_old_report_without_current_pack_keeps_compatibility_path(monkeypatch) -> None:
    expected = {"status": "ok", "lifecycle_status": "HEADS_UP"}
    monkeypatch.setattr(
        decision,
        "_v5_enrich_report",
        lambda report, *, symbol, timeframe: copy.deepcopy(expected),
    )

    result = decision.enrich_report({}, symbol="AAPL", timeframe="1D")

    assert result["status"] == "ok"
    assert result["sc_v925_decision"]["available"] is False


def test_live_quote_attachment_cannot_change_final_decision(monkeypatch) -> None:
    final = {
        "direction": 1,
        "lifecycle_status": "ACTIONABLE",
        "recommendation": "شراء مشروط",
        "risk_plan": {
            "entry": 100.0,
            "stop": 98.0,
            "target1": 103.0,
            "target2": 106.0,
        },
        "plan_geometry": {"valid": True, "target_r": [1.5, 3.0]},
        "features": {"closed_candle_feature": 1},
        "engine_meta": {"decision_engine_version": "6.0"},
    }
    protected = {
        name: copy.deepcopy(final[name])
        for name in (
            "direction",
            "lifecycle_status",
            "recommendation",
            "risk_plan",
            "plan_geometry",
        )
    }
    monkeypatch.setattr(live_report, "_saudi_symbol", lambda _symbol: ("2222", "2222.SR"))
    monkeypatch.setattr(
        live_report,
        "fetch_live_quote",
        lambda _symbol: (
            {
                "price": 101.0,
                "source": "sahmk",
                "delay_status": "realtime",
                "freshness_status": "fresh",
                "price_confidence": "high",
                "price_conflict": False,
                "source_count": 2,
                "source_agreement_pct": 0.1,
                "decision_use": "live_context_only_closed_candle_confirmation",
                "browser_sources_used_for_decision": False,
                "fusion_version": "16.0",
            },
            [],
        ),
    )

    result = live_report._attach_live_context(final, symbol="2222")

    for name, value in protected.items():
        assert result[name] == value
    assert result["live_quote_context"]["price"] == 101.0
    assert result["features"]["live_price"] == 101.0
    assert result["engine_meta"]["live_quote"][
        "attached_after_final_decision"
    ] is True
    assert result["engine_meta"]["live_quote"]["changes_signal"] is False
