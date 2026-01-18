import streamlit as st
import extra_streamlit_components as stx
from database import init_db, create_user, verify_user
from config import DEFAULT_COLORS, get_master_styles, APP_NAME, APP_ICON
from logic import get_financial_summary
import views
import charts
import time

# 1. إعداد الصفحة
st.set_page_config(page_title=APP_NAME, layout="wide", page_icon=APP_ICON, initial_sidebar_state="collapsed")

# 2. إدارة الكوكيز
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()

# تهيئة متغيرات الجلسة
if 'page' not in st.session_state: st.session_state.page = 'home'
if 'custom_colors' not in st.session_state: st.session_state.custom_colors = DEFAULT_COLORS.copy()

# 3. نظام تسجيل الدخول
def login_system():
    init_db()
    
    # محاولة الدخول التلقائي عبر الكوكيز
    user_token = cookie_manager.get(cookie="osoul_user")
    if user_token:
        st.session_state['logged_in'] = True
        st.session_state['username'] = user_token
        return True

    if st.session_state.get("logged_in", False):
        return True

    # شاشة تسجيل الدخول
    st.markdown("""
        <style>
        .stTextInput input { text-align: center; }
        </style>
        """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(f"<h1 style='text-align: center; color: #0052CC;'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
        
        tab_login, tab_register = st.tabs(["🔑 تسجيل الدخول", "👤 إنشاء حساب جديد"])
        
        with tab_login:
            username_in = st.text_input("اسم المستخدم", key="login_user")
            password_in = st.text_input("كلمة المرور", type="password", key="login_pass")
            
            if st.button("دخول", type="primary", use_container_width=True):
                if verify_user(username_in, password_in):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username_in
                    cookie_manager.set("osoul_user", username_in, expires_at=None) # حفظ الدخول
                    st.success("تم الدخول بنجاح!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("اسم المستخدم أو كلمة المرور غير صحيحة")

        with tab_register:
            new_user = st.text_input("اختر اسم مستخدم", key="reg_user")
            new_pass = st.text_input("اختر كلمة مرور", type="password", key="reg_pass")
            
            if st.button("إنشاء الحساب", type="secondary", use_container_width=True):
                if new_user and new_pass:
                    if create_user(new_user, new_pass):
                        st.success("تم إنشاء الحساب! يمكنك الآن تسجيل الدخول.")
                    else:
                        st.error("اسم المستخدم هذا موجود مسبقاً.")
                else:
                    st.warning("الرجاء تعبئة جميع الحقول.")

    return False

# 4. تنفيذ الحماية
if not login_system():
    st.stop()

# ---------------------------------------------------------
# المحتوى الرئيسي للتطبيق
# ---------------------------------------------------------

# تطبيق الستايل والألوان
C = st.session_state.custom_colors
st.markdown(get_master_styles(C), unsafe_allow_html=True)

# 🔴 تم حذف القائمة الجانبية (Sidebar) من هنا لحل مشكلة الشريط الرمادي 🔴

# عرض القائمة العلوية
views.render_navbar()

# --- معالجة تسجيل الخروج ---
if st.session_state.page == 'logout':
    cookie_manager.delete("osoul_user")
    st.session_state.clear()
    st.rerun()

# جلب البيانات المالية
fin_data = get_financial_summary()

# توجيه الصفحات
page = st.session_state.page

if page == 'home': 
    if hasattr(views, 'view_dashboard'): views.view_dashboard(fin_data)
elif page == 'spec': 
    if hasattr(views, 'view_portfolio'): views.view_portfolio(fin_data, "مضاربة")
elif page == 'invest': 
    if hasattr(views, 'view_portfolio'): views.view_portfolio(fin_data, "استثمار")
elif page == 'cash': 
    if hasattr(views, 'view_liquidity'): views.view_liquidity()
elif page == 'analysis': 
    charts.view_analysis(fin_data)
elif page == 'add': 
    if hasattr(views, 'view_add_trade'): views.view_add_trade()
elif page == 'settings': 
    if hasattr(views, 'view_settings'): views.view_settings()
