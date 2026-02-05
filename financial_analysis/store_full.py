# financial_analysis/store_full.py
"""Compatibility wrapper.

Some older versions referenced `financial_analysis.store_full`.
In the current codebase, full-statement storage/retrieval lives in `financial_analysis.store`.
"""

from .store import (
    ensure_financialstatements_raw_table,
    save_full_statement_record,
    fetch_full_statement_records,
    has_full_statement,
)
