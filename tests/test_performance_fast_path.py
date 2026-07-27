from __future__ import annotations

import ast
import inspect

import pandas as pd

from views import dashboard
from views import fast_portfolio
from views import _portfolio_cache_key


def test_router_cache_key_does_not_poll_database_tables():
    assert _portfolio_cache_key(7, 11) == "u7:p11"
    source = inspect.getsource(__import__("views"))
    assert "get_portfolio_cache_key" not in source
    assert "ttl=45" not in source


def test_portfolio_display_preparation_is_network_free():
    source = inspect.getsource(fast_portfolio.prepare_open_positions)
    assert "fetch_batch_data" not in source
    frame, live = fast_portfolio.prepare_open_positions(
        pd.DataFrame(
            [
                {
                    "symbol": "1120",
                    "quantity": 10,
                    "entry_price": 50,
                    "current_price": 55,
                }
            ]
        )
    )
    assert live == {}
    assert float(frame.iloc[0]["market_value"]) == 550.0
    assert float(frame.iloc[0]["gain"]) == 50.0


def test_dashboard_has_no_heavy_top_level_market_or_plotly_imports():
    tree = ast.parse(inspect.getsource(dashboard))
    top_level_imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            top_level_imports.add(str(node.module or ""))

    assert "plotly.express" not in top_level_imports
    assert "market_data" not in top_level_imports
    assert "analytics" not in top_level_imports
    source = inspect.getsource(dashboard.view_dashboard)
    assert "if not advanced_loaded:" in source
    assert "تحميل بيانات السوق والرسوم المتقدمة" in source
