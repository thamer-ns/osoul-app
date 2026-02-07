from osoli_logging import log_exception
# views/settings.py
import streamlit as st

from analytics import create_smart_backup
from database import db_healthcheck


def view_tools():
    st.header("🛠️ أدوات")
    st.info("حاسبة الزكاة (قريباً)")

    # -------------------------
    # Diagnostics: imports
    # -------------------------
    st.subheader("🔎 التشخيص")
    try:
        from views.shared import get_import_diagnostics
        diag = get_import_diagnostics()
        if diag.get("has_issues"):
            st.warning("تم رصد مشاكل في استيراد بعض الوحدات/الاعتمادات. هذا قد يمنع ظهور بعض الميزات.")
            for k, v in diag.get("issues", {}).items():
                with st.expander(f"تفاصيل: {k}", expanded=False):
                    st.code(v)
        else:
            st.success("✅ لا توجد مشاكل استيراد ظاهرة.")
    except Exception as e:
        st.error(f"تعذر تحميل التشخيص: {e}")

    # -------------------------
    # Diagnostics: AI Engine self-test
    # -------------------------
    st.subheader("🤖 فحص محرك المستشار (AI Engine)")
    st.caption("يفحص توفر الوحدات الأساسية، ثم يمكنك تشغيل تقرير تجريبي على أي رمز للتأكد من سلامة الحسابات.")

    try:
        from ai_engine_core import self_test as _engine_self_test
        if st.button("✅ تشغيل self_test", key="ai_self_test_btn"):
            rep = _engine_self_test()
            if rep.get("ok"):
                st.success("✅ self_test: المحرك يبدو سليمًا.")
            else:
                st.warning("⚠️ self_test: توجد ملاحظات قد تؤثر على النتائج.")
            st.json(rep)
    except Exception as e:
        st.error(f"تعذر تشغيل self_test: {e}")

    with st.expander("🧪 تشغيل تقرير تجريبي (اختياري)", expanded=False):
        sym = st.text_input("رمز للاختبار (مثال: 1120.SR)", value="1120.SR", key="ai_test_symbol")
        tf = st.selectbox("الفاصل", ["1d", "1wk", "1mo"], index=0, key="ai_test_tf")
        if st.button("🚀 توليد تقرير", key="ai_test_run"):
            try:
                from views.shared import _generate_ai_report_flex
                with st.spinner("جاري التوليد..."):
                    rep = _generate_ai_report_flex(sym, timeframe=tf)
                if isinstance(rep, dict) and rep.get("__error__"):
                    st.error("فشل توليد التقرير.")
                    st.code(rep.get("__trace__", ""))
                else:
                    st.success("✅ تم توليد التقرير.")
                    st.json(rep)
            except Exception as e:
                st.error(f"فشل الاختبار: {e}")

    # -------------------------
    # Diagnostics: DB healthcheck
    # -------------------------
    st.subheader("🩺 فحص قاعدة البيانات")
    try:
        ok, details = db_healthcheck()
        if ok:
            st.success("✅ الاتصال بقاعدة البيانات يعمل.")
        else:
            st.warning("⚠️ توجد ملاحظة في قاعدة البيانات.")
        st.json(details)
    except Exception as e:
        st.error(f"تعذر فحص قاعدة البيانات: {e}")

    st.subheader("📦 نسخ احتياطي ذكي")
    if st.button("إنشاء نسخة احتياطية الآن", key="smart_backup_btn"):
        try:
            rep = create_smart_backup()
            st.success("تم إنشاء نسخة احتياطية.")
            st.json(rep)
        except Exception as e:
            st.error(f"فشل النسخ الاحتياطي: {e}")
