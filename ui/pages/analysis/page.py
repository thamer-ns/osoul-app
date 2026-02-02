# ui/pages/analysis/page.py
import streamlit as st
import pandas as pd

from database import fetch_table
from market_data import get_chart_history
from data_source import get_company_details

from ui.common import sym_key as _sym_key, normalize_symbol as _normalize_symbol
from ui.common import safe_status_series as _safe_status_series, clean_symbols_list as _clean_symbols_list

from ui.pages.analysis.tabs.ai import render_tab as render_ai_tab
from ui.pages.analysis.tabs.finance import render_tab as render_finance_tab
from ui.pages.analysis.tabs.technical import render_tab as render_technical_tab
from ui.pages.analysis.tabs.classical import render_tab as render_classical_tab
from ui.pages.analysis.tabs.thesis import render_tab as render_thesis_tab


def _get_watchlist_symbols() -> list[str]:
    try:
        wl = fetch_table("watchlist")
        if isinstance(wl, pd.DataFrame) and (not wl.empty) and ("symbol" in wl.columns):
            return wl["symbol"].astype(str).tolist()
    except Exception:
        pass
    return []


def _get_trades_symbols(fin: dict) -> list[str]:
    trades = fin.get("all_trades", pd.DataFrame())
    if isinstance(trades, pd.DataFrame) and (not trades.empty) and ("symbol" in trades.columns):
        return trades["symbol"].astype(str).tolist()
    return []


def _symbol_exists(symbol: str) -> bool:
    # 1) نحاول تفاصيل الشركة
    try:
        info = get_company_details(symbol)
        if isinstance(info, (list, tuple)) and len(info) >= 1:
            return bool(str(info[0]).strip())
        if isinstance(info, dict):
            return bool(str(info.get("name") or info.get("Name") or "").strip())
        return bool(str(info).strip())
    except Exception:
        pass

    # 2) fallback: نجرب نجلب شارت بسيط
    try:
        df = get_chart_history(symbol, period="1mo")
        return isinstance(df, pd.DataFrame) and (not df.empty)
    except Exception:
        return False


def _resolve_company_name_sector(symbol: str) -> tuple[str, str]:
    try:
        info = get_company_details(symbol)
        if isinstance(info, (list, tuple)) and len(info) >= 2:
            return str(info[0] or symbol), str(info[1] or "")
        if isinstance(info, dict):
            name = info.get("name") or info.get("Name") or symbol
            sector = info.get("sector") or info.get("Sector") or ""
            return str(name or symbol), str(sector or "")
    except Exception:
        pass
    return symbol, ""


def view_analysis(fin: dict):
    st.header("🔬 التحليل الشامل")

    # -----------------------------
    # (اختياري) اختبار التحمل
    # -----------------------------
    trades = fin.get("all_trades", pd.DataFrame())
    if isinstance(trades, pd.DataFrame) and (not trades.empty) and ("status" in trades.columns):
        try:
            from ai_engine import run_stress_test  # موجود عندك
            status = _safe_status_series(trades)
            open_pos = trades[status == "open"].copy()

            if not open_pos.empty:
                st.subheader("📊 اختبار التحمل")
                res = run_stress_test(float(fin.get("market_val_open", 0)), open_pos)
                if isinstance(res, dict) and res.get("scenarios"):
                    sdf = pd.DataFrame(res["scenarios"])
                    if (not sdf.empty) and ("scenario" in sdf.columns) and ("impact_pct" in sdf.columns):
                        import plotly.express as px
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.plotly_chart(px.bar(sdf, x="scenario", y="impact_pct"), use_container_width=True)
                        with c2:
                            st.info(res.get("insight", "") or "")
                st.divider()
        except Exception:
            # ما نخليها تكسر الصفحة
            pass

    # -----------------------------
    # قائمة الرموز (من صفقات + ووتش ليست)
    # -----------------------------
    syms = _get_trades_symbols(fin) + _get_watchlist_symbols()
    all_syms = _clean_symbols_list(syms)

    st.markdown("##### 🔎 البحث عن سهم")
    with st.form("analysis_search_form", clear_on_submit=False):
        c1, c2, c3 = st.columns([1.6, 2.2, 1.2])

        q = c1.text_input("اكتب الرمز", key="analysis_q", placeholder="مثال: 1120 أو 1120.SR")
        q_plain = (q or "").strip().upper()

        filtered = all_syms
        if q_plain:
            filtered = [s for s in all_syms if (q_plain in s.upper()) or (q_plain in s.upper().replace(".SR", ""))]
            filtered = filtered[:80]

        picked = c2.selectbox(
            "اقتراحات من أسهمك",
            options=(filtered if filtered else (all_syms[:80] if all_syms else ["-"])),
            key="analysis_pick",
            disabled=(len(all_syms) == 0),
        )
        go_btn = c3.form_submit_button("تحليل", type="primary")

    c_clear, _ = st.columns([1, 6])
    with c_clear:
        if st.button("مسح", key="analysis_clear"):
            st.session_state.pop("analysis_active_symbol", None)
            st.rerun()

    if go_btn:
        raw = q_plain.strip()
        if (not raw) or raw == "-":
            raw = picked if picked and picked != "-" else ""
        sym_try = _normalize_symbol(raw)

        if not sym_try or sym_try == ".SR":
            st.warning("الرجاء إدخال رمز صحيح مثل: 1120 أو 1120.SR")
        else:
            if _symbol_exists(sym_try):
                st.session_state["analysis_active_symbol"] = sym_try
                st.rerun()
            else:
                st.error("❌ الرمز غير معروف أو لا يمكن جلب بياناته الآن. تأكد من كتابة الرمز بشكل صحيح.")

    sym = st.session_state.get("analysis_active_symbol")
    if not sym:
        st.info("اختر سهمًا للبدء.")
        return

    sym = _normalize_symbol(sym)
    if not sym or sym == ".SR":
        st.warning("الرجاء إدخال رمز صحيح.")
        return

    name, sector = _resolve_company_name_sector(sym)
    st.markdown(f"### {name} ({sym})")
    if sector:
        st.caption(f"القطاع: {sector}")

    tabs = st.tabs(["🤖 المستشار", "💰 مالي", "📈 فني", "🏛️ كلاسيكي", "📝 أطروحة"])

    with tabs[0]:
        render_ai_tab(symbol=sym, fin=fin, company_name=name, sector=sector)

    with tabs[1]:
        render_finance_tab(symbol=sym, fin=fin, company_name=name, sector=sector)

    with tabs[2]:
        render_technical_tab(symbol=sym, fin=fin, company_name=name, sector=sector)

    with tabs[3]:
        render_classical_tab(symbol=sym, fin=fin, company_name=name, sector=sector)

    with tabs[4]:
        render_thesis_tab(symbol=sym, fin=fin, company_name=name, sector=sector)
