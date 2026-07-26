from datetime import date, timedelta

import pandas as pd

from analytics_hardening import (
    _external_cashflows,
    compute_portfolio_xirr,
)


def _scenario():
    start = date.today() - timedelta(days=365)
    deposits = pd.DataFrame([{"date": start, "amount": 1000.0}])
    withdrawals = pd.DataFrame()
    internal_returns = pd.DataFrame(
        [
            {
                "date": date.today() - timedelta(days=30),
                "amount": 50.0,
            }
        ]
    )
    return deposits, withdrawals, internal_returns


def test_internal_return_is_not_external_cashflow():
    deposits, withdrawals, internal_returns = _scenario()
    flows = _external_cashflows(
        deposits,
        withdrawals,
        internal_returns,
        ending_value=1100.0,
    )
    assert len(flows) == 2
    assert [amount for _, amount in flows] == [-1000.0, 1100.0]


def test_xirr_uses_stable_bisection_method():
    deposits, withdrawals, internal_returns = _scenario()
    rate, method = compute_portfolio_xirr(
        deposits,
        withdrawals,
        internal_returns,
        ending_value=1100.0,
    )
    assert method == "cashflow_bisection_v2"
    assert rate is not None


def test_xirr_numeric_rate_is_about_ten_percent():
    deposits, withdrawals, internal_returns = _scenario()
    rate, _ = compute_portfolio_xirr(
        deposits,
        withdrawals,
        internal_returns,
        ending_value=1100.0,
    )
    assert rate is not None
    assert abs(rate - 0.10) < 0.01


def test_xirr_requires_positive_and_negative_external_flows():
    rate, note = compute_portfolio_xirr(
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        ending_value=1000.0,
    )
    assert rate is None
    assert note == "no_convergence"
