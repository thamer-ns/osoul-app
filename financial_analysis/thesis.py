# financial_analysis/thesis.py
from datetime import datetime

from database import execute_query, fetch_table
from market_data import get_ticker_symbol
from .utils import _safe_float


# ==============================================================
# 📝 Thesis (DB fixed)
# ==============================================================
def get_thesis(symbol):
    symbol = get_ticker_symbol(symbol)
    try:
        df = fetch_table("investmentthesis")
        if df is None or df.empty:
            return None
        sub = df[df["symbol"].astype(str) == symbol]
        if sub.empty:
            return None
        return sub.iloc[0]
    except Exception:
        return None


def save_thesis(symbol, thesis_text, target_price, recommendation):
    symbol = get_ticker_symbol(symbol)
    thesis_text = str(thesis_text or "")
    recommendation = str(recommendation or "Hold")[:20]
    try:
        tp = _safe_float(target_price)
    except Exception:
        tp = 0.0

    today = datetime.now().strftime("%Y-%m-%d")

    execute_query(
        """
        INSERT INTO investmentthesis (symbol, thesis_text, target_price, recommendation, last_updated)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (symbol)
        DO UPDATE SET
            thesis_text=EXCLUDED.thesis_text,
            target_price=EXCLUDED.target_price,
            recommendation=EXCLUDED.recommendation,
            last_updated=EXCLUDED.last_updated;
        """,
        (symbol, thesis_text, tp, recommendation, today),
    )
