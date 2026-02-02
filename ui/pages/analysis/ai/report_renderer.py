# ui/pages/analysis/ai/report_renderer.py
import streamlit as st

from ui.pages.analysis.ai.entry_risk import render_entry_risk_levels
from ui.pages.analysis.ai.targets import render_targets
from ui.pages.analysis.ai.scenarios import render_scenarios
from ui.pages.analysis.shared import badge


def _to_float(x, default=None):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def _safe_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return [i for i in x if i is not None and str(i).strip() != ""]
    return [x]


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

    score = rep.get("score", rep.get("osoli_score", 0))
    score = int(_to_float(score, 0) or 0)
    score = max(0, min(100, score))

    conf = rep.get("confidence", rep.get("conf", 0))
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


def _render_bullets(title, items, icon="•", limit=8, empty_text="لا يوجد"):
    st.markdown(f"**{title}**")
    items = _safe_list(items)
    if not items:
        st.caption(empty_text)
        return
    for x in items[:limit]:
        st.write(f"{icon} {x}")


def _render_risk_gates(risk_gates: dict):
    if not isinstance(risk_gates, dict) or not risk_gates:
        st.info("لا توجد بوابات مخاطر حالياً.")
        return

    passed = bool(risk_gates.get("pass", False))
    reasons = _safe_list(risk_gates.get("reasons", []))

    c1, c2 = st.columns([1, 3])
    with c1:
        badge("✅ اجتاز" if passed else "❌ لم يجتز", "success" if passed else "danger")
    with c2:
        if reasons:
            st.markdown("**الأسباب:**")
            for r in reasons[:12]:
                st.write(f"- {r}")
        else:
            st.caption("لا توجد أسباب مسجلة.")


def render_ai_report_readable(
    rep: dict,
    ai_engine_version: str = "unknown",
    ai_self_test_fn=None,
    show_debug: bool = False,
    compact: bool = False,
):
    # أخطاء المستشار
    if isinstance(rep, dict) and (rep.get("__error__") or rep.get("__trace__")):
        st.error("⚠️ المستشار لم يعمل.")
        st.write(rep.get("__error__", "Unknown AI error"))
        with st.expander("📌 تفاصيل الخطأ (Trace)"):
            st.code(rep.get("__trace__", ""), language="text")
        if callable(ai_self_test_fn):
            with st.expander("🧪 تشخيص AI Engine"):
                st.json(ai_self_test_fn())
        return

    data = _extract_ai(rep)
    if not data.get("ok"):
        st.warning("⚠️ تقرير المستشار غير صالح.")
        st.write(data.get("raw"))
        return

    st.caption(f"🧩 AI Engine v{ai_engine_version}")

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
        badge(f"Score {data['score']}/100", "success" if data["score"] >= 70 else "warning" if data["score"] >= 40 else "danger")
    with c2:
        conf = data["confidence"]
        label = data["confidence_label"]
        badge(f"{label} ({conf}%)", "success" if conf >= 70 else "warning" if conf >= 40 else "danger")
    with c3:
        st.progress(data["confidence"])

    if data.get("summary_text"):
        st.markdown("### 🧾 سبب التوصية")
        st.code(str(data["summary_text"]).strip(), language="text")

    if any([data.get("entry"), data.get("risk"), data.get("levels"), data.get("targets")]):
        render_entry_risk_levels(data.get("entry") or {}, data.get("risk") or {}, data.get("levels") or {}, data.get("score") or 0)
        st.markdown("### 🎯 الأهداف")
        render_targets(data.get("targets") or [])

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
    render_scenarios(data["scenarios"])

    notes = data.get("notes", [])
    if notes:
        with st.expander("🧾 ملاحظات إضافية"):
            for x in notes[:25]:
                st.write(f"- {x}")

    if show_debug:
        with st.expander("🧩 عرض التقرير الخام (JSON)"):
            st.json(data["raw"])
