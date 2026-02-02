# ui/pages/analysis/shared.py
# أدوات مشتركة لصفحة التحليل وتبويباتها
# الهدف: منع ImportError وتجميع Helpers مشتركة (مثل badge و sym_key)

from __future__ import annotations

from typing import Any, List, Optional
import streamlit as st


# =========================================================
# Try importing canonical helpers from ui.common (preferred)
# =========================================================

try:
    from ui.common import sym_key as _sym_key_impl  # type: ignore
except Exception:
    _sym_key_impl = None

try:
    from ui.common import normalize_symbol as _normalize_symbol_impl  # type: ignore
except Exception:
    _normalize_symbol_impl = None

try:
    from ui.common import clean_symbols_list as _clean_symbols_list_impl  # type: ignore
except Exception:
    _clean_symbols_list_impl = None

try:
    from ui.common import safe_status_series as _safe_status_series_impl  # type: ignore
except Exception:
    _safe_status_series_impl = None


# =========================================================
# Public wrappers expected by legacy tabs
# =========================================================

def sym_key(symbol: str) -> str:
    """
    Key-safe string for Streamlit widgets.
    Legacy tabs قد تعتمد عليها.
    """
    if callable(_sym_key_impl):
        try:
            return _sym_key_impl(symbol)
        except Exception:
            pass
    # fallback
    s = (symbol or "").strip().upper()
    s = s.replace(".", "_").replace("-", "_").replace(" ", "_")
    return s or "SYM"


def normalize_symbol(symbol: str) -> str:
    """
    Normalize 1120 -> 1120.SR etc (حسب منطق مشروعك).
    """
    if callable(_normalize_symbol_impl):
        try:
            return _normalize_symbol_impl(symbol)
        except Exception:
            pass

    # fallback بسيط وآمن
    s = (symbol or "").strip().upper()
    if not s:
        return ""
    # إذا رقم وبدون .SR نضيفها
    if s.isdigit() and not s.endswith(".SR"):
        return f"{s}.SR"
    # إذا كتب 1120.SR تمام
    return s


def clean_symbols_list(symbols: Any) -> List[str]:
    """
    Clean list of symbols.
    """
    if callable(_clean_symbols_list_impl):
        try:
            return _clean_symbols_list_impl(symbols)
        except Exception:
            pass

    # fallback
    if symbols is None:
        return []
    if not isinstance(symbols, list):
        symbols = [symbols]
    out = []
    for x in symbols:
        s = str(x).strip()
        if not s:
            continue
        out.append(normalize_symbol(s))
    # إزالة التكرار مع الحفاظ على الترتيب
    seen = set()
    res = []
    for s in out:
        if s in seen:
            continue
        seen.add(s)
        res.append(s)
    return res


def safe_status_series(df):
    """
    Legacy helper: يرجع Series/status بشكل آمن حتى لو العمود غير موجود.
    """
    if callable(_safe_status_series_impl):
        try:
            return _safe_status_series_impl(df)
        except Exception:
            pass

    # fallback
    try:
        if df is None or getattr(df, "empty", True):
            return None
        if "status" in df.columns:
            return df["status"].astype(str).str.lower()
        return None
    except Exception:
        return None


# =========================================================
# Basic helpers
# =========================================================

def safe_list(x: Any) -> List[Any]:
    """يرجع دائمًا قائمة نظيفة."""
    if x is None:
        return []
    if isinstance(x, list):
        return [i for i in x if i is not None and str(i).strip() != ""]
    return [x]


def to_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def fmt_price(x: Any) -> str:
    v = to_float(x, None)
    return "—" if v is None else f"{v:,.2f}"


# =========================================================
# UI: Badge / Pills
# =========================================================

def badge(text: str, tone: str = "neutral") -> None:
    """
    شارة صغيرة (pill) مثل:
    badge("AI: OK", "success")
    """
    bg = {
        "success": "#e8fff2",
        "warning": "#fff6e5",
        "danger":  "#ffecec",
        "neutral": "#f2f4f7",
        "blue":    "#eef4ff",
    }.get(tone, "#f2f4f7")

    fg = {
        "success": "#0f7a3c",
        "warning": "#8a5a00",
        "danger":  "#a40e26",
        "neutral": "#344054",
        "blue":    "#1d4ed8",
    }.get(tone, "#344054")

    st.markdown(
        f"""
        <span style="
            background:{bg};
            color:{fg};
            padding:4px 10px;
            border-radius:999px;
            font-weight:800;
            font-size:0.85rem;
            border:1px solid rgba(0,0,0,0.06);
            display:inline-block;
        ">{text}</span>
        """,
        unsafe_allow_html=True,
    )


def render_bullets(
    title: str,
    items: Any,
    icon: str = "•",
    limit: int = 8,
    empty_text: str = "لا يوجد",
) -> None:
    st.markdown(f"**{title}**")
    xs = safe_list(items)
    if not xs:
        st.caption(empty_text)
        return
    for x in xs[:limit]:
        st.write(f"{icon} {x}")


def json_debug_block(title: str, data: Any) -> None:
    """بلوك Debug اختياري مرتب."""
    with st.expander(title):
        try:
            st.json(data)
        except Exception:
            st.write(data)


# =========================================================
# Compatibility exports (old naming)
# =========================================================

def _badge(text: str, tone: str = "neutral") -> None:
    return badge(text, tone)


def _safe_list(x: Any) -> List[Any]:
    return safe_list(x)


def _to_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    return to_float(x, default)


def _fmt_price(x: Any) -> str:
    return fmt_price(x)


# =========================================================
# Optional: shared UI injection flag
# =========================================================

def ensure_ui_once() -> None:
    """
    يمنع حقن CSS/i18n أكثر من مرة (اختياري).
    """
    if st.session_state.get("_analysis_ui_injected_once"):
        return
    st.session_state["_analysis_ui_injected_once"] = True
