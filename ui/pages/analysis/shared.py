# ui/pages/analysis/shared.py
# أدوات مشتركة لصفحة التحليل وتبويباتها
# الهدف: منع ImportError وتجميع Helpers مشتركة (مثل badge)

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st


# =========================
# Basic helpers
# =========================

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


# =========================
# UI: Badge / Pills
# =========================

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


# =========================
# Compatibility exports
# (لو تبغى تستخدمها بأسماء قديمة)
# =========================

# بعض الملفات القديمة قد تنادي _badge بدل badge
def _badge(text: str, tone: str = "neutral") -> None:
    return badge(text, tone)


def _safe_list(x: Any) -> List[Any]:
    return safe_list(x)


def _to_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    return to_float(x, default)


def _fmt_price(x: Any) -> str:
    return fmt_price(x)


# =========================
# Optional: shared UI injection flag
# (ما يغير الواجهة، بس يمنع التكرار لو احتجته تبويبات ثانية)
# =========================

def ensure_ui_once() -> None:
    """
    استخدمها إذا تبغى تمنع حقن CSS/i18n أكثر من مرة.
    (هنا تركناها عامة بدون استيراد ملفات أخرى لتجنب circular imports)
    """
    if st.session_state.get("_analysis_ui_injected_once"):
        return
    st.session_state["_analysis_ui_injected_once"] = True
