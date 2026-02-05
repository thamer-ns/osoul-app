# views/shared.py
import streamlit as st
import pandas as pd

# Lazy plotly import to speed up app startup
_PLOTLY = None

def _lazy_plotly():
    global _PLOTLY
    if _PLOTLY is None:
        import plotly.graph_objects as go  # type: ignore
        from plotly.subplots import make_subplots  # type: ignore
        _PLOTLY = (go, make_subplots)
    return _PLOTLY
from datetime import date
import traceback

from config import DEFAULT_COLORS
from components import (
    render_kpi,
    render_custom_table,
    render_ticker_card,
    safe_fmt,
    inject_component_styles,
    inject_streamlit_ar_i18n,
    render_osoli_report as _render_osoli_report_base,
)

from analytics import (
    generate_equity_curve,
)
from market_data import get_chart_history

# ========================================================
# 🛡️ Fail-Safe Imports (كما في ملفك)
# ========================================================

# 1) Charts
try:
    from charts import render_technical_chart
except Exception as e:
    from osoli_logging import log_exception
    log_exception(e, "Optional module failed to import: charts.render_technical_chart", level="WARNING")
    def render_technical_chart(symbol, *args, **kwargs):
        st.warning("⚠️ ملف charts.py مفقود أو به خطأ.")

# 2) Backtester
bt_import_error = None
try:
    from backtester import run_backtest, list_strategies
except Exception as e:
    from osoli_logging import log_exception
    log_exception(e, "Optional module failed to import: backtester", level="WARNING")

    run_backtest = None
    list_strategies = lambda: []
    bt_import_error = repr(e)

# 3) Financial Analysis
fin_import_error = None
try:
    from financial_analysis import (
        get_thesis, save_thesis,
        FinancialParser, save_financial_record,
        get_stored_financials_df, get_advanced_fundamental_ratios,
        sync_auto_yahoo, sync_full_yahoo, get_fundamental_ratios,
        get_financial_statements,
        fetch_full_statement_records, has_full_statement,
    )
except Exception as e:
    from osoli_logging import log_exception
    log_exception(e, "Optional module failed to import: financial_analysis", level="WARNING")
    fin_import_error = traceback.format_exc()
    def get_thesis(s): return None
    def save_thesis(s, t, tg, r): pass
    def get_stored_financials_df(s, p): return pd.DataFrame()
    def get_advanced_fundamental_ratios(s): return {}
    def get_financial_statements(s, p="Annual", refresh=False): return pd.DataFrame()
    def fetch_full_statement_records(s, statement="income", period_type="Annual", scale="thousands"): return pd.DataFrame()
    def has_full_statement(s, statement="income", period_type="Annual", scale="thousands"): return False

    class FinancialParser:
        def process_file_or_text(self, uploaded_file=None, text_input=None):
            return [], None, "FinancialParser غير متوفر"

    def save_financial_record(*args, **kwargs): return False
    def sync_auto_yahoo(s): return False, (fin_import_error or repr(e))
    def sync_full_yahoo(s, include_ttm=True): return False, (fin_import_error or repr(e))
    def get_fundamental_ratios(s): return {}

# 4) Classical Analysis
try:
    from classical_analysis import render_classical_analysis
except Exception:
    def render_classical_analysis(s):
        st.warning("⚠️ ملف classical_analysis.py مفقود أو به خطأ.")

# 5) AI Engine
ai_import_error = None
AI_ENGINE_VERSION = "unknown"
AI_ENGINE_NAME = "Osoli AI Engine"

# ✅ هنا التعديل الرئيسي: import مرن + fallback للـ ai_engine_core/reporting.py
try:
    # المسار الطبيعي (مثل ملفك)
    from ai_engine import (
        AI_ENGINE_VERSION,
        AI_ENGINE_NAME,
        generate_ai_report,
        calculate_portfolio_risk_score,
        run_stress_test,
        generate_rebalancing_suggestions,
        save_user_rule,
        load_user_rules,
    )
