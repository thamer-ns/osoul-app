from __future__ import annotations

import datetime as dt
import os

import streamlit as st

from analytics import create_smart_backup
from database import db_healthcheck
from feature_flags import get_all_flags, set_flag
from tenant_scope import current_tenant


def _result_message(result) -> tuple[bool, str]:
    if isinstance(result, dict):
        ok = bool(result.get("ok", True))
        if ok:
            evaluated = result.get("evaluated")
            updated = result.get("updated")
            details = []
            if evaluated is not None:
                details.append(f"تم تقييم {int(evaluated)} إشارة")
            if updated is not None:
                details.append(f"تم تحديث {int(updated)} وزن")
            return True, " — ".join(details) or "اكتملت العملية"
        return False, str(result.get("reason") or "تعذر تنفيذ العملية")
    return True, "اكتملت العملية"


def _session_expiry_label() -> str:
    try:
        expires = int(st.session_state.get("auth_exp", 0) or 0)
        if expires <= 0:
            return "غير متاح"
        value = dt.datetime.fromtimestamp(expires, tz=dt.timezone.utc)
        riyadh = dt.timezone(dt.timedelta(hours=3))
        return value.astimezone(riyadh).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "غير متاح"


def _render_account_actions() -> None:
    """Keep destructive and network actions together inside settings."""
    with st.expander("👤 الحساب والجلسة", expanded=True):
        username = str(st.session_state.get("username") or "—")
        restored = bool(st.session_state.get("auth_restored_from_cookie"))
        session_source = "كوكي المتصفح" if restored else "تسجيل الدخول الحالي"

        info_left, info_right = st.columns(2)
        info_left.markdown(f"**المستخدم:** `{username}`")
        info_right.markdown(f"**انتهاء الجلسة:** `{_session_expiry_label()}`")
        st.caption(
            f"مصدر الجلسة: {session_source}. "
            "تحديث الأسعار يتصل بمصادر السوق عند الطلب فقط."
        )

        refresh_col, logout_col = st.columns(2, gap="small")
        if refresh_col.button(
            "تحديث أسعار المحافظ",
            icon="🔄",
            type="primary",
            use_container_width=True,
            key="settings_refresh_prices",
            help="جلب أحدث الأسعار المتاحة ثم تحديث ملخصات المحافظ",
        ):
            from views.navbar import navigate_to

            navigate_to("update")

        confirm_logout = logout_col.checkbox(
            "تأكيد الخروج",
            value=False,
            key="settings_confirm_logout",
        )
        if logout_col.button(
            "تسجيل الخروج",
            icon="🚪",
            disabled=not confirm_logout,
            use_container_width=True,
            key="settings_logout",
            help="حذف جلسة المتصفح والعودة إلى شاشة الدخول",
        ):
            from security import logout_user

            logout_user()
            st.cache_data.clear()
            st.rerun()


