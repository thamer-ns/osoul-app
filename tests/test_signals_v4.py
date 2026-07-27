from __future__ import annotations

import inspect

from views import signals
from views import signals_v4


def test_signal_center_supports_full_compass_timeframe_range():
    assert set(signals.TIMEFRAMES) == {
        "1m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"
    }


def test_signal_center_runs_only_after_user_action_and_shows_v4_fields():
    source = inspect.getsource(signals_v4.view_signals)
    module_source = inspect.getsource(signals_v4)
    assert "تشغيل مسح الإشارات" in source
    assert "if run or refresh" in source
    assert "school_consensus" in module_source
    assert "plan_geometry" in module_source
    assert "لا يوجد تنفيذ أوامر" in module_source


def test_legacy_signal_module_is_a_small_v4_compatibility_route():
    assert signals.view_signals is signals_v4.view_signals
    assert signals._decision_fields is signals_v4._decision_fields
