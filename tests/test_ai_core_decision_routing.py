import ai_engine_core


def test_public_report_path_always_passes_through_decision_layer(monkeypatch):
    calls = []

    def fake_lazy_attr(module_name, attr_name):
        if (module_name, attr_name) == (".reporting", "generate_ai_report"):
            return lambda *args, **kwargs: {"status": "ok", "raw_marker": True}
        if (module_name, attr_name) == (".decision_engine_v3", "enrich_report"):
            def enrich(report, *, symbol, timeframe):
                calls.append((report, symbol, timeframe))
                return {"status": "ok", "routed": True}
            return enrich
        raise AssertionError((module_name, attr_name))

    monkeypatch.setattr(ai_engine_core, "_lazy_attr", fake_lazy_attr)

    result = ai_engine_core.generate_ai_report("1120.SR", timeframe="1D")

    assert result == {"status": "ok", "routed": True}
    assert calls == [({"status": "ok", "raw_marker": True}, "1120.SR", "1D")]
