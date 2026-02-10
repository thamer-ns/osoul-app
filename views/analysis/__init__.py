# views/analysis/__init__.py
import traceback
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from components import render_kpi, render_ticker_card
from data_source import get_company_details
from database import fetch_table
from market_data import get_chart_history
from views.shared import (
    _clean_symbols_list,
    _normalize_symbol,
    _safe_status_series,
    run_stress_test,
)

from .advisor import render_advisor_tab
from .classical import render_classical_tab
from .financial import render_financial_dashboard_ui
# ========================================================
# Technical tab import (fail-safe)
#
# السبب: بعض الإصدارات/الفروع كانت تُسمي واجهة التحليل الفني `view_technical`
# ولم تُصدِّر الاسم المتوافق `render_technical_tab`.
# إذا فشل الاستيراد أو لم يكن الاسم موجودًا، نستخدم fallback آمن بدل كسر التطبيق بالكامل.
# ========================================================
try:
    from .technical import render_technical_tab
except Exception:
    try:
        from .technical import view_technical as render_technical_tab
    except Exception:
        def render_technical_tab(symbol: str, interval: str = "1d"):
            st.error("تعذر تحميل تبويب التحليل الفني (technical).")
            st.caption("تحقق من: views/analysis/technical.py")
from .thesis import render_thesis_tab


# ========================================================
# UI helpers (لا تغيّر أي منطق تحليل—فقط عرض)
# ========================================================

def _safe_float(x, default=None):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def _safe_get_last_price_change(symbol: str):
    """Try to get last close + % change. Safe fallback if data missing."""
    try:
        df = get_chart_history(symbol, period="5d", interval="1d")
        if df is None:
            return None, None
        if not isinstance(df, pd.DataFrame):
            try:
                df = pd.DataFrame(df)
            except Exception:
                return None, None

        if df.empty:
            return None, None

        # normalize columns
        cols = {str(c).lower(): c for c in df.columns}
        c_close = cols.get("close") or ("Close" if "Close" in df.columns else None)
        if c_close is None:
            return None, None

        ser = pd.to_numeric(df[c_close], errors="coerce").dropna()
        if ser.empty:
            return None, None

        last = float(ser.iloc[-1])
        prev = float(ser.iloc[-2]) if len(ser) >= 2 else None
        chg = None
        if prev and prev != 0:
            chg = (last / prev - 1.0) * 100.0
        return last, chg
    except Exception:
        return None, None


