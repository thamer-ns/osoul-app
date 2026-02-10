#views/analysis/advisor.py
import streamlit as st
from datetime import datetime

from views.shared import (
    _sym_key,
    _generate_ai_report_flex,
    _render_ai_report_readable,
    render_osoli_report,
    save_user_rule,
    load_user_rules,
)

# (اختياري) لو كانت موجودة في shared.py
try:
    from views.shared import _extract_ai  # type: ignore
except Exception:
    _extract_ai = None


def _as_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return [i for i in x if i is not None and str(i).strip() != ""]
    return [x]


def _ai_quick_parse(rep) -> dict:
    """
    استخراج سريع بدون تغيير منطق المحرك.
    الهدف: تحسين العرض + ضمان ظهور التفاصيل.
    """
    if _extract_ai:
        try:
            return _extract_ai(rep) or {}
        except Exception:
            pass

    # fallback بسيط
    if not isinstance(rep, dict):
        return {"ok": False, "raw": rep, "error": "AI report not dict"}

    if rep.get("__error__"):
        return {"ok": False, "raw": rep, "error": rep.get("__error__")}

    score = rep.get("score", rep.get("osoli_score", 0)) or 0
    conf = rep.get("confidence", rep.get("conf", 0)) or 0
    rec = rep.get("recommendation") or rep.get("action") or "—"
    strat = rep.get("strategy") or rep.get("strategy_name") or rep.get("model") or "—"

    ex = rep.get("explainability") if isinstance(rep.get("explainability"), dict) else {}
    positives = _as_list(ex.get("positives", rep.get("positives", [])))
    negatives = _as_list(ex.get("negatives", rep.get("negatives", [])))
    scenarios = rep.get("scenarios", []) if isinstance(rep.get("scenarios", []), list) else []
    risk_gates = rep.get("risk_gates", {}) if isinstance(rep.get("risk_gates", {}), dict) else {}

    return {
        "ok": True,
        "score": int(score) if str(score).replace(".", "", 1).isdigit() else score,
        "confidence": int(conf) if str(conf).replace(".", "", 1).isdigit() else conf,
        "recommendation": rec,
        "strategy": strat,
        "top_evidence": positives,
        "top_risks": negatives,
        "risk_gates": risk_gates,
        "scenarios": scenarios,
        "engine_meta": rep.get("engine_meta") if isinstance(rep.get("engine_meta"), dict) else {},
        "raw": rep,
    }


def _tone_for_score(score: int) -> str:
    try:
        s = int(score)
    except Exception:
        return "neutral"
    if s >= 70:
        return "success"
    if s >= 40:
        return "warning"
    return "danger"


def _tone_for_conf(conf: int) -> str:
    try:
        c = int(conf)
    except Exception:
        return "neutral"
    if c >= 70:
        return "success"
    if c >= 40:
        return "warning"
    return "danger"


def _chip(text: str, tone: str = "neutral"):
    cls = {
        "success": "os-chip-green",
        "warning": "os-chip-amber",
        "danger": "os-chip-red",
        "blue": "os-chip-blue",
        "neutral": "os-chip-gray",
    }.get(tone, "os-chip-gray")

    st.markdown(
        f'<span class="os-chip {cls}"><span class="mi">check_circle</span>{text}</span>',
        unsafe_allow_html=True,
    )


