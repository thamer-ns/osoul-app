from __future__ import annotations

from pathlib import Path

import bot_contract_runtime_v10 as contract
import live_market_report_v17 as report_v17
import live_market_runtime_v17 as runtime_v17

ROOT = Path(__file__).resolve().parents[1]


def test_single_source_does_not_claim_agreement() -> None:
    payload = runtime_v17._normalize(  # noqa: SLF001
        {
            "price": 26.55,
            "source": "sahmk",
            "source_count": 1,
            "source_agreement_pct": 0.0,
            "fusion_version": "16.0",
        }
    )
    assert payload["source_spread_pct"] == 0.0
    assert payload["source_agreement_pct_semantics"] == "spread_not_agreement"
    assert payload["comparison_label"] == (
        "مصدر واحد — لا يمكن قياس اتفاق المصادر"
    )
    assert payload["closed_candle_price_preserved"] is True
    assert payload["live_price_is_context_only"] is True


def test_multi_source_value_is_named_spread() -> None:
    payload = runtime_v17._normalize(  # noqa: SLF001
        {
            "price": 26.55,
            "source": "sahmk",
            "source_count": 3,
            "source_agreement_pct": 0.12,
        }
    )
    assert payload["source_spread_pct"] == 0.12
    assert payload["comparison_label"] == "فارق المصادر 0.12%"


def test_public_report_keeps_v17_semantics() -> None:
    public = report_v17._public_quote(  # noqa: SLF001
        runtime_v17._normalize(  # noqa: SLF001
            {
                "price": 26.55,
                "source": "sahmk",
                "source_count": 1,
                "source_agreement_pct": 0.0,
                "quote_age_seconds": 21,
            }
        )
    )
    assert public["price"] == 26.55
    assert public["comparison_label"].startswith("مصدر واحد")
    assert public["closed_candle_price_preserved"] is True
    assert public["live_price_is_context_only"] is True
    assert public["fusion_version"] == "17.0"


def test_osoli_expects_the_v61_bot_contract() -> None:
    assert contract.EXPECTED_CONTRACT == "SC-V92.5-v1-plan-isolation-v61"
    assert contract.EXPECTED_RUNTIME_VERSION == "61.0"
    assert contract.EXPECTED_FEATURE_VERSION == "58.0"


def test_production_routes_install_v17_not_v15() -> None:
    source = (ROOT / "analysis_routes_v5.py").read_text(encoding="utf-8")
    assert "install_live_market_runtime_v17" in source
    assert "install_live_market_report_v17" in source
    assert "install_live_market_runtime_v15" not in source


def test_remote_contract_checks_closed_price_integrity() -> None:
    source = (ROOT / "ai_engine_core" / "bot_remote_analysis_v8.py").read_text(
        encoding="utf-8"
    )
    assert "closed_price_mismatch" in source
    assert "closed_price_may_be_overwritten" in source
    assert "source_comparison_semantics_unsafe" in source
