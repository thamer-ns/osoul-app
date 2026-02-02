# ui/pages/analysis/ai/ai_tab.py
import streamlit as st

from ui.pages.analysis.ai.controls import render_ai_controls
from ui.pages.analysis.ai.cache import clear_symbol, get_or_generate
from ui.pages.analysis.ai.report_renderer import render_ai_report_readable
from ui.pages.analysis.ai.user_rules import render_user_rules_panel


def _resolve_deps():
    """
    يحاول يجيب الدوال من المكان الحالي (views_impl) بدون ما يسبب كسر،
    عشان نضمن توافق المرحلة الانتقالية.
    """
    deps = {
        "AI_ENGINE_OK": False,
        "AI_ENGINE_VERSION": "unknown",
        "_ai_self_test": lambda: {"ok": False, "reason": "self_test missing"},
        "_generate_ai_report_flex": None,
        "save_user_rule": None,
        "load_user_rules": None,
        "render_osoli_report": None,
    }

    try:
        import views_impl as v
        deps["AI_ENGINE_OK"] = bool(getattr(v, "AI_ENGINE_OK", False))
        deps["AI_ENGINE_VERSION"] = getattr(v, "AI_ENGINE_VERSION", "unknown")
        deps["_ai_self_test"] = getattr(v, "_ai_self_test", deps["_ai_self_test"])
        deps["_generate_ai_report_flex"] = getattr(v, "_generate_ai_report_flex", None)
        deps["save_user_rule"] = getattr(v, "save_user_rule", None)
        deps["load_user_rules"] = getattr(v, "load_user_rules", None)
        deps["render_osoli_report"] = getattr(v, "render_osoli_report", None)
    except Exception:
        pass

    return deps


def _gen_report_call(gen_fn, symbol: str, tf: str):
    """
    مرن: يدعم اختلاف التواقيع (keyword/positional/no args).
    """
    if not callable(gen_fn):
        return {"__error__": "AI generator missing", "__trace__": "No generate function", "symbol": symbol, "timeframe": tf}

    try:
        try:
            return gen_fn(symbol, timeframe=tf)
        except TypeError:
            try:
                return gen_fn(symbol, tf)
            except TypeError:
                return gen_fn(symbol)
    except Exception as e:
        return {"__error__": str(e), "__trace__": "generator failed", "symbol": symbol, "timeframe": tf}


def render_ai_tab(symbol: str):
    """
    Main AI tab renderer.
    Controls + cache + report renderer + user rules.
    """
    deps = _resolve_deps()

    # Controls
    ctl = render_ai_controls(symbol, deps["AI_ENGINE_OK"])

    # Refresh => clear cache for this symbol
    if ctl.get("refresh"):
        clear_symbol(symbol)
        st.rerun()

    tf = ctl.get("tf", "1d")
    view_mode = ctl.get("view_mode", "تفصيلي")

    # Get report (cached)
    def _generator():
        return _gen_report_call(deps["_generate_ai_report_flex"], symbol, tf)

    rep = get_or_generate(symbol, tf, _generator)

    # View modes
    if view_mode == "مبسط":
        render_ai_report_readable(
            rep,
            ai_engine_version=deps["AI_ENGINE_VERSION"],
            ai_self_test_fn=deps["_ai_self_test"],
            show_debug=False,
            compact=True,
        )
    elif view_mode == "تفصيلي":
        render_ai_report_readable(
            rep,
            ai_engine_version=deps["AI_ENGINE_VERSION"],
            ai_self_test_fn=deps["_ai_self_test"],
            show_debug=False,
            compact=False,
        )
    elif view_mode == "بطاقات (Osoli)":
        ok_cards = False
        if callable(deps.get("render_osoli_report")):
            try:
                deps["render_osoli_report"](rep, title=f"🤖 تقرير المستشار | {ctl.get('tf_label','')}")
                ok_cards = True
            except Exception:
                ok_cards = False

        if not ok_cards:
            render_ai_report_readable(
                rep,
                ai_engine_version=deps["AI_ENGINE_VERSION"],
                ai_self_test_fn=deps["_ai_self_test"],
                show_debug=False,
                compact=False,
            )
    else:
        # مطور
        render_ai_report_readable(
            rep,
            ai_engine_version=deps["AI_ENGINE_VERSION"],
            ai_self_test_fn=deps["_ai_self_test"],
            show_debug=True,
            compact=False,
        )

    st.markdown("---")

    # User Rules (منفصلة)
    def _on_saved():
        clear_symbol(symbol)  # عشان يعيد توليد التقرير بعد إضافة قاعدة جديدة

    render_user_rules_panel(
        symbol=symbol,
        save_user_rule_fn=deps.get("save_user_rule"),
        load_user_rules_fn=deps.get("load_user_rules"),
        on_saved=_on_saved,
    )

    with st.expander("🧪 تشخيص المستشار (AI Engine Diagnostics)"):
        st.json(deps["_ai_self_test"]())
        if not deps["AI_ENGINE_OK"]:
            st.warning("المشكلة غالباً داخل ai_engine.py (ImportError/Dependency/NameError).")
            st.info("أرسل لي نص الخطأ الموجود هنا وسأصلح ai_engine.py لك مباشرة.")
