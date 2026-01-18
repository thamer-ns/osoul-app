import streamlit as st
import extra_streamlit_components as stx
from database import init_db, create_user, verify_user
from config import DEFAULT_COLORS, get_master_styles
from logic import get_financial_summary
import views
import charts
import time

# 1. إعداد الصفحة
st.set_page_config(page_title="أصولي", layout="wide", page_icon="📈", initial_sidebar_state="collapsed")

# 2. إدارة الكوكيز (للحفاظ على تسجيل الدخول)
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()

if 'page' not in st.session_state: st.session_state.page = 'home'
if 'custom_colors' not in st.session_state: st.session_state.custom_colors = DEFAULT_COLORS.copy()

# 3. نظام تسجيل الدخول مع الكوكيز
def login_system():
    init_db()
    
    # التحقق من الكوكي
    user_token = cookie_manager.get(cookie="osoul_user")
    if user_token:
        st.session_state['logged_in'] = True
        st.session_state['username'] = user_token
        return True

    if st.session_state.get("logged_in", False):
        return True

    # واجهة الدخول
    st.markdown("<h1 style='text-align: center; color: #0052CC;'>📈 مرحباً بك في أصولي</h1>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["تسجيل الدخول", "حساب جديد"])
    
    with tab1:
        u_in = st.text_input("اسم المستخدم", key="l_u")
        p_in = st.text_input("كلمة المرور", type="password", key="l_p")
        if st.button("دخول", use_container_width=True):
            if verify_user(u_in, p_in):
                st.session_state['logged_in'] = True
                st.session_state['username'] = u_in
                # حفظ الكوكي لمدة 30 يوم
                cookie_manager.set("osoul_user", u_in, expires_at=None, key="set_cookie")
                st.success("تم الدخول!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("بيانات خاطئة")

    with tab2:
        new_u = st.text_input("اسم مستخدم جديد", key="r_u")
        new_p = st.text_input("كلمة مرور جديدة", type="password", key="r_p")
        if st.button("إنشاء حساب", use_container_width=True):
            if create_user(new_u, new_p):
                st.success("تم الإنشاء! سجل دخولك الآن.")
            else:
                st.error("المستخدم موجود مسبقاً")
    
    return False

# 4. تشغيل التطبيق
if not login_system():
    st.stop()

# --- التطبيق يعمل الآن ---
C = st.session_state.custom_colors
st.markdown(get_master_styles(C), unsafe_allow_html=True)

# زر الخروج
with st.sidebar:
    st.write(f"مرحباً {st.session_state.get('username')}")
    if st.button("تسجيل خروج"):
        cookie_manager.delete("osoul_user")
        st.session_state.clear()
        st.rerun()

views.render_navbar()

# جلب البيانات
fin_data = get_financial_summary()

# التوجيه
if st.session_state.page == 'home':
    # تأكد من نقل دالة view_dashboard إلى views.py
    if hasattr(views, 'view_dashboard'): views.view_dashboard(fin_data)
    else: st.info("الصفحة قيد الإنشاء")
elif st.session_state.page == 'analysis':
    charts.view_analysis(fin_data)
elif st.session_state.page == 'settings':
    # صفحة الإعدادات
    if hasattr(views, 'view_settings'): views.view_settings()
    else: st.info("الإعدادات")
else:
    st.info(f"صفحة {st.session_state.page}")
