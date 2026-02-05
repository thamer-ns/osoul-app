"""Compatibility wrapper for full-statement storage.

Some code versions import `financial_analysis.store_full`.
The canonical implementation lives in `financial_analysis.store`.
"""

from .store import (
    ensure_financialstatements_raw_table,
    save_full_statement_record,
    fetch_full_statement_records,
    has_full_statement,
)
