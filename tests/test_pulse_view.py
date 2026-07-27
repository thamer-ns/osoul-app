from __future__ import annotations

import inspect

import pandas as pd
import pytest

from views import _render_page
from views import owned_stocks


def test_owned_stocks_aggregates_open_stock_lots_and_excludes_sukuk():
    finance = {
        "open_positions_df": pd.DataFrame(
            [
                {
                    "symbol": "1120.SR",
                    "company_name": "الراجحي",
                    "strategy": "مضاربة",
                    "asset_type": "Stock",
                    "quantity": 10.0,
                    "entry_price": 80.0,
                    "current_price": 90.0,
                    "prev_close": 88.0,
                    "price_source": "stored",
                    "price_stale": False,
                },
                {
                    "symbol": "1120.SR",
                    "company_name": "الراجحي",
                    "strategy": "استثمار",
                    "asset_type": "Stock",
                    "quantity": 5.0,
                    "entry_price": 70.0,
                    "current_price": 90.0,
                    "prev_close": 88.0,
                    "price_source": "stored",
                    "price_stale": False,
                },
                {
                    "symbol": "SUKUK-1",
                    "company_name": "صك تجريبي",
                    "strategy": "استثمار",
                    "asset_type": "Sukuk",
                    "quantity": 1.0,
                    "entry_price": 1000.0,
                    "current_price": 1000.0,
                    "prev_close": 0.0,
                },
            ]
        )
    }

    result = owned_stocks.build_owned_stocks_frame(finance)

    assert len(result) == 1
    row = result.iloc[0]
    assert row["symbol"] == "1120.SR"
    assert row["company_name"] == "الراجحي"
    assert row["portfolio"] == "مضاربة + استثمار"
    assert row["quantity"] == pytest.approx(15.0)
    assert row["average_cost"] == pytest.approx((10 * 80 + 5 * 70) / 15)
    assert row["current_price"] == pytest.approx(90.0)
    assert row["day_change_amount"] == pytest.approx(2.0)
    assert row["day_change_pct"] == pytest.approx(2 / 88 * 100)
    assert row["daily_pnl"] == pytest.approx(30.0)
    assert row["market_value"] == pytest.approx(1350.0)
    assert row["unrealized_pnl"] == pytest.approx(200.0)
    assert row["direction"] == "صاعد"


def test_owned_stocks_is_database_backed_and_home_embedded():
    source = inspect.getsource(owned_stocks)
    router_source = inspect.getsource(_render_page)

    assert "fetch_batch_data" not in source
    assert "market_data" not in source
    assert 'st.expander("📋 أسهمي المملوكة"' in source
    assert '"home": ("views.home", "view_home", (finance,))' in router_source
    assert '"pulse":' not in router_source
