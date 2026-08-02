from ai_engine_core import compass_contract as contract


def test_current_indicator_sources_are_registered():
    assert {"SC-V94.7-I", "SC-V94.7-D"} <= contract.STRICT_SOURCES
    assert "SC-FXM-V18.8" in contract.STRICT_SOURCES
    assert "SC-V94.7-I" in contract.INTRADAY_STOCK_SOURCES
    assert "SC-V94.7-D" in contract.DAILY_STOCK_SOURCES


def test_historical_sources_remain_accepted():
    assert {"SC-V92-I", "SC-V92-D", "SC-V90-I", "SC-V90-D"} <= contract.STRICT_SOURCES
    assert {"SC-FXM-V16", "SC-FXM-V14"} <= contract.STRICT_SOURCES
