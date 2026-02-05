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
        from pathlib import Path

        def _p(x) -> str:
            # دعم Path و str
            if isinstance(x, Path):
                return str(x)
            return str(x) if isinstance(x, str) else ""

        logo_full_p = _p(LOGO_FULL_PATH)
        logo_mark_p = _p(LOGO_MARK_PATH)
        logo_app_p = _p(LOGO_APP_PATH)

        any_logo = any([
            bool(logo_full_p) and os.path.exists(logo_full_p),
            bool(logo_mark_p) and os.path.exists(logo_mark_p),
            bool(logo_app_p) and os.path.exists(logo_app_p),
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
                    if logo_full_p and os.path.exists(logo_full_p):
                        st.caption("logo_full.png")
                        st.image(logo_full_p, use_container_width=True)
                with cols[1]:
                    if logo_mark_p and os.path.exists(logo_mark_p):
                        st.caption("logo_mark.png")
                        st.image(logo_mark_p, use_container_width=True)
                with cols[2]:
                    if logo_app_p and os.path.exists(logo_app_p):
                        st.caption("logo_app.png")
                        st.image(logo_app_p, use_container_width=True)

                # تنبيه إرشادي فقط إذا كانت بعض الملفات ناقصة
                if not (os.path.exists(logo_full_p) and os.path.exists(logo_mark_p) and os.path.exists(logo_app_p)):
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
