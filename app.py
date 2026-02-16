# app.py
import os
import sys

# Load local environment variables for development (safe no-op on Streamlit Cloud)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

import streamlit as st

# Arabic UI: translate Streamlit default placeholders (called after set_page_config)
try:
    from components import inject_streamlit_ar_i18n
except Exception:
    inject_streamlit_ar_i18n = None

# -----------------------------------------------------------------------------
# 🔧 Import bootstrap
# بعض الرفعّات إلى GitHub تضع المشروع داخل مجلد فرعي (مثل: osoul-app-main).
# هذا البلوك يجعل الاستيرادات تعمل حتى لو تغيّر مسار التشغيل.
# -----------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

PARENT_DIR = os.path.dirname(ROOT_DIR)
if PARENT_DIR and PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

# -----------------------------------------------------------------------------
# 🧩 App configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="أُصول",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

if inject_streamlit_ar_i18n:
    try:
        inject_streamlit_ar_i18n()
    except Exception:
        pass

# -----------------------------------------------------------------------------
# 🧠 Imports (after sys.path bootstrap)
# -----------------------------------------------------------------------------
from analytics import calculate_portfolio_metrics, get_portfolio_cache_key  # noqa: E402
from views.dashboard import view_dashboard  # noqa: E402
from views.signals import view_signals  # noqa: E402
from views.analysis import view_analysis  # noqa: E402
from views.settings import view_settings  # noqa: E402

# -----------------------------------------------------------------------------
# 🧭 Sidebar navigation (stable — no dynamic imports)
# -----------------------------------------------------------------------------
def _render_sidebar() -> str:
    st.sidebar.title("أُصول")
    st.sidebar.caption("منصة تحليل واستثمار")

    pages = {
        "الرئيسية": "home",
        "المستشار": "advisor",
        "الإشارات": "signals",
        "التقارير": "reports",
        "التحليل": "analysis",
        "الإعدادات": "settings",
    }

    choice = st.sidebar.radio("القائمة", list(pages.keys()), index=0)
    return pages[choice]


page = _render_sidebar()

# -----------------------------------------------------------------------------
# 🚀 Page router
# -----------------------------------------------------------------------------
def _load_fin():
    with st.spinner("جارٍ تحميل بيانات المحفظة..."):
        return calculate_portfolio_metrics(cache_key=get_portfolio_cache_key())


def _render_reports_placeholder():
    st.header("التقارير")
    st.info("صفحة التقارير قيد التطوير. مؤقتًا: استخدم صفحة التحليل + الإشارات.")


def _render_advisor_placeholder(fin):
    st.header("المستشار")
    st.caption("المستشار موجود داخل صفحة **التحليل** (تبويب/قسم المستشار).")
    st.markdown("➡️ افتح **التحليل** ثم اختر تبويب/قسم **المستشار**.")
    # عرض التحليل مباشرة لتقليل الإحساس بأن الصفحة فارغة
    view_analysis(fin)


try:
    fin = _load_fin()

    if page == "home":
        view_dashboard(fin)

    elif page == "signals":
        view_signals(fin)

    elif page == "analysis":
        view_analysis(fin)

    elif page == "settings":
        view_settings()

    elif page == "reports":
        _render_reports_placeholder()

    elif page == "advisor":
        _render_advisor_placeholder(fin)

    else:
        view_dashboard(fin)

except Exception as e:
    st.error("حدث خطأ أثناء تشغيل التطبيق.")
    st.exception(e)
    st.info("جرّب إعادة تشغيل التطبيق من Manage app → Reboot، أو راجع سجلّ الأخطاء في Streamlit Cloud.")