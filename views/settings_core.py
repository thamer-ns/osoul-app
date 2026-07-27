"""Clean settings surface without obsolete experimental toggles."""
from __future__ import annotations

import streamlit as st

from tenant_scope import current_tenant
from views import settings as settings_base


def _render_integrated_capabilities() -> None:
    with st.expander("🧠 ميزات التحليل المدمجة", expanded=False):
        st.markdown(
            """
            | الميزة | وضعها الآن | فائدتها |
            |---|---|---|
            | **العائد الحقيقي XIRR** | يعمل تلقائيًا عند توفر تدفقات نقدية كافية | يقيس العائد مع مراعاة تواريخ الإيداع والسحب بدل نسبة ربح سطحية |
            | **عناصر الإدخال العربية** | مفعلة دائمًا | اتجاه وتسميات عربية موحدة دون خيار قد يعطلها |
            | **ملاحظات الاستراتيجيات وسجل الاختبارات** | مدمجة داخل الاختبار الخلفي | توضح منطق الاستراتيجية وتعرض نتائج التشغيلات السابقة |
            | **تسجيل نتائج المستشار** | يعمل تلقائيًا عند إنشاء تحليل | يبني سجلًا يمكن تقييمه لاحقًا لمعرفة ما نجح وما فشل |
            | **تحديث أوزان المستشار** | يدوي وتحت تأكيد من صفحة الأدوات | يمنع تغيير الأوزان بعينات قليلة أو دون موافقة المستخدم |
            """
        )
        st.info(
            "تم حذف خيار مقارنة المحرك القديم والجديد لأنه لم يكن مرتبطًا "
            "بتنفيذ فعلي، وحُذفت مفاتيح الجلسة التي كانت توحي بتفعيل ميزات "
            "بينما لا تغيّر سلوك البرنامج."
        )
        if st.button(
            "فتح أدوات التقييم والتعلم",
            icon="🛠️",
            use_container_width=True,
            key="settings_open_learning_tools",
        ):
            from views.navbar import navigate_to

            navigate_to("tools")


def view_settings() -> None:
    st.header("⚙️ الإعدادات")
    tenant = current_tenant()
    if tenant is not None:
        st.caption(f"المحفظة النشطة: {tenant.username} — المحفظة الرئيسية")

    settings_base._render_account_actions()
    _render_integrated_capabilities()
    settings_base._render_theme()
    settings_base._render_brand_preview()
    settings_base._render_database_health()
    settings_base._render_backup()
