# financial_analysis/__init__.py

from .utils import HEADERS
from .store import save_financial_record, get_stored_financials_df
from .yahoo_data import (
    fetch_financial_statements_yahoo_json,
    fetch_financials_from_yahoo,
    get_financial_statements,
    fetch_full_financial_statements_yahoo_json,
    fetch_full_financial_statements_yahoo_html,
    get_last_yahoo_diagnostics,
    diagnose_yahoo_quote_summary,
)
from .parsers import (
    FinancialParser,
    fetch_financials_from_argaam,
    fetch_financials_from_google_finance,
)
from .sync import sync_auto_yahoo, sync_auto_multi_sources, sync_full_yahoo
from . import metrics as _metrics
from .quality_contract_v34 import (
    QUALITY_CONTRACT_VERSION,
    attach_financial_quality_contract,
    build_financial_quality_contract,
)
from .quality_gate import evaluate_financial_data_quality
from .thesis import get_thesis, save_thesis

_base_get_advanced_fundamental_ratios = _metrics.get_advanced_fundamental_ratios


def get_advanced_fundamental_ratios(*args, **kwargs):
    """Return legacy metrics enriched by the SC-FQ3.4 quality contract."""
    metrics = _base_get_advanced_fundamental_ratios(*args, **kwargs)
    return attach_financial_quality_contract(metrics)


def get_fundamental_ratios(*args, **kwargs):
    return get_advanced_fundamental_ratios(*args, **kwargs)


# Keep direct imports from financial_analysis.metrics consistent as well.
_metrics.get_advanced_fundamental_ratios = get_advanced_fundamental_ratios
_metrics.get_fundamental_ratios = get_fundamental_ratios

try:
    from .ui import render_financial_dashboard_ui
except Exception:
    render_financial_dashboard_ui = None


__all__ = [
    "HEADERS",
    "QUALITY_CONTRACT_VERSION",
    "FinancialParser",
    "attach_financial_quality_contract",
    "build_financial_quality_contract",
    "diagnose_yahoo_quote_summary",
    "evaluate_financial_data_quality",
    "fetch_financial_statements_yahoo_json",
    "fetch_financials_from_argaam",
    "fetch_financials_from_google_finance",
    "fetch_financials_from_yahoo",
    "fetch_full_financial_statements_yahoo_html",
    "fetch_full_financial_statements_yahoo_json",
    "get_advanced_fundamental_ratios",
    "get_financial_statements",
    "get_fundamental_ratios",
    "get_last_yahoo_diagnostics",
    "get_stored_financials_df",
    "get_thesis",
    "render_financial_dashboard_ui",
    "save_financial_record",
    "save_thesis",
    "sync_auto_multi_sources",
    "sync_auto_yahoo",
    "sync_full_yahoo",
]
