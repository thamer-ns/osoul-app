# financial_analysis/__init__.py

# utils (اختياري تصديرها إذا تحتاج)
from .utils import HEADERS

# store
from .store import save_financial_record, get_stored_financials_df

# yahoo json + unified df
from .yahoo_data import (
    fetch_financial_statements_yahoo_json,
    fetch_financials_from_yahoo,
    get_financial_statements,
)

# parsers + external
from .parsers import FinancialParser, fetch_financials_from_argaam, fetch_financials_from_google_finance

# sync
from .sync import sync_auto_yahoo, sync_auto_multi_sources, sync_full_yahoo

# metrics
from .metrics import get_advanced_fundamental_ratios, get_fundamental_ratios

# thesis
from .thesis import get_thesis, save_thesis

# ui (اختياري): لا نخلي أي خطأ في واجهة UI يكسر استيراد الحزمة كاملة
# لأن views/shared.py يستورد financial_analysis داخل try/except
# فإذا فشل الاستيراد لأي سبب، يتعطل التحليل المالي بالكامل.
try:
    from .ui import render_financial_dashboard_ui
except Exception:
    render_financial_dashboard_ui = None

# full statements store
from .store_full import fetch_full_statement_records, has_full_statement
# full statements fetch
from .yahoo_data import fetch_full_financial_statements_yahoo_json
