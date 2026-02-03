# ai_engine_core/core.py

from datetime import datetime

def _normalize_symbol(sym: str) -> str:
    sym = (sym or "").strip().upper()
    if sym.isdigit():
        return f"{sym}.SR"
    sym = sym.replace(" ", "").replace("-", "")
    if sym.endswith("SR") and ".SR" not in sym:
        sym = sym.replace("SR", ".SR")
    return sym

def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _map_period_from_timeframe(timeframe: str):
    tf = (timeframe or "1D").upper().strip()
    if tf in ["1H", "60M", "H"]:
        return "60d"
    if tf in ["4H", "240M"]:
        return "180d"
    if tf in ["1W", "W"]:
        return "5y"
    if tf in ["1MO", "1M", "MO"]:
        return "10y"
    return "6mo"
