# ui/pages/analysis/page.py
import streamlit as st
import pandas as pd

from ui.pages.analysis.tabs import ai as tab_ai
from ui.pages.analysis.tabs import finance as tab_finance
from ui.pages.analysis.tabs import technical as tab_technical
from ui.pages.analysis.tabs import classical as tab_classical
from ui.pages.analysis.tabs import thesis as tab_thesis


def view_analysis(fin):
    st.header("🔬 التحليل الشامل")

    # نأخذ trades من fin (مثل القديم)
    trades = fin.get("all_trades", pd.DataFrame())

    # ✅ اختبار التحمل
    try:
        import views_impl as v
        if not trades.empty and "status" in trades.columns and hasattr(v, "run_stress_test") and hasattr(v, "_safe_status_series"):
            status = v._safe_status_series(trades)
            open_pos = trades[status == "open"].copy()

            st.subheader("📊 اختبار التحمل")
            res = v.run_stress_test(float(fin.get("market_val_open", 0)), open_pos)

            if isinstance(res, dict) and res.get("scenarios"):
                import plotly.express as px
                c_stress, c_insight = st.columns([3, 1])
                with c_stress:
                    sdf = pd.DataFrame(res["scenarios"])
                    if not sdf.empty and "scenario" in sdf.columns and "impact_pct" in sdf.columns:
                        st.plotly_chart(px.bar(sdf, x="scenario", y="impact_pct"), use_container_width=True)
                with c_insight:
                    st.info(res.get("insight", ""))
            st.markdown("---")
    except Exception:
        pass

    # ✅ watchlist
    try:
        import views_impl as v
        try:
            wl = v.fetch_table("watchlist")
        except Exception:
            wl = pd.DataFrame(columns=["symbol"])
    except Exception:
        wl = pd.DataFrame(columns=["symbol"])

    # جمع رموز من صفقات + watchlist
    syms = []
    try:
        if not trades.empty and "symbol" in trades.columns:
            base = trades["symbol"].astype(str).unique().tolist()
            wls = wl["symbol"].astype(str).unique().tolist() if ("symbol" in wl.columns) else []
            syms = list(set(base + wls))
        else:
            syms = wl["symbol"].astype(str).unique().tolist() if ("symbol" in wl.columns) else []
    except Exception:
        syms = []

    # تنظيف الرموز باستخدام أدواتك الموجودة
    try:
        import views_impl as v
        all_syms = v._clean_symbols_list(syms) if hasattr(v, "_clean_symbols_list") else syms
    except Exception:
        all_syms = syms

    st.markdown("##### 🔎 البحث عن سهم")
    with st.form("analysis_search_form", clear_on_submit=False):
        c1, c2, c3 = st.columns([1.6, 2.2, 1.2])
        q = c1.text_input("اكتب الرمز", key="analysis_q", placeholder="مثال: 1120 أو 1120.SR")

        q_plain = (q or "").strip().upper()
        filtered = all_syms
        if q_plain:
            filtered = []
            for s in all_syms:
                su = str(s).upper()
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

    # تنفيذ التحليل/تثبيت الرمز
    if go_btn:
        raw = (q_plain or "").strip()
        if (not raw) or raw == "-":
            raw = picked if picked and picked != "-" else ""

        sym_try = raw
        try:
            import views_impl as v
            if hasattr(v, "_normalize_symbol"):
                sym_try = v._normalize_symbol(raw)
        except Exception:
            pass

        if not sym_try or sym_try == ".SR":
            st.warning("الرجاء إدخال رمز صحيح مثل: 1120 أو 1120.SR")
        else:
            ok = False

            # محاولة التحقق من الرمز
            try:
                import views_impl as v
                info = v.get_company_details(sym_try) if hasattr(v, "get_company_details") else None
                if isinstance(info, (list, tuple)) and len(info) >= 1:
                    ok = bool(str(info[0]).strip())
                elif isinstance(info, dict):
                    ok = bool(str(info.get("name") or info.get("Name") or "").strip())
                else:
                    ok = bool(str(info).strip()) if info is not None else False
            except Exception:
                ok = False

            if not ok:
                try:
                    import views_impl as v
                    if hasattr(v, "_get_chart_history_flex"):
                        dfx = v._get_chart_history_flex(sym_try, "1mo", "1d")
                    elif hasattr(v, "get_chart_history"):
                        dfx = v.get_chart_history(sym_try, "1mo")
                    else:
                        dfx = None
                    ok = isinstance(dfx, pd.DataFrame) and (not dfx.empty)
                except Exception:
                    ok = False

            if ok:
                st.session_state["analysis_active_symbol"] = sym_try
                st.rerun()
            else:
                st.error("❌ الرمز غير معروف أو لا يمكن جلب بياناته الآن. تأكد من كتابة الرمز بشكل صحيح.")

    sym = st.session_state.get("analysis_active_symbol")

    if not sym:
        return

    # Normalize symbol
    try:
        import views_impl as v
        if hasattr(v, "_normalize_symbol"):
            sym = v._normalize_symbol(sym)
    except Exception:
        pass

    if not sym or sym == ".SR":
        st.warning("الرجاء إدخال رمز صحيح.")
        return

    # اسم/قطاع
    n, sec = sym, ""
    try:
        import views_impl as v
        info = v.get_company_details(sym) if hasattr(v, "get_company_details") else None
        if isinstance(info, (list, tuple)) and len(info) >= 2:
            n, sec = info[0], info[1]
        elif isinstance(info, dict):
            n = info.get("name") or info.get("Name") or sym
            sec = info.get("sector") or info.get("Sector") or ""
    except Exception:
        pass

    st.markdown(f"### {n} ({sym})")
    tabs = st.tabs(["🤖 المستشار", "💰 مالي", "📈 فني", "🏛️ كلاسيكي", "📝 أطروحة"])

    with tabs[0]:
        tab_ai.render(sym)

    with tabs[1]:
        tab_finance.render(sym)

    with tabs[2]:
        tab_technical.render(sym)

    with tabs[3]:
        tab_classical.render(sym)

    with tabs[4]:
        tab_thesis.render(sym)
