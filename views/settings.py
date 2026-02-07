from osoli_logging import log_exception
# views/settings.py

"""Settings & tools pages.

IMPORTANT:
- Do NOT place any Streamlit rendering at module import time.
  Router imports modules eagerly, and any top-level st.* calls will
  "flash" on other pages during reruns.
"""

import os
from pathlib import Path

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
            for k, v in (diag.get("issues", {}) or {}).items():
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
            rep = _engine_self_test() or {}
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
        info = db_healthcheck() or {}
        if not info.get("connected"):
            st.error("❌ لا يوجد اتصال بقاعدة البيانات. تأكد من DATABASE_URL في Secrets/Env.")
        else:
            st.success("✅ الاتصال بقاعدة البيانات يعمل.")
            if info.get("db"):
                st.json(info.get("db", {}))
            with st.expander("Counts", expanded=False):
                st.json(info.get("counts", {}))
            if info.get("dup_tables"):
                st.warning("تم العثور على جداول مكررة (قد تسبب لخبطة):")
                st.json(info.get("dup_tables"))
    except Exception as e:
        st.error(f"فشل فحص DB: {e}")

    # -------------------------
    # Backup
    # -------------------------
    st.subheader("💾 نسخة احتياطية")
    if st.button("📦 إنشاء نسخة احتياطية ذكية", key="smart_backup_btn"):
        try:
            path = create_smart_backup()
            st.success("✅ تم إنشاء النسخة الاحتياطية.")
            st.code(str(path))
        except Exception as e:
            st.error(f"فشل إنشاء النسخة الاحتياطية: {e}")


def view_settings():
    st.header("الإعدادات")

    # =====================================================
    # ✅ Theme (Light/Dark) - CSS only, no logic changes
    # =====================================================
    with st.expander("🌓 المظهر (ثيم فاتح/داكن)", expanded=False):
        current = (st.session_state.get("ui_theme") or "light").strip().lower()
        current = current if current in ("light", "dark") else "light"

        choice = st.radio(
            "اختر ثيم البرنامج",
            options=["light", "dark"],
            format_func=lambda x: "فاتح" if x == "light" else "داكن",
            index=0 if current == "light" else 1,
            horizontal=True,
            key="ui_theme_picker",
        )

        if choice != current:
            st.session_state["ui_theme"] = choice
            st.success("✅ تم تغيير الثيم.\nقد تحتاج تحديث الصفحة إذا لم يظهر التغيير فوراً.")
            st.rerun()

    # =====================================================
    # الهوية والشعار (اختياري)
    # =====================================================
    try:
        from config import LOGO_FULL_PATH, LOGO_MARK_PATH, LOGO_APP_PATH

        def _p(x) -> str:
            if isinstance(x, Path):
                return str(x)
            return str(x or "")

        def _exists(pth: str) -> bool:
            try:
                return bool(pth) and os.path.exists(pth)
            except Exception:
                return False

        with st.expander("🎨 الهوية (الشعار/الأيقونة)", expanded=False):
            full_default = _p(LOGO_FULL_PATH)
            mark_default = _p(LOGO_MARK_PATH)
            app_default = _p(LOGO_APP_PATH)

            # Allow user override (stored in session only)
            st.caption("يمكنك تغيير الشعار محليًا (داخل الجلسة) دون تعديل الملفات.")
            cols = st.columns(3)
            with cols[0]:
                st.write("الشعار الكامل")
                if _exists(st.session_state.get("ui_logo_full") or full_default):
                    st.image(st.session_state.get("ui_logo_full") or full_default, width=180)
                up = st.file_uploader("رفع شعار كامل", type=["png", "jpg", "jpeg", "webp"], key="upl_full")
                if up:
                    tmp = os.path.join("/tmp", f"osoul_logo_full_{up.name}")
                    with open(tmp, "wb") as f:
                        f.write(up.getbuffer())
                    st.session_state["ui_logo_full"] = tmp
                    st.success("✅ تم تحديث الشعار الكامل للجلسة.")
                    st.rerun()

            with cols[1]:
                st.write("علامة الشعار")
                if _exists(st.session_state.get("ui_logo_mark") or mark_default):
                    st.image(st.session_state.get("ui_logo_mark") or mark_default, width=120)
                up = st.file_uploader("رفع علامة", type=["png", "jpg", "jpeg", "webp"], key="upl_mark")
                if up:
                    tmp = os.path.join("/tmp", f"osoul_logo_mark_{up.name}")
                    with open(tmp, "wb") as f:
                        f.write(up.getbuffer())
                    st.session_state["ui_logo_mark"] = tmp
                    st.success("✅ تم تحديث علامة الشعار للجلسة.")
                    st.rerun()

            with cols[2]:
                st.write("أيقونة التطبيق")
                if _exists(st.session_state.get("ui_logo_app") or app_default):
                    st.image(st.session_state.get("ui_logo_app") or app_default, width=90)
                up = st.file_uploader("رفع أيقونة", type=["png", "jpg", "jpeg", "webp"], key="upl_app")
                if up:
                    tmp = os.path.join("/tmp", f"osoul_logo_app_{up.name}")
                    with open(tmp, "wb") as f:
                        f.write(up.getbuffer())
                    st.session_state["ui_logo_app"] = tmp
                    st.success("✅ تم تحديث الأيقونة للجلسة.")
                    st.rerun()

    except Exception as e:
        log_exception(e, "Settings logos failed", level="DEBUG")
