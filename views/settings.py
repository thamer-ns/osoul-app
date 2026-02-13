#views/settings.py
import streamlit as st

from feature_flags import get_all_flags, set_flag
from analytics import create_smart_backup
from database import db_healthcheck

def view_tools():
    st.header("🛠️ أدوات")
    st.caption("تشخيصات + تقييم أداء المستشار + التعلم الذاتي (تجريبي وآمن)")

    # ============================
    # 🧠 التعلم الذاتي (Level Pro)
    # ============================
    with st.expander("🧠 التعلم الذاتي (Level Pro) — تقييم النتائج + تحديث الأوزان", expanded=False):
        st.write("• يسجل قرارات المستشار كـ Signals ثم يقيّم النتائج بعد 5/10/20/60 يوم (أو أسابيع للفريم الأسبوعي).")
        st.write("• يقيّم النتائج **بسلوك TP/SL** إذا كانت موجودة في خطة المخاطر، وليس فقط إغلاق بعد مدة.")
        st.write("• يحدث الأوزان **حسب السياق**: اتجاه السوق (TASI) + ADX Regime (Trend/Range) + القطاع إن وجد.")
        st.warning("ملاحظة: لتقليل أي انحراف، التعلّم يطبق حدود (Safety Rails) ويتطلب حد أدنى من العينات قبل تعديل أي وزن.")

        c1, c2, c3 = st.columns(3)
        with c1:
            interval = st.selectbox("الفريم للتقييم", options=["1d", "1wk"], index=0)
        with c2:
            horizons = st.multiselect("آفاق التقييم", options=[5,10,20,60,4,8,13,26], default=[5,10,20,60])
        with c3:
            max_rows = st.number_input("أقصى عدد إشارات للفحص", min_value=50, max_value=5000, value=400, step=50)

        b1, b2 = st.columns(2)
        with b1:
            if st.button("✅ قيّم الإشارات المستحقة الآن", width="stretch"):
                try:
                    from ai_engine_core.logging_learning import evaluate_pending_outcomes_pro
                    res = evaluate_pending_outcomes_pro(horizons=horizons or None, max_rows=int(max_rows), interval=str(interval))
                    st.success(res)
                except Exception as e:
                    st.error(f"فشل التقييم: {e}")

        with b2:
            target_h = st.selectbox("الأفق المستهدف للتعلّم", options=[5,10,20,60,4,8,13,26], index=2)
            min_samples = st.number_input("أقل عدد عينات لكل ميزة/سياق", min_value=10, max_value=500, value=40, step=5)
            if st.button("🧠 حدّث الأوزان (تعلم) الآن", width="stretch"):
                try:
                    from ai_engine_core.logging_learning import learn_from_history_pro
                    res = learn_from_history_pro(target_horizon=int(target_h), min_samples=int(min_samples))
                    st.success(res)
                except Exception as e:
                    st.error(f"فشل التعلّم: {e}")

    st.divider()

    st.info("حاسبة الزكاة (قريباً)")


def view_settings():
    st.header("الإعدادات")


    # =====================================================
    # 🧪 ميزات تجريبية (Feature Flags)
    # - لا تغيّر السلوك الافتراضي
    # - تظهر فقط لمن يريد تفعيلها
    # =====================================================
    with st.expander("🧪 ميزات تجريبية (اختيارية)", expanded=False):
        flags = get_all_flags()

        st.caption("هذه الميزات اختيارية ولا تؤثر على المستخدم العادي إلا إذا فعّلتها هنا.")
        c1, c2 = st.columns(2)

        with c1:
            v_xirr = st.checkbox("📈 إظهار XIRR للمحفظة", value=bool(flags.get("enable_xirr", False)))
            v_notes = st.checkbox("📒 إظهار ملاحظات الاستراتيجيات + سجل التجارب", value=bool(flags.get("enable_strategy_notes", False)))

        with c2:
            v_wrappers = st.checkbox("🈶 استخدام عناصر عربية محسّنة (placeholders)", value=bool(flags.get("use_ar_wrappers", False)))
            v_compare = st.checkbox("🧠 مقارنة محرك المستشار (قديم/جديد) — متقدم", value=bool(flags.get("enable_engine_compare", False)))
            v_learn = st.checkbox("🧠 تفعيل التعلم الذاتي للمستشار (Signals/Outcomes/Weights)", value=bool(flags.get("enable_self_learning", True)))

        # persist to session
        set_flag("enable_xirr", v_xirr)
        set_flag("enable_strategy_notes", v_notes)
        set_flag("use_ar_wrappers", v_wrappers)
        set_flag("enable_engine_compare", v_compare)
        set_flag("enable_self_learning", v_learn)

        st.info("✅ يتم حفظ الاختيارات لهذه الجلسة. إذا أردت جعلها دائمة لاحقًا نربطها بقاعدة البيانات (اختياري).")

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
                        st.image(LOGO_FULL_PATH, width="stretch")
                with cols[1]:
                    if isinstance(LOGO_MARK_PATH, str) and os.path.exists(LOGO_MARK_PATH):
                        st.caption("logo_mark.png")
                        st.image(LOGO_MARK_PATH, width="stretch")
                with cols[2]:
                    if isinstance(LOGO_APP_PATH, str) and os.path.exists(LOGO_APP_PATH):
                        st.caption("logo_app.png")
                        st.image(LOGO_APP_PATH, width="stretch")

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
