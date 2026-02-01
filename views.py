# views.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date
import traceback

VIEWS_UI_VERSION = "3.2.0"

from config import DEFAULT_COLORS
from components import (
    render_kpi,
    render_custom_table,
    render_ticker_card,
    safe_fmt,
    inject_component_styles,
    inject_streamlit_ar_i18n,
)
from analytics import (
    calculate_portfolio_metrics,
    update_prices,
    generate_equity_curve,
    create_smart_backup,
)
from database import execute_query, fetch_table, db_healthcheck
from market_data import get_tasi_data, get_chart_history, fetch_batch_data
from data_source import get_company_details
from security import validate_trade_inputs


# ========================================================
# 🛡️ Fail-Safe Imports
# ========================================================
try:
    from charts import render_technical_chart
except Exception:
    def render_technical_chart(symbol, *args, **kwargs):
        st.warning("⚠️ ملف charts.py مفقود أو به خطأ.")

bt_import_error = None
try:
    from backtester import run_backtest, list_strategies
except Exception as e:
    run_backtest = None
    list_strategies = lambda: []
    bt_import_error = repr(e)

try:
    from financial_analysis import (
        get_thesis, save_thesis,
        FinancialParser, save_financial_record,
        get_stored_financials_df, get_advanced_fundamental_ratios,
        sync_auto_yahoo, get_fundamental_ratios,
        get_financial_statements,
    )
except Exception:
    def get_thesis(s): return None
    def save_thesis(s, t, tg, r): pass
    def get_stored_financials_df(s, p): return pd.DataFrame()
    def get_advanced_fundamental_ratios(s): return {}
    def get_financial_statements(s, p="Annual", refresh=False): return pd.DataFrame()

    class FinancialParser:
        def process_file_or_text(self, uploaded_file=None, text_input=None):
            return [], None, "FinancialParser غير متوفر"
    def save_financial_record(*args, **kwargs): return False
    def sync_auto_yahoo(s): return False, "Module Missing"
    def get_fundamental_ratios(s): return {}

try:
    from classical_analysis import render_classical_analysis
except Exception:
    def render_classical_analysis(s):
        st.warning("⚠️ ملف classical_analysis.py مفقود أو به خطأ.")

ai_import_error = None
AI_ENGINE_VERSION = "unknown"
try:
    from ai_engine import (
        generate_ai_report,
        calculate_portfolio_risk_score,
        run_stress_test,
        generate_rebalancing_suggestions,
        save_user_rule,
        load_user_rules,
        AI_ENGINE_VERSION as _AE_VER,
    )
    AI_ENGINE_VERSION = _AE_VER
except Exception:
    ai_import_error = traceback.format_exc()

    def generate_ai_report(symbol, timeframe="1d"):
        return {"__error__": "AI Engine import failed", "__trace__": ai_import_error}

    def calculate_portfolio_risk_score(df, c): return 50
    def run_stress_test(v, df): return {"scenarios": [], "insight": ""}
    def generate_rebalancing_suggestions(df, c): return []
    def save_user_rule(rule_text: str, title: str = None, enabled: int = 1):
        return {"ok": False, "reason": "AI Engine missing", "trace": ai_import_error}
    def load_user_rules(enabled_only=True, max_rows=50):
        return []


# ========================================================
# Helpers
# ========================================================
def _ensure_ui_once():
    if st.session_state.get("_ui_injected_once"):
        return
    st.session_state["_ui_injected_once"] = True
    try:
        inject_component_styles()
    except Exception:
        pass
    try:
        inject_streamlit_ar_i18n(True)
    except Exception:
        pass


def _sym_key(sym: str) -> str:
    return (sym or "").replace(".", "_").replace("-", "_").replace(" ", "_")


def _normalize_symbol(sym: str) -> str:
    sym = (sym or "").strip().upper()
    if not sym:
        return ""
    if sym.isdigit():
        return f"{sym}.SR"
    sym = sym.replace(" ", "").replace("-", "")
    if sym.endswith("SR") and ".SR" not in sym:
        sym = sym.replace("SR", ".SR")
    return sym


