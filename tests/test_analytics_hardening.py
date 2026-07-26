from datetime import date, timedelta

import pandas as pd

from analytics_hardening import compute_portfolio_xirr


def test_xirr_does_not_double_count_internal_returns():
    start = date.today() - timedelta(days=365)
    deposits = pd.DataFrame([{"date": start, "amount": 1000.0}])
    withdrawals = pd.DataFrame()
    internal_returns = pd.DataFrame([{"date": date.today() - timedelta(days=30), "amount": 50.0}])

    rate, method = compute_portfolio_xirr(deposits, withdrawals, internal_returns, ending_value=1100.0)

    assert method == "cashflow_bisection_v2"
    assert rate is not None
    assert abs(rate - 0.10) < 0.01


def test_xirr_requires_positive_and_negative_external_flows():
    rate, note = compute_portfolio_xirr(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), ending_value=1000.0)
    assert rate is None
    assert note == "no_convergence"
