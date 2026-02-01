# ui/pages/analysis/ai_tab.py
import streamlit as st
import pandas as pd
import traceback
import inspect

from components import render_osoli_report
from ui.common import sym_key as _sym_key

from ui.pages.analysis.shared import (
    to_float, safe_list, badge, fmt_price
)


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
    save_user_rule = ai_engine_module.save_user_rule
    load_user_rules = ai_engine_module.load_user_rules
    run_stress_test = ai_engine_module.run_stress_test  # للتبويب الرئيسي إن احتجناه

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


def _extract_ai(rep: dict) -> dict:
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


def _render_risk_gates(risk_gates: dict):
    if not isinstance(risk_gates, dict) or not risk_gates:
        st.info("لا توجد بوابات مخاطر حالياً.")
        return

    passed = bool(risk_gates.get("pass", False))
    reasons = safe_list(risk_gates.get("reasons", []))

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


def _render_ai_report_readable(rep: dict, show_debug=False, compact=False):
    if isinstance(rep, dict) and (rep.get("__error__") or rep.get("__trace__")):
        st.error("⚠️ المستشار لم يعمل.")
        st.write(rep.get("__error__", "Unknown AI error"))
        with st.expander("📌 تفاصيل الخطأ (Trace)"):
            st.code(rep.get("__trace__", ""), language="text")
        with st.expander("🧪 تشخيص AI Engine"):
            st.json(ai_self_test())
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
            badge("AI: OK", "success")
        else:
            badge("AI: Error", "danger")

    if st.button("🔄 تحديث المستشار", key=f"ai_refresh_{symk}"):
        cache = st.session_state.get("_ai_rep_cache", {})
        for k in list(cache.keys()):
            if k.startswith(f"{symbol}|"):
                del cache[k]
        st.session_state["_ai_rep_cache"] = cache
        st.rerun()

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
                    if k.startswith(f"{symbol}|"):
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
        st.json(ai_self_test())
        if not AI_ENGINE_OK:
            st.warning("المشكلة غالباً داخل ai_engine.py (ImportError/Dependency/NameError).")
