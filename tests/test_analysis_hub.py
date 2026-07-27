from __future__ import annotations

from views import PAGES_REQUIRING_PORTFOLIO
from views import insights


def test_analysis_hub_contains_exactly_the_three_requested_sections():
    assert insights._SECTION_KEYS == ("analysis", "signals", "backtest")
    assert set(insights._SECTION_META) == set(insights._SECTION_KEYS)

    for key in insights._SECTION_KEYS:
        meta = insights._SECTION_META[key]
        assert str(meta["label"]).strip()
        assert str(meta["icon"]).strip()
        assert str(meta["description"]).strip()
        assert str(meta["module"]).startswith("views.")
        assert str(meta["renderer"]).startswith("view_")


def test_router_loads_portfolio_once_for_the_analysis_hub():
    assert "insights" in PAGES_REQUIRING_PORTFOLIO
    assert "analysis" not in PAGES_REQUIRING_PORTFOLIO
    assert "signals" not in PAGES_REQUIRING_PORTFOLIO
    assert "backtest" not in PAGES_REQUIRING_PORTFOLIO
