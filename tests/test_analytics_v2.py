from datetime import datetime, timedelta, timezone

import pandas as pd

from analytics_v2 import _normalize_trade_status, compute_portfolio_xirr


def test_closed_trade_normalization_uses_exit_price():
    frame = pd.DataFrame(
        [
            {"status": "Open", "exit_price": 0, "exit_date": None},
            {"status": "Open", "exit_price": 12.5, "exit_date": None},
        ]
    )
    result = _normalize_trade_status(frame)
    assert result["status"].tolist() == ["Open", "Close"]


def test_xirr_does_not_double_count_internal_distributions():
    start = datetime.now(timezone.utc) - timedelta(days=365)
    deposits = pd.DataFrame([{"date": start, "amount": 1000.0}])
    withdrawals = pd.DataFrame()
    internal_returns = pd.DataFrame(
        [{"date": start + timedelta(days=180), "amount": 100.0}]
    )

    value, note = compute_portfolio_xirr(
        deposits,
        withdrawals,
        internal_returns,
        ending_value=1100.0,
    )
    assert note in {"bisect", "bracket"}
    assert value is not None
    assert 0.08 <= value <= 0.12