except Exception:
    ai_import_error = traceback.format_exc()

    # ✅ fallback: استخدم محركك الموجود داخل ai_engine_core/reporting.py مباشرة
    try:
        from ai_engine_core.config import AI_ENGINE_VERSION, AI_ENGINE_NAME
    except Exception:
        AI_ENGINE_VERSION = "unknown"
        AI_ENGINE_NAME = "Osoli AI Engine"

    try:
        from ai_engine_core.reporting import generate_ai_report  # الدالة الموجودة في ملفك
    except Exception:
        def generate_ai_report(symbol, timeframe="1D"):
            return {"__error__": "AI Engine import failed", "__trace__": ai_import_error}

    # اختياريات: إذا ما كانت مصدّرة من ai_engine.py
    def calculate_portfolio_risk_score(df, c):
        return None
    def run_stress_test(v, df):
        return {"__error__": "AI Engine import failed", "__trace__": ai_import_error, "scenarios": [], "insight": ""}
    def generate_rebalancing_suggestions(df, c):
        return {"__error__": "AI Engine import failed", "__trace__": ai_import_error, "items": []}

    # ✅ User rules fallback
    try:
        from ai_engine_core.user_rules import load_user_rules, save_user_rule
    except Exception:
        def save_user_rule(rule_text: str, title: str = None, enabled: int = 1):
            return {"ok": False, "reason": "AI Engine missing", "trace": ai_import_error}

        def load_user_rules(enabled_only=True, max_rows=50):
            return []

# ========================================================
# Helpers (كما في ملفك)
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
# ✅ AI Helpers + Renderer (كما في ملفك)
# ========================================================

# ✅ تعديل: نخلي الـ timeframe بصيغة محركك (1D/1W/1M/1H..)
def _ai_timeframe_normalize(tf: str) -> str:
    t = (tf or "").strip()
    if not t:
        return "1D"

    u = t.strip().upper()
    l = t.strip().lower()

    # Daily/Weekly/Monthly
    if u in ["1D", "D", "DAY", "DAILY"] or l in ["1d", "day", "daily"]:
        return "1D"
    if u in ["1W", "W", "WEEK", "WEEKLY"] or l in ["1wk", "1w", "week", "weekly"]:
        return "1W"
    if u in ["1M", "M", "MONTH", "MONTHLY"] or l in ["1mo", "month", "monthly"]:
        return "1M"

    # Intraday (لو تبغاه)
    if u in ["1H", "H", "60M", "60MIN"] or l in ["1h", "60m"]:
        return "1H"
    if u in ["30M", "30MIN"] or l in ["30m"]:
        return "30M"
    if u in ["15M", "15MIN"] or l in ["15m"]:
        return "15M"
    if u in ["5M", "5MIN"] or l in ["5m"]:
        return "5M"

    # fallback: لو المستخدم كتب شيء غريب، خلّه كما هو لكن Upper
    return u

def _generate_ai_report_flex(symbol: str, timeframe: str):
    tf = _ai_timeframe_normalize(timeframe)
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

def _score_from_new_engine(rep: dict) -> int:
    try:
        tech = _to_float(rep.get("tech_score"), 0) or 0
        fund = _to_float(rep.get("fund_score"), 0) or 0
        total = tech + fund
        score = int(max(0, min(100, round(50 + (total * 5)))))
        return score
    except Exception:
        return 0

