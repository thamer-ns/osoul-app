# ui/common.py
import pandas as pd


def sym_key(sym: str) -> str:
    """مفتاح آمن للاستخدام داخل session_state/keys."""
    return (sym or "").replace(".", "_").replace("-", "_").replace(" ", "_")


def normalize_symbol(sym: str) -> str:
    sym = (sym or "").strip().upper()
    if not sym:
        return ""
    if sym.isdigit():
        return f"{sym}.SR"
    sym = sym.replace(" ", "").replace("-", "")
    if sym.endswith("SR") and ".SR" not in sym:
        sym = sym.replace("SR", ".SR")
    return sym


def safe_status_series(df: pd.DataFrame) -> pd.Series:
    """يرجع status موحد lower/strip لتفادي Open/OPEN/Close/Closed..."""
    if df is None or df.empty or "status" not in df.columns:
        return pd.Series([], dtype=str)
    return df["status"].astype(str).str.strip().str.lower()


def clean_symbols_list(values) -> list:
    """ينظف الرموز: يحذف الفارغ/NaN ويطبّع ويزيل التكرار"""
    out = []
    try:
        for x in (values or []):
            s = normalize_symbol(str(x))
            if s and s != ".SR" and s.lower() != "nan":
                out.append(s)
    except Exception:
        pass
    return list(sorted(set(out)))

