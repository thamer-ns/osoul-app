# views/shared.py
import streamlit as st
import pandas as pd
import plotly.express as px  # موجود لأن views.py كان يستورده (حتى لو ما يُستخدم هنا)
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date
import traceback
from feature_flags import get_flag

from config import DEFAULT_COLORS
from components import (
    ar_selectbox,

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
except Exception:
    def render_technical_chart(symbol, *args, **kwargs):
        st.warning("⚠️ ملف charts.py مفقود أو به خطأ.")

# 2) Backtester
bt_import_error = None
try:
    from backtester import run_backtest, list_strategies
except Exception as e:
    run_backtest = None
    list_strategies = lambda: []
    bt_import_error = repr(e)

# 3) Financial Analysis
financial_import_error = None
try:
    from financial_analysis import (
        get_thesis, save_thesis,
        FinancialParser, save_financial_record,
        get_stored_financials_df, get_advanced_fundamental_ratios,
        sync_auto_yahoo, sync_full_yahoo,
        get_fundamental_ratios,
        get_financial_statements,
        get_last_yahoo_diagnostics,
        diagnose_yahoo_quote_summary,
    )
except Exception:
    financial_import_error = traceback.format_exc()
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
    def sync_full_yahoo(*args, **kwargs): return False, "Module Missing"
    def get_last_yahoo_diagnostics(): return {}
    def diagnose_yahoo_quote_summary(s): return {}
    def get_fundamental_ratios(s): return {}

def get_financial_import_error() -> str | None:
    """Expose last financial_analysis import error for UI debugging."""
    return financial_import_error

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
    """
    يحقن واجهة البرنامج مرة واحدة:
    - CSS الأساسي (RTL + الأيقونات + الخطوط + نقل الـ sidebar) من styles.py
    - CSS مكونات الواجهة من components.py
    - تعريب/RTL لعناصر Streamlit الافتراضية
    """
    if st.session_state.get("_ui_injected_once"):
        return
    st.session_state["_ui_injected_once"] = True

    # ✅ 1) CSS الأساسي للبرنامج (يرجّع نفس الشكل القديم)
    try:
        from styles import apply_custom_css
        apply_custom_css()
    except Exception:
        pass

    # ✅ 2) CSS الخاص بالمكونات
    try:
        inject_component_styles()
    except Exception:
        pass

    # ✅ 3) ترجمة/RTL لعناصر Streamlit الافتراضية
    try:
        inject_streamlit_ar_i18n(True)
    except Exception:
        pass

def _sym_key(sym: str) -> str:
    return (sym or "").replace(".", "_").replace("-", "_").replace(" ", "_")

def _normalize_symbol(symbol: str) -> str:
    """Normalize symbol consistently with market_data.get_ticker_symbol.

    ✅ Keeps crypto pairs like BTC-USD (does not strip '-').
    """
    try:
        from market_data import get_ticker_symbol
        return get_ticker_symbol(symbol)
    except Exception:
        s = str(symbol or "").strip().upper().replace(" ", "")
        if s.isdigit():
            return f"{s}.SR"
        return s

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

        label = (ar_selectbox if get_flag('use_ar_wrappers', False) else st.selectbox)(
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
    return (ar_selectbox if get_flag('use_ar_wrappers', False) else st.selectbox)("اختر الاستراتيجية", raw_str, index=0, key=f"{key_prefix}_strat")

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

# ========================================================
# TradingView-like Plot (كما في ملفك)
# ========================================================

def _build_tv_like_plot(df: pd.DataFrame, title: str = "", show_rangeslider: bool = False) -> go.Figure:
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

# ==============================================================
# 🕯️ Twelve Data Diagnostics (UI-safe wrappers)
# ==============================================================

def get_twelvedata_usage():
    """UI wrapper: return Twelve Data API usage info (if key configured)."""
    try:
        from twelvedata_provider import get_api_usage  # type: ignore
        d = get_api_usage()
        return dict(d) if isinstance(d, dict) else {"ok": False, "error": "invalid usage type"}
    except Exception:
        return {"ok": False, "error": "usage unavailable", "hint": "تأكد من TWELVEDATA_API_KEY"}


def diagnose_twelvedata_symbol(symbol: str):
    """UI wrapper: quick quote + small candles sample to validate symbol coverage."""
    out = {"symbol": symbol}
    try:
        from twelvedata_provider import get_quote, get_time_series  # type: ignore

        q = get_quote(symbol)
        out["quote"] = dict(q) if isinstance(q, dict) else {"ok": False, "error": "invalid quote"}

        df = get_time_series(symbol, interval="1d", years=1, outputsize=120)
        out["candles"] = {
            "ok": bool(df is not None and not df.empty),
            "rows": int(len(df)) if df is not None else 0,
            "from": str(df.index.min().date()) if df is not None and not df.empty else "",
            "to": str(df.index.max().date()) if df is not None and not df.empty else "",
        }
        out["ok"] = bool(out["quote"].get("ok") or out["candles"].get("ok"))
        return out
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)
        return out