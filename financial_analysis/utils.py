# financial_analysis/utils.py
import re
from datetime import datetime
from typing import Optional

import numpy as np

# Web (اختياري)
try:
    import requests
    from bs4 import BeautifulSoup
except Exception:
    requests = None
    BeautifulSoup = None


# ==============================================================
# 🧰 Helpers
# ==============================================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _safe_float(x) -> float:
    try:
        if x is None:
            return 0.0
        if isinstance(x, (np.floating, np.integer)):
            return float(x)
        s = str(x).replace(",", "").strip()
        if s.lower() in ("nan", "none", ""):
            return 0.0
        return float(s)
    except Exception:
        return 0.0


def _safe_div(a, b, default=0.0):
    try:
        a = _safe_float(a)
        b = _safe_float(b)
        if b == 0:
            return default
        return a / b
    except Exception:
        return default


def _is_missing(x) -> bool:
    """Return True if x is a missing/NA-like value."""
    try:
        if x is None:
            return True
        if isinstance(x, str) and x.strip().lower() in ("", "nan", "none", "null", "-"):
            return True
        # pandas NA
        try:
            import pandas as pd
            if hasattr(pd, "isna") and pd.isna(x):
                return True
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at financial_analysis/utils.py:65')
        # numpy NaN
        try:
            import numpy as np
            if isinstance(x, (np.floating, np.integer)):
                try:
                    return bool(np.isnan(float(x)))
                except Exception:
                    return False
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at financial_analysis/utils.py:75')
        return False
    except Exception:
        return False


def _safe_float_none(x):
    """Safe float that preserves missing as None (does NOT coerce to 0)."""
    try:
        if _is_missing(x):
            return None
        try:
            import numpy as np
            if isinstance(x, (np.floating, np.integer)):
                return float(x)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at financial_analysis/utils.py:91')
        s = str(x).replace(",", "").strip()
        if s.lower() in ("nan", "none", ""):
            return None
        return float(s)
    except Exception:
        return None


def _safe_div_none(a, b):
    """Division that returns None when operands missing/invalid or denominator=0."""
    try:
        av = _safe_float_none(a)
        bv = _safe_float_none(b)
        if av is None or bv is None or bv == 0:
            return None
        return av / bv
    except Exception:
        return None




def _safe_date_str(d) -> str:
    """
    يحاول تحويل تاريخ yahoo (Timestamp) أو string إلى YYYY-MM-DD
    """
    try:
        if hasattr(d, "strftime"):
            return d.strftime("%Y-%m-%d")
        s = str(d).strip()
        s = s.split(" ")[0]
        s = s.split("T")[0]
        return s
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def _is_year_like(s: str) -> bool:
    try:
        y = int(s)
        return 2000 <= y <= 2099
    except Exception:
        return False


def _looks_like_date_token(s: str) -> bool:
    s = str(s or "").strip()
    return bool(re.search(r"\b(20\d{2})\b", s) or re.search(r"\d{4}-\d{2}-\d{2}", s))


def _fetch_html(url: str, timeout: int = 7) -> str:
    if not requests:
        return ""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            return ""
        return r.text or ""
    except Exception:
        return ""
