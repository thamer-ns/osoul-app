# ui/pages/analysis/ai_tab.py
import streamlit as st
import traceback
import inspect

from components import render_osoli_report
from ui.common import sym_key as _sym_key

from ui.pages.analysis.ai.report_renderer import render_ai_report_readable
from ui.pages.analysis.ai.user_rules import render_user_rules_section


# ========================================================
# AI Engine (Fail-safe)
# ========================================================

ai_import_error = None
ai_engine_module = None
AI_ENGINE_OK = False
AI_ENGINE_VERSION = "unknown"
ai_engine_path = None

try:
    import ai_engine as ai_engine_module
    AI_ENGINE_VERSION = getattr(ai_engine_module, "AI_ENGINE_VERSION", "unknown")
    ai_engine_path = getattr(ai_engine_module, "__file__", None)

    required = [
        "generate_ai_report",
        "run_stress_test",
        "save_user_rule",
        "load_user_rules",
    ]
    missing = [fn for fn in required if not hasattr(ai_engine_module, fn)]
    if missing:
        raise ImportError(f"ai_engine missing functions: {missing}")

    generate_ai_report = ai_engine_module.generate_ai_report
    save_user_rule = ai_engine_module.save_user_rule
    load_user_rules = ai_engine_module.load_user_rules
    run_stress_test = ai_engine_module.run_stress_test

    AI_ENGINE_OK = True

except Exception:
    ai_import_error = traceback.format_exc()
    AI_ENGINE_OK = False

    def generate_ai_report(symbol, timeframe="1d"):
        return {"__error__": "AI Engine import failed", "__trace__": ai_import_error}

    def save_user_rule(rule_text: str, title: str = None, enabled: int = 1):
        return {"ok": False, "reason": "AI Engine missing", "trace": ai_import_error}

    def load_user_rules(enabled_only=True, max_rows=50):
        return []

    def run_stress_test(v, df):
        return {"scenarios": [], "insight": ""}


def ai_self_test():
    info = {
        "ok": bool(AI_ENGINE_OK),
        "version": AI_ENGINE_VERSION,
        "path": ai_engine_path,
        "import_error": ai_import_error if not AI_ENGINE_OK else "",
        "functions": {},
    }
    try:
        if AI_ENGINE_OK and ai_engine_module:
            for fn in ["generate_ai_report", "run_stress_test", "save_user_rule", "load_user_rules"]:
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


def _clear_ai_cache_for_symbol(symbol: str):
    cache = st.session_state.get("_ai_rep_cache", {})
    for k in list(cache.keys()):
        if k.startswith(f"{symbol}|"):
            del cache[k]
    st.session_state["_ai_rep_cache"] = cache


def render_ai_tab(symbol: str, ai_tf_default_label: str = "يومي (1D)"):
    symk = _sym_key(symbol)
    tf_map = {"يومي (1D)": "1d", "أسبوعي (1W)": "1wk", "شهري (1M)": "1mo"}

    top1, top2, top3, top4 = st.columns([1.2, 1.8, 1.4, 1.0])
    labels = list(tf_map.keys())
    try:
        idx_default = labels.index(ai_tf_default_label)
    except Exception:
        idx_default = 0

    ai_tf_label = top1.selectbox("الفاصل الزمني", labels, index=idx_default, key=f"ai_tf_{symk}")
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
            st.success("AI: OK")
        else:
            st.error("AI: Error")

    if st.button("🔄 تحديث المستشار", key=f"ai_refresh_{symk}"):
        _clear_ai_cache_for_symbol(symbol)
        st.rerun()

    # cache report per (symbol|timeframe)
    cache = st.session_state.setdefault("_ai_rep_cache", {})
    cache_key = f"{symbol}|{ai_tf}"

    if cache_key in cache:
        rep = cache[cache_key]
    else:
        with st.spinner("جاري توليد تقرير المستشار..."):
            rep = _generate_ai_report_flex(symbol, timeframe=ai_tf)

        # لا نخزن لو فيه خطأ
        if not (isinstance(rep, dict) and (rep.get("__error__") or rep.get("__trace__"))):
            cache[cache_key] = rep

    # -----------------------
    # 1) عرض التقرير (من ملف مستقل)
    # -----------------------
    if view_mode == "بطاقات (Osoli)":
        try:
            render_osoli_report(rep, title=f"🤖 تقرير المستشار | {ai_tf_label}")
        except Exception:
            render_ai_report_readable(
                rep,
                ai_engine_version=AI_ENGINE_VERSION,
                ai_self_test_fn=ai_self_test,
                show_debug=False,
                compact=False
            )
    else:
        render_ai_report_readable(
            rep,
            ai_engine_version=AI_ENGINE_VERSION,
            ai_self_test_fn=ai_self_test,
            show_debug=(view_mode == "مطور (مع JSON)"),
            compact=(view_mode == "مبسط")
        )

    st.markdown("---")

    # -----------------------
    # 2) قواعد المستخدم (من ملف مستقل)
    # -----------------------
    render_user_rules_section(
        symbol=symbol,
        symk=symk,
        save_user_rule_fn=save_user_rule,
        load_user_rules_fn=load_user_rules,
        clear_cache_fn=_clear_ai_cache_for_symbol
    )

    # تشخيص
    with st.expander("🧪 تشخيص المستشار (AI Engine Diagnostics)"):
        st.json(ai_self_test())
        if not AI_ENGINE_OK:
            st.warning("المشكلة غالباً داخل ai_engine.py (ImportError/Dependency/NameError).")
