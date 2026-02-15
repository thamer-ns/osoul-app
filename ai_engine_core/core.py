# ai_engine_core/core.py

from datetime import datetime
import re

def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_symbol(symbol: str) -> str:
    """Normalize symbol without breaking crypto pairs like BTC-USD."""
    sym = str(symbol or "").strip().upper().replace(" ", "")
    if not sym:
        return ""

    # Allow SR.#### shortcut
    m = re.match(r"^SR\.?([0-9]{1,6})$", sym)
    if m:
        sym = m.group(1)

    # Digits only => Saudi suffix
    if sym.isdigit():
        return f"{sym}.SR"

    # Keep other formats as-is (AAPL, BTC-USD, ^GSPC, EURUSD=X, etc.)
    if sym.endswith("SR") and not sym.endswith(".SR") and sym[:-2].isdigit():
        return f"{sym[:-2]}.SR"

    return sym

def _map_period_from_timeframe(timeframe: str) -> str:
    """Best-effort mapping from timeframe to history period.

    - Daily/Weekly/Monthly default to long history (>=5y) as requested.
    - Intraday is limited by data vendors, so we request a reasonable window.
    """
    tf = str(timeframe or "").strip().upper()
    if tf in ("15M", "30M"):
        return "180d"
    if tf in ("1H",):
        return "730d"
    if tf in ("4H",):
        return "5y"  # may be limited by provider
    if tf in ("1D", "D"):
        return "5y"
    if tf in ("1W", "W"):
        return "10y"
    if tf in ("1M", "M"):
        return "20y"
    return "5y"

