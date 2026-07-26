from __future__ import annotations

import pandas as pd

from financial_analysis.metrics import _piotroski_score


def test_piotroski_does_not_award_missing_criteria():
    current = pd.Series({"net_income": 10.0, "total_assets": 100.0, "operating_cash_flow": 12.0})
    previous = pd.Series({"net_income": 5.0, "total_assets": 100.0})

    score, coverage, criteria = _piotroski_score(current, previous)

    assert coverage == 4
    assert score == 4
    assert criteria["no_share_dilution"] is None
    assert criteria["higher_gross_margin"] is None


def test_piotroski_full_nine_criteria():
    current = pd.Series(
        {
            "net_income": 15.0,
            "operating_cash_flow": 20.0,
            "total_assets": 100.0,
            "long_term_debt": 10.0,
            "current_assets": 60.0,
            "current_liabilities": 20.0,
            "shares_outstanding": 100.0,
            "revenue": 120.0,
            "gross_profit": 60.0,
        }
    )
    previous = pd.Series(
        {
            "net_income": 5.0,
            "total_assets": 100.0,
            "long_term_debt": 20.0,
            "current_assets": 40.0,
            "current_liabilities": 20.0,
            "shares_outstanding": 100.0,
            "revenue": 80.0,
            "gross_profit": 32.0,
        }
    )

    score, coverage, _ = _piotroski_score(current, previous)

    assert coverage == 9
    assert score == 9


def test_piotroski_single_period_does_not_fake_comparative_points():
    current = pd.Series(
        {
            "net_income": 10.0,
            "operating_cash_flow": 12.0,
            "total_assets": 100.0,
            "shares_outstanding": 100.0,
        }
    )
    score, coverage, criteria = _piotroski_score(current, pd.Series(dtype=object))

    assert score == 4
    assert coverage == 4
    assert criteria["no_share_dilution"] is None
