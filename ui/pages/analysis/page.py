# ui/pages/analysis/page.py
import streamlit as st
import pandas as pd

from database import fetch_table
from market_data import get_chart_history
from data_source import get_company_details

from ui.common import clean_symbols_list, normalize_symbol, sym_key, safe_status_series


def _call_first_available(mod, names, *args, **kwargs):
    """
    يحاول يستدعي أول دالة موجودة ضمن قائمة names داخل module.
    إذا ولا وحدة موجودة يرجع False.
    """
    for n in names:
        fn = getattr(mod, n, None)
        if callable(fn):
            fn(*args, **kwargs)
            return True
    return False


def _symbol_picker(fin) -> str:
    """
    يختار رمز للتحليل من:
    - صفقات المستخدم
    - watchlist
    ويخزن الرمز في session_state: analysis_active_symbol
    """
    trades = fin.get("all_trades", pd.DataFrame())

    # watchlist
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
            ok = False
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
    هذا هو الاسم الذي تعتمد عليه views.py و ui/router.py
    """
    st.header("🔬 التحليل الشامل")

    # اختيار الرمز
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
            n = info.get("na