def _extract_ai(rep: dict) -> dict:
    if not isinstance(rep, dict):
        return {"ok": False, "raw": rep, "error": "AI report is not dict"}

    if rep.get("__error__"):
        return {"ok": False, "raw": rep, "error": rep.get("__error__")}

    ex = rep.get("explainability") or {}
    if not isinstance(ex, dict):
        ex = {}

    positives = _safe_list(ex.get("positives", rep.get("positives", [])))
    negatives = _safe_list(ex.get("negatives", rep.get("negatives", [])))
    notes = _safe_list(ex.get("notes", rep.get("notes", [])))

    tech_reasons = _safe_list(rep.get("tech_reasons", []))
    fund_reasons = _safe_list(rep.get("fund_reasons", []))

    top_evidence = _safe_list(rep.get("top_evidence", positives if positives else tech_reasons))
    top_risks = _safe_list(rep.get("top_risks", negatives if negatives else fund_reasons))

    risk_gates = rep.get("risk_gates", {})
    if not isinstance(risk_gates, dict):
        risk_gates = {}

    scenarios = rep.get("scenarios", [])
    if not isinstance(scenarios, list):
        scenarios = []

    engine_meta = rep.get("engine_meta") or {}
    if not isinstance(engine_meta, dict):
        engine_meta = {}

    score = rep.get("score", rep.get("osoli_score", None))
    if score is None and ("tech_score" in rep or "fund_score" in rep):
        score = _score_from_new_engine(rep)

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

    risk_plan = rep.get("risk_plan") or {}
    if isinstance(risk_plan, dict) and risk_plan:
        entry.setdefault("entry_zone", risk_plan.get("entry"))
        risk.setdefault("stop", risk_plan.get("stop"))
        risk.setdefault("rr", risk_plan.get("rr"))
        if risk_plan.get("target1") is not None and not targets:
            targets = [{"name": "Target 1", "price": risk_plan.get("target1"), "note": ""}]

    if not summary_text:
        s = []
        if tech_reasons:
            s.append(" | ".join(tech_reasons[:3]))
        if fund_reasons:
            s.append(" | ".join(fund_reasons[:2]))
        summary_text = "\n".join(s).strip()

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
        "engine_meta": engine_meta,
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
    """عرض الأهداف بنفس نمط جداول البرنامج (render_custom_table) لضمان توحيد الشكل."""
    targets = _safe_list(targets)
    if not targets:
        st.info("لا توجد أهداف جاهزة حالياً.")
        return

    rows = []
    for t in targets[:50]:
        if isinstance(t, dict):
            rows.append({
                "الهدف": t.get("name") or t.get("label") or "Target",
                "السعر": _fmt_price(t.get("price") or t.get("value")),
                "ملاحظة": t.get("note") or ""
            })
        else:
            rows.append({"الهدف": "Target", "السعر": _fmt_price(t), "ملاحظة": ""})

    df = pd.DataFrame(rows)

    # توحيد الشكل مع جدول الصفقات (نفس render_custom_table)
    cols_spec = [
        ("الهدف", "الهدف", "text"),
        ("السعر", "السعر", "money"),
        ("ملاحظة", "ملاحظة", "text"),
    ]
    try:
        render_custom_table(df, cols_spec)
    except Exception:
        # fallback آمن
        st.dataframe(df, use_container_width=True, hide_index=True)

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


def _chip(text: str, tone: str = "neutral"):
    # يستخدم CSS الموجود في styles.py (.os-chip ودرجات الألوان)
    cls = {
        "success": "os-chip-green",
        "warning": "os-chip-amber",
        "danger": "os-chip-red",
        "blue": "os-chip-blue",
        "neutral": "os-chip-gray",
    }.get(tone, "os-chip-gray")
    st.markdown(
        f'<span class="os-chip {cls}"><span class="mi">insights</span>{text}</span>',
        unsafe_allow_html=True,
    )

def _tone_score(score: int) -> str:
    try:
        s = int(score)
    except Exception:
        return "neutral"
    return "success" if s >= 70 else "warning" if s >= 40 else "danger"

def _tone_conf(conf: int) -> str:
    try:
        c = int(conf)
    except Exception:
        return "neutral"
    return "success" if c >= 70 else "warning" if c >= 40 else "danger"

def _looks_like_html(s: str) -> bool:
    if not isinstance(s, str):
        return False
    t = s.lower()
    return any(tag in t for tag in ["<div", "<span", "<p", "<br", "</", "style="])


# ========================================================
# ✅ NEW: Evidence/Risks Search + Auto-Rank + Categorization
# ========================================================

def _norm_text(s: str) -> str:
    """تطبيع بسيط للنص للبحث/التصنيف/الترتيب (UI فقط)."""
    try:
        t = str(s or "")
    except Exception:
        return ""
    t = t.strip().lower()
    rep = {
        "أ": "ا", "إ": "ا", "آ": "ا",
        "ة": "ه",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
    }
    for a, b in rep.items():
        t = t.replace(a, b)
    return t

