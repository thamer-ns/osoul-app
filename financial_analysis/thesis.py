# financial_analysis/thesis.py
from market_data_v2 import get_ticker_symbol
from tenant_runtime import get_thesis_v2, save_thesis_v2


def get_thesis(symbol):
    """Return the current user's thesis for one symbol."""
    try:
        return get_thesis_v2(get_ticker_symbol(symbol))
    except Exception:
        return None


def save_thesis(symbol, thesis_text, target_price, recommendation):
    """Upsert a thesis without allowing one user to overwrite another user's row."""
    try:
        return save_thesis_v2(
            get_ticker_symbol(symbol),
            str(thesis_text or ""),
            target_price,
            str(recommendation or "Hold")[:20],
        )
    except Exception:
        return False
