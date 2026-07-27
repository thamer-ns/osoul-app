from __future__ import annotations

import pandas as pd

from ai_engine_core.portfolio import (
    _get_open_trades,
    _speculation_market_value_ratio,
)


def test_speculation_ratio_is_market_value_weighted():
    frame = pd.DataFrame(
        [
            {"status": "Open", "strategy": "مضاربة", "market_value": 10.0},
            {"status": "Open", "strategy": "استثمار", "market_value": 990.0},
        ]
    )
    assert abs(_speculation_market_value_ratio(frame) - 0.01) < 1e-12


def test_open_status_supports_arabic_values():
    frame = pd.DataFrame(
        [
            {"status": "مفتوحة", "symbol": "1120.SR"},
            {"status": "مغلقة", "symbol": "1150.SR"},
        ]
    )
    opened = _get_open_trades(frame)
    assert opened["symbol"].tolist() == ["1120.SR"]
