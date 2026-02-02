# ui/pages/analysis/tabs/ai.py
import traceback
import streamlit as st

from ui.common import sym_key as _sym_key
from components import render_osoli_report

# Fail-safe import for ai_engine
AI_ENGINE_OK = False
ai_import_error = ""

try:
    import ai_engine as ai_engine_module

    required = [
        "generate_ai_report",
        "save_user_rule",
        "load_user_rules",
    ]
    missing = [fn for fn in required if not hasattr(ai_engine_module, fn)]
    if missing:
        raise ImportError(f"ai_engine missing functions: {missing}")

    generate_ai_report = ai_engine_module.generate_ai_report
    save_user_rule = ai_engine_module.save_user_rule
    load_user_rules = ai_engine_module.load_user_rules
    AI_ENGINE_OK = True

except Exception:
    AI_ENGINE_OK = False
    ai_import_error = traceback.format_exc()

    def generate_ai_report(symbol, timeframe="1d"):
        return {"__error__": "AI Engine import failed", "__trace__": ai_import_error}

    def save_user_rule(rule_text: str, title: str = None, enabled: int = 1):
        return {"ok": False, "reason": "AI Engine missing", "trace": ai_import_error}

    def load_user_rules(enabled_only=True, max_rows=50):
        return []


def _ai_timeframe_normalize(tf: str) -> str:
    t = (tf or "").strip().lower()
    if not t:
        return "1d"
    mapping = {
        "1d": "1d", "daily": "1d", "day": "1d",
        "1wk": "1wk", "1w": "1wk", "weekly": "1wk", "week": "1wk",
        "1mo": "1mo", "monthly": "1mo", "month": "1mo",
    }
    return mapping.get(t, t)


def render_tab(symbol: str, fin: dict, company_name: str = "", sector: str = ""):
    symk = _sym_key(symbol)

    tf_map = {"يومي (1D)": "1d", "أسبوعي (1W)": "1wk", "شهري (1M)": "1mo"}
    top1, top2, top3 = st.columns([1.2, 1.8, 1.0])

    ai_tf_label = top1.selectbox("الفاصل الزمني", list(tf_map.keys()), index=0, key=f"ai_tf_{symk}")
    ai_tf = _ai_timeframe_normalize(tf_map[ai_tf_label])

    view_mode = top2.radio(
        "طريقة العرض",
        ["بطاقات (Osoli)", "JSON"],
        horizontal=True,
        key=f"ai_view_{symk}",
    )
    top3.caption("AI OK ✅" if AI_ENGINE_OK else "AI Error ❌")

    # كاش بسيط
    cache = st.session_state.setdefault("_ai_rep_cache", {})
    cache_key = f"{symbol}|{ai_tf}"

    if st.button("🔄 تحديث المستشار", key=f"ai_refresh_{symk}"):
        cache.pop(cache_key, None)
        st.rerun()

    rep = cache.get(cache_key)
    if rep is None:
        with st.spinner("جاري توليد تقرير المستشار..."):
            try:
                rep = generate_ai_report(symbol, timeframe=ai_tf)
            except TypeError:
                rep = generate_ai_report(symbol, ai_tf)
            except Exception:
                rep = {"__error__": "AI report failed", "__trace__": traceback.format_exc()}

        # لا نكاشي الأخطاء
        if not (isinstance(rep, dict) and (rep.get("__error__") or rep.get("__trace__"))):
            cache[cache_key] = rep

    # عرض الأخطاء بشكل واضح
    if isinstance(rep, dict) and (rep.get("__error__") or rep.get("__trace__")):
        st.error("⚠️ المستشار لم يعمل.")
        st.write(rep.get("__error__", "Unknown AI error"))
        with st.expander("📌 تفاصيل الخطأ (Trace)"):
            st.code(rep.get("__trace__", ""), language="text")
        return

    if view_mode == "بطاقات (Osoli)":
        try:
            render_osoli_report(rep, title=f"🤖 تقرير المستشار | {ai_tf_label}")
        except Exception:
            st.warning("تعذر عرض البطاقات — سأعرض JSON.")
            st.json(rep)
    else:
        st.json(rep)

    st.divider()
    st.subheader("🧠 استراتيجياتي الخاصة")
    st.caption("اكتب قواعدك بصيغة بسيطة مثل: (RSI فوق 70) أو (اختراق مقاومة + حجم مرتفع)")

    rule_text = st.text_area("✍️ أدخل الاستراتيجية", key=f"user_rule_text_{symk}", height=110)
    c1, c2 = st.columns([1, 2])

    with c1:
        if st.button("💾 حفظ الاستراتيجية", key=f"save_rule_{symk}", type="primary"):
            if not rule_text.strip():
                st.warning("اكتب القاعدة أولاً.")
            else:
                res = save_user_rule(rule_text, title="قاعدة من المستخدم", enabled=1)
                if isinstance(res, dict) and res.get("ok"):
                    st.success("✅ تم حفظ الاستراتيجية")
                else:
                    st.error(f"لم يتم الحفظ: {res.get('reason','') if isinstance(res, dict) else ''}")
                    if isinstance(res, dict) and res.get("trace"):
                        with st.expander("Trace"):
                            st.code(res.get("trace"), language="text")

    with st.expander("📌 عرض آخر الاستراتيجيات المحفوظة"):
        rules = load_user_rules(enabled_only=True, max_rows=10) or []
        if rules:
            for r in rules:
                title = (r.get("title") if isinstance(r, dict) else "") or "قاعدة"
                txt = (r.get("rule_text") if isinstance(r, dict) else "") or ""
                st.write(f"- **{title}**: {txt}")
        else:
            st.info("لا توجد قواعد محفوظة بعد.")
