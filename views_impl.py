# views_impl.py
# ✅ Real implementation layer (moved out of views.py to avoid circular imports)
# (نفس views.py الكبير سابقًا لكن بدون Router وبدون render_navbar وبدون view_dashboard)

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date
import traceback
import inspect

from config import DEFAULT_COLORS
from components import (
    render_kpi,
    render_custom_table,
    render_ticker_card,
    safe_fmt,
    inject_component_styles,
    inject_streamlit_ar_i18n,
    render_osoli_report,
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

from ui.common import sym_key as _sym_key, normalize_symbol as _normalize_symbol
from ui.common import safe_status_series as _safe_status_series, clean_symbols_list as _clean_symbols_list


# ========================================================
# 🛡️ Fail-Safe Imports
# ========================================================

# 1) Charts (النسخة القديمة - نخليها fallback)
try:
    from charts import render_technical_chart
except Exception:
    def render_technical_chart(symbol, *args, **kwargs):
        st.warning("⚠️ ملف charts.py مفقود أو به خطأ.")


# 2) Backtester (مع إظهار سبب الفشل داخل الواجهة)
bt_import_error = None
try:
    from backtester import run_backtest, list_strategies
except Exception as e:
    run_backtest = None
    list_strategies = lambda: []
    bt_import_error = repr(e)


# 3) Financial Analysis
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


# 4) Classical Analysis
try:
    from classical_analysis import render_classical_analysis
except Exception:
    def render_classical_analysis(s):
        st.warning("⚠️ ملف classical_analysis.py مفقود أو به خطأ.")


# ========================================================
# 5) AI Engine (تشخيص + منع كاش الخطأ + fallback تقرير)
# ========================================================

ai_import_error = None
ai_engine_path = None
ai_engine_module = None
AI_ENGINE_OK = False
AI_ENGINE_VERSION = "unknown"

try:
    import ai_engine as ai_engine_module
    AI_ENGINE_VERSION = getattr(ai_engine_module, "AI_ENGINE_VERSION", "unknown")
    ai_engine_path = getattr(ai_engine_module, "__file__", None)

    required = [
        "generate_ai_report",
        "calculate_portfolio_risk_score",
        "run_stress_test",
        "generate_rebalancing_suggestions",
        "save_user_rule",
        "load_user_rules",
    ]
    missing = [fn for fn in required if not hasattr(ai_engine_module, fn)]
    if missing:
        raise ImportError(f"ai_engine missing functions: {missing}")

    generate_ai_report = ai_engine_module.generate_ai_report
    calculate_portfolio_risk_score = ai_engine_module.calculate_portfolio_risk_score
    run_stress_test = ai_engine_module.run_stress_test
    generate_rebalancing_suggestions = ai_engine_module.generate_rebalancing_suggestions
    save_user_rule = ai_engine_module.save_user_rule
    load_user_rules = ai_engine_module.load_user_rules

    AI_ENGINE_OK = True

except Exception:
    ai_import_error = traceback.format_exc()
    AI_ENGINE_OK = False

    def generate_ai_report(symbol, timeframe="1d"):
        return {"__error__": "AI Engine import failed", "__trace__": ai_import_error}

    def calculate_portfolio_risk_score(df, c): return 50
    def run_stress_test(v, df): return {"scenarios": [], "insight": ""}
    def generate_rebalancing_suggestions(df, c): return []

    def save_user_rule(rule_text: str, title: str = None, enabled: int = 1):
        return {"ok": False, "reason": "AI Engine missing", "trace": ai_import_error}

    def load_user_rules(enabled_only=True, max_rows=50):
        return []


def _ai_self_test():
    info = {
        "ok": bool(AI_ENGINE_OK),
        "version": AI_ENGINE_VERSION,
        "path": ai_engine_path,
        "import_error": ai_import_error if not AI_ENGINE_OK else "",
        "functions": {},
    }
    try:
        if AI_ENGINE_OK and ai_engine_module:
            for fn in ["generate_ai_report", "calculate_portfolio_risk_score", "run_stress_test", "save_user_rule", "load_user_rules"]:
                obj = getattr(ai_engine_module, fn, None)
                if obj:
                    try:
                        sig = str(inspect.signature(obj))
                    except Exception:
                        sig = "?"
                    info["functions"][fn] = {"exists": True, "signature": sig}
                else:
                    info["functions"][fn] = {"exists": False, "signature": ""}
    except Exception as e:
        info["ok"] = False
        info["import_error"] = (info.get("import_error") or "") + f"\nSELF_TEST_ERR: {e}"
    return info


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


def _select_strategy_ui(key_prefix: str = "lab"):
    """
    يدعم list_strategies سواء رجعت:
    - ["Trend","Sniper"]
    - [("Trend","ترند"), ("Sniper","قناص")]
    - [{"key":"Trend","name":"ترند"}]
    ويرجع دائمًا قيمة strategy كنص (string) لتفادي خطأ tuple.title()
    """
    raw = list_strategies() or ["Trend", "Sniper"]

    # tuples/lists: (key, name)
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

    # dicts
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
# ✅ AI: Normalize + Friendly Renderer
# ========================================================

def _to_float(x, default=None):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def _fmt_price(x):
    v = _to_float(x, None)
    return "—" if v is None else f"{v:,.2f}"


def _safe_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return [i for i in x if i is not None and str(i).strip() != ""]
    return [x]


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


def _fallback_ai_report(symbol: str, tf: str, reason: str, trace: str = ""):
    return {
        "recommendation": "تعذر توليد التقرير الآن",
        "strategy": "Fallback",
        "color": "#b42318",
        "score": 0,
        "confidence": 0,
        "confidence_label": "منخفضة",
        "summary_text": f"المستشار غير متاح: {reason}",
        "entry": {},
        "risk": {},
        "levels": {},
        "targets": [],
        "top_evidence": [],
        "top_risks": [],
        "risk_gates": {"pass": False, "reasons": ["AI Engine غير متاح"]},
        "scenarios": [],
        "__error__": reason,
        "__trace__": trace,
        "symbol": symbol,
        "timeframe": tf,
    }


def _generate_ai_report_flex(symbol: str, timeframe: str):
    tf = _ai_timeframe_normalize(timeframe)

    if not AI_ENGINE_OK:
        return _fallback_ai_report(symbol, tf, "Import failed", ai_import_error or "")

    try:
        try:
            return generate_ai_report(symbol, timeframe=tf)
        except TypeError:
            try:
                return generate_ai_report(symbol, timeframe=timeframe)
            except TypeError:
                try:
                    return generate_ai_report(symbol, tf)
                except TypeError:
                    return generate_ai_report(symbol)

    except Exception as e:
        return _fallback_ai_report(symbol, tf, str(e), traceback.format_exc())


def _badge(text, tone="neutral"):
    bg = {
        "success": "#e8fff2",
        "warning": "#fff6e5",
        "danger":  "#ffecec",
        "neutral": "#f2f4f7",
    }.get(tone, "#f2f4f7")

    fg = {
        "success": "#0f7a3c",
        "warning": "#8a5a00",
        "danger":  "#a40e26",
        "neutral": "#344054",
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
        unsafe_allow_html=True
    )


def _render_bullets(title, items, icon="•", limit=8, empty_text="لا يوجد"):
    st.markdown(f"**{title}**")
    items = _safe_list(items)
    if not items:
        st.caption(empty_text)
        return
    for x in items[:limit]:
        st.write(f"{icon} {x}")


def _extract_ai(rep: dict) -> dict:
    if not isinstance(rep, dict):
        return {"ok": False, "raw": rep, "error": "AI report is not dict"}

    ex = rep.get("explainability") or {}
    if not isinstance(ex, dict):
        ex = {}

    positives = _safe_list(ex.get("positives", rep.get("positives", [])))
    negatives = _safe_list(ex.get("negatives", rep.get("negatives", [])))
    notes = _safe_list(ex.get("notes", rep.get("notes", [])))

    top_evidence = _safe_list(rep.get("top_evidence", positives))
    top_risks = _safe_list(rep.get("top_risks", negatives))

    risk_gates = rep.get("risk_gates", {})
    if not isinstance(risk_gates, dict):
        risk_gates = {}

    scenarios = rep.get("scenarios", [])
    if not isinstance(scenarios, list):
        scenarios = []

    score = rep.get("score", rep.get("osoli_score", None))
    score = int(_to_float(score, 0) or 0)
    score = max(0, min(100, score))

    conf = rep.get("confidence", rep.get("conf", None))
    conf = int(_to_float(conf, 0) or 0)
    conf = max(0, min(100, conf))

    conf_label = rep.get("confidence_label") or rep.get("confidenceLabel")
    if not conf_label:
        conf_label = "مرتفعة" if conf >= 70 else "متوسطة" if conf >= 40 else "منخفضة"

    summary_text = rep.get("summary_text") or rep.get("summary") or rep.get("reasoning") or ""
    entry = rep.get("entry", {}) if isinstance(rep.get("entry", {}), dict) else {}
    risk = rep.get("risk", {}) if isinstance(rep.get("risk", {}), dict) else {}
    levels = rep.get("levels", {}) if isinstance(rep.get("levels", {}), dict) else {}
    targets = rep.get("targets", [])
    if not isinstance(targets, list):
        targets = []

    rec = rep.get("recommendation") or rep.get("action") or "—"
    strat = rep.get("strategy") or rep.get("strategy_name") or rep.get("model") or "—"
    col = rep.get("color") or rep.get("tone_color") or "#667085"

    return {
        "ok": True,
        "recommendation": rec,
        "strategy": strat,
        "color": col,
        "score": score,
        "confidence": conf,
        "confidence_label": conf_label,
        "summary_text": summary_text,
        "entry": entry,
        "risk": risk,
        "levels": levels,
        "targets": targets,
        "notes": notes,
        "top_evidence": top_evidence,
        "top_risks": top_risks,
        "risk_gates": risk_gates,
        "scenarios": scenarios,
        "raw": rep,
    }


def _render_risk_gates(risk_gates: dict):
    if not isinstance(risk_gates, dict) or not risk_gates:
        st.info("لا توجد بوابات مخاطر حالياً.")
        return

    passed = bool(risk_gates.get("pass", False))
    reasons = _safe_list(risk_gates.get("reasons", []))

    c1, c2 = st.columns([1, 3])
    with c1:
        _badge("✅ اجتاز" if passed else "❌ لم يجتز", "success" if passed else "danger")
    with c2:
        if reasons:
            st.markdown("**الأسباب:**")
            for r in reasons[:12]:
                st.write(f"- {r}")
        else:
            st.caption("لا توجد أسباب مسجلة.")


def _render_targets(targets):
    targets = _safe_list(targets)
    if not targets:
        st.info("لا توجد أهداف جاهزة حالياً.")
        return
    rows = []
    for t in targets[:8]:
        if isinstance(t, dict):
            rows.append({
                "الهدف": t.get("name") or t.get("label") or "Target",
                "السعر": _fmt_price(t.get("price") or t.get("value")),
                "ملاحظة": t.get("note") or ""
            })
        else:
            rows.append({"الهدف": "Target", "السعر": _fmt_price(t), "ملاحظة": ""})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_entry_risk_levels(entry: dict, risk: dict, levels: dict, score: int):
    st.markdown("### 🧭 خطة الدخول والمخاطر")
    c1, c2, c3, c4 = st.columns(4)

    entry_zone = entry.get("entry_zone") or entry.get("zone") or entry.get("price")
    stop = risk.get("stop") or risk.get("sl") or risk.get("stop_loss")
    inv = risk.get("invalidation") or risk.get("invalid") or risk.get("break_level")
    rr = risk.get("rr") or risk.get("risk_reward")

    sup = levels.get("support")
    res = levels.get("resistance")

    with c1:
        st.metric("Score", f"{score}/100")
    with c2:
        st.metric("منطقة الدخول", _fmt_price(entry_zone))
    with c3:
        st.metric("وقف الخسارة", _fmt_price(stop))
    with c4:
        st.metric("إبطال الفكرة", _fmt_price(inv))

    c5, c6, c7 = st.columns(3)
    with c5:
        st.metric("R:R", f"{_to_float(rr, 0):.2f}" if rr is not None else "—")
    with c6:
        st.metric("Support", _fmt_price(sup))
    with c7:
        st.metric("Resistance", _fmt_price(res))


def _render_scenarios(scenarios):
    scenarios = _safe_list(scenarios)
    if not scenarios:
        st.info("لا توجد سيناريوهات جاهزة حالياً.")
        return

    for i, sc in enumerate(scenarios[:8], start=1):
        if not isinstance(sc, dict):
            continue

        name = sc.get("name", f"سيناريو {i}")
        trigger = sc.get("trigger") or sc.get("condition") or "—"
        entry = sc.get("entry")
        stop = sc.get("stop") or sc.get("sl")
        t1 = sc.get("target1") or sc.get("target") or sc.get("tp1")
        t2 = sc.get("target2") or sc.get("tp2")
        t_list = sc.get("targets") if isinstance(sc.get("targets"), list) else None
        note = sc.get("note", "")

        st.markdown(
            """
            <div style="
                border:1px solid rgba(0,0,0,0.08);
                border-radius:14px;
                padding:14px;
                margin:10px 0;
                background:#fff;
            ">
            """,
            unsafe_allow_html=True
        )

        top = st.columns([2, 1])
        with top[0]:
            st.markdown(f"### {name}")
            st.caption(f"🎯 الشرط: {trigger}")
        with top[1]:
            e = _to_float(entry, None)
            s = _to_float(stop, None)
            tg = _to_float(t1, None)
            if e is not None and s is not None and tg is not None and (e - s) != 0:
                rr = (tg - e) / (e - s)
                _badge(f"R:R {rr:.2f}", "success" if rr >= 1.5 else "warning" if rr >= 1.0 else "danger")
            else:
                _badge("سيناريو", "neutral")

        cA, cB, cC, cD = st.columns(4)
        cA.metric("الدخول", _fmt_price(entry))
        cB.metric("وقف الخسارة", _fmt_price(stop))
        cC.metric("الهدف 1", _fmt_price(t1))
        cD.metric("الهدف 2", _fmt_price(t2) if t2 is not None else "—")

        if t_list:
            st.caption("🎯 أهداف إضافية:")
            st.write([_fmt_price(x.get("price") if isinstance(x, dict) else x) for x in t_list[:8]])

        if note:
            st.caption(f"📝 ملاحظة: {note}")

        st.markdown("</div>", unsafe_allow_html=True)


def _render_ai_report_readable(rep: dict, show_debug=False, compact=False):
    if isinstance(rep, dict) and (rep.get("__error__") or rep.get("__trace__")):
        st.error("⚠️ المستشار لم يعمل.")
        st.write(rep.get("__error__", "Unknown AI error"))
        with st.expander("📌 تفاصيل الخطأ (Trace)"):
            st.code(rep.get("__trace__", ""), language="text")
        with st.expander("🧪 تشخيص AI Engine"):
            st.json(_ai_self_test())
        return

    data = _extract_ai(rep)
    if not data.get("ok"):
        st.warning("⚠️ تقرير المستشار غير صالح.")
        st.write(data.get("raw"))
        return

    st.caption(f"🧩 AI Engine v{AI_ENGINE_VERSION}")

    col = data["color"]
    st.markdown(
        f"""
        <div style="
            border:2px solid {col};
            border-radius:16px;
            padding:16px;
            text-align:center;
            background: rgba(102,112,133,0.06);
        ">
            <div style="font-size:1.4rem; font-weight:900;">{data['recommendation']}</div>
            <div style="opacity:0.9; margin-top:6px;">{data['strategy']}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("### 🧠 التقييم والثقة")
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        _badge(f"Score {data['score']}/100", "success" if data["score"] >= 70 else "warning" if data["score"] >= 40 else "danger")
    with c2:
        conf = data["confidence"]
        label = data["confidence_label"]
        _badge(f"{label} ({conf}%)", "success" if conf >= 70 else "warning" if conf >= 40 else "danger")
    with c3:
        st.progress(data["confidence"])

    if data.get("summary_text"):
        st.markdown("### 🧾 سبب التوصية")
        st.code(str(data["summary_text"]).strip(), language="text")

    if any([data.get("entry"), data.get("risk"), data.get("levels"), data.get("targets")]):
        _render_entry_risk_levels(data.get("entry") or {}, data.get("risk") or {}, data.get("levels") or {}, data.get("score") or 0)
        st.markdown("### 🎯 الأهداف")
        _render_targets(data.get("targets") or [])

    st.markdown("---")
    a, b = st.columns(2)
    with a:
        _render_bullets("✅ أقوى الأدلة", data["top_evidence"], icon="✅", limit=(3 if compact else 8))
    with b:
        _render_bullets("⚠️ أكبر المخاطر", data["top_risks"], icon="⚠️", limit=(3 if compact else 8))

    st.markdown("---")
    st.markdown("### 🛡️ بوابات المخاطر")
    _render_risk_gates(data["risk_gates"])

    st.markdown("---")
    st.markdown("### 🧭 السيناريوهات المقترحة")
    _render_scenarios(data["scenarios"])

    notes = data.get("notes", [])
    if notes:
        with st.expander("🧾 ملاحظات إضافية"):
            for x in notes[:25]:
                st.write(f"- {x}")

    if show_debug:
        with st.expander("🧩 عرض التقرير الخام (JSON)"):
            st.json(data["raw"])


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
        xaxis2=dict(
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
        ),
        yaxis=dict(
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            fixedrange=False
        ),
        yaxis2=dict(
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            fixedrange=False
        ),
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
                df2 = df.copy()
                df2 = df2.reset_index().rename(columns={"index": "date"})
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
                    "drawline",
                    "drawopenpath",
                    "drawrect",
                    "drawcircle",
                    "eraseshape",
                ],
            },
        )
        st.caption("💡 تلميح: اسحب للتحريك (Pan)، و Scroll للتكبير/التصغير، و Range Slider للتنقل.")
    except Exception as e:
        st.error(f"❌ فشل بناء الشارت الاحترافي: {e}")
        st.info("سأعرض الشارت القديم كخطة بديلة.")
        _render_technical_chart_flex(symbol, period=period, interval=interval)


# ========================================================
# ✅ Table wrapper
# ========================================================

def _render_table_like_trades(df: pd.DataFrame, cols_spec=None, max_rows: int = 400):
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        st.info("📭 لا توجد بيانات لعرضها")
        return

    d = df.copy()
    if max_rows and len(d) > max_rows:
        d = d.head(max_rows)

    label_map = {
        "date": "التاريخ",
        "ts": "التاريخ",
        "time": "التاريخ",
        "year": "السنة",
        "period": "الفترة",
        "symbol": "الرمز",
        "revenue": "الإيرادات",
        "net_income": "صافي الربح",
        "operating_cash_flow": "التدفق النقدي التشغيلي",
        "total_assets": "إجمالي الأصول",
        "total_liabilities": "إجمالي المطلوبات",
        "current_assets": "الأصول المتداولة",
        "current_liabilities": "المطلوبات المتداولة",
        "total_equity": "حقوق الملكية",
        "long_term_debt": "ديون طويلة",
        "open": "الافتتاح",
        "high": "الأعلى",
        "low": "الأدنى",
        "close": "الإغلاق",
        "volume": "الحجم",
        "portfolio_value": "قيمة المحفظة",
        "return_pct": "العائد %",
        "final_value": "القيمة النهائية",
    }

    def _guess_type(col: str) -> str:
        c = str(col).lower()
        if c in ("date", "ts") or "date" in c or "time" in c:
            return "date"
        if any(k in c for k in ["pct", "percent", "margin", "ratio", "yield", "growth"]):
            return "percent"
        if any(k in c for k in ["price", "value", "amount", "revenue", "income", "cash", "assets", "liab", "equity", "debt", "cost", "market"]):
            return "money"
        if any(k in c for k in ["qty", "quantity", "volume"]):
            return "number"
        return "text"

    if cols_spec is None:
        cols_spec = []
        for col in list(d.columns)[:30]:
            key = str(col)
            lbl = label_map.get(key.lower(), key)
            cols_spec.append((key, lbl, _guess_type(key)))

    render_custom_table(d, cols_spec)


# ========================================================
# 4) Sukuk Portfolio
# ========================================================

def view_sukuk_portfolio(fin):
    st.header("📜 محفظة الصكوك")
    df = fin.get("all_trades", pd.DataFrame())

    if df.empty or "asset_type" not in df.columns:
        sukuk = pd.DataFrame()
    else:
        sukuk = df[df["asset_type"].astype(str).str.lower() == "sukuk"].copy()

    status = _safe_status_series(sukuk) if not sukuk.empty else pd.Series([], dtype=str)
    if len(status):
        op = sukuk[status == "open"].copy()
        cl = sukuk[status.isin(["close", "closed"])].copy()
    else:
        op = sukuk.copy()
        cl = pd.DataFrame()

    t1, t2 = st.tabs(["الصكوك القائمة (Open)", "الأرشيف (Closed)"])

    with t1:
        total_cost = float(op["total_cost"].sum()) if (not op.empty and "total_cost" in op.columns) else 0
        total_market = float(op["market_value"].sum()) if (not op.empty and "market_value" in op.columns) else 0
        total_gain = float(op["gain"].sum()) if (not op.empty and "gain" in op.columns) else 0
        total_pct = (total_gain / total_cost * 100) if total_cost else 0.0

        k1, k2, k3, k4 = st.columns(4)
        with k1: render_kpi("إجمالي الاستثمار", safe_fmt(total_cost), "neutral", "🕌")
        with k2: render_kpi("القيمة الحالية", safe_fmt(total_market), "blue", "📊")
        with k3: render_kpi("الربح/الخسارة", safe_fmt(total_gain), "success" if total_gain >= 0 else "danger", "📈")
        with k4: render_kpi("النسبة %", f"{total_pct:.2f}%", "success" if total_pct >= 0 else "danger", "٪")

        st.markdown("---")

        if not op.empty:
            if "company_name" not in op.columns:
                op["company_name"] = op.get("symbol", "")
            op["company_name"] = op["company_name"].fillna(op.get("symbol", ""))

            if "date" in op.columns:
                op["months_held"] = ((pd.to_datetime(date.today()) - pd.to_datetime(op["date"])).dt.days / 30).astype(int)
            else:
                op["months_held"] = 0

            if "entry_price" in op.columns:
                op["current_price"] = op["entry_price"]
            else:
                op["current_price"] = 0

            sb = st.selectbox("فرز الصكوك حسب:", ["التاريخ (الأحدث)", "القيمة (الأعلى)", "الاسم"], key="sort_sk")
            if "القيمة" in sb and "total_cost" in op.columns:
                op = op.sort_values("total_cost", ascending=False)
            elif "الاسم" in sb and "company_name" in op.columns:
                op = op.sort_values("company_name")
            else:
                if "date" in op.columns:
                    op = op.sort_values("date", ascending=False)

            render_custom_table(
                op,
                [
                    ("company_name", "اسم الصك", "text"),
                    ("quantity", "العدد", "text"),
                    ("entry_price", "التكلفة (للوحدة)", "money"),
                    ("current_price", "السعر الحالي", "money"),
                    ("total_cost", "الاجمالي", "money"),
                    ("months_held", "المده (شهر)", "text"),
                ]
            )

            c1, c2 = st.columns(2)

            with c1:
                with st.expander("💰 بيع / تصفية صك"):
                    if "id" in op.columns and len(op["id"].tolist()) > 0:
                        sid = st.selectbox(
                            "اختر الصك للبيع:",
                            op["id"].tolist(),
                            format_func=lambda x: f"{op[op['id']==x]['company_name'].iloc[0]}",
                            key="sell_sukuk_sel"
                        )
                        if sid:
                            curr_sell = op[op["id"] == sid].iloc[0]
                            with st.form(f"sk_sell_{sid}"):
                                st.write(f"تصفية: **{curr_sell.get('company_name','-')}**")
                                val = st.number_input("المبلغ المستلم كاملاً", min_value=0.0, step=100.0, key=f"sk_val_{sid}")
                                dt = st.date_input("تاريخ البيع", date.today(), key=f"sk_dt_{sid}")
                                if st.form_submit_button("تأكيد البيع"):
                                    qty = float(curr_sell.get("quantity", 0) or 0)
                                    if qty > 0:
                                        ep = val / qty
                                        execute_query(
                                            "UPDATE trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s",
                                            (ep, str(dt), sid)
                                        )
                                        st.success("تم الحفظ")
                                        st.cache_data.clear()
                                        st.rerun()
                                    else:
                                        st.error("خطأ: الكمية صفر")
                    else:
                        st.info("لا توجد صكوك لاختيارها")

            with c2:
                with st.expander("✏️ تعديل بيانات صك"):
                    if "id" in op.columns and len(op["id"].tolist()) > 0:
                        eid = st.selectbox("اختر الصك للتعديل:", op["id"].tolist(), key="sk_e")
                        if eid:
                            rw = op[op["id"] == eid].iloc[0]
                            with st.form(f"sk_edit_{eid}"):
                                nm = st.text_input("اسم الصك", value=str(rw.get("company_name", "")), key=f"sk_nm_{eid}")
                                qt = st.number_input("عدد الصكوك", value=float(rw.get("quantity", 1)), min_value=1.0, key=f"sk_qt_{eid}")
                                pr = st.number_input("قيمة الصك", value=float(rw.get("entry_price", 0)), min_value=0.0, key=f"sk_pr_{eid}")
                                try:
                                    nd_val = pd.to_datetime(rw.get("date", date.today())).date()
                                except Exception:
                                    nd_val = date.today()
                                nd = st.date_input("تاريخ الشراء", nd_val, key=f"sk_nd_{eid}")
                                if st.form_submit_button("حفظ التصحيح"):
                                    valid, msg = validate_trade_inputs(qt, pr)
                                    if valid:
                                        execute_query(
                                            "UPDATE trades SET symbol=%s, company_name=%s, quantity=%s, entry_price=%s, date=%s WHERE id=%s",
                                            (nm, nm, qt, pr, str(nd), eid)
                                        )
                                        st.success("تم التعديل")
                                        st.cache_data.clear()
                                        st.rerun()
                                    else:
                                        st.error(msg)
                    else:
                        st.info("لا توجد صكوك لاختيارها")
        else:
            st.info("لا توجد صكوك قائمة حالياً")

        st.markdown("---")
        if st.button("➕ إضافة صك", key="add_sukuk_btn", type="primary"):
            st.session_state.page = "add"
            st.rerun()

    with t2:
        if not cl.empty:
            if "company_name" not in cl.columns:
                cl["company_name"] = cl.get("symbol", "")
            cl["company_name"] = cl["company_name"].fillna(cl.get("symbol", ""))

            if "market_value" in cl.columns and "total_cost" in cl.columns:
                cl["realized_return"] = cl["market_value"] - cl["total_cost"]
            else:
                cl["realized_return"] = 0

            sort_by_cl = st.selectbox("فرز الأرشيف حسب:", ["تاريخ البيع (الأحدث)", "الربح (الأعلى)"], key="sort_sukuk_cl")
            if "الربح" in sort_by_cl and "realized_return" in cl.columns:
                cl = cl.sort_values("realized_return", ascending=False)
            else:
                if "exit_date" in cl.columns:
                    cl = cl.sort_values("exit_date", ascending=False)

            render_custom_table(
                cl,
                [
                    ("company_name", "اسم الصك", "text"),
                    ("total_cost", "التكلفة", "money"),
                    ("market_value", "قيمة البيع", "money"),
                    ("realized_return", "الربح المحقق", "colorful"),
                    ("exit_date", "تاريخ البيع", "date"),
                ]
            )
        else:
            st.info("أرشيف الصكوك فارغ")


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
        with st.expander("➕ تسجيل إيداع جديد"):
            with st.form("new_dep"):
                a = st.number_input("المبلغ", min_value=0.0, step=100.0, key="dep_amt")
                d = st.date_input("التاريخ", date.today(), key="dep_date")
                n = st.text_input("ملاحظة", key="dep_note")
                if st.form_submit_button("حفظ"):
                    if a > 0:
                        execute_query("INSERT INTO deposits (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                        st.success("تم")
                        st.cache_data.clear()
                        st.rerun()

        if not dep.empty:
            render_custom_table(dep.sort_values("date", ascending=False) if "date" in dep.columns else dep, cols_base)
            st.markdown("---")
            with st.expander("✏️ تعديل سجل إيداع سابق"):
                if "id" in dep.columns:
                    dep_map = {f"{row.get('date','-')} - {row.get('amount','-')} ({row.get('note','')})": row["id"] for _, row in dep.iterrows()}
                    sel_dep = st.selectbox("اختر العملية للتعديل:", list(dep_map.keys()), key="edit_dep_sel")
                    if sel_dep:
                        tid = dep_map[sel_dep]
                        curr = dep[dep["id"] == tid].iloc[0]
                        with st.form(f"edit_dep_form_{tid}"):
                            na = st.number_input("المبلغ الصحيح", value=float(curr.get("amount", 0)), key=f"dep_fix_amt_{tid}")
                            nd = st.date_input("التاريخ الصحيح", pd.to_datetime(curr.get("date", date.today())).date(), key=f"dep_fix_date_{tid}")
                            nn = st.text_input("ملاحظة", value=str(curr.get("note", "") or ""), key=f"dep_fix_note_{tid}")
                            if st.form_submit_button("حفظ التعديلات"):
                                execute_query("UPDATE deposits SET amount=%s, date=%s, note=%s WHERE id=%s", (na, str(nd), nn, tid))
                                st.success("تم التعديل بنجاح")
                                st.cache_data.clear()
                                st.rerun()

    with t2:
        with st.expander("➖ تسجيل سحب جديد"):
            with st.form("new_wit"):
                a = st.number_input("المبلغ", min_value=0.0, step=100.0, key="wit_amt")
                d = st.date_input("التاريخ", date.today(), key="wit_date")
                n = st.text_input("ملاحظة", key="wit_note")
                if st.form_submit_button("حفظ"):
                    if a > 0:
                        execute_query("INSERT INTO withdrawals (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                        st.success("تم")
                        st.cache_data.clear()
                        st.rerun()

        if not wit.empty:
            render_custom_table(wit.sort_values("date", ascending=False) if "date" in wit.columns else wit, cols_base)
            st.markdown("---")
            with st.expander("✏️ تعديل سجل سحب سابق"):
                if "id" in wit.columns:
                    wit_map = {f"{row.get('date','-')} - {row.get('amount','-')} ({row.get('note','')})": row["id"] for _, row in wit.iterrows()}
                    sel_wit = st.selectbox("اختر العملية للتعديل:", list(wit_map.keys()), key="edit_wit_sel")
                    if sel_wit:
                        tid = wit_map[sel_wit]
                        curr = wit[wit["id"] == tid].iloc[0]
                        with st.form(f"edit_wit_form_{tid}"):
                            na = st.number_input("المبلغ الصحيح", value=float(curr.get("amount", 0)), key=f"wit_fix_amt_{tid}")
                            nd = st.date_input("التاريخ الصحيح", pd.to_datetime(curr.get("date", date.today())).date(), key=f"wit_fix_date_{tid}")
                            nn = st.text_input("ملاحظة", value=str(curr.get("note", "") or ""), key=f"wit_fix_note_{tid}")
                            if st.form_submit_button("حفظ التعديلات"):
                                execute_query("UPDATE withdrawals SET amount=%s, date=%s, note=%s WHERE id=%s", (na, str(nd), nn, tid))
                                st.success("تم التعديل بنجاح")
                                st.cache_data.clear()
                                st.rerun()

    with t3:
        with st.expander("💵 تسجيل عائد/توزيع"):
            with st.form("new_ret"):
                s_raw = st.text_input("رمز السهم", key="ret_sym")
                a = st.number_input("المبلغ", min_value=0.0, step=10.0, key="ret_amt")
                d = st.date_input("التاريخ", date.today(), key="ret_date")
                if st.form_submit_button("حفظ"):
                    if a > 0:
                        s = _normalize_symbol(s_raw)
                        execute_query("INSERT INTO returnsgrants (date, symbol, amount) VALUES (%s,%s,%s)", (str(d), s, a))
                        st.success("تم")
                        st.cache_data.clear()
                        st.rerun()

        if not ret.empty:
            render_custom_table(
                ret.sort_values("date", ascending=False) if "date" in ret.columns else ret,
                [("date", "التاريخ", "date"), ("symbol", "السهم", "text"), ("amount", "المبلغ", "money")]
            )


# ========================================================
# 6) Financial UI
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

            if not final_symbol:
                final_symbol = st.text_input("⚠️ الرجاء إدخال رمز السهم (مثال: 1120.SR):", key=f"fin_manual_sym_{symbol}")

            if final_symbol:
                st.write("### 🧐 مراجعة البيانات المستخرجة:")
                preview_df = pd.DataFrame([{"Date": r["date"], **r["data"]} for r in results])
                _render_table_like_trades(preview_df, max_rows=200)

                if st.button("💾 تأكيد وحفظ في قاعدة البيانات", key=f"fin_save_{final_symbol}"):
                    count = 0
                    for r in results:
                        if save_financial_record(final_symbol, r["date"], r["data"], period_type="Annual", source="File/Paste"):
                            count += 1
                    st.success(f"تم حفظ {count} سجلات لشركة {final_symbol}.")
                    st.rerun()
            else:
                st.error("يجب تحديد رمز السهم للحفظ.")
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

            try:
                plot_df = df.copy()
                if "date" in plot_df.columns:
                    plot_df["Year"] = plot_df["date"].dt.strftime("%Y-%m") if hasattr(plot_df["date"].dt, "strftime") else plot_df["date"].astype(str)
                    cols_to_plot = [c for c in ["revenue", "net_income", "operating_cash_flow"] if c in plot_df.columns and pd.to_numeric(plot_df[c], errors="coerce").fillna(0).sum() != 0]
                    if cols_to_plot:
                        fig = px.bar(
                            plot_df.sort_values("date") if "date" in plot_df.columns else plot_df,
                            x="Year",
                            y=cols_to_plot,
                            barmode="group",
                            title="الأداء المالي التاريخي"
                        )
                        st.plotly_chart(fig, use_container_width=True)
            except Exception:
                pass

            with st.expander("عرض الجدول التفصيلي"):
                _render_table_like_trades(df, max_rows=600)

    with tab_data_mgmt:
        st.markdown("#### مصادر البيانات")
        t1, t2, t3 = st.tabs(["⚡ تحديث آلي (Yahoo)", "📂 استيراد ملف/نص", "✍️ إدخال يدوي شامل"])

        with t1:
            st.caption("جلب البيانات من Yahoo Finance مباشرة")
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

        with t3:
            st.markdown("##### تسجيل البيانات المالية يدوياً")
            st.caption("أدخل البيانات اللازمة للتحليل المالي.")

            with st.form(f"manual_fin_entry_{_sym_key(symbol)}"):
                col_meta1, col_meta2 = st.columns(2)
                f_date = col_meta1.date_input("تاريخ القوائم", date.today(), key=f"fin_date_{_sym_key(symbol)}")
                f_type = col_meta2.selectbox("الفترة", ["Annual", "Quarterly"], key=f"fin_type_{_sym_key(symbol)}")

                st.divider()
                st.markdown("**1. قائمة الدخل (Income Statement)**")
                c_inc1, c_inc2 = st.columns(2)
                rev = c_inc1.number_input("إجمالي الإيرادات", min_value=0.0, format="%.2f", key=f"fin_rev_{_sym_key(symbol)}")
                net_inc = c_inc2.number_input("صافي الربح", format="%.2f", key=f"fin_net_{_sym_key(symbol)}")

                st.divider()
                st.markdown("**2. قائمة التدفقات النقدية**")
                ocf = st.number_input("التدفق النقدي التشغيلي", help="Operating Cash Flow", format="%.2f", key=f"fin_ocf_{_sym_key(symbol)}")

                st.divider()
                st.markdown("**3. المركز المالي (Balance Sheet)**")
                c_bs1, c_bs2 = st.columns(2)
                tot_assets = c_bs1.number_input("إجمالي الأصول", min_value=0.0, format="%.2f", key=f"fin_assets_{_sym_key(symbol)}")
                tot_liab = c_bs2.number_input("إجمالي المطلوبات", min_value=0.0, format="%.2f", key=f"fin_liab_{_sym_key(symbol)}")

                c_bs3, c_bs4 = st.columns(2)
                cur_assets = c_bs3.number_input("الأصول المتداولة", min_value=0.0, format="%.2f", key=f"fin_cur_assets_{_sym_key(symbol)}")
                cur_liab = c_bs4.number_input("المطلوبات المتداولة", min_value=0.0, format="%.2f", key=f"fin_cur_liab_{_sym_key(symbol)}")

                c_bs5, c_bs6 = st.columns(2)
                tot_equity = c_bs5.number_input("إجمالي حقوق الملكية", format="%.2f", key=f"fin_equity_{_sym_key(symbol)}")
                lt_debt = c_bs6.number_input("الديون طويلة الأجل", min_value=0.0, format="%.2f", key=f"fin_ltdebt_{_sym_key(symbol)}")

                st.divider()
                if st.form_submit_button("💾 حفظ البيانات"):
                    data = {
                        "revenue": rev,
                        "net_income": net_inc,
                        "operating_cash_flow": ocf,
                        "total_assets": tot_assets,
                        "total_liabilities": tot_liab,
                        "current_assets": cur_assets,
                        "current_liabilities": cur_liab,
                        "total_equity": tot_equity,
                        "long_term_debt": lt_debt,
                    }
                    if save_financial_record(symbol, str(f_date), data, f_type, "Manual_Full"):
                        st.success("تم الحفظ بنجاح!")
                        st.rerun()
                    else:
                        st.error("فشل الحفظ. تأكد من البيانات.")


# ========================================================
# 7) Analysis
# ========================================================

def view_analysis(fin):
    st.header("🔬 التحليل الشامل")
    trades = fin.get("all_trades", pd.DataFrame())

    # ✅ اختبار التحمل
    if not trades.empty and "status" in trades.columns:
        status = _safe_status_series(trades)
        open_pos = trades[status == "open"].copy()
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

    all_syms = _clean_symbols_list(syms)

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

            if not ok:
                try:
                    dfx = _get_chart_history_flex(sym_try, "1mo", "1d")
                    ok = isinstance(dfx, pd.DataFrame) and (not dfx.empty)
                except Exception:
                    ok = False

            if ok:
                st.session_state["analysis_active_symbol"] = sym_try
                st.rerun()
            else:
                st.error("❌ الرمز غير معروف أو لا يمكن جلب بياناته الآن. تأكد من كتابة الرمز بشكل صحيح.")

    sym = st.session_state.get("analysis_active_symbol")

    if sym:
        sym = _normalize_symbol(sym)
        if not sym or sym == ".SR":
            st.warning("الرجاء إدخال رمز صحيح.")
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
        tabs = st.tabs(["🤖 المستشار", "💰 مالي", "📈 فني", "🏛️ كلاسيكي", "📝 أطروحة"])

        # --------------------------
        # 🤖 المستشار
        # --------------------------
        with tabs[0]:
            symk = _sym_key(sym)
            tf_map = {"يومي (1D)": "1d", "أسبوعي (1W)": "1wk", "شهري (1M)": "1mo"}

            top1, top2, top3, top4 = st.columns([1.2, 1.8, 1.4, 1.0])
            ai_tf_label = top1.selectbox("الفاصل الزمني", list(tf_map.keys()), index=0, key=f"ai_tf_{symk}")
            ai_tf = tf_map[ai_tf_label]

            view_mode = top2.radio(
                "طريقة العرض",
                ["مبسط", "تفصيلي", "بطاقات (Osoli)", "مطور (مع JSON)"],
                horizontal=True,
                key=f"ai_view_{symk}"
            )
            top3.caption("مبسط=مختصر | تفصيلي=كامل | بطاقات=واجهة أصولي | مطور=مع JSON")

            with top4:
                if AI_ENGINE_OK:
                    _badge("AI: OK", "success")
                else:
                    _badge("AI: Error", "danger")

            if st.button("🔄 تحديث المستشار", key=f"ai_refresh_{symk}"):
                cache = st.session_state.get("_ai_rep_cache", {})
                for k in list(cache.keys()):
                    if k.startswith(f"{sym}|"):
                        del cache[k]
                st.session_state["_ai_rep_cache"] = cache
                st.rerun()

            cache = st.session_state.setdefault("_ai_rep_cache", {})
            cache_key = f"{sym}|{ai_tf}"

            rep = None
            if cache_key in cache:
                rep = cache[cache_key]
            else:
                with st.spinner("جاري توليد تقرير المستشار..."):
                    rep = _generate_ai_report_flex(sym, timeframe=ai_tf)

                if isinstance(rep, dict) and (rep.get("__error__") or rep.get("__trace__")):
                    pass
                else:
                    cache[cache_key] = rep

            if view_mode == "مبسط":
                _render_ai_report_readable(rep, show_debug=False, compact=True)
            elif view_mode == "تفصيلي":
                _render_ai_report_readable(rep, show_debug=False, compact=False)
            elif view_mode == "بطاقات (Osoli)":
                try:
                    render_osoli_report(rep, title=f"🤖 تقرير المستشار | {ai_tf_label}")
                except Exception:
                    _render_ai_report_readable(rep, show_debug=False, compact=False)
            else:
                _render_ai_report_readable(rep, show_debug=True, compact=False)

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
                        cache = st.session_state.get("_ai_rep_cache", {})
                        for k in list(cache.keys()):
                            if k.startswith(f"{sym}|"):
                                del cache[k]
                        st.session_state["_ai_rep_cache"] = cache
                        st.rerun()
                    else:
                        st.error(f"لم يتم الحفظ: {res.get('reason','')}")
                        if res.get("trace"):
                            with st.expander("Trace"):
                                st.code(res.get("trace"), language="text")

            with st.expander("📌 عرض آخر الاستراتيجيات المحفوظة"):
                rules = load_user_rules(enabled_only=True, max_rows=10) or []
                if rules:
                    for r in rules:
                        st.write(f"- **{r.get('title','قاعدة')}**: {r.get('rule_text','')}")
                else:
                    st.info("لا توجد قواعد محفوظة بعد.")

            with st.expander("🧪 تشخيص المستشار (AI Engine Diagnostics)"):
                st.json(_ai_self_test())
                if not AI_ENGINE_OK:
                    st.warning("المشكلة غالباً داخل ai_engine.py (ImportError/Dependency/NameError).")
                    st.info("أرسل لي نص الخطأ الموجود هنا وسأصلح ai_engine.py لك مباشرة.")

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

            period_opts = {
                "6 أشهر": "6mo",
                "سنة": "1y",
                "سنتين": "2y",
                "5 سنوات": "5y",
                "10 سنوات": "10y",
                "الحد الأقصى": "max",
            }
            interval_opts = {
                "يومي 1D": "1d",
                "أسبوعي 1W": "1wk",
                "شهري 1M": "1mo",
                "ساعة 1H": "1h",
                "30 دقيقة": "30m",
                "15 دقيقة": "15m",
            }

            c_p, c_i, c_mode = st.columns([1.2, 1.2, 1.6])
            p_label = c_p.selectbox("الفترة (Period)", list(period_opts.keys()), index=2, key=f"tech_p_{symk}")
            i_label = c_i.selectbox("الفاصل (Interval)", list(interval_opts.keys()), index=0, key=f"tech_i_{symk}")

            mode = c_mode.radio(
                "وضع الشارت",
                ["احترافي", "قديم (Fallback)"],
                horizontal=True,
                key=f"tech_mode_{symk}"
            )

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
# 8) Other Pages
# ========================================================

def view_backtester_ui(fin):
    st.header("🧪 المختبر")

    if not run_backtest:
        st.warning("Backtester غير متوفر حالياً.")
        if bt_import_error:
            st.code(bt_import_error)
        st.info("✅ الحل: تأكد أن backtester.py يحتوي list_strategies و run_backtest بشكل صحيح.")
        return

    st.markdown("#### ⚙️ إعدادات الاختبار")
    cA, cB, cC = st.columns([1.2, 1.2, 1.6])
    s = cA.text_input("رمز السهم", "1120", key="lab_symbol", help="اكتب 1120 أو 1120.SR")
    cap = cB.number_input("رأس المال", min_value=1000.0, value=100000.0, step=1000.0, key="lab_cap")
    period = cC.selectbox("الفترة التاريخية", ["6mo", "1y", "2y", "5y", "10y", "max"], index=3, key="lab_period")

    strat = _select_strategy_ui(key_prefix="lab")

    st.caption("💡 إذا الاستراتيجية تعتمد على مؤشرات طويلة، اختر فترة أكبر (مثل 5y أو 10y).")

    if st.button("🚀 بدء الاختبار", key="bt_run", type="primary"):
        try:
            s_norm = _normalize_symbol(s)
            st.caption(f"🔎 الرمز: {s_norm} | الفترة: {period} | الاستراتيجية: {strat}")

            with st.spinner("جاري جلب البيانات التاريخية..."):
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

            with st.spinner("🧪 جاري تنفيذ الاستراتيجية على البيانات..."):
                res = run_backtest(data, str(strat), float(cap), symbol=s_norm, sector=sec)

            if not res:
                st.warning("⚠️ لم يرجع الاختبار نتيجة.")
                return

            st.session_state["__last_bt_result__"] = res
            st.success(f"✅ اكتمل الاختبار ({res.get('strategy_name_ar', strat)})")

        except Exception as e:
            st.error(f"Backtest Error: {e}")
            st.code(traceback.format_exc())

    res = st.session_state.get("__last_bt_result__")
    if res:
        st.markdown("---")
        st.markdown("#### 📊 النتائج")

        t_sum, t_curve, t_trades, t_raw = st.tabs(["ملخص", "منحنى المحفظة", "الصفقات", "خام"])

        with t_sum:
            kpis = {
                "return_pct": ("العائد %", "percent"),
                "final_value": ("القيمة النهائية", "money"),
                "max_drawdown_pct": ("أقصى سحب %", "percent"),
                "win_rate": ("نسبة النجاح", "percent"),
                "trades_count": ("عدد الصفقات", "number"),
                "sharpe": ("Sharpe", "number"),
            }

            cols = st.columns(4)
            idx = 0
            for k, (label, typ) in kpis.items():
                if k in res:
                    v = res.get(k)
                    if typ == "percent":
                        txt = f"{_to_float(v, 0):.2f}%"
                    elif typ == "money":
                        txt = safe_fmt(_to_float(v, 0))
                    elif typ == "number":
                        try:
                            txt = str(int(_to_float(v, 0)))
                        except Exception:
                            txt = str(v)
                    else:
                        try:
                            txt = f"{_to_float(v, 0):.2f}"
                        except Exception:
                            txt = str(v)

                    with cols[idx % 4]:
                        st.metric(label, txt)
                    idx += 1

            if isinstance(res.get("metrics"), dict) and res["metrics"]:
                st.markdown("---")
                st.markdown("**📌 مؤشرات إضافية**")
                mdf = pd.DataFrame([{"Metric": k, "Value": v} for k, v in res["metrics"].items()])
                st.dataframe(mdf, use_container_width=True)

        with t_curve:
            df_curve = res.get("df")
            if isinstance(df_curve, pd.DataFrame) and not df_curve.empty:
                col = None
                for cand in ["Portfolio_Value", "portfolio_value", "equity", "Equity", "value"]:
                    if cand in df_curve.columns:
                        col = cand
                        break
                if col:
                    st.line_chart(df_curve[col])
                else:
                    st.info("لا يوجد عمود منحنى واضح داخل df.")
                    st.dataframe(df_curve.head(50), use_container_width=True)
            else:
                st.info("لا يوجد DataFrame منحنى داخل النتيجة.")

        with t_trades:
            trades_df = res.get("trades") or res.get("trades_df")
            if isinstance(trades_df, pd.DataFrame) and not trades_df.empty:
                st.dataframe(trades_df, use_container_width=True)
            else:
                st.info("لا توجد صفقات مسجلة داخل نتيجة الاختبار (أو الاستراتيجية لا ترجعها).")

        with t_raw:
            st.json({k: v for k, v in res.items() if k != "df"})


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


# ✅ انتهى الملف هنا عمداً (بدون Router)
