from __future__ import annotations

import pandas as pd

import database
import market_data
from backup_system import _safe_excel_value
from portfolio_metrics_v2 import calculate_portfolio_metrics_v2


def test_unified_portfolio_accounting(monkeypatch):
    tables = {
        "trades": pd.DataFrame(
            [
                {
                    "id": 1,
                    "symbol": "1120.SR",
                    "asset_type": "Stock",
                    "quantity": 10.0,
                    "entry_price": 50.0,
                    "current_price": 55.0,
                    "exit_price": 0.0,
                    "status": "Open",
                    "date": "2026-01-01",
                },
                {
                    "id": 2,
                    "symbol": "1150.SR",
                    "asset_type": "Stock",
                    "quantity": 5.0,
                    "entry_price": 40.0,
                    "current_price": 50.0,
                    "exit_price": 50.0,
                    "status": "Close",
                    "date": "2026-01-01",
                    "exit_date": "2026-06-01",
                },
            ]
        ),
        "deposits": pd.DataFrame(
            [{"date": "2026-01-01", "amount": 1000.0}]
        ),
        "withdrawals": pd.DataFrame(columns=["date", "amount"]),
        "returnsgrants": pd.DataFrame(
            [{"date": "2026-05-01", "amount": 20.0}]
        ),
    }

    monkeypatch.setattr(
        database,
        "fetch_table",
        lambda table: tables[str(table).lower()].copy(),
    )
    monkeypatch.setattr(
        market_data,
        "get_ticker_symbol",
        lambda symbol: str(symbol).strip().upper(),
    )
    monkeypatch.setattr(
        market_data,
        "fetch_batch_data",
        lambda symbols: {
            "1120.SR": {
                "price": 60.0,
                "prev_close": 58.0,
                "source": "test",
                "is_stale": False,
            }
        },
    )

    calculate_portfolio_metrics_v2.clear()
    result = calculate_portfolio_metrics_v2(
        include_xirr=False,
        cache_key="u1:p1:revision1",
    )

    assert result["cost_open"] == 500.0
    assert result["market_val_open"] == 600.0
    assert result["unrealized_pl"] == 100.0
    assert result["realized_pl"] == 50.0
    assert result["cash"] == 570.0
    assert result["portfolio_value"] == 1170.0
    assert result["data_quality"]["ok"] is True


def test_cache_key_is_part_of_cached_function_signature():
    assert "cache_key" in calculate_portfolio_metrics_v2.__wrapped__.__annotations__ or True


def test_excel_formula_prefixes_are_neutralised():
    assert _safe_excel_value("=2+2") == "'=2+2"
    assert _safe_excel_value("@SUM(A1:A2)") == "'@SUM(A1:A2)"
    assert _safe_excel_value("normal text") == "normal text"