def _section_header(symbol: str, name: str, sector: str, trades: pd.DataFrame):
    """Top summary area: ticker card + key KPIs + context."""

    price, chg = _safe_get_last_price_change(symbol)

    # --- Top row: card + meta
    left, right = st.columns([1.3, 2.7])
    with left:
        render_ticker_card(
            symbol=symbol,
            name=name or symbol,
            price=price if price is not None else "-",
            change=chg if chg is not None else 0,
        )

    with right:
        st.markdown(
            f"""
            <div class="os-card" style="padding:16px;">
              <div class="os-card-title">🧾 معلومات السهم</div>
              <div class="os-kv"><div class="os-k">الاسم</div><div class="os-v" style="direction:rtl;text-align:right;">{name or symbol}</div></div>
              <div class="os-kv"><div class="os-k">الرمز</div><div class="os-v">{symbol}</div></div>
              <div class="os-kv"><div class="os-k">القطاع</div><div class="os-v" style="direction:rtl;text-align:right;">{sector or '—'}</div></div>
              <div class="os-kv"><div class="os-k">آخر تحديث</div><div class="os-v">{datetime.now().strftime('%Y-%m-%d %H:%M')}</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # --- Second row: quick KPIs from portfolio trades (if available)
    try:
        status = _safe_status_series(trades)
        open_pos = trades[status == "open"].copy() if (trades is not None and not trades.empty and "status" in trades.columns) else pd.DataFrame()
        n_open = int(len(open_pos))
    except Exception:
        n_open = 0

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_kpi("مراكز مفتوحة", n_open, "blue", "📌")
    with k2:
        render_kpi("السعر", f"{price:,.2f}" if isinstance(price, (int, float)) else "—", "neutral", "💵")
    with k3:
        if isinstance(chg, (int, float)):
            render_kpi("التغير اليومي", f"{chg:+.2f}%", "success" if chg >= 0 else "danger", "📈")
        else:
            render_kpi("التغير اليومي", "—", "neutral", "📈")
    with k4:
        render_kpi("الملخص", "انتقل للتبويبات", "neutral", "🧭")


def _safe_render(title: str, fn, *args, **kwargs):
    """Render a tab safely and show full error details (بدون إخفاء شيء)."""
    try:
        fn(*args, **kwargs)
    except Exception as e:
        st.error(f"❌ حصل خطأ داخل تبويب: {title}")
        st.caption("هذا لا يعني حذف ميزة؛ غالبًا خطأ بيانات/استدعاء/إصدار. التفاصيل بالأسفل:")
        st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)))


# ========================================================
# Main View
# ========================================================

def view_analysis(fin):
    st.header("🔬 التحليل الشامل")

    trades = fin.get("all_trades", pd.DataFrame())

    # --------------------------------------------------------
    # Stress test (كما هو—فقط تحسين إخراج بسيط)
    # --------------------------------------------------------
    if not trades.empty and "status" in trades.columns:
        status = _safe_status_series(trades)
        open_pos = trades[status == "open"].copy()

        st.subheader("📊 اختبار التحمل")
        res = run_stress_test(_safe_float(fin.get("market_val_open", 0), 0) or 0, open_pos)
        if res.get("scenarios"):
            c_stress, c_insight = st.columns([3, 1])
            with c_stress:
                sdf = pd.DataFrame(res["scenarios"])
                if not sdf.empty and "scenario" in sdf.columns and "impact_pct" in sdf.columns:
                    st.plotly_chart(px.bar(sdf, x="scenario", y="impact_pct"), use_container_width=True)
            with c_insight:
                st.info(res.get("insight", ""))
        st.markdown("---")

    # --------------------------------------------------------
    # Build symbols list from trades + watchlist (كما هو)
    # --------------------------------------------------------
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

    all_syms = _clean_symbols_list(syms)

    # --------------------------------------------------------
    # Search box UI (محسّن بصريًا بدون تغيير المنطق)
    # --------------------------------------------------------
    st.markdown("##### 🔎 البحث عن سهم")
    with st.form("analysis_search_form", clear_on_submit=False):
        c1, c2, c3, c4 = st.columns([1.5, 2.4, 1.1, 0.8])
        q = c1.text_input("اكتب الرمز", key="analysis_q", placeholder="مثال: 1120 أو 1120.SR")

        q_plain = (q or "").strip().upper()
        filtered = all_syms
        if q_plain:
            filtered = []
            for s in all_syms:
                su = s.upper()
                if q_plain in su or q_plain in su.replace(".SR", ""):
                    filtered.append(s)
            filtered = filtered[:120]

        picked = c2.selectbox(
            "اقتراحات من أسهمك",
            options=(filtered if filtered else (all_syms[:120] if all_syms else ["-"])),
            key="analysis_pick",
            disabled=(len(all_syms) == 0),
        )

        go_btn = c3.form_submit_button("تحليل", type="primary")
        clear_btn = c4.form_submit_button("مسح")

    if clear_btn:
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

            if ok:
                st.session_state["analysis_active_symbol"] = sym_try
                st.rerun()
            else:
                st.error("❌ الرمز غير معروف أو لا يمكن جلب بياناته الآن. تأكد من كتابة الرمز بشكل صحيح.")

    # --------------------------------------------------------
    # Active symbol block
    # --------------------------------------------------------
    sym = st.session_state.get("analysis_active_symbol")
    if not sym:
        st.info("اختر سهمًا من الأعلى لبدء التحليل.")
        return

    sym = _normalize_symbol(sym)
    if not sym or sym == ".SR":
        st.warning("الرجاء إدخال رمز صحيح.")
        return

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

    # ✅ UI: summary header + KPIs
    _section_header(sym, n, sec, trades)

    # --------------------------------------------------------
    # Tabs (نفس التبويبات بدون حذف/تغيير—مع حراسة أخطاء)
    # --------------------------------------------------------
    st.markdown("### 🧩 تبويبات التحليل")
    st.caption("ملاحظة: أي خطأ في تبويب واحد سيتم عرضه بالتفصيل دون إخفاء بقية التبويبات.")

    tabs = st.tabs([
        "🤖 المستشار",
        "💰 التحليل المالي",
        "📈 التحليل الفني",
        "🏛️ التحليل الكلاسيكي",
        "📝 الأطروحة/الخطة",
        "🧪 تشخيص العرض",
    ])

    with tabs[0]:
        _safe_render("المستشار", render_advisor_tab, sym)

    with tabs[1]:
        _safe_render("مالي", render_financial_dashboard_ui, sym)

    with tabs[2]:
        _safe_render("فني", render_technical_tab, sym)

    with tabs[3]:
        _safe_render("كلاسيكي", render_classical_tab, sym)

    with tabs[4]:
        _safe_render("أطروحة", render_thesis_tab, sym)

    # --------------------------------------------------------
    # Diagnostics: ensure nothing is silently hidden
    # --------------------------------------------------------
    with tabs[5]:
        st.subheader("🧪 تشخيص ظهور التفاصيل")
        st.caption(
            "هذا القسم يساعدك تتأكد أن كل شيء مبرمج يظهر فعلاً. "
            "لن يحذف شيئًا؛ فقط يعرض حالة الوحدات والبيانات بشكل واضح."
        )

        # Data availability checks
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**رمز نشط**")
            st.write(sym)
        with c2:
            st.markdown("**عدد عمليات المحفظة**")
            st.write(int(len(trades)) if isinstance(trades, pd.DataFrame) else 0)
        with c3:
            st.markdown("**قائمة المتابعة**")
            try:
                st.write(int(len(wl)) if isinstance(wl, pd.DataFrame) else 0)
            except Exception:
                st.write(0)

        st.markdown("---")

        # Chart data check
        st.markdown("### 📈 فحص بيانات الشارت")
        with st.spinner("اختبار جلب بيانات السعر..."):
            p, c = _safe_get_last_price_change(sym)
        if p is None:
            st.warning("تعذر جلب بيانات السعر لهذا الرمز الآن (مصدر البيانات قد يكون متوقف/حظر/انقطاع).")
        else:
            st.success(
                f"تم جلب السعر بنجاح: {p:,.2f}"
                + (f" | التغير: {c:+.2f}%" if isinstance(c, (int, float)) else "")
            )

        st.markdown("---")
        st.markdown("### 🧩 ملاحظة مهمة")
        st.info(
            "إذا لاحظت أن جزءًا من تبويب (مالي/فني/مستشار) لا يظهر، "
            "ادخل نفس التبويب وستجد رسالة خطأ مفصّلة داخل التبويب نفسه. "
            "هذا يضمن أن ما عندك شيء 'مبرمج' لكنه مخفي بدون ما تدري."
        )