def _safe_status_series(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty or "status" not in df.columns:
        return pd.Series([], dtype=str)
    return df["status"].astype(str).str.strip().str.lower()


def _clean_symbols_list(values) -> list:
    out = []
    try:
        for x in (values or []):
            s = _normalize_symbol(str(x))
            if s and s != ".SR" and s.lower() != "nan":
                out.append(s)
    except Exception:
        pass
    return list(sorted(set(out)))


def _select_strategy_ui(key_prefix: str = "lab"):
    raw = list_strategies() or ["Trend", "Sniper"]

    if raw and isinstance(raw[0], (tuple, list)):
        strat_map = {}
        for item in raw:
            if not item:
                continue
            k = str(item[0])
            label = str(item[1]) if len(item) > 1 else k
            strat_map[label] = k

        if not strat_map:
            return "Trend"

        label = st.selectbox(
            "اختر الاستراتيجية",
            list(strat_map.keys()),
            index=0,
            key=f"{key_prefix}_strat_label",
        )
        return strat_map[label]

    if raw and isinstance(raw[0], dict):
        strat_map = {}
        for d in raw:
            k = str(d.get("key") or d.get("id") or d.get("value") or "")
            label = str(d.get("name") or d.get("label") or k)
            if k:
                strat_map[label] = k
        if strat_map:
            label = st.selectbox(
                "اختر الاستراتيجية",
                list(strat_map.keys()),
                index=0,
                key=f"{key_prefix}_strat_label",
            )
            return strat_map[label]
        return "Trend"

    raw_str = [str(x) for x in raw] if raw else ["Trend", "Sniper"]
    return st.selectbox("اختر الاستراتيجية", raw_str, index=0, key=f"{key_prefix}_strat")


def _render_technical_chart_flex(symbol: str, period: str = "2y", interval: str = "1d"):
    try:
        return render_technical_chart(symbol, period=period, interval=interval)
    except TypeError:
        try:
            return render_technical_chart(symbol, period=period)
        except TypeError:
            try:
                return render_technical_chart(symbol, period)
            except TypeError:
                return render_technical_chart(symbol)


def _get_chart_history_flex(symbol: str, period: str, interval: str):
    try:
        return get_chart_history(symbol, period=period, interval=interval)
    except TypeError:
        try:
            return get_chart_history(symbol, period)
        except TypeError:
            return get_chart_history(symbol)


# ========================================================
# ✅ NEW: AI Report Rendering (واضح جدًا)
# ========================================================
def _ai_timeframe_normalize(tf: str) -> str:
    t = (tf or "").strip()
    if not t:
        return "1d"
    t_low = t.lower()
    if t in ["1D", "D", "DAY"]:
        return "1d"
    if t in ["1W", "W", "WEEK"]:
        return "1wk"
    if t in ["1M", "M", "MONTH"]:
        return "1mo"
    if t_low in ["1d", "day", "daily"]:
        return "1d"
    if t_low in ["1wk", "1w", "week", "weekly"]:
        return "1wk"
    if t_low in ["1mo", "month", "monthly"]:
        return "1mo"
    return t_low


def _generate_ai_report_flex(symbol: str, timeframe: str):
    tf = _ai_timeframe_normalize(timeframe)
    try:
        return generate_ai_report(symbol, timeframe=tf)
    except TypeError:
        try:
            return generate_ai_report(symbol, tf)
        except TypeError:
            return generate_ai_report(symbol)


def _pill(text: str, bg="#0ea5e9"):
    st.markdown(
        f"<span style='display:inline-block;padding:6px 10px;border-radius:999px;background:{bg};color:white;font-weight:700;font-size:0.9rem;'>"
        f"{text}</span>",
        unsafe_allow_html=True
    )


def _render_risk_gates_table(gates):
    if not gates:
        st.info("لا توجد بوابات مخاطرة في التقرير.")
        return
    df = pd.DataFrame(gates)
    if df.empty:
        st.info("لا توجد بوابات مخاطرة في التقرير.")
        return

    # ترتيب أعمدة
    cols = []
    for c in ["gate", "status", "note"]:
        if c in df.columns:
            cols.append(c)
    df = df[cols]

    def _status_badge(x):
        x = str(x).lower().strip()
        if x == "pass":
            return "✅ PASS"
        if x == "fail":
            return "❌ FAIL"
        if x == "warn":
            return "⚠️ WARN"
        return x

    if "status" in df.columns:
        df["status"] = df["status"].apply(_status_badge)

    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_targets(targets):
    if not targets:
        st.info("لا توجد أهداف محددة في التقرير.")
        return
    df = pd.DataFrame(targets)
    if df.empty:
        st.info("لا توجد أهداف محددة في التقرير.")
        return
    # تنسيق
    if "price" in df.columns:
        df["price"] = pd.to_numeric(df["price"], errors="coerce").round(2)
    if "rr" in df.columns:
        df["rr"] = pd.to_numeric(df["rr"], errors="coerce").round(2)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_ai_report_ui(rep: dict):
    if not isinstance(rep, dict):
        st.warning("⚠️ تقرير المستشار ليس dict.")
        st.write(rep)
        return

    # Header version stamp (للتأكد أن التغيير اشتغل)
    st.caption(f"🧩 UI Build: views.py v{VIEWS_UI_VERSION} | AI Engine v{AI_ENGINE_VERSION}")

    # Error
    if rep.get("__error__") or rep.get("__trace__"):
        st.error("فشل تشغيل المستشار (AI Engine).")
        st.code(rep.get("__trace__", "")[:4000])
        st.json(rep)
        return

    rec = rep.get("recommendation", "-")
    score = rep.get("score", None)
    conf = int(rep.get("confidence", 0) or 0)
    col = rep.get("color", "#666")
    tf = rep.get("meta", {}).get("timeframe", rep.get("timeframe", "-"))
    as_of = rep.get("meta", {}).get("as_of", "")

    # Top Card
    st.markdown(
        f"""
        <div style="border:2px solid {col};border-radius:16px;padding:16px;">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
                <div style="font-size:1.3rem;font-weight:900;">{rec}</div>
                <div style="opacity:0.85;font-weight:700;">TF: {tf} &nbsp; | &nbsp; {as_of}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    c1, c2, c3 = st.columns([1.2, 1.2, 2.0])
    with c1:
        if score is not None:
            st.metric("Score", f"{score}/100")
        else:
            st.metric("Score", "N/A")
    with c2:
        st.metric("Confidence", f"{conf}%")
    with c3:
        st.progress(min(max(conf, 0), 100))

    # Summary text (سبب التوصية كنص واحد مرتب)
    summary_text = rep.get("summary_text", "")
    if summary_text:
        st.markdown("### 🧾 سبب التوصية (مرتب)")
        st.code(summary_text, language="text")
    else:
        st.info("لا يوجد summary_text في التقرير (تأكد من ai_engine.py).")

    st.markdown("---")

    # Entry / Risk / Targets
    entry = rep.get("entry", {}) or {}
    risk = rep.get("risk", {}) or {}
    targets = rep.get("targets", []) or []

    e1, e2, e3 = st.columns(3)
    with e1:
        st.markdown("#### 🎯 دخول")
        ez = entry.get("entry_zone")
        if ez and isinstance(ez, (list, tuple)) and len(ez) == 2:
            _pill(f"Zone: {ez[0]} → {ez[1]}", bg="#0ea5e9")
        else:
            st.write("Zone: -")
        if entry.get("entry_note"):
            st.caption(entry.get("entry_note"))

    with e2:
        st.markdown("#### 🛑 وقف/إبطال")
        st.write(f"Stop: **{risk.get('stop','-')}**")
        st.write(f"Invalidation: **{risk.get('invalidation','-')}**")
        st.write(f"RR (T1): **{risk.get('rr','-')}**")

    with e3:
        st.markdown("#### 🧩 مستويات")
        lv = rep.get("levels", {}) or {}
        st.write(f"Support: **{lv.get('support','-')}**")
        st.write(f"Resistance: **{lv.get('resistance','-')}**")
        if lv.get("fib382") is not None:
            st.caption(f"Fibo 38.2: {lv.get('fib382')} | 50: {lv.get('fib50')} | 61.8: {lv.get('fib618')}")

    st.markdown("#### 🎯 الأهداف (Targets)")
    _render_targets(targets)

    st.markdown("---")

    # Evidence
    ev = rep.get("evidence", {}) or {}
    pos = ev.get("positives", []) or []
    neg = ev.get("negatives", []) or []
    notes = ev.get("notes", []) or []

    a, b = st.columns(2)
    with a:
        st.markdown("### ✅ Evidence داعم")
        if pos:
            for x in pos:
                st.write(f"- {x}")
        else:
            st.info("لا توجد نقاط داعمة.")

    with b:
        st.markdown("### ⚠️ مخاطر/سلبيات")
        if neg:
            for x in neg:
                st.write(f"- {x}")
        else:
            st.info("لا توجد مخاطر واضحة في التقرير.")

    with st.expander("🗒️ ملاحظات إضافية"):
        if notes:
            for x in notes:
                st.write(f"- {x}")
        else:
            st.info("لا توجد ملاحظات.")

    st.markdown("---")

    # Risk gates table
    st.markdown("### 🧱 بوابات المخاطرة (Risk Gates)")
    _render_risk_gates_table(rep.get("risk_gates", []) or [])

    st.markdown("---")

    # Scenarios
    sc = rep.get("scenarios", []) or []
    st.markdown("### 🧭 سيناريوهات متعددة")
    if not sc:
        st.info("لا توجد سيناريوهات.")
    else:
        names = [f"{x.get('name','Scenario')} ({x.get('probability','-')}%)" for x in sc]
        tabs = st.tabs(names)
        for i, t in enumerate(tabs):
            with t:
                s = sc[i]
                st.write(f"**الخطة:** {s.get('plan','-')}")
                st.write(f"**Stop:** {s.get('stop','-')}")
                st.markdown("**Targets:**")
                _render_targets(s.get("targets", []) or [])

    # Raw JSON (للتشخيص)
    with st.expander("🧩 عرض التقرير الخام (JSON)"):
        st.json(rep)


# ========================================================
# TradingView-like Plot
# ========================================================
def _build_tv_like_plot(df: pd.DataFrame, title: str = "") -> go.Figure:
    d = df.copy()

    if "date" in d.columns:
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d = d.dropna(subset=["date"]).sort_values("date")
        x = d["date"]
    else:
        try:
            d.index = pd.to_datetime(d.index, errors="coerce")
        except Exception:
            pass
        d = d[~pd.isna(d.index)]
        d = d.sort_index()
        x = d.index

    colmap = {str(c).lower(): c for c in d.columns}
    Open = colmap.get("open") if "open" in colmap else ("Open" if "Open" in d.columns else None)
    High = colmap.get("high") if "high" in colmap else ("High" if "High" in d.columns else None)
    Low  = colmap.get("low") if "low" in colmap else ("Low" if "Low" in d.columns else None)
    Close= colmap.get("close") if "close" in colmap else ("Close" if "Close" in d.columns else None)
    Vol  = colmap.get("volume") if "volume" in colmap else ("Volume" if "Volume" in d.columns else None)

    if not all([Open, High, Low, Close]):
        raise ValueError("بيانات الشارت لا تحتوي أعمدة OHLC بشكل صحيح.")

    for c in [Open, High, Low, Close]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if Vol and Vol in d.columns:
        d[Vol] = pd.to_numeric(d[Vol], errors="coerce").fillna(0)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25]
    )

    fig.add_trace(
        go.Candlestick(
            x=x,
            open=d[Open], high=d[High], low=d[Low], close=d[Close],
            name="OHLC",
        ),
        row=1, col=1
    )

    if Vol and Vol in d.columns:
        fig.add_trace(
            go.Bar(x=x, y=d[Vol], name="Volume"),
            row=2, col=1
        )

    fig.update_layout(
        title=title,
        height=720,
        margin=dict(l=10, r=10, t=50, b=10),
        xaxis=dict(
            rangeslider=dict(visible=True),
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            showline=True,
        ),
        xaxis2=dict(showspikes=True, spikemode="across", spikesnap="cursor"),
        yaxis=dict(showspikes=True, spikemode="across", spikesnap="cursor", fixedrange=False),
        yaxis2=dict(showspikes=True, spikemode="across", spikesnap="cursor", fixedrange=False),
        hovermode="x unified",
        dragmode="pan",
        showlegend=False,
    )

    fig.update_xaxes(
        rangeselector=dict(
            buttons=list([
                dict(count=7, label="7D", step="day", stepmode="backward"),
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=3, label="3M", step="month", stepmode="backward"),
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="1Y", step="year", stepmode="backward"),
                dict(step="all", label="All"),
            ])
        )
    )
    return fig


def _render_tv_like_chart(symbol: str, period: str, interval: str):
    with st.spinner("جاري جلب بيانات الشارت..."):
        df = _get_chart_history_flex(symbol, period, interval)

    if df is None:
        st.error("❌ لم يتم جلب بيانات الشارت.")
        return

    if not isinstance(df, pd.DataFrame):
        try:
            df = pd.DataFrame(df)
        except Exception:
            st.error("❌ البيانات غير قابلة للتحويل إلى DataFrame.")
            return

    if df.empty:
        st.warning("⚠️ البيانات فارغة (جرّب فترة أكبر).")
        return

    if "date" not in df.columns:
        try:
            if isinstance(df.index, pd.DatetimeIndex):
                df2 = df.copy().reset_index().rename(columns={"index": "date"})
                df = df2
        except Exception:
            pass

    try:
        fig = _build_tv_like_plot(df, title=f"{symbol} | {period} | {interval}")
        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "scrollZoom": True,
                "displaylogo": False,
                "displayModeBar": True,
                "modeBarButtonsToAdd": [
                    "drawline", "drawopenpath", "drawrect", "drawcircle", "eraseshape",
                ],
            },
        )
        st.caption("💡 اسحب للتحريك، Scroll للتكبير، و Range Slider للتنقل.")
    except Exception as e:
        st.error(f"❌ فشل بناء الشارت الاحترافي: {e}")
        st.info("سأعرض الشارت القديم كخطة بديلة.")
        _render_technical_chart_flex(symbol, period=period, interval=interval)


# ========================================================
# 1) Navigation
# ========================================================
def render_navbar():
    buttons = [
        ("🏠 الرئيسية", "home"),
        ("⚡ مضاربة", "spec"),
        ("💎 استثمار", "invest"),
        ("💓 نبض", "pulse"),
        ("📜 صكوك", "sukuk"),
        ("🔍 تحليل", "analysis"),
        ("🧪 المختبر", "backtest"),
        ("💰 السيولة", "cash"),
        ("🔄 تحديث", "update"),
    ]

    st.markdown(
        """<style>
        div.stButton > button {width: 100%; border-radius: 8px;}
        </style>""",
        unsafe_allow_html=True
    )

    cols = st.columns(len(buttons) + 1)

    for i, (label, key) in enumerate(buttons):
        with cols[i]:
            type_btn = "primary" if st.session_state.get("page") == key else "secondary"
            if st.button(label, key=f"nav_{key}", type=type_btn):
                st.session_state.page = key
                st.rerun()

    with cols[-1]:
        with st.popover("👤 القائمة"):
            st.write(f"مرحباً {st.session_state.get('username','User')}")
            if st.button("➕ إضافة صفقة", key="menu_add_trade"):
                st.session_state.page = "add"
                st.rerun()
            if st.button("⚙️ إعدادات", key="menu_settings"):
                st.session_state.page = "settings"
                st.rerun()

            st.markdown("---")
            if st.button("🚪 خروج", key="menu_logout"):
                try:
                    from security import logout
                    logout()
                except Exception:
                    st.session_state.clear()
                    st.rerun()


# ========================================================
# 2) Dashboard
# ========================================================
def view_dashboard(fin):
    try:
        tp, tc = get_tasi_data()
    except Exception:
        tp, tc = 0, 0

    ar = "🔼" if tc >= 0 else "🔽"
    df = fin.get("all_trades", pd.DataFrame())

    total_assets = float(fin.get("market_val_open", 0)) + float(fin.get("cash", 0))
    cash_pct = (float(fin.get("cash", 0)) / total_assets * 100) if total_assets else 0

    risk_score = calculate_portfolio_risk_score(df, cash_pct)
    risk_color = "success" if risk_score < 40 else "danger" if risk_score > 70 else "neutral"
    risk_label = "منخفضة" if risk_score < 40 else "عالية" if risk_score > 70 else "متوسطة"

    c_tasi, c_risk = st.columns([3, 1])
    with c_tasi:
        st.markdown(
            f"""
            <div class="tasi-card">
                <div>
                    <div style="opacity:0.9;">المؤشر العام (TASI)</div>
                    <div style="font-size:2.5rem; font-weight:900;">{safe_fmt(tp)}</div>
                </div>
                <div style="background:rgba(255,255,255,0.2); padding:5px 15px; border-radius:10px; font-weight:bold; direction:ltr;">
                    {ar} {tc:.2f}%
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with c_risk:
        render_kpi(f"المخاطرة ({risk_label})", f"{risk_score}/100", risk_color, "🛡️")

    c1, c2, c3, c4 = st.columns(4)
    total_pl = float(fin.get("unrealized_pl", 0)) + float(fin.get("realized_pl", 0))
    with c1:
        render_kpi(f"الكاش ({cash_pct:.1f}%)", safe_fmt(fin.get("cash", 0)), "blue", "💵")
    with c2:
        render_kpi("صافي الإيداعات", safe_fmt(fin.get("total_deposited", 0) - fin.get("total_withdrawn", 0)), "neutral", "🏗️")
    with c3:
        render_kpi("إجمالي الأصول", safe_fmt(total_assets), "neutral", "🏦")
    with c4:
        render_kpi("صافي الربح الكلي", safe_fmt(total_pl), "success" if total_pl >= 0 else "danger", "📈")

    st.markdown("---")
    if df.empty:
        st.info("👋 مرحباً بك! ابدأ بإضافة صفقات.")
        return

    st.subheader("📊 توزيع الأصول (مبسط)")
    status = _safe_status_series(df)
    open_df = df[status == "open"].copy() if len(status) else df.copy()

    invest_val = 0
    spec_val = 0
    sukuk_val = 0
    try:
        if "strategy" in open_df.columns and "market_value" in open_df.columns:
            invest_val = open_df[open_df["strategy"].astype(str).str.contains("استثمار", na=False)]["market_value"].sum()
            spec_val = open_df[open_df["strategy"].astype(str).str.contains("مضاربة", na=False)]["market_value"].sum()
    except Exception:
        pass
    if "asset_type" in open_df.columns and "market_value" in open_df.columns:
        sukuk_val = open_df[open_df["asset_type"].astype(str).str.lower() == "sukuk"]["market_value"].sum()

    alloc_df = pd.DataFrame({
        "Asset": ["استثمار", "مضاربة", "صكوك", "كاش"],
        "Value": [invest_val, spec_val, sukuk_val, float(fin.get("cash", 0))]
    })
    alloc_df = alloc_df[alloc_df["Value"] > 0]

    c_ch1, c_ch2 = st.columns(2)
    with c_ch1:
        if not alloc_df.empty:
            st.plotly_chart(px.pie(alloc_df, values="Value", names="Asset", hole=0.4), use_container_width=True)
        else:
            st.info("لا توجد أصول")
    with c_ch2:
        crv = generate_equity_curve(df)
        if isinstance(crv, pd.DataFrame) and not crv.empty and "date" in crv.columns:
            ycol = "cumulative_invested" if "cumulative_invested" in crv.columns else crv.columns[-1]
            st.plotly_chart(px.line(crv, x="date", y=ycol), use_container_width=True)
        else:
            st.info("لا توجد بيانات تاريخية")


# ========================================================
# 3) Portfolio View
# ========================================================
def view_portfolio(fin, key):
    ts = "مضاربة" if key == "spec" else "استثمار"
    st.header(f"💼 محفظة {ts}")

    df = fin.get("all_trades", pd.DataFrame())
    if df.empty:
        st.info("لا توجد صفقات.")
        return

    if "strategy" in df.columns:
        sub = df[df["strategy"].astype(str).str.contains(ts, na=False)].copy()
    else:
        sub = df.copy()

    status = _safe_status_series(sub)
    op = sub[status == "open"].copy()
    cl = sub[status.isin(["close", "closed"])].copy()

    t1, t2 = st.tabs(["الصفقات القائمة", "الأرشيف"])

    with t1:
        k1, k2, k3, k4 = st.columns(4)
        total_cost = float(op["total_cost"].sum()) if (not op.empty and "total_cost" in op.columns) else 0
        total_market = float(op["market_value"].sum()) if (not op.empty and "market_value" in op.columns) else 0
        total_gain = float(op["gain"].sum()) if (not op.empty and "gain" in op.columns) else 0
        total_pct = (total_gain / total_cost * 100) if total_cost else 0.0
        with k1: render_kpi("إجمالي التكلفة", safe_fmt(total_cost), "neutral")
        with k2: render_kpi("سعر السوق", safe_fmt(total_market), "blue")
        with k3: render_kpi("الربح/الخسارة", safe_fmt(total_gain), "success" if total_gain >= 0 else "danger")
        with k4: render_kpi("النسبة %", f"{total_pct:.2f}%", "success" if total_pct >= 0 else "danger", "٪")

        st.markdown("---")
        if op.empty:
            st.info("لا توجد صفقات قائمة حالياً")
        else:
            for col in ["company_name", "sector", "gain_pct", "weight"]:
                if col not in op.columns:
                    op[col] = ""

            symbols = _clean_symbols_list(op["symbol"].astype(str).tolist()) if "symbol" in op.columns else []
            try:
                live_data = fetch_batch_data(symbols) if symbols else {}
            except Exception:
                live_data = {}

            op["symbol"] = op["symbol"].astype(str).apply(_normalize_symbol)
            op["current_price"] = op["symbol"].apply(lambda x: live_data.get(x, {}).get("price", 0))
            op["prev_close"] = op["symbol"].apply(lambda x: live_data.get(x, {}).get("prev_close", 0))
            op["day_change"] = op.apply(
                lambda r: ((r.get("current_price", 0) - r.get("prev_close", 0)) / r.get("prev_close", 1) * 100)
                if (r.get("prev_close", 0) and r.get("prev_close", 0) > 0) else 0,
                axis=1
            )
            op["status_ar"] = "مفتوحة"

            render_custom_table(
                op,
                [
                    ("company_name", "اسم الشركة", "text"),
                    ("sector", "القطاع", "text"),
                    ("status_ar", "الحالة", "badge"),
                    ("symbol", "رمز الشركة", "text"),
                    ("date", "تاريخ الشراء", "date"),
                    ("quantity", "الكمية", "money"),
                    ("entry_price", "سعر الشراء", "money"),
                    ("total_cost", "التكلفة", "money"),
                    ("current_price", "السعر الحالي", "money"),
                    ("market_value", "سعر السوق", "money"),
                    ("gain", "الربح والخسارة", "colorful"),
                    ("gain_pct", "نسبة الربح والخسارة", "percent"),
                    ("day_change", "نسبة التغير اليومي", "percent"),
                ]
            )

    with t2:
        if cl.empty:
            st.info("الأرشيف فارغ")
        else:
            render_custom_table(
                cl,
                [
                    ("company_name", "الشركة", "text"),
                    ("symbol", "الرمز", "text"),
                    ("gain", "الربح", "colorful"),
                    ("gain_pct", "%", "percent"),
                    ("exit_date", "تاريخ البيع", "date"),
                ]
            )


# ========================================================
# 4) Sukuk Portfolio
# ========================================================
def view_sukuk_portfolio(fin):
    st.header("📜 محفظة الصكوك")
    df = fin.get("all_trades", pd.DataFrame())
    if df.empty or "asset_type" not in df.columns:
        st.info("لا توجد صكوك.")
        return

    sukuk = df[df["asset_type"].astype(str).str.lower() == "sukuk"].copy()
    status = _safe_status_series(sukuk)
    op = sukuk[status == "open"].copy()
    cl = sukuk[status.isin(["close", "closed"])].copy()

    t1, t2 = st.tabs(["الصكوك القائمة (Open)", "الأرشيف (Closed)"])

    with t1:
        if op.empty:
            st.info("لا توجد صكوك قائمة.")
        else:
            render_custom_table(
                op,
                [
                    ("company_name", "اسم الصك", "text"),
                    ("quantity", "العدد", "text"),
                    ("entry_price", "التكلفة (للوحدة)", "money"),
                    ("total_cost", "الاجمالي", "money"),
                    ("date", "تاريخ الشراء", "date"),
                ]
            )

    with t2:
        if cl.empty:
            st.info("أرشيف الصكوك فارغ")
        else:
            render_custom_table(
                cl,
                [
                    ("company_name", "اسم الصك", "text"),
                    ("total_cost", "التكلفة", "money"),
                    ("market_value", "قيمة البيع", "money"),
                    ("exit_date", "تاريخ البيع", "date"),
                ]
            )


# ========================================================
# 5) Cash Log
# ========================================================
def view_cash_log(fin):
    st.header("💰 السيولة والسجلات المالية")

    dep = fin.get("deposits", pd.DataFrame())
    wit = fin.get("withdrawals", pd.DataFrame())
    ret = fin.get("returns", pd.DataFrame())

    c1, c2, c3 = st.columns(3)
    with c1: render_kpi("إجمالي الإيداعات", safe_fmt(dep["amount"].sum() if (not dep.empty and "amount" in dep.columns) else 0), "success", "📥")
    with c2: render_kpi("إجمالي السحوبات", safe_fmt(wit["amount"].sum() if (not wit.empty and "amount" in wit.columns) else 0), "danger", "📤")
    with c3: render_kpi("إجمالي العوائد", safe_fmt(ret["amount"].sum() if (not ret.empty and "amount" in ret.columns) else 0), "blue", "🎁")

    st.markdown("---")
    t1, t2, t3 = st.tabs(["📥 سجل الإيداعات", "📤 سجل السحوبات", "🎁 سجل العوائد"])
    cols_base = [("date", "التاريخ", "date"), ("amount", "المبلغ", "money"), ("note", "ملاحظات", "text")]

    with t1:
        render_custom_table(dep.sort_values("date", ascending=False) if (not dep.empty and "date" in dep.columns) else dep, cols_base)

    with t2:
        render_custom_table(wit.sort_values("date", ascending=False) if (not wit.empty and "date" in wit.columns) else wit, cols_base)

    with t3:
        render_custom_table(ret.sort_values("date", ascending=False) if (not ret.empty and "date" in ret.columns) else ret,
                            [("date", "التاريخ", "date"), ("symbol", "السهم", "text"), ("amount", "المبلغ", "money")])


# ========================================================
# 6) Financial UI (كما عندك)
# ========================================================
def render_data_import_ui_content(symbol):
    st.info("يدعم النظام: ملفات PDF من تداول، ملفات Excel/CSV، أو النسخ واللصق المباشر.")
    parser = FinancialParser()

    uploaded_file = st.file_uploader("رفع ملف قوائم مالية (PDF, Excel, CSV)", type=["pdf", "xlsx", "xls", "csv"])
    pasted_text = st.text_area("أو الصق البيانات هنا مباشرة:")

    if st.button("🚀 معالجة واستخراج البيانات", key=f"fin_parse_{symbol}"):
        results, detected_symbol, err = [], None, None

        with st.spinner("جاري تحليل النصوص واستخراج الأرقام..."):
            if uploaded_file:
                results, detected_symbol, err = parser.process_file_or_text(uploaded_file=uploaded_file)
            elif pasted_text:
                results, detected_symbol, err = parser.process_file_or_text(text_input=pasted_text)
            else:
                st.warning("الرجاء اختيار ملف أو لصق نص.")
                return

        if err:
            st.error(err)
            return

        if results:
            st.success(f"تم استخراج {len(results)} سجلات بنجاح!")
            final_symbol = symbol

            if detected_symbol and detected_symbol != symbol:
                st.warning(f"⚠️ الملف لشركة {detected_symbol}، وأنت في صفحة {symbol}.")
                if st.checkbox(f"استخدام {detected_symbol}؟", value=True, key=f"use_detect_{symbol}"):
                    final_symbol = detected_symbol

            if final_symbol:
                preview_df = pd.DataFrame([{"Date": r["date"], **r["data"]} for r in results])
                st.dataframe(preview_df, use_container_width=True)

                if st.button("💾 تأكيد وحفظ في قاعدة البيانات", key=f"fin_save_{final_symbol}"):
                    count = 0
                    for r in results:
                        if save_financial_record(final_symbol, r["date"], r["data"], period_type="Annual", source="File/Paste"):
                            count += 1
                    st.success(f"تم حفظ {count} سجلات لشركة {final_symbol}.")
                    st.rerun()
        else:
            st.error("لم يتم العثور على بيانات مالية صالحة.")


def render_financial_dashboard_ui(symbol):
    tab_dashboard, tab_data_mgmt = st.tabs(["📊 لوحة التحليل المالي", "⚙️ إدارة البيانات"])

    with tab_dashboard:
        df_annual = get_financial_statements(symbol, "Annual")
        df_quarter = get_financial_statements(symbol, "Quarterly")

        ptype = st.radio(
            "نطاق التحليل:",
            ["Annual", "Quarterly"],
            horizontal=True,
            label_visibility="collapsed",
            key=f"fin_ptype_{_sym_key(symbol)}"
        )

        df = df_annual if ptype == "Annual" else df_quarter

        if df is None or df.empty:
            st.warning("⚠️ لا توجد بيانات مالية محفوظة لهذا السهم.")
            st.info("👈 انتقل لتبويب 'إدارة البيانات' لرفع ملف أو جلب المعلومات.")
        else:
            metrics = get_advanced_fundamental_ratios(symbol)
            c1, c2, c3 = st.columns(3)
            c1.metric("المتانة (F-Score)", f"{metrics.get('Piotroski_Score',0)}/9", metrics.get("Financial_Health","-"))
            fv = metrics.get("Fair_Value_Graham", 0)
            c2.metric("قيمة جراهام", f"{fv:,.2f}" if fv and fv > 0 else "N/A")
            c3.write(f"**ملاحظات:** {metrics.get('Opinions', '-')}")
            st.markdown("---")
            with st.expander("عرض الجدول التفصيلي"):
                st.dataframe(df, use_container_width=True)

    with tab_data_mgmt:
        t1, t2 = st.tabs(["⚡ تحديث آلي (Yahoo)", "📂 استيراد ملف/نص"])
        with t1:
            if st.button("بدء المزامنة الآلية", key=f"sync_yahoo_{_sym_key(symbol)}"):
                with st.spinner("جاري الاتصال..."):
                    ok, msg = sync_auto_yahoo(symbol)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        with t2:
            render_data_import_ui_content(symbol)


# ========================================================
# 7) Analysis (المستشار + مالي + فني + كلاسيكي + أطروحة)
# ========================================================
def view_analysis(fin):
    st.header("🔬 التحليل الشامل")

    trades = fin.get("all_trades", pd.DataFrame())

    # Stress test
    if not trades.empty and "status" in trades.columns:
        status = _safe_status_series(trades)
        open_pos = trades[status == "open"].copy()
        st.subheader("📊 اختبار التحمل")
        res = run_stress_test(float(fin.get("market_val_open", 0)), open_pos)
        if res.get("scenarios"):
            sdf = pd.DataFrame(res["scenarios"])
            if not sdf.empty:
                st.plotly_chart(px.bar(sdf, x="scenario", y="impact_pct"), use_container_width=True)
        if res.get("insight"):
            st.info(res.get("insight"))
        st.markdown("---")

    # symbols
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

    all_syms = _clean_symbols_list(syms)

    st.markdown("##### 🔎 البحث عن سهم")
    with st.form("analysis_search_form", clear_on_submit=False):
        c1, c2, c3 = st.columns([1.6, 2.2, 1.2])
        q = c1.text_input("اكتب الرمز", key="analysis_q", placeholder="مثال: 1120 أو 1120.SR")
        q_plain = (q or "").strip().upper()

        filtered = all_syms
        if q_plain:
            filtered = [s for s in all_syms if (q_plain in s.upper() or q_plain in s.upper().replace(".SR", ""))][:80]

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
        sym_try = _normalize_symbol(raw)

        if not sym_try or sym_try == ".SR":
            st.warning("الرجاء إدخال رمز صحيح مثل: 1120 أو 1120.SR")
        else:
            st.session_state["analysis_active_symbol"] = sym_try
            st.rerun()

    sym = st.session_state.get("analysis_active_symbol")
    if not sym:
        return

    sym = _normalize_symbol(sym)
    if not sym or sym == ".SR":
        st.warning("الرجاء إدخال رمز صحيح.")
        return

    # company info
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
    tabs = st.tabs(["🤖 المستشار", "💰 مالي", "📈 فني", "🏛️ كلاسيكي", "📝 أطروحة"])

    # --------------------------
    # 🤖 المستشار
    # --------------------------
    with tabs[0]:
        symk = _sym_key(sym)
        tf_map = {"يومي (1D)": "1d", "أسبوعي (1W)": "1wk", "شهري (1M)": "1mo"}

        c_tf1, c_tf2, c_tf3 = st.columns([1.2, 2.0, 1.0])
        ai_tf_label = c_tf1.selectbox("الفاصل الزمني", list(tf_map.keys()), index=0, key=f"ai_tf_{symk}")
        ai_tf = tf_map[ai_tf_label]
        c_tf2.caption("يغيّر منظور المستشار (قصير/متوسط/طويل).")

        if c_tf3.button("🔄 تحديث", key=f"ai_refresh_{symk}"):
            cache = st.session_state.get("_ai_rep_cache", {})
            cache_key = f"{sym}|{ai_tf}"
            if cache_key in cache:
                del cache[cache_key]
            st.session_state["_ai_rep_cache"] = cache
            st.rerun()

        cache = st.session_state.setdefault("_ai_rep_cache", {})
        cache_key = f"{sym}|{ai_tf}"

        if cache_key in cache:
            rep = cache[cache_key]
        else:
            with st.spinner("جاري توليد تقرير المستشار..."):
                rep = _generate_ai_report_flex(sym, timeframe=ai_tf)
            cache[cache_key] = rep

        _render_ai_report_ui(rep)

        st.markdown("---")
        st.subheader("🧠 استراتيجياتي الخاصة")
        st.caption("اكتب قواعدك بصيغة بسيطة مثل: (تقاطع الماكد صعوداً + اختراق خط الصفر) أو (RSI فوق 70)")

        rule_text = st.text_area("✍️ أدخل الاستراتيجية", key=f"user_rule_text_{symk}", height=110)
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("💾 حفظ الاستراتيجية", key=f"save_rule_{symk}", type="primary"):
                res = save_user_rule(rule_text, title="قاعدة من المستخدم", enabled=1)
                if res.get("ok"):
                    st.success("✅ تم حفظ الاستراتيجية")
                    # clear AI cache for this symbol
                    cache = st.session_state.get("_ai_rep_cache", {})
                    for k in list(cache.keys()):
                        if k.startswith(f"{sym}|"):
                            del cache[k]
                    st.session_state["_ai_rep_cache"] = cache
                    st.rerun()
                else:
                    st.error(f"لم يتم الحفظ: {res.get('reason','')}")

        with st.expander("📌 عرض آخر الاستراتيجيات المحفوظة"):
            rules = load_user_rules(enabled_only=True, max_rows=10) or []
            if rules:
                for r in rules:
                    st.write(f"- **{r.get('title','قاعدة')}**: {r.get('rule_text','')}")
            else:
                st.info("لا توجد قواعد محفوظة بعد.")

    # --------------------------
    # 💰 المالي
    # --------------------------
    with tabs[1]:
        render_financial_dashboard_ui(sym)

    # --------------------------
    # 📈 الفني
    # --------------------------
    with tabs[2]:
        symk = _sym_key(sym)
        period_opts = {"6 أشهر": "6mo", "سنة": "1y", "سنتين": "2y", "5 سنوات": "5y", "10 سنوات": "10y", "الحد الأقصى": "max"}
        interval_opts = {"يومي 1D": "1d", "أسبوعي 1W": "1wk", "شهري 1M": "1mo", "ساعة 1H": "1h", "30 دقيقة": "30m", "15 دقيقة": "15m"}

        c_p, c_i, c_mode = st.columns([1.2, 1.2, 1.6])
        p_label = c_p.selectbox("الفترة (Period)", list(period_opts.keys()), index=2, key=f"tech_p_{symk}")
        i_label = c_i.selectbox("الفاصل (Interval)", list(interval_opts.keys()), index=0, key=f"tech_i_{symk}")
        mode = c_mode.radio("وضع الشارت", ["احترافي", "قديم (Fallback)"], horizontal=True, key=f"tech_mode_{symk}")

        if mode == "احترافي":
            _render_tv_like_chart(sym, period_opts[p_label], interval_opts[i_label])
        else:
            _render_technical_chart_flex(sym, period=period_opts[p_label], interval=interval_opts[i_label])

    # --------------------------
    # 🏛️ الكلاسيكي
    # --------------------------
    with tabs[3]:
        render_classical_analysis(sym)

    # --------------------------
    # 📝 الأطروحة
    # --------------------------
    with tabs[4]:
        th = get_thesis(sym)
        txt = th["thesis_text"] if (isinstance(th, dict) and "thesis_text" in th) else (
            th.thesis_text if th is not None and hasattr(th, "thesis_text") else ""
        )
        with st.form(f"th_{_sym_key(sym)}"):
            nt = st.text_area("نص الأطروحة", value=txt)
            if st.form_submit_button("حفظ"):
                save_thesis(sym, nt, 0, "Hold")
                st.success("تم")


# ========================================================
# 8) Backtester
# ========================================================
def view_backtester_ui(fin):
    st.header("🧪 المختبر")

    # توضيح بصري إنه تم تحديث الواجهة
    st.caption(f"🧩 UI Build: views.py v{VIEWS_UI_VERSION}")

    if not run_backtest:
        st.warning("Backtester غير متوفر حالياً.")
        if bt_import_error:
            st.code(bt_import_error)
        st.info("✅ تأكد أن backtester.py يحتوي list_strategies ويرجع str أو dict/tuple بشكل صحيح.")
        return

    s = st.text_input("رمز السهم", "1120", key="lab_symbol")
    cap = st.number_input("رأس المال", min_value=1000.0, value=100000.0, step=1000.0, key="lab_cap")

    strat = _select_strategy_ui(key_prefix="lab")
    period = st.selectbox("الفترة التاريخية", ["6mo", "1y", "2y", "5y", "10y", "max"], index=3, key="lab_period")

    # تحسين العرض: خيارات نتائج
    st.markdown("#### ⚙️ إعدادات العرض")
    show_trades = st.checkbox("عرض سجل الصفقات الناتج", value=True, key="lab_show_trades")
    show_curve = st.checkbox("عرض منحنى المحفظة", value=True, key="lab_show_curve")

    if st.button("🚀 بدء الاختبار", key="bt_run", type="primary"):
        try:
            s_norm = _normalize_symbol(s)
            st.info(f"🔎 الرمز: {s_norm} | الفترة: {period} | الاستراتيجية: {strat}")

            data = get_chart_history(s_norm, period)
            if data is None or (isinstance(data, pd.DataFrame) and data.empty):
                st.error("❌ لم يتم جلب بيانات (DataFrame فارغ)")
                return
            if not isinstance(data, pd.DataFrame):
                data = pd.DataFrame(data)

            if "Close" not in data.columns and "close" not in data.columns:
                st.error("❌ لا يوجد عمود Close في البيانات")
                st.write("الأعمدة:", list(data.columns))
                return

            try:
                info = get_company_details(s_norm)
                if isinstance(info, (list, tuple)) and len(info) >= 2:
                    sec = info[1]
                elif isinstance(info, dict):
                    sec = info.get("sector") or info.get("Sector") or ""
                else:
                    sec = ""
            except Exception:
                sec = ""

            res = run_backtest(data, str(strat), cap, symbol=s_norm, sector=sec)
            if not res:
                st.warning("⚠️ لم يرجع الاختبار نتيجة.")
                return

            st.success(f"✅ اكتمل الاختبار ({res.get('strategy_name_ar', strat)})")

            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("العائد", f"{res.get('return_pct', 0):.2f}%")
            with m2:
                st.metric("القيمة النهائية", safe_fmt(res.get("final_value", 0)))
            with m3:
                st.metric("عدد الصفقات", int(res.get("trades_count", 0) or 0))

            if show_curve and "df" in res and isinstance(res["df"], pd.DataFrame):
                dfres = res["df"]
                if "Portfolio_Value" in dfres.columns:
                    st.markdown("### 📈 منحنى المحفظة")
                    st.line_chart(dfres["Portfolio_Value"])

            if show_trades and isinstance(res.get("trades"), pd.DataFrame):
                st.markdown("### 🧾 سجل الصفقات")
                st.dataframe(res["trades"], use_container_width=True)

            with st.expander("🧩 نتيجة خام (JSON)"):
                st.json({k: v for k, v in res.items() if k not in ["df", "trades"]})

        except Exception as e:
            st.error(f"Backtest Error: {e}")
            st.code(traceback.format_exc())


# ========================================================
# Pulse / Add / Tools / Settings
# ========================================================
def render_pulse_dashboard():
    st.header("نبض السوق")
    try:
        trades = fetch_table("trades")
    except Exception:
        trades = pd.DataFrame()

    syms = list(trades["symbol"].astype(str).unique()) if (not trades.empty and "symbol" in trades.columns) else []
    syms = _clean_symbols_list(syms)
    if syms:
        d = fetch_batch_data(syms)
        cols = st.columns(4)
        for i, (s, v) in enumerate(d.items()):
            prev = v.get("prev_close") or 0
            chg = ((v.get("price", 0) - prev) / prev) * 100 if prev else 0
            with cols[i % 4]:
                render_ticker_card(s, "سهم", v.get("price", 0), chg)
    else:
        st.info("لا توجد رموز لعرض نبض السوق.")


def view_add_trade():
    st.header("➕ إضافة صفقة")
    with st.form("add_t"):
        c1, c2 = st.columns(2)
        s_raw = c1.text_input("رمز السهم (مثال: 1120)", key="add_sym")
        typ = c2.selectbox("نوع الصفقة", ["استثمار", "مضاربة", "صكوك"], key="add_typ")
        c3, c4, c5 = st.columns(3)
        q = c3.number_input("الكمية", min_value=1.0, key="add_q")
        p = c4.number_input("السعر", min_value=0.0, key="add_p")
        d = c5.date_input("التاريخ", date.today(), key="add_d")

        if st.form_submit_button("حفظ"):
            valid, msg = validate_trade_inputs(q, p)
            if valid:
                s = _normalize_symbol(s_raw)

                try:
                    info = get_company_details(s)
                    if isinstance(info, (list, tuple)) and len(info) >= 2:
                        nm, sec = info[0], info[1]
                    elif isinstance(info, dict):
                        nm = info.get("name") or info.get("Name") or s
                        sec = info.get("sector") or info.get("Sector") or ""
                    else:
                        nm, sec = s, ""
                except Exception:
                    nm, sec = s, ""

                at = "Sukuk" if typ == "صكوك" else "Stock"
                execute_query(
                    "INSERT INTO trades (symbol, company_name, sector, asset_type, quantity, entry_price, strategy, status, date) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'Open',%s)",
                    (s, nm, sec, at, q, p, typ, str(d))
                )
                st.success("تم")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(msg)


def view_tools():
    st.header("🛠️ أدوات")
    st.info("حاسبة الزكاة (قريباً)")


def view_settings():
    st.header("الإعدادات")

    st.caption(f"🧩 UI Build: views.py v{VIEWS_UI_VERSION} | AI Engine v{AI_ENGINE_VERSION}")

    if st.button("🔎 تشخيص قاعدة البيانات", key="db_diag"):
        rep = db_healthcheck()
        if not rep.get("connected"):
            st.error("غير متصل بقاعدة البيانات")
        else:
            st.success("✅ اتصال ناجح")
            st.json(rep.get("db", {}))
            st.write("### Counts")
            st.json(rep.get("counts", {}))
            if rep.get("dup_tables"):
                st.error(f"⚠️ يوجد ازدواج جداول: {rep['dup_tables']}")
            else:
                st.success("✅ لا يوجد ازدواج جداول (Case Safe)")

    st.markdown("---")
    if st.button("نسخة احتياطية", key="backup_btn"):
        d, n = create_smart_backup()
        if d:
            st.download_button("تحميل", d, n)


# ========================================================
# 9) Router
# ========================================================
def router():
    _ensure_ui_once()

    if "page" not in st.session_state:
        st.session_state.page = "home"

    render_navbar()
    pg = st.session_state.page

    fin = calculate_portfolio_metrics()

    if pg == "home":
        view_dashboard(fin)
    elif pg == "spec":
        view_portfolio(fin, "spec")
    elif pg == "invest":
        view_portfolio(fin, "invest")
    elif pg == "sukuk":
        view_sukuk_portfolio(fin)
    elif pg == "analysis":
        view_analysis(fin)
    elif pg == "cash":
        view_cash_log(fin)
    elif pg == "backtest":
        view_backtester_ui(fin)
    elif pg == "pulse":
        render_pulse_dashboard()
    elif pg == "add":
        view_add_trade()
    elif pg == "tools":
        view_tools()
    elif pg == "settings":
        view_settings()
    elif pg == "update":
        with st.spinner("جاري التحديث..."):
            update_prices()
        st.cache_data.clear()
        st.rerun()
    else:
        st.session_state.page = "home"
        st.rerun()