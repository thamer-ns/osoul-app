# ui/pages/analysis/page.py
import streamlit as st
import pandas as pd

from database import fetch_table
from data_source import get_company_details
from market_data import get_chart_history

from ui.common import sym_key as _sym_key, normalize_symbol as _normalize_symbol
from ui.common import clean_symbols_list as _clean_symbols_list

from ui.pages.analysis.tabs.ai import render_tab as render_ai_tab
from ui.pages.analysis.tabs.finance import render_tab as render_finance_tab
from ui.pages.analysis.tabs.technical import render_tab as render_technical_tab
from ui.pages.analysis.tabs.classical import render_tab as render_classical_tab
from ui.pages.analysis.tabs.thesis import render_tab as render_thesis_tab


def _symbol_exists_quick(sym: str) -> bool:
    """تحقق سريع إذا الرمز معروف: (اسم شركة) أو (بيانات شارت)."""
    if not sym:
        return False

    try:
        info = get_company_details(sym)
        if isinstance(info, (list, tuple)) and len(info) >= 1:
            if str(info[0]).strip():
                return True
        elif isinstance(info, dict):
            if str(info.get("name") or info.get("Name") or "").strip():
                return True
        else:
            if str(info).strip():
                return True
    except Exception:
        pass

    # fallback: جرّب شارت شهر
    try:
        dfx = get_chart_history(sym, "1mo")
        return isinstance(dfx, pd.DataFrame) and (not dfx.empty)
    except Exception:
        return False


def _get_company_name_sector(sym: str):
    """يرجع (name, sector) بشكل آمن."""
    try:
        info = get_company_details(sym)
        if isinstance(info, (list, tuple)) and len(info) >= 2:
            return str(info[0] or sym), str(info[1] or "")
        if isinstance(info, dict):
            n = info.get("name") or info.get("Name") or sym
            sec = info.get("sector") or info.get("Sector") or ""
            return str(n or sym), str(sec or "")
    except Exception:
        pass
    return sym, ""


def view_analysis(fin: dict):
    st.header("🔬 التحليل الشامل")

    trades = fin.get("all_trades", pd.DataFrame())

    # watchlist
    try:
        wl = fetch_table("watchlist")
    except Exception:
        wl = pd.DataFrame(columns=["symbol"])

    # جمع الرموز من صفقات + ووتش ليست
    syms = []
    try:
        if isinstance(trades, pd.DataFrame) and (not trades.empty) and ("symbol" in trades.columns):
            syms += trades["symbol"].astype(str).unique().tolist()
        if isinstance(wl, pd.DataFrame) and (not wl.empty) and ("symbol" in wl.columns):
            syms += wl["symbol"].astype(str).unique().tolist()
    except Exception:
        syms = []

    all_syms = _clean_symbols_list(list(set([s for s in syms if s])))

    st.markdown("##### 🔎 البحث عن سهم")
    with st.form("analysis_search_form", clear_on_submit=False):
        c1, c2, c3 = st.columns([1.6, 2.2, 1.2])
        q = c1.text_input("اكتب الرمز", key="analysis_q", placeholder="مثال: 1120 أو 1120.SR")

        q_plain = (q or "").strip().upper()
        filtered = all_syms

        if q_plain:
            tmp = []
            for s in all_syms:
                su = s.upper()
                if q_plain in su or q_plain in su.replace(".SR", ""):
                    tmp.append(s)
            filtered = tmp[:80]

        picked = c2.selectbox(
            "اقتراحات من أسهمك",
            options=(filtered if filtered else (all_syms[:80] if all_syms else ["-"])),
            key="analysis_pick",
            disabled=(len(all_syms) == 0),
        )

        go_btn = c3.form_submit_button("تحليل", type="primary")

    col_clear, _ = st.columns([1, 5])
    with col_clear:
        if st.button("مسح", key="analysis_clear"):
            st.session_state.pop("analysis_active_symbol", None)
            st.rerun()

    if go_btn:
        raw = (q_plain or "").strip()
        if (not raw) or raw == "-":
            raw = picked if picked and picked != "-" else ""

        sym_try = _normalize_symbol(raw)

        if not sym_try or sym_try == ".SR":
            st.warning("الرجاء إدخال رمز صحيح مثل: 1120 أو 1120.SR")
        else:
            if _symbol_exists_quick(sym_try):
                st.session_state["analysis_active_symbol"] = sym_try
                st.rerun()
            else:
                st.error("❌ الرمز غير معروف أو لا يمكن جلب بياناته الآن. تأكد من كتابة الرمز بشكل صحيح.")

    sym = st.session_state.get("analysis_active_symbol")
    if not sym:
        st.info("اختر سهم من الأعلى لبدء التحليل.")
        return

    sym = _normalize_symbol(sym)
    if not sym or sym == ".SR":
        st.warning("الرجاء إدخال رمز صحيح.")
        return

    name, sector = _get_company_name_sector(sym)
    st.markdown(f"### {name} ({sym})")
    if sector:
        st.caption(sector)

    # ✅ المهم
