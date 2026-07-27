from __future__ import annotations

from views import PAGES_REQUIRING_PORTFOLIO
from views import portfolios


def test_portfolios_hub_contains_exactly_the_three_requested_sections():
    assert portfolios._SECTION_KEYS == ("spec", "invest", "sukuk")
    assert set(portfolios._SECTION_META) == set(portfolios._SECTION_KEYS)

    for key in portfolios._SECTION_KEYS:
        meta = portfolios._SECTION_META[key]
        assert str(meta["label"]).strip()
        assert str(meta["icon"]).strip()
        assert str(meta["description"]).strip()
        assert str(meta["module"]).startswith("views.")
        assert str(meta["renderer"]).startswith("view_")
        assert isinstance(meta.get("args"), tuple)


def test_router_loads_portfolio_once_for_the_portfolios_hub():
    assert "portfolios" in PAGES_REQUIRING_PORTFOLIO
    assert "spec" not in PAGES_REQUIRING_PORTFOLIO
    assert "invest" not in PAGES_REQUIRING_PORTFOLIO
    assert "sukuk" not in PAGES_REQUIRING_PORTFOLIO


def test_portfolio_sections_use_the_fast_or_dedicated_renderer():
    assert portfolios._SECTION_META["spec"]["module"] == "views.fast_portfolio"
    assert portfolios._SECTION_META["spec"]["args"] == ("spec",)
    assert portfolios._SECTION_META["invest"]["module"] == "views.fast_portfolio"
    assert portfolios._SECTION_META["invest"]["args"] == ("invest",)
    assert portfolios._SECTION_META["sukuk"]["module"] == "views.sukuk"
    assert portfolios._SECTION_META["sukuk"]["args"] == ()
