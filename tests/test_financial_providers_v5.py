from __future__ import annotations

from financial_providers_v5 import _merge_period_rows, _normalize_rows, assess_summary_quality


def test_statement_rows_merge_by_period_and_keep_missing_values_missing():
    income = [
        {"date": "2025-12-31", "revenue": 1000, "netIncome": 120},
        {"date": "2024-12-31", "revenue": 900, "netIncome": 100},
    ]
    balance = [
        {"date": "2025-12-31", "totalAssets": 2000, "totalLiabilities": 800, "totalStockholdersEquity": 1200},
        {"date": "2024-12-31", "totalAssets": 1800, "totalLiabilities": 750, "totalStockholdersEquity": 1050},
    ]
    cash = [
        {"date": "2025-12-31", "operatingCashFlow": 150, "capitalExpenditure": -40},
        {"date": "2024-12-31", "operatingCashFlow": 130, "capitalExpenditure": -35},
    ]

    frame = _normalize_rows(
        _merge_period_rows(income, balance, cash),
        source="fixture",
        period_type="Annual",
        currency="SAR",
    )

    assert len(frame) == 2
    assert frame.iloc[0]["revenue"] == 1000
    assert frame.iloc[0]["free_cash_flow"] == 110
    assert frame.iloc[0]["currency"] == "SAR"
    assert frame.iloc[0]["current_assets"] is None or str(frame.iloc[0]["current_assets"]) == "nan"


def test_financial_quality_requires_two_periods_and_balanced_core_fields():
    frame = _normalize_rows(
        _merge_period_rows(
            [
                {"date": "2025-12-31", "revenue": 1000, "netIncome": 120},
                {"date": "2024-12-31", "revenue": 900, "netIncome": 100},
            ],
            [
                {"date": "2025-12-31", "totalAssets": 2000, "totalLiabilities": 800, "totalStockholdersEquity": 1200},
                {"date": "2024-12-31", "totalAssets": 1800, "totalLiabilities": 750, "totalStockholdersEquity": 1050},
            ],
            [
                {"date": "2025-12-31", "operatingCashFlow": 150},
                {"date": "2024-12-31", "operatingCashFlow": 130},
            ],
        ),
        source="fixture",
        period_type="Annual",
    )

    result = assess_summary_quality(frame)

    assert result["pass"] is True
    assert result["periods"] == 2
    assert result["score"] >= 55
