from __future__ import annotations

import inspect

from views import pulse


def test_pulse_tracks_open_stock_positions_only():
    source = inspect.getsource(pulse.view_pulse)
    assert 'status == "open"' in source
    assert 'asset_type.eq("sukuk")' in source
    assert "fetch_batch_data(symbols)" in source
    assert "ليست توصية شراء أو بيع" in source


def test_pulse_is_a_dedicated_lazy_page():
    from views import _render_page

    source = inspect.getsource(_render_page)
    assert '"pulse": ("views.pulse", "view_pulse", ())' in source
