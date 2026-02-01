# ui/pages/analysis/main.py
import streamlit as st
import pandas as pd
import plotly.express as px

from database import fetch_table
from data_source import get_company_details
from ui.common import normalize_symbol, safe_status_series, clean_symbols_list, sym_key as _sym_key
from market_data import get_chart_history

from ui.pages.analysis.ai_tab import render_ai_tab, run_stress_test
from ui.pages.analysis.financial_tab import render_financial_tab
from ui.pages.analysis.technical_tab import render_technical_tab
from ui.pages.analysis.classical_tab import render_classical_tab
from ui.pages.analysis.thesis_tab import render_thesis_tab


def _symbol_is_valid(sym: str) -> bool:
    if not sym or sym == ".SR":
        return False

    # 1) جرب company details
    try:
        info = get_company_details(sym)
        if isinstance(info, (list, tuple)) and len(info) >= 1:
            if bool(str(info[0]).strip()):
                return True
        elif isinstance(info, dict):
            if bool(str(info.get("name") or info.get("Name") or "").strip()):
                return True
        else:
            if bool(str(info).strip()):
                return True
    except Exception:
        pass

    # 2) fallback: وجود بيانات سعر
    try:
        dfx = get_chart_history(sym, "1mo")
        if isinstance(dfx, pd.DataFrame) and (not dfx.empty):
            return True
    except Exception:
        pass

    return False


def _get_company_name_sector(sym: str):
    try:
        info = get_company_details(sym)
        if isinstance(info, (list, tuple)) and len(info) >= 2:
            return info[0], info[1]
        if isinstance(info, dict):
            n = info.get("name") or info.get("Name") or sym
            sec = info.get("sector") or info.get("Sector") or ""
            return n, sec
    except Exception:
        pass
    return sym, ""


def view_analysis(fin):
    st.header("🔬 التحليل الشامل")
    trades = fin.get("all_trades", pd.DataFrame())

    # ✅ اختبار التحمل
    if not trades.empty and "status" in trades.columns:
        try:
            status = safe_status_series(trades)
            open_pos = trades[status == "open"].copy()
        except Exception:
            open_pos = pd.DataFrame()

        if not open_pos.empty:
            st.subheader("📊 اختبار التحمل")
            res = run_stress_test(float(fin.get("market_val_open", 0)), open_pos)
            if res.get("scenarios"):
                c_stress, c_insight = st.columns([3, 1])
                with c_stress:
                    sdf = pd.DataFrame(res["scenarios"])
                    if not sdf.empty and "scenario" in sdf.columns and "impact_pct" in sdf.columns:
                        st.plotly_chart(px.bar(sdf, x="scenario", y="impact_pct"), use_container_width=True)
                with c_insight:
                    st.info(res.get("insight", ""))
            st.markdown("---")

    # ✅ watchlist
    try:
        wl = fetch_table("watchlist")
    except Exception:
        wl = pd.DataFrame(columns=["symbol"])

    syms = []
    try:
        if not trades.empty and "symbol" in trades.columns:
            syms = list(set(
                trades["symbol"].astype(str).unique().tolist() +
                (wl["symbol"].astype(str).unique().tolist() if "symbol" in wl.columns else [])
            ))
        else:
            syms = wl["symbol"].astype(str).unique().tolist() if "symbol" in wl.columns else []
    except Exception:
        syms = []

    all_syms = clean_symbols_list(syms)

    st.markdown("##### 🔎 البحث عن سهم")
    with st.form("analysis_search_form", clear_on_submit=False):
        c1, c2, c3 = st.columns([1.6, 2.2, 1.2])
        q = c1.text_input("اكتب الرمز", key="analysis_q", placeholder="مثال: 1120 أو 1120.SR")

        q_plain = (q or "").strip().upper()
        filtered = all_syms
        if q_plain:
            filtered = []
            for s in all_syms:
                su = s.upper()
                if q_plain in su or q_plain in su.replace(".SR", ""):
                    filtered.append(s)
            filtered = filtered[:80]

        picked = c2.selectbox(
            "اقتراحات من أسهمك",
            options=(filtered if filtered else (all_syms[:80] if all_syms else ["-"])),
            key="analysis_pick",
            disabled=(len(all_syms) == 0),
        )
        go_btn = c3.form_submit_button("تحليل", type="primary")

    if st.button("مسح", key="analysis_clear"):
        st.session_state.pop("analysis_active_symbol", None)
        st.rerun()

    if go_btn:
        raw = (q_plain or "").strip()
        if (not raw) or raw == "-":
            raw = picked if picked and picked != "-" else ""
        sym_try = normalize_symbol(raw)

        if not sym_try or sym_try == ".SR":
            st.warning("الرجاء إدخال رمز صحيح مثل: 1120 أو 1120.SR")
        else:
            if _symbol_is_valid(sym_try):
                st.session_state["analysis_active_symbol"] = sym_try
                st.rerun()
            else:
                st.error("❌ الرمز غير معروف أو لا يمكن جلب بياناته الآن. تأكد من كتابة الرمز بشكل صحيح.")

    sym = st.session_state.get("analysis_active_symbol")

    if sym:
        sym = normalize_symbol(sym)
        if not sym or sym == ".SR":
            st.warning("الرجاء إدخال رمز صحيح.")
            return

        n, sec = _get_company_name_sector(sym)
        st.markdown(f"### {n} ({sym})")

        tabs = st.tabs(["🤖 المستشار", "💰 مالي", "📈 فني", "🏛️ كلاسيكي", "📝 أطروحة"])

        with tabs[0]:
            render_ai_tab(sym)

        with tabs[1]:
            render_financial_tab(sym)

        with tabs[2]:
            render_technical_tab(sym)

        with tabs[3]:
            render_classical_tab(sym)

        with tabs[4]:
            render_thesis_tab(sym)
