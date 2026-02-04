#views/settings.py
import streamlit as st
from analytics import create_smart_backup
from database import db_healthcheck

def view_tools():
    st.header("🛠️ أدوات")
    st.info("حاسبة الزكاة (قريباً)")

def view_settings():
    st.header("الإعدادات")

    # =====================================================
    # الهوية والشعار (اختياري)
    # - يعرض الشعار إذا كان موجوداً داخل assets/
    # - لا يغيّر أي منطق أو إعدادات، فقط تحسين العرض
    # =====================================================
    try:
        from config import LOGO_FULL_PATH, LOGO_MARK_PATH, LOGO_APP_PATH
        import os

        any_logo = any([
            isinstance(LOGO_FULL_PATH, str) and os.path.exists(LOGO_FULL_PATH),
            isinstance(LOGO_MARK_PATH, str) and os.path.exists(LOGO_MARK_PATH),
            isinstance(LOGO_APP_PATH, str) and os.path.exists(LOGO_APP_PATH),
        ])

        with st.expander("🎨 الهوية والشعار", expanded=False):
            if any_logo:
                cols = st.columns(3)
                with cols[0]:
                    if isinstance(LOGO_FULL_PATH, str) and os.path.exists(LOGO_FULL_PATH):
                        st.caption("logo_full.png")
                        st.image(LOGO_FULL_PATH, use_container_width=True)
                with cols[1]:
                    if isinstance(LOGO_MARK_PATH, str) and os.path.exists(LOGO_MARK_PATH):
                        st.caption("logo_mark.png")
                        st.image(LOGO_MARK_PATH, use_container_width=True)
                with cols[2]:
                    if isinstance(LOGO_APP_PATH, str) and os.path.exists(LOGO_APP_PATH):
                        st.caption("logo_app.png")
                        st.image(LOGO_APP_PATH, use_container_width=True)

                st.info(
                    "ضع ملفات الشعار داخل مجلد assets/ بالأسماء التالية ليتم ربطها تلقائياً: "
                    "logo_full.png و logo_mark.png و logo_app.png"
                )
            else:
                st.warning(
                    "لا يوجد شعار داخل assets/ حالياً. "
                    "إذا رغبت، أنشئ مجلد assets/ وضع داخله: logo_full.png و logo_mark.png و logo_app.png"
                )
    except Exception:
        pass

    if st.button("🔎 تشخيص قاعدة البيانات", key="db_diag"):
        rep = db_healthcheck()
        if not rep.get("connected"):
            st.error("غير متصل بقاعدة البيانات")
        else:
            st.success("✅ اتصال ناجح")
            st.json(rep.get("db", {}))
            st.write("### Counts")
            st.json(rep.get("counts", {}))
            if rep.get("dup_tables"):
                st.error(f"⚠️ يوجد ازدواج جداول: {rep['dup_tables']}")
            else:
                st.success("✅ لا يوجد ازدواج جداول (Case Safe)")

    st.markdown("---")
    if st.button("نسخة احتياطية", key="backup_btn"):
        d, n = create_smart_backup()
        if d:
            st.download_button("تحميل", d, n)
