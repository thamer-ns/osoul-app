#views/settings.py
import streamlit as st

from feature_flags import get_all_flags, set_flag
from analytics import create_smart_backup
from database import db_healthcheck


def _render_self_learning_dashboard():
    """Dashboard to evaluate past AI signals and adapt weights (safe + bounded)."""
    try:
        from ai_engine_core.logging_learning import (
            evaluate_pending_outcomes,
            learn_from_history,
            get_calibration_snapshot,
        )
    except Exception:
        st.error("تعذر تحميل وحدة التعلم الذاتي (ai_engine_core/logging_learning.py).")
        return

    st.subheader("🧠 التعلم الذاتي (تجربة → تقييم لاحق → تكيّف)")
    st.caption(
        "الفكرة: يسجل البرنامج الإشارات التي يعطيها، وبعد مرور عدد أيام/شموع محدد يقوم بتقييم النتيجة "
        "ثم يحدّث أوزان بعض الإشارات (بحدود آمنة) لتحسين الدقة تدريجيًا."  # noqa
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        max_eval = st.number_input("حد أعلى للتقييم دفعة واحدة", 10, 500, 80, step=10)
    with c2:
        strict = st.checkbox("استخدم شموع تداول فقط (أدق)", value=True)
    with c3:
        run_learn = st.checkbox("بعد التقييم: حدّث الأوزان تلقائيًا", value=True)

    if st.button("🚀 قيّم الإشارات المستحقة الآن", use_container_width=True):
        with st.spinner("جاري تقييم الإشارات القديمة بناءً على الحركة السعرية..."):
            rep = evaluate_pending_outcomes(max_rows=int(max_eval), trading_bars=bool(strict))
        if not rep.get("ok"):
            st.error(f"فشل التقييم: {rep.get('reason')}")
        else:
            st.success(
                f"✅ تم تقييم: {rep.get('evaluated', 0)} | تم تخطي: {rep.get('skipped', 0)} | أخطاء: {rep.get('errors', 0)}"
            )
            if rep.get("details"):
                with st.expander("تفاصيل مختصرة", expanded=False):
                    st.json(rep["details"])

            if run_learn:
                with st.spinner("جاري تحديث الأوزان بناءً على النتائج..."):
                    lr = learn_from_history(max_rows=600)
                if lr.get("ok"):
                    st.success(f"✅ تم تحديث أوزان: {lr.get('updated', 0)} (من أصل خصائص: {lr.get('features', 0)})")
                else:
                    st.warning(f"لم يتم تحديث الأوزان: {lr.get('reason')}")

    st.markdown("---")
    st.write("### 📊 معايرة الأداء (Calibration)")
    sym = st.text_input("رمز (اختياري)", value="")
    tf = st.selectbox("الإطار", options=["1D", "1W", "1H", "30M"], index=0)
    snap = get_calibration_snapshot(symbol=sym.strip() or None, timeframe=tf)
    if snap.get("ok"):
        st.json(snap)
    else:
        st.info("لا يوجد بيانات تقييم كافية بعد. استخدم زر التقييم أولاً.")

def view_tools():
    st.header("🛠️ أدوات")
    st.info("حاسبة الزكاة (قريباً)")

    # Self learning dashboard (if enabled)
    flags = get_all_flags()
    if bool(flags.get("enable_self_learning", True)):
        with st.expander("🧠 التعلم الذاتي وتحسين المستشار", expanded=True):
            _render_self_learning_dashboard()
    else:
        st.caption("التعلم الذاتي معطّل من الإعدادات (ميزات تجريبية).")

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

        v_learn = st.checkbox("🧠 تفعيل التعلم الذاتي (يسجل ويقيّم ويكيّف الأوزان)", value=bool(flags.get("enable_self_learning", True)))

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
