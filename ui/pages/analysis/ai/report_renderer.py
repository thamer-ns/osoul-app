# ui/pages/analysis/ai/report_renderer.py
import streamlit as st
import pandas as pd

from ui.pages.analysis.shared import to_float, safe_list, badge, fmt_price
from ui.pages.analysis.ai.risk_gates import render_risk_gates


def extract_ai(rep: dict) -> dict:
    if not isinstance(rep, dict):
        return {"ok": False, "raw": rep, "error": "AI report is not dict"}

    ex = rep.get("explainability") or {}
    if not isinstance(ex, dict):
        ex = {}

    positives = safe_list(ex.get("positives", rep.get("positives", [])))
    negatives = safe_list(ex.get("negatives", rep.get("negatives", [])))
    notes = safe_list(ex.get("notes", rep.get("notes", [])))

    top_evidence = safe_list(rep.get("top_evidence", positives))
    top_risks = safe_list(rep.get("top_risks", negatives))

    risk_gates = rep.get("risk_gates", {})
    if not isinstance(risk_gates, dict):
        risk_gates = {}

    scenarios = rep.get("scenarios", [])
    if not isinstance(scenarios, list):
        scenarios = []

    score = rep.get("score", rep.get("osoli_score", None))
    score = int(to_float(score, 0) or 0)
    score = max(0, min(100, score))

    conf = rep.get("confidence", rep.get("conf", None))
    conf = int(to_float(conf, 0) or 0)
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
    items = safe_list(items)
    if not items:
        st.caption(empty_text)
        return
    for x in items[:limit]:
        st.write(f"{icon} {x}")


def _render_targets(targets):
    targets = safe_list(targets)
    if not targets:
        st.info("لا توجد أهداف جاهزة حالياً.")
        return

    rows = []
    for t in targets[:8]:
        if isinstance(t, dict):
            rows.append({
                "الهدف": t.get("name") or t.get("label") or "Target",
                "السعر": fmt_price(t.get("price") or t.get("value")),
                "ملاحظة": t.get("note") or ""
            })
        else:
            rows.append({"الهدف": "Target", "السعر": fmt_price(t), "ملاحظة": ""})

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
        st.metric("منطقة الدخول", fmt_price(entry_zone))
    with c3:
        st.metric("وقف الخسارة", fmt_price(stop))
    with c4:
        st.metric("إبطال الفكرة", fmt_price(inv))

    c5, c6, c7 = st.columns(3)
    with c5:
        st.metric("R:R", f"{to_float(rr, 0):.2f}" if rr is not None else "—")
    with c6:
        st.metric("Support", fmt_price(sup))
    with c7:
        st.metric("Resistance", fmt_price(res))


def _render_scenarios(scenarios):
    scenarios = safe_list(scenarios)
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
            e = to_float(entry, None)
            s = to_float(stop, None)
            tg = to_float(t1, None)
            if e is not None and s is not None and tg is not None and (e - s) != 0:
                rr = (tg - e) / (e - s)
                badge(f"R:R {rr:.2f}", "success" if rr >= 1.5 else "warning" if rr >= 1.0 else "danger")
            else:
                badge("سيناريو", "neutral")

        cA, cB, cC, cD = st.columns(4)
        cA.metric("الدخول", fmt_price(entry))
        cB.metric("وقف الخسارة", fmt_price(stop))
        cC.metric("الهدف 1", fmt_price(t1))
        cD.metric("الهدف 2", fmt_price(t2) if t2 is not None else "—")

        if t_list:
            st.caption("🎯 أهداف إضافية:")
            st.write([fmt_price(x.get("price") if isinstance(x, dict) else x) for x in t_list[:8]])

        if note:
            st.caption(f"📝 ملاحظة: {note}")

        st.markdown("</div>", unsafe_allow_html=True)


def render_ai_report_readable(
    rep: dict,
    ai_engine_version: str,
    ai_self_test_fn,
    show_debug: bool = False,
    compact: bool = False,
):
    # حالة خطأ محرك AI
    if isinstance(rep, dict) and (rep.get("__error__") or rep.get("__trace__")):
        st.error("⚠️ المستشار لم يعمل.")
        st.write(rep.get("__error__", "Unknown AI error"))
        with st.expander("📌 تفاصيل الخطأ (Trace)"):
            st.code(rep.get("__trace__", ""), language="text")
        with st.expander("🧪 تشخيص AI Engine"):
            st.json(ai_self_test_fn())
        return

    data = extract_ai(rep)
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
        badge(
            f"Score {data['score']}/100",
            "success" if data["score"] >= 70 else "warning" if data["score"] >= 40 else "danger"
        )
    with c2:
        conf = data["confidence"]
        label = data["confidence_label"]
        badge(
            f"{label} ({conf}%)",
            "success" if conf >= 70 else "warning" if conf >= 40 else "danger"
        )
    with c3:
        st.progress(data["confidence"])

    if data.get("summary_text"):
        st.markdown("### 🧾 سبب التوصية")
        st.code(str(data["summary_text"]).strip(), language="text")

    if any([data.get("entry"), data.get("risk"), data.get("levels"), data.get("targets")]):
        _render_entry_risk_levels(
            data.get("entry") or {},
            data.get("risk") or {},
            data.get("levels") or {},
            data.get("score") or 0
        )
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
    render_risk_gates(data["risk_gates"])

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
