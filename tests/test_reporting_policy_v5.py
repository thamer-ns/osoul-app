from ai_engine_core.reporting_policy_v5 import timeframe_to_interval


def test_minute_and_month_timeframes_are_not_confused():
    assert timeframe_to_interval("1m") == "1m"
    assert timeframe_to_interval("1min") == "1m"
    assert timeframe_to_interval("1mo") == "1mo"
    assert timeframe_to_interval("month") == "1mo"


def test_four_hour_and_weekly_routes_are_supported():
    assert timeframe_to_interval("4h") == "4h"
    assert timeframe_to_interval("240m") == "4h"
    assert timeframe_to_interval("1wk") == "1wk"
    assert timeframe_to_interval("1W") == "1wk"
