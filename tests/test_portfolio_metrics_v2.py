from __future__ import annotations

import pandas as pd

import database
import market_data
from backup_system import _safe_excel_value
from portfolio_metrics_v2 import calculate_portfolio_metrics_v2


def test_unified_portfolio_accounting_uses_stored_prices_only(monkeypatch):
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

    def fail_on_network(_symbols):
        raise AssertionError("normal portfolio metrics must not call market providers")

    monkeypatch.setattr(market_data, "fetch_batch_data", fail_on_network)

    calculate_portfolio_metrics_v2.clear()
    result = calculate_portfolio_metrics_v2(
        include_xirr=False,
        cache_key="u1:p1",
    )

    assert result["cost_open"] == 500.0
    assert result["market_val_open"] == 550.0
    assert result["unrealized_pl"] == 50.0
    assert result["realized_pl"] == 50.0
    assert result["cash"] == 570.0
    assert result["portfolio_value"] == 1120.0
    assert result["price_mode"] == "stored"
    assert result["data_quality"]["ok"] is False
    assert "آخر سعر محفوظ" in result["data_quality"]["notes"][0]


def test_excel_formula_prefixes_are_neutralised():
    assert _safe_excel_value("=2+2") == "'=2+2"
    assert _safe_excel_value("@SUM(A1:A2)") == "'@SUM(A1:A2)"
    assert _safe_excel_value("normal text") == "normal text"


def test_stored_fallback_price_is_marked_stale(monkeypatch):
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
                }
            ]
        ),
        "deposits": pd.DataFrame(
            [{"date": "2026-01-01", "amount": 1000.0}]
        ),
        "withdrawals": pd.DataFrame(columns=["date", "amount"]),
        "returnsgrants": pd.DataFrame(columns=["date", "amount"]),
    }
    monkeypatch.setattr(
        database,
        "fetch_table",
        lambda table: tables[str(table).lower()].copy(),
    )
    monkeypatch.setattr(
        market_data,
        "fetch_batch_data",
        lambda symbols: (_ for _ in ()).throw(
            AssertionError("network call is forbidden on normal page load")
        ),
    )

    calculate_portfolio_metrics_v2.clear()
    result = calculate_portfolio_metrics_v2(
        include_xirr=False,
        cache_key="u1:p1:stale-test",
    )
    open_positions = result["open_positions_df"]
    assert bool(open_positions.iloc[0]["price_stale"]) is True
    assert open_positions.iloc[0]["price_source"] == "stored"
    assert result["data_quality"]["ok"] is False