def _render_quick_summary(sym: str, ai_data: dict, tf_label: str):
    """
    هيدر سريع: توصية + استراتيجية + Score + Confidence
    (لا يغيّر أي شيء في الحسابات)
    """
    if not ai_data.get("ok"):
        return

    rec = str(ai_data.get("recommendation", "—"))
    strat = str(ai_data.get("strategy", "—"))
    score = ai_data.get("score", 0)
    conf = ai_data.get("confidence", 0)

    c1, c2 = st.columns([2.2, 1.8])
    with c1:
        st.markdown(
            f"""
            <div class="os-card">
              <div class="os-card-title">🤖 ملخص المستشار</div>
              <div style="font-weight:950;font-size:1.15rem;margin:8px 0 2px 0;">{rec}</div>
              <div class="os-muted">الاستراتيجية: {strat} • الفاصل: {tf_label} • الرمز: <span style="direction:ltr;display:inline-block">{sym}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="os-card">
              <div class="os-card-title">📌 أرقام سريعة</div>
              <div class="os-kv"><div class="os-k">Score</div><div class="os-v">{score}/100</div></div>
              <div class="os-kv"><div class="os-k">الثقة</div><div class="os-v">{conf}%</div></div>
              <div class="os-kv"><div class="os-k">تحديث</div><div class="os-v">{st.session_state.get("_ai_last_update", "—")}</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Chips row
    st.markdown("<div class='os-card' style='padding:12px;margin-top:10px;'>", unsafe_allow_html=True)
    _chip(f"Score {score}/100", _tone_for_score(score))
    _chip(f"الثقة {conf}%", _tone_for_conf(conf))
    st.markdown(
        "<span class='os-chip os-chip-blue'><span class='mi'>insights</span>تأكد من الأدلة/المخاطر قبل القرار</span>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_evidence_risks(ai_data: dict, compact: bool = False):
    # Dedup مع الحفاظ على الترتيب لتقليل التكرارات وإظهار المعلومة بوضوح
    def _dedup(xs: list) -> list:
        out, seen = [], set()
        for it in xs:
            s = str(it).strip()
            if not s:
                continue
            key = s.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        return out

    ev = _dedup(_as_list(ai_data.get("top_evidence", [])))
    rk = _dedup(_as_list(ai_data.get("top_risks", [])))
    lim = 4 if compact else 10

    a, b = st.columns(2)
    with a:
        st.markdown("<div class='os-card'>", unsafe_allow_html=True)
        st.markdown("<div class='os-card-title'>✅ أقوى الأدلة</div>", unsafe_allow_html=True)
        if not ev:
            st.caption("لا توجد أدلة مسجلة.")
        else:
            st.markdown("\n".join([f"- ✅ {x}" for x in ev[:lim]]))
        st.markdown("</div>", unsafe_allow_html=True)

    with b:
        st.markdown("<div class='os-card'>", unsafe_allow_html=True)
        st.markdown("<div class='os-card-title'>⚠️ أكبر المخاطر</div>", unsafe_allow_html=True)
        if not rk:
            st.caption("لا توجد مخاطر مسجلة.")
        else:
            st.markdown("\n".join([f"- ⚠️ {x}" for x in rk[:lim]]))
        st.markdown("</div>", unsafe_allow_html=True)


def _render_scenarios(ai_data: dict):
    scenarios = ai_data.get("scenarios", [])
    if not isinstance(scenarios, list):
        scenarios = []

    if not scenarios:
        st.info("لا توجد سيناريوهات جاهزة حالياً.")
        return

    st.markdown("<div class='os-card'>", unsafe_allow_html=True)
    st.markdown("<div class='os-card-title'>🧭 السيناريوهات</div>", unsafe_allow_html=True)
    st.caption("عرض السيناريوهات كما هي من المحرك—مع تحسين التنسيق فقط.")

    for i, sc in enumerate(scenarios[:12], start=1):
        if not isinstance(sc, dict):
            continue

        name = sc.get("name", f"سيناريو {i}")
        trigger = sc.get("trigger") or sc.get("condition") or "—"
        entry = sc.get("entry", "—")
        stop = sc.get("stop") or sc.get("sl") or "—"
        t1 = sc.get("target1") or sc.get("target") or sc.get("tp1") or "—"
        t2 = sc.get("target2") or sc.get("tp2") or "—"
        note = sc.get("note", "")

        st.markdown(
            f"""
            <div style="border:1px solid rgba(15,23,42,0.10);border-radius:14px;padding:12px;margin:10px 0;background:#fff;">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
                <div style="font-weight:950">{name}</div>
                <div class="os-chip os-chip-gray"><span class="mi">flag</span>{trigger}</div>
              </div>
              <div style="margin-top:8px;display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">
                <div class="os-card" style="padding:10px"><div class="os-muted">الدخول</div><div class="os-v">{entry}</div></div>
                <div class="os-card" style="padding:10px"><div class="os-muted">وقف الخسارة</div><div class="os-v">{stop}</div></div>
                <div class="os-card" style="padding:10px"><div class="os-muted">الهدف 1</div><div class="os-v">{t1}</div></div>
                <div class="os-card" style="padding:10px"><div class="os-muted">الهدف 2</div><div class="os-v">{t2}</div></div>
              </div>
              {f"<div class='os-muted' style='margin-top:8px'>📝 {note}</div>" if note else ""}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)


def _render_risk_gates(ai_data: dict):
    gates = ai_data.get("risk_gates", {})
    if not isinstance(gates, dict) or not gates:
        st.info("لا توجد بوابات مخاطر حالياً.")
        return

    passed = bool(gates.get("pass", False))
    reasons = _as_list(gates.get("reasons", []))

    st.markdown("<div class='os-card'>", unsafe_allow_html=True)
    st.markdown("<div class='os-card-title'>🛡️ بوابات المخاطر</div>", unsafe_allow_html=True)
    if passed:
        _chip("اجتاز البوابات", "success")
    else:
        _chip("لم يجتز البوابات", "danger")

    if reasons:
        st.markdown("**الأسباب:**")
        for r in reasons[:20]:
            st.write(f"- {r}")
    else:
        st.caption("لا توجد أسباب مسجلة.")

    st.markdown("</div>", unsafe_allow_html=True)


