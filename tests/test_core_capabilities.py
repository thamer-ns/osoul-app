from __future__ import annotations

import inspect
from types import SimpleNamespace

import feature_flags
from views import _render_page
from views import settings_core


def test_useful_capabilities_are_permanent_and_obsolete_flags_are_removed(monkeypatch):
    monkeypatch.setattr(feature_flags, "st", SimpleNamespace(session_state={}))

    assert feature_flags.get_flag("enable_strategy_notes") is True
    assert feature_flags.get_flag("use_ar_wrappers") is True
    assert feature_flags.get_flag("enable_self_learning") is True
    assert feature_flags.get_flag("enable_xirr") is False
    assert feature_flags.get_flag("enable_engine_compare") is False
    assert "enable_xirr" not in feature_flags.CORE_CAPABILITIES
    assert "enable_engine_compare" not in feature_flags.CORE_CAPABILITIES


def test_settings_show_integrated_capabilities_without_experimental_checkboxes():
    source = inspect.getsource(settings_core)
    router_source = inspect.getsource(_render_page)

    assert "ميزات التحليل المدمجة" in source
    assert "مقارنة المحرك القديم والجديد" in source
    assert "st.checkbox" not in source
    assert '"settings": ("views.settings_core", "view_settings", ())' in router_source
    assert '"tools": ("views.tools_core", "view_tools", ())' in router_source