def _score_signal_strength(text: str, mode: str = "evidence") -> int:
    """نقاط قوة تقديرية حسب كلمات/إشارات (UI فقط)."""
    t = _norm_text(text)
    score = 0

    # إشارات فنية/سعرية قوية
    strong_positive = [
        ("اختراق", 9), ("breakout", 9), ("كسر مقاومه", 9), ("break resistance", 9),
        ("retest", 5), ("اعاده اختبار", 5),
        ("bullish", 6), ("شراء", 4), ("buy", 4),
        ("order block", 7), ("ob", 6), ("اوردربلوك", 7), ("بلوك", 3),
        ("rsi", 4), ("macd", 4), ("adx", 3), ("stochastic", 3),
        ("divergence", 5), ("تباعد", 5),
        ("volume", 5), ("حجم", 5), ("سيوله", 5),
        ("uptrend", 6), ("ترند صاعد", 6),
        ("support", 3), ("دعم", 3),
        ("relative strength", 6), ("rs", 5),
        ("gap", 3), ("فجوه", 3),
    ]

    strong_negative = [
        ("كسر دعم", 10), ("break support", 10),
        ("bearish", 7), ("sell", 5), ("بيع", 5),
        ("downtrend", 7), ("ترند هابط", 7),
        ("fail", 5), ("فشل", 5),
        ("leverage", 6), ("رافعة", 6), ("leverag", 6),
        ("altman", 5),
        ("debt", 4), ("دين", 4),
        ("risk", 4), ("مخاطر", 4),
        ("volatility", 3), ("تذبذب", 3),
        ("loss", 3), ("خساره", 3),
        ("ضعف", 3), ("weak", 3),
        ("ضغط", 3), ("distribution", 4), ("تصريف", 4),
        ("upthrust", 4), ("shakeout", 4),
    ]

    # VSA
    vsa_boost = [
        ("no supply", 5), ("no demand", 5),
        ("absorption", 5), ("accumulation", 5),
        ("distribution", 5), ("climactic", 5),
        ("squat", 4), ("end of rising", 5),
        ("تجميع", 5), ("تصريف", 5),
        ("امتصاص", 5),
    ]

    # علامات عامة
    if "✅" in str(text): score += 2
    if "⚠️" in str(text): score += 2
    if "❌" in str(text): score += 3
    if "!" in str(text): score += 1

    if mode == "evidence":
        for k, w in strong_positive:
            if k in t:
                score += w
        for k, w in vsa_boost:
            if k in t:
                score += max(1, w // 2)
    else:
        for k, w in strong_negative:
            if k in t:
                score += w
        for k, w in vsa_boost:
            if k in t:
                score += max(1, w // 3)

    # وجود أرقام غالباً يعني إشارة أدق (مثل RSI=..)
    if any(ch.isdigit() for ch in t):
        score += 2

    return int(max(0, min(60, score)))

def _filter_items(items, query: str = "") -> list:
    items = _safe_list(items)
    q = _norm_text(query)
    if not q:
        return [str(x) for x in items]
    out = []
    for x in items:
        s = str(x)
        if q in _norm_text(s):
            out.append(s)
    return out

def _rank_items(items, mode: str = "evidence") -> list:
    scored = [(s, _score_signal_strength(s, mode=mode)) for s in items]
    scored.sort(key=lambda z: (z[1], len(z[0])), reverse=True)
    return [s for s, _ in scored]

def _categorize_evidence(text: str) -> str:
    """تصنيف تلقائي للأدلة إلى: فني / مالي / VSA / كلاسيكي / أخرى (UI فقط)."""
    t = _norm_text(text)

    # Financial
    fin_keys = [
        "altman", "z", "peg", "pe", "p/e", "valuation", "gordon", "graham",
        "liquidity", "سيوله", "cash", "operating cash", "free cash", "fcf",
        "earnings", "ربحيه", "net income", "profit", "هامش", "margin",
        "debt", "دين", "leverage", "رافعة", "sg r", "sgr",
        "dupont", "roe", "roa", "ebit", "ebitda",
    ]
    # VSA
    vsa_keys = [
        "vsa", "no supply", "no demand", "absorption", "accumulation",
        "distribution", "climactic", "squat", "upthrust", "shakeout",
        "تجميع", "تصريف", "امتصاص",
    ]
    # Classical / Structure
    cls_keys = [
        "pivot", "pivots", "زون", "zone", "supply", "demand",
        "double top", "double bottom", "head and shoulders", "shoulders",
        "inside bar", "dow", "trendline", "support", "resistance",
        "قمه مزدوجه", "قاع مزدوج", "كتف", "رأس", "داو", "ترندلاين",
    ]
    # Technical
    tech_keys = [
        "rsi", "macd", "adx", "stochastic", "ema", "sma", "ma ", "moving average",
        "breakout", "اختراق", "retest", "gap", "divergence", "volume",
        "bollinger", "atr", "momentum",
        "شمعة", "ابتلاع", "كسر", "ارتداد",
        "order block", "ob", "اوردربلوك",
        "relative strength", "rs",
    ]

    # أولوية: VSA ثم مالي ثم كلاسيكي ثم فني
    if any(k in t for k in vsa_keys):
        return "VSA"
    if any(k in t for k in fin_keys):
        return "مالي"
    if any(k in t for k in cls_keys):
        return "كلاسيكي/هيكلي"
    if any(k in t for k in tech_keys):
        return "فني"
    return "أخرى"

def _group_evidence(items: list) -> dict:
    """يرجع dict: category -> list[str]"""
    groups = {"فني": [], "مالي": [], "VSA": [], "كلاسيكي/هيكلي": [], "أخرى": []}
    for s in items:
        c = _categorize_evidence(s)
        groups.setdefault(c, []).append(s)
    return groups

def _render_list(title: str, items: list, prefix: str = "•", empty_text: str = "لا يوجد", limit: int = 9999):
    st.markdown(f"<div class='os-card-title'>{title}</div>", unsafe_allow_html=True)
    if not items:
        st.caption(empty_text)
        return
    for s in items[:limit]:
        st.write(f"- {prefix} {s}")

def _render_colored_rows_table(items: list, tone: str = "success", max_rows: int = 40):
    """جدول HTML بسيط بخلفية صفوف ملوّنة (لتوحيد الشكل بدون تغيير render_custom_table)."""
    items = [str(x) for x in _safe_list(items)]
    if not items:
        st.caption("لا يوجد")
        return

    bg = {
        "success": "rgba(5,150,105,0.08)",
        "danger":  "rgba(220,38,38,0.08)",
        "warning": "rgba(245,158,11,0.10)",
        "neutral": "rgba(15,23,42,0.04)",
    }.get(tone, "rgba(15,23,42,0.04)")

    bd = {
        "success": "rgba(5,150,105,0.22)",
        "danger":  "rgba(220,38,38,0.22)",
        "warning": "rgba(245,158,11,0.24)",
        "neutral": "rgba(15,23,42,0.10)",
    }.get(tone, "rgba(15,23,42,0.10)")

    rows = items[:max_rows]
    html_rows = []
    for i, s in enumerate(rows, start=1):
        html_rows.append(
            f"""<tr style="background:{bg}; border-bottom:1px solid {bd};">
                    <td style="width:52px; text-align:center; font-weight:900;">{i}</td>
                    <td style="text-align:right; font-weight:800;">{s}</td>
                </tr>"""
        )

    st.markdown(
        f"""
        <table class="finance-table" style="margin-top:8px;">
            <thead>
                <tr>
                    <th style="width:52px; text-align:center;">#</th>
                    <th>النص</th>
                </tr>
            </thead>
            <tbody>
                {''.join(html_rows)}
            </tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )

    if len(items) > max_rows:
        with st.expander("عرض المزيد"):
            for s in items[max_rows: max_rows + 200]:
                st.write(f"- {s}")



def _render_ai_report_readable(rep: dict, show_debug: bool = False, compact: bool = False):
    """عرض تقرير المستشار بشكل أجمل/أوضح — بدون تغيير أي بيانات أو منطق.
    - لا يحذف أي قسم (الأهداف/الأدلة/المخاطر/بوابات المخاطر/السيناريوهات/JSON)
    - يحسن ترتيب العرض + يضيف بطاقات/Chips باستخدام CSS الموجود لديك.
    """
    data = _extract_ai(rep)
    if not data.get("ok"):
        st.warning("⚠️ تقرير المستشار غير صالح.")
        err = data.get("error")
        if err:
            st.error(str(err))
        st.write(data.get("raw"))
        return

    meta = data.get("engine_meta") or {}
    tf = meta.get("timeframe") or meta.get("tf") or "—"

    # ==========================
    # Hero Card (Recommendation)
    # ==========================
    col = data.get("color") or "#667085"
    rec = str(data.get("recommendation", "—"))
    strat = str(data.get("strategy", "—"))

    st.markdown(
        f"""
        <div class="os-card" style="border:2px solid {col}; background: linear-gradient(135deg, rgba(102,112,133,0.06), rgba(37,99,235,0.05));">
          <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;">
            <div>
              <div style="font-size:1.45rem;font-weight:950;line-height:1.2;">{rec}</div>
              <div class="os-muted" style="margin-top:6px;">{strat}</div>
              <div class="os-muted" style="margin-top:6px;">🧩 {AI_ENGINE_NAME} v{AI_ENGINE_VERSION} • Base Interval: {tf}</div>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;">
              <span class="os-chip os-chip-blue"><span class="mi">token</span>AI</span>
              <span class="os-chip os-chip-gray"><span class="mi">timeline</span>{tf}</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ==========================
    # KPI Cards
    # ==========================
    score = int(_to_float(data.get("score"), 0) or 0)
    conf = int(_to_float(data.get("confidence"), 0) or 0)
    conf_label = str(data.get("confidence_label") or "—")

    # Chips row
    st.markdown("<div class='os-card' style='padding:12px;margin-top:10px;'>", unsafe_allow_html=True)
    _chip(f"Score {score}/100", _tone_score(score))
    _chip(f"{conf_label} ({conf}%)", _tone_conf(conf))
    st.markdown(
        "<span class='os-chip os-chip-gray'><span class='mi'>rule</span>اعتمد على الأدلة + بوابات المخاطر</span>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # Progress
    st.progress(max(0, min(100, conf)))

    # ==========================
    # Summary / Reason
    # ==========================
    summary_text = str(data.get("summary_text") or "").strip()
    if summary_text:
        st.markdown("### 🧾 سبب التوصية")
        st.markdown("<div class='os-card'>", unsafe_allow_html=True)
        if _looks_like_html(summary_text):
            st.markdown(summary_text, unsafe_allow_html=True)
        else:
            # عرض قابل للقراءة (بدون ما يظهر كود كبير)
            st.markdown(f"<div style='white-space:pre-wrap;line-height:1.8;font-weight:800;color:var(--txt);'>{summary_text}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ==========================
    # Entry / Risk / Levels / Targets
    # ==========================
    has_plan = any([data.get("entry"), data.get("risk"), data.get("levels"), data.get("targets")])
    if has_plan:
        _render_entry_risk_levels(
            data.get("entry") or {},
            data.get("risk") or {},
            data.get("levels") or {},
            score,
        )

        st.markdown("### 🎯 الأهداف")
        _render_targets(data.get("targets") or [])
    # ==========================
    # Evidence & Risks (NEW: search + rank + categorize)
    # ==========================
    st.markdown("---")

    # عرض سريع (مختصر) + تفاصيل داخل Expander لتسهيل القراءة
    ev_all = _safe_list(data.get("top_evidence", []))
    rk_all = _safe_list(data.get("top_risks", []))

    a, b = st.columns(2)
    with a:
        st.markdown("<div class='os-card'>", unsafe_allow_html=True)
        st.markdown("<div class='os-card-title'>✅ أقوى الأدلة (مختصر)</div>", unsafe_allow_html=True)
        if not ev_all:
            st.caption("لا يوجد")
        else:
            for s in ev_all[:6 if compact else 10]:
                st.markdown(f"- ✅ {s}")
        st.markdown("</div>", unsafe_allow_html=True)

    with b:
        st.markdown("<div class='os-card'>", unsafe_allow_html=True)
        st.markdown("<div class='os-card-title'>⚠️ أكبر المخاطر (مختصر)</div>", unsafe_allow_html=True)
        if not rk_all:
            st.caption("لا يوجد")
        else:
            for s in rk_all[:6 if compact else 10]:
                st.markdown(f"- ⚠️ {s}")
        st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("تفاصيل الأدلة والمخاطر (بحث/ترتيب/تصنيف)"):
        # Searches (منفصل لكل عمود)
        c_search1, c_search2 = st.columns(2)
        with c_search1:
            q_ev = st.text_input("بحث داخل الأدلة", value="", placeholder="مثال: اختراق / OB / RSI / سيولة ...", key="ev_search")
            auto_rank_ev = st.toggle("ترتيب تلقائي (الأقوى أولاً)", value=True, key="ev_rank")
        with c_search2:
            q_rk = st.text_input("بحث داخل المخاطر", value="", placeholder="مثال: كسر دعم / ديون / Leverage ...", key="rk_search")
            auto_rank_rk = st.toggle("ترتيب تلقائي (الأقوى أولاً)", value=True, key="rk_rank")

        a2, b2 = st.columns(2)

        # -------- Evidence column --------
        with a2:
            st.markdown("<div class='os-card'>", unsafe_allow_html=True)
            ev_f = _filter_items(ev_all, q_ev)
            if auto_rank_ev:
                ev_f = _rank_items(ev_f, mode="evidence")

            view_table_ev = st.toggle("عرض كجدول (تلوين الصفوف)", value=False, key="ev_table")

            st.markdown("<div class='os-card-title'>✅ أقوى الأدلة</div>", unsafe_allow_html=True)
            if not ev_all:
                st.caption("لا يوجد")
            else:
                st.caption(f"المعروض: {len(ev_f)}/{len(ev_all)}")

            if view_table_ev:
                _render_colored_rows_table(ev_f, tone="success", max_rows=(20 if compact else 40))
            else:
                groups = _group_evidence(ev_f)
                ordered = ["فني", "مالي", "VSA", "كلاسيكي/هيكلي", "أخرى"]
                shown_any = False
                lim = 6 if compact else 30
                for cat in ordered:
                    items = groups.get(cat, [])
                    if not items:
                        continue
                    shown_any = True
                    st.markdown(f"**{cat}**  \n<span class='os-muted'>({len(items)})</span>", unsafe_allow_html=True)
                    for s in items[:lim]:
                        st.markdown(f"- ✅ {s}")
                    if len(items) > lim:
                        with st.expander(f"عرض المزيد من {cat}"):
                            for s in items[lim:]:
                                st.markdown(f"- ✅ {s}")
                if not shown_any:
                    st.caption("لا توجد نتائج مطابقة للبحث.")

            with st.expander("🧾 عرض قائمة الأدلة كاملة (خام)"):
                for s in ev_all[:200]:
                    st.markdown(f"- {s}")

            st.markdown("</div>", unsafe_allow_html=True)

        # -------- Risks column --------
        with b2:
            st.markdown("<div class='os-card'>", unsafe_allow_html=True)
            rk_f = _filter_items(rk_all, q_rk)
            if auto_rank_rk:
                rk_f = _rank_items(rk_f, mode="risk")

            view_table_rk = st.toggle("عرض كجدول (تلوين الصفوف)", value=False, key="rk_table")

            st.markdown("<div class='os-card-title'>⚠️ أكبر المخاطر</div>", unsafe_allow_html=True)
            if not rk_all:
                st.caption("لا يوجد")
            else:
                st.caption(f"المعروض: {len(rk_f)}/{len(rk_all)}")

            if view_table_rk:
                _render_colored_rows_table(rk_f, tone="danger", max_rows=(20 if compact else 40))
            else:
                lim = 6 if compact else 30
                if not rk_f:
                    st.caption("لا توجد نتائج مطابقة للبحث.")
                else:
                    for s in rk_f[:lim]:
                        st.markdown(f"- ⚠️ {s}")
                    if len(rk_f) > lim:
                        with st.expander("عرض المزيد من المخاطر"):
                            for s in rk_f[lim:]:
                                st.markdown(f"- ⚠️ {s}")

            with st.expander("🧾 عرض قائمة المخاطر كاملة (خام)"):
                for s in rk_all[:200]:
                    st.markdown(f"- {s}")

            st.markdown("</div>", unsafe_allow_html=True)

    # ==========================
    # Risk gates

    # ==========================
    st.markdown("---")
    st.markdown("### 🛡️ بوابات المخاطر")
    _render_risk_gates(data.get("risk_gates") or {})

    # ==========================
    # Scenarios
    # ==========================
    st.markdown("---")
    st.markdown("### 🧭 السيناريوهات المقترحة")
    _render_scenarios(data.get("scenarios") or [])

    # Notes
    notes = _safe_list(data.get("notes", []))
    if notes and not compact:
        with st.expander("🧾 ملاحظات إضافية"):
            for x in notes[:30]:
                st.write(f"- {x}")

    # Raw JSON
    if show_debug:
        with st.expander("🧩 عرض التقرير الخام (JSON)"):
            st.json(data.get("raw", rep))


def render_osoli_report(rep: dict, title: str = "🤖 تقرير أصولي", *args, **kwargs):
    """واجهة بطاقات (Osoli) محسّنة — مع الحفاظ على العرض الأصلي الموجود في components.py.
    - بشكل افتراضي: يعرض نسخة محسّنة (بطاقات + Chips)
    - ثم يوفر Expander لعرض النسخة الأصلية (عدم فقد أي ميزة/تفصيل سابق)
    """
    st.markdown(f"### {title}")

    # نسخة محسّنة تعتمد على نفس parse (_extract_ai) — لا تغيير في البيانات
    try:
        _render_ai_report_readable(rep, show_debug=False, compact=False)
    except Exception as e:
        st.warning("⚠️ تعذر عرض البطاقات المحسّنة، سيتم استخدام العرض الأصلي.")
        st.code(str(e))

    # النسخة الأصلية (كما هي) لضمان عدم فقد أي تفاصيل/مزايا
    with st.expander("🧩 عرض أصولي (النسخة الأصلية)"):
        try:
            return _render_osoli_report_base(rep, title=title, *args, **kwargs)
        except TypeError:
            # بعض النسخ لا تدعم title كوسيط
            return _render_osoli_report_base(rep, *args, **kwargs)


# ========================================================
# TradingView-like Plot (كما في ملفك)
# ========================================================

def _build_tv_like_plot(df: pd.DataFrame, title: str = "", show_rangeslider: bool = False) -> "object":
    go, make_subplots = _lazy_plotly()
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
    Low  = colmap.get("low")  if "low"  in colmap else ("Low"  if "Low"  in d.columns else None)
    Close= colmap.get("close")if "close"in colmap else ("Close"if "Close" in d.columns else None)
    Vol  = colmap.get("volume")if "volume"in colmap else ("Volume" if "Volume" in d.columns else None)

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
            rangeslider=dict(visible=bool(show_rangeslider)),
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

def _render_tv_like_chart(symbol: str, period: str, interval: str, show_rangeslider: bool = False):
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
                df = df.reset_index().rename(columns={"index": "date"})
        except Exception:
            pass

    try:
        fig = _build_tv_like_plot(df, title=f"{symbol} | {period} | {interval}", show_rangeslider=show_rangeslider)
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
# Table wrapper (كما في ملفك)
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
# 🔎 Import diagnostics (used by views/__init__.py and Tools page)
# ========================================================

def get_import_diagnostics():
    """Return a safe diagnostics dict for optional modules.

    Must NEVER raise because it's used during app boot.
    """
    try:
        diag = {
            "ai_engine": {
                "ok": (globals().get("ai_import_error") is None),
                "name": globals().get("AI_ENGINE_NAME", "Osoli AI Engine"),
                "version": globals().get("AI_ENGINE_VERSION", "unknown"),
                "error": globals().get("ai_import_error"),
                "fallback_reporting": ("ai_engine_core.reporting" in (getattr(generate_ai_report, "__module__", "") or "")),
            },
            "backtester": {
                "ok": (globals().get("bt_import_error") is None),
                "error": globals().get("bt_import_error"),
            },
        }

        # Best-effort checks for other optional modules (do not store as globals)
        for mod in ("financial_analysis", "charts", "classical_analysis"):
            try:
                __import__(mod)
                diag[mod] = {"ok": True, "error": None}
            except Exception as e:
                diag[mod] = {"ok": False, "error": repr(e)}

        return diag
    except Exception:
        # Absolute last-resort: never crash startup
        return {
            "ai_engine": {"ok": False, "error": "diagnostics_failed"},
            "backtester": {"ok": False, "error": "diagnostics_failed"},
        }