def render_advisor_tab(sym: str):
    symk = _sym_key(sym)

    # نخلي القيم تدعم محركك (shared.py يحوّلها لاحقاً)
    tf_map = {"يومي (1D)": "1d", "أسبوعي (1W)": "1wk", "شهري (1M)": "1mo"}

    # --------------------------------------------------------
    # Controls (محسّنة بصرياً بدون تغيير المنطق)
    # --------------------------------------------------------
    st.markdown("### 🤖 المستشار الذكي")
    c1, c2, c3, c4 = st.columns([1.1, 1.6, 1.7, 0.9])

    ai_tf_label = c1.selectbox("الفاصل الزمني", list(tf_map.keys()), index=0, key=f"ai_tf_{symk}")
    ai_tf = tf_map[ai_tf_label]

    view_mode = c2.selectbox(
        "طريقة العرض",
        ["مبسط", "تفصيلي", "بطاقات (Osoli)", "مطور (مع JSON)"],
        index=0,
        key=f"ai_view_{symk}",
    )
    compact = (view_mode == "مبسط")

    c3.caption("مبسط=مختصر • تفصيلي=كامل • بطاقات=واجهة أصولي • مطور=مع JSON")

    if c4.button("🔄 تحديث", key=f"ai_refresh_{symk}"):
        cache = st.session_state.get("_ai_rep_cache", {})
        for k in list(cache.keys()):
            if k.startswith(f"{sym}|"):
                del cache[k]
        st.session_state["_ai_rep_cache"] = cache
        st.rerun()

    # --------------------------------------------------------
    # Cache (كما هو)
    # --------------------------------------------------------
    cache = st.session_state.setdefault("_ai_rep_cache", {})
    cache_key = f"{sym}|{ai_tf}"

    if cache_key in cache:
        rep = cache[cache_key]
    else:
        with st.spinner("جاري توليد تقرير المستشار..."):
            rep = _generate_ai_report_flex(sym, timeframe=ai_tf)
        cache[cache_key] = rep

    st.session_state["_ai_last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    # --------------------------------------------------------
    # Error handling (كما هو)
    # --------------------------------------------------------
    if isinstance(rep, dict) and (rep.get("__error__") or rep.get("__trace__")):
        st.error("فشل تشغيل المستشار (AI Engine).")
        st.code(rep.get("__trace__", ""))
        st.warning("سأكمل عرض بقية التبويبات (مالي/فني/كلاسيكي).")
        return

    # --------------------------------------------------------
    # ✅ UI: Quick summary + evidence/risks + scenarios/gates
    # (لا يحذف العرض القديم، فقط يضيف فوقه)
    # --------------------------------------------------------
    ai_data = _ai_quick_parse(rep)
    _render_quick_summary(sym, ai_data, ai_tf_label)
    _render_evidence_risks(ai_data, compact=compact)

    # --------------------------------------------------------
    # Existing render modes (موجودة كما هي)
    # --------------------------------------------------------
    st.markdown("---")
    st.markdown("### 🧾 التقرير التفصيلي")
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

    # --------------------------------------------------------
    # Extra: Scenarios & Risk gates (تحسين عرض + لا حذف)
    # --------------------------------------------------------
    st.markdown("---")
    st.markdown("### 🧭 إضافات منظمة")
    _render_risk_gates(ai_data)
    _render_scenarios(ai_data)

    # --------------------------------------------------------
    # User rules (كما هو + تحسين ترتيب)
    # --------------------------------------------------------
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

    with col2:
        st.markdown(
            """
            <div class="os-card" style="padding:14px;">
              <div class="os-card-title">💡 نصيحة سريعة</div>
              <div class="os-muted">
                كلما كانت القاعدة محددة (شرط + تأكيد + إدارة مخاطرة) كان تطبيقها أدق.
                مثال: "اختراق مقاومة + حجم أعلى من المتوسط + وقف تحت الدعم".
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander("📌 عرض آخر الاستراتيجيات المحفوظة"):
        rules = load_user_rules(enabled_only=True, max_rows=20) or []
        if rules:
            for r in rules:
                st.write(f"- **{r.get('title','قاعدة')}**: {r.get('rule_text','')}")
        else:
            st.info("لا توجد قواعد محفوظة بعد.")