def view_tools():
    st.header("🛠️ أدوات المحفظة")
    tenant = current_tenant()
    if tenant is None:
        st.error("تعذر تحديد المحفظة النشطة")
        return

    st.caption(
        "التقييم والتعلم في هذه الصفحة يخصان المحفظة النشطة فقط، "
        "ولا يغيران قواعد أو أوزان أي مستخدم آخر."
    )

    with st.expander(
        "🧠 تقييم إشارات المستشار والتعلم من النتائج",
        expanded=True,
    ):
        st.write(
            "يقارن الإشارات القديمة بحركة السعر اللاحقة، ويطبق منطق أول وصول "
            "للهدف أو وقف الخسارة عند توفرهما."
        )
        st.warning(
            "نتائج التعلم إحصائية وتجريبية وليست توصية تداول. "
            "لا تُحدّث الأوزان بعينات قليلة."
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            interval = st.selectbox(
                "فاصل التقييم",
                options=["1d", "1wk"],
                format_func=lambda value: "يومي" if value == "1d" else "أسبوعي",
            )
        with c2:
            horizons = st.multiselect(
                "آفاق التقييم",
                options=[4, 5, 8, 10, 13, 20, 26, 60],
                default=[5, 10, 20, 60],
            )
        with c3:
            max_rows = st.number_input(
                "أقصى عدد إشارات",
                min_value=50,
                max_value=5000,
                value=400,
                step=50,
            )

        left, right = st.columns(2)
        with left:
            if st.button(
                "تقييم الإشارات المستحقة",
                type="primary",
                use_container_width=True,
            ):
                try:
                    from ai_engine_core.logging_learning import (
                        evaluate_pending_outcomes_pro,
                    )

                    result = evaluate_pending_outcomes_pro(
                        horizons=horizons or None,
                        max_rows=int(max_rows),
                        interval=str(interval),
                    )
                    ok, message = _result_message(result)
                    st.success(message) if ok else st.error(message)
                except Exception:
                    st.error("تعذر تقييم الإشارات. راجع سجل الخادم.")

        with right:
            target_horizon = st.selectbox(
                "أفق التعلم المستهدف",
                options=[4, 5, 8, 10, 13, 20, 26, 60],
                index=5,
            )
            minimum_samples = st.number_input(
                "الحد الأدنى للعينات",
                min_value=20,
                max_value=500,
                value=50,
                step=5,
            )
            confirm_learning = st.checkbox(
                "أفهم أن التحديث يغير أوزان مستشار محفظتي",
                value=False,
            )
            if st.button(
                "تحديث أوزان مستشار المحفظة",
                disabled=not confirm_learning,
                use_container_width=True,
            ):
                try:
                    from ai_engine_core.logging_learning import (
                        learn_from_history_pro,
                    )

                    result = learn_from_history_pro(
                        target_horizon=int(target_horizon),
                        min_samples=int(minimum_samples),
                    )
                    ok, message = _result_message(result)
                    st.success(message) if ok else st.error(message)
                except Exception:
                    st.error("تعذر تحديث الأوزان. راجع سجل الخادم.")

    with st.expander("🧾 أدوات مالية قادمة"):
        st.info("حاسبة الزكاة وتقرير الأداء الدوري ضمن المرحلة التالية.")


def _render_feature_flags() -> None:
    with st.expander("🧪 ميزات تجريبية", expanded=False):
        flags = get_all_flags()
        left, right = st.columns(2)
        with left:
            show_xirr = st.checkbox(
                "إظهار XIRR للمحفظة",
                value=bool(flags.get("enable_xirr", True)),
            )
            strategy_notes = st.checkbox(
                "ملاحظات الاستراتيجيات وسجل التجارب",
                value=bool(flags.get("enable_strategy_notes", False)),
            )
            arabic_wrappers = st.checkbox(
                "عناصر إدخال عربية محسنة",
                value=bool(flags.get("use_ar_wrappers", False)),
            )
        with right:
            engine_compare = st.checkbox(
                "مقارنة محرك المستشار القديم والجديد",
                value=bool(flags.get("enable_engine_compare", False)),
            )
            self_learning = st.checkbox(
                "تفعيل تسجيل نتائج المستشار والتعلم الذاتي",
                value=bool(flags.get("enable_self_learning", True)),
            )

        set_flag("enable_xirr", show_xirr)
        set_flag("enable_strategy_notes", strategy_notes)
        set_flag("use_ar_wrappers", arabic_wrappers)
        set_flag("enable_engine_compare", engine_compare)
        set_flag("enable_self_learning", self_learning)
        st.caption("هذه الاختيارات محفوظة في الجلسة الحالية فقط.")


def _render_theme() -> None:
    with st.expander("🌓 المظهر", expanded=False):
        current = str(st.session_state.get("ui_theme") or "light").lower()
        if current not in {"light", "dark"}:
            current = "light"
        selected = st.radio(
            "اختر المظهر",
            options=["light", "dark"],
            format_func=lambda value: "فاتح" if value == "light" else "داكن",
            index=0 if current == "light" else 1,
            horizontal=True,
        )
        if selected != current:
            st.session_state["ui_theme"] = selected
            st.success("تم تغيير المظهر")
            st.rerun()


def _render_brand_preview() -> None:
    with st.expander("🎨 الهوية والشعار", expanded=False):
        try:
            from config import LOGO_APP_PATH, LOGO_FULL_PATH, LOGO_MARK_PATH

            paths = [
                ("الشعار الكامل", LOGO_FULL_PATH),
                ("العلامة", LOGO_MARK_PATH),
                ("أيقونة التطبيق", LOGO_APP_PATH),
            ]
            available = [item for item in paths if item[1] and os.path.exists(item[1])]
            if not available:
                st.info("لا توجد ملفات شعار متاحة داخل assets حاليًا.")
                return
            columns = st.columns(len(available))
            for column, (label, path) in zip(columns, available):
                with column:
                    st.caption(label)
                    st.image(path, use_container_width=True)
        except Exception:
            st.info("تعذر عرض معاينة الشعار.")


def _render_database_health() -> None:
    with st.expander("🩺 حالة الاتصال", expanded=False):
        if not st.button("فحص الاتصال بقاعدة البيانات"):
            return
        report = db_healthcheck() or {}
        if report.get("ok"):
            kind = str(report.get("kind") or "غير معروف")
            label = "PostgreSQL" if kind == "postgres" else "SQLite للتطوير"
            st.success(f"الاتصال يعمل — {label}")
            if kind != "postgres":
                st.warning("لا تستخدم SQLite في بيئة الإنتاج.")
        else:
            st.error("تعذر الاتصال بقاعدة البيانات. راجع إعدادات الخادم.")


def _render_backup() -> None:
    with st.expander("💾 نسخة احتياطية", expanded=True):
        st.caption(
            "النسخة تحتوي بيانات المستخدم والمحفظة النشطة فقط، "
            "ولا تتضمن كلمات المرور أو أسرار الخادم أو معرفات العزل الداخلية."
        )
        if st.button("إنشاء نسخة Excel", type="primary"):
            data, filename = create_smart_backup()
            if data is None or not filename:
                st.error("تعذر إنشاء النسخة الاحتياطية")
            else:
                payload = data.getvalue() if hasattr(data, "getvalue") else bytes(data)
                st.session_state["backup_payload"] = payload
                st.session_state["backup_filename"] = filename
                st.success("تم إنشاء النسخة الاحتياطية")

        payload = st.session_state.get("backup_payload")
        filename = st.session_state.get("backup_filename")
        if payload and filename:
            st.download_button(
                "تحميل النسخة الاحتياطية",
                data=payload,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )


def view_settings():
    st.header("⚙️ الإعدادات")
    tenant = current_tenant()
    if tenant is not None:
        st.caption(f"المحفظة النشطة: {tenant.username} — المحفظة الرئيسية")

    _render_account_actions()
    _render_feature_flags()
    _render_theme()
    _render_brand_preview()
    _render_database_health()
    _render_backup()
