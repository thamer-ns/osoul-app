from osoli_logging import log_exception
#views/settings.py
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
    # Diagnostics: DB healthcheck
    # -------------------------
    st.subheader("🩺 فحص قاعدة البيانات")
    try:
        info = db_healthcheck()
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
            # ---------------------------------
            # ✅ Logo preset selector (Try/Preview)
            # ---------------------------------
            # ملاحظة: "logo_tile.png" لم يعد مستخدماً (كان يسبب تحذير بأن الأصول غير موجودة)
            presets = {
                "افتراضي": {
                    "full": "assets/logo_full.png",
                    "mark": "assets/logo_mark.png",
                    "app":  "assets/logo_app.png",
                },
                "شفاف": {
                    "full": "assets/logo_full.png",
                    "mark": "assets/logo_mark.png",
                    "app":  "assets/logo_mark.png",
                },
                "مربع": {
                    "full": "assets/logo_full.png",
                    "mark": "assets/logo_app.png",
                    "app":  "assets/logo_app.png",
                },
            }

            cur_preset = st.session_state.get("ui_logo_preset") or "افتراضي"
            if cur_preset not in presets:
                cur_preset = "افتراضي"

            picked = st.selectbox(
                "اختر أسلوب الشعار (للتجربة)",
                options=list(presets.keys()),
                index=list(presets.keys()).index(cur_preset),
                help="يؤثر على شعار الهيدر/السايدبار وأيقونة الصفحة (CSS/عرض فقط)",
                key="ui_logo_preset_picker",
            )

            if picked != cur_preset:
                st.session_state["ui_logo_preset"] = picked
                st.session_state["ui_logo_full"] = presets[picked]["full"]
                st.session_state["ui_logo_mark"] = presets[picked]["mark"]
                st.session_state["ui_logo_app"] = presets[picked]["app"]
                st.success("✅ تم تحديث اختيار الشعار.\nقد تحتاج تحديث الصفحة/إعادة تشغيل التطبيق لتحديث favicon.")
                st.rerun()

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

                # تنبيه إرشادي فقط إذا كانت بعض الملفات ناقصة
                if not (os.path.exists(LOGO_FULL_PATH) and os.path.exists(LOGO_MARK_PATH) and os.path.exists(LOGO_APP_PATH)):
                    st.info(
                        "ضع ملفات الشعار داخل مجلد assets/ بالأسماء التالية ليتم ربطها تلقائياً: "
                        "logo_full.png و logo_mark.png و logo_app.png"
                    )
            else:
                st.warning(
                    "لا يوجد شعار داخل assets/ حالياً. "
                    "إذا رغبت، أنشئ مجلد assets/ وضع داخله: logo_full.png و logo_mark.png و logo_app.png"
                )
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
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
