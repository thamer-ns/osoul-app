# ui/pages/analysis/page.py
import streamlit as st
import pandas as pd

from database import fetch_table
from market_data import get_chart_history
from data_source import get_company_details

from ui.common import clean_symbols_list, normalize_symbol, sym_key


def _call_first_available(mod, names, *args, **kwargs):
    """Call the first callable found in mod from a list of candidate function names."""
    for n in names:
        fn = getattr(mod, n, None)
        if callable(fn):
            fn(*args, **kwargs)
            return True
    return False


def _symbol_picker(fin) -> str:
    """Pick a symbol for analysis and store it in session_state['analysis_active_symbol']."""
    trades = fin.get("all_trades", pd.DataFrame())

    # watchlist
    try:
        wl = fetch_table("watchlist")
    except Exception:
        wl = pd.DataFrame(columns=["symbol"])

    syms = []
    try:
        if not trades.empty and "symbol" in trades.columns:
            syms = list(
                set(
                    trades["symbol"].astype(str).unique().tolist()
                    + (wl["symbol"].astype(str).unique().tolist() if "symbol" in wl.columns else [])
                )
            )
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
            ok = False

            # 1) تحقق عبر تفاصيل الشركة
            try:
                info = get_company_details(sym_try)
                if isinstance(info, (list, tuple)) and len(info) >= 1:
                    ok = bool(str(info[0]).strip())
                elif isinstance(info, dict):
                    ok = bool(str(info.get("name") or info.get("Name") or "").strip())
                else:
                    ok = bool(str(info).strip())
            except Exception:
                ok = False

            # 2) fallback: تاريخ سعر بسيط
            if not ok:
                try:
                    dfx = get_chart_history(sym_try, "1mo")
                    ok = isinstance(dfx, pd.DataFrame) and (not dfx.empty)
                except Exception:
                    ok = False

            if ok:
                st.session_state["analysis_active_symbol"] = sym_try
                st.rerun()
            else:
                st.error("❌ الرمز غير معروف أو لا يمكن جلب بياناته الآن. تأكد من كتابة الرمز بشكل صحيح.")

    return st.session_state.get("analysis_active_symbol", "")


def view_analysis(fin):
    """
    ✅ Entry point الرسمي للتحليل
    هذا الاسم لازم يكون موجود لأن router/views يعتمدون عليه.
    """
    st.header("🔬 التحليل الشامل")

    sym = _symbol_picker(fin)
    sym = normalize_symbol(sym) if sym else ""

    if not sym or sym == ".SR":
        st.info("اختر سهم لعرض تبويبات التحليل.")
        return

    # اسم/قطاع
    try:
        info = get_company_details(sym)
        if isinstance(info, (list, tuple)) and len(info) >= 2:
            n, sec = info[0], info[1]
        elif isinstance(info, dict):
            n = info.get("name") or info.get("Name") or sym
            sec = info.get("sector") or info.get("Sector") or ""
        else:
            n, sec = sym, ""
    except Exception:
        n, sec = sym, ""

    st.markdown(f"### {n} ({sym})")
    if sec:
        st.caption(sec)

    tabs = st.tabs(["🤖 المستشار", "💰 مالي", "📈 فني", "🏛️ كلاسيكي", "📝 أطروحة"])

    # Import داخل الدالة لتجنب circular imports
    try:
        from ui.pages.analysis.tabs import ai as tab_ai
        from ui.pages.analysis.tabs import finance as tab_fin
        from ui.pages.analysis.tabs import technical as tab_tech
        from ui.pages.analysis.tabs import classical as tab_classic
        from ui.pages.analysis.tabs import thesis as tab_thesis
    except Exception as e:
        st.error("تعذر تحميل تبويبات التحليل من ui/pages/analysis/tabs")
        st.exception(e)
        return

    symk = sym_key(sym)

    with tabs[0]:
        ok = _call_first_available(
            tab_ai,
            ["render", "render_ai", "render_ai_tab", "view", "view_ai", "tab"],
            fin, sym, symk
        )
        if not ok:
            st.error("تبويب AI: ما لقيت دالة تشغيل داخل ui/pages/analysis/tabs/ai.py")

    with tabs[1]:
        ok = _call_first_available(
            tab_fin,
            ["render", "render_finance", "render_finance_tab", "view", "view_finance", "tab"],
            fin, sym, symk
        )
        if not ok:
            st.error("تبويب المالي: ما لقيت دالة تشغيل داخل ui/pages/analysis/tabs/finance.py")

    with tabs[2]:
        ok = _call_first_available(
            tab_tech,
            ["render", "render_technical", "render_technical_tab", "view", "view_technical", "tab"],
            fin, sym, symk
        )
        if not ok:
            st.error("تبويب الفني: ما لقيت دالة تشغيل داخل ui/pages/analysis/tabs/technical.py")

    with tabs[3]:
        ok = _call_first_available(
            tab_classic,
            ["render", "render_classical", "render_classical_tab", "view", "view_classical", "tab"],
            fin, sym, symk
        )
        if not ok:
            st.error("تبويب الكلاسيكي: ما لقيت دالة تشغيل داخل ui/pages/analysis/tabs/classical.py")

    with tabs[4]:
        ok = _call_first_available(
            tab_thesis,
            ["render", "render_thesis", "render_thesis_tab", "view", "view_thesis", "tab"],
            fin, sym, symk
        )
        if not ok:
            st.error("تبويب الأطروحة: ما لقيت دالة تشغيل داخل ui/pages/analysis/tabs/thesis.py")
