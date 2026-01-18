import streamlit as st
import pandas as pd
from database import init_db, create_user, verify_user
from logic import get_financial_summary
# تأخير استيراد views لتجنب المشاكل الدائرية
import config
from config import DEFAULT_COLORS, PRESET_THEMES, get_master_styles, APP_NAME, APP_ICON
import time
import datetime
import extra_streamlit_components as stx
import views
import charts

# 1. إعداد الصفحة
st.set_page_config(page_title=APP_NAME, layout="wide", page_icon=APP_ICON, initial_sidebar_state="collapsed")

# 2. تحميل الألوان والخطوط (CSS)
if 'custom_colors' not in st.session_state:
    st.session_state.custom_colors = DEFAULT_COLORS.copy()
C = st.session_state.custom_colors
st.markdown(get_master_styles(C), unsafe_allow_html=True)

# 3. إدارة الكوكيز
def get_manager():
    return stx.CookieManager(key="cookie_manager_app")

cookie_manager = get_manager()

# 4. نظام تسجيل الدخول
def login_system():
    init_db()
    time.sleep(0.1)
    cookie_user = cookie_manager.get(cookie="osoul_user")
    
    if cookie_user:
        st.session_state["logged_in"] = True
        st.session_state["username"] = cookie_user
        return True

    if st.session_state.get("logged_in", False):
        return True

    # واجهة الدخول
    st.markdown("""<style>.stTextInput input { text-align: center; } .auth-container { max-width: 400px; margin: 0 auto; padding: 20px; }</style>""", unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(f"<h1 style='text-align: center; color: #0052CC;'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
        tab_login, tab_register = st.tabs(["🔑 تسجيل الدخول", "👤 إنشاء حساب جديد"])
        
        with tab_login:
            st.markdown("##### الدخول للحساب الشخصي")
            username_in = st.text_input("اسم المستخدم", key="login_user")
            password_in = st.text_input("الرمز السري (PIN)", type="password", key="login_pass")
            remember_me = st.checkbox("تذكرني")
            
            if st.button("دخول", type="primary", use_container_width=True):
                if verify_user(username_in, password_in):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username_in
                    if remember_me:
                        cookie_manager.set('osoul_user', username_in, expires_at=datetime.datetime.now() + datetime.timedelta(days=30), key="set_cookie")
                    st.success("تم الدخول بنجاح!"); time.sleep(0.5); st.rerun()
                else:
                    st.error("بيانات غير صحيحة")

        with tab_register:
            st.markdown("##### إنشاء حساب جديد")
            new_user = st.text_input("اختر اسم مستخدم", key="reg_user")
            new_pass = st.text_input("اختر رمزاً سرياً", type="password", key="reg_pass")
            if st.button("إنشاء الحساب", type="secondary", use_container_width=True):
                if new_user and new_pass:
                    if create_user(new_user, new_pass):
                        st.success("تم إنشاء الحساب! سجل دخولك الآن.")
                    else:
                        st.error("اسم المستخدم موجود مسبقاً.")
                else:
                    st.warning("الرجاء تعبئة الحقول.")
    return False

if not login_system():
    st.stop()

# ---------------------------------------------------------
# المنطقة المحمية (التطبيق الرئيسي)
# ---------------------------------------------------------

# تهيئة الصفحة الافتراضية
if 'page' not in st.session_state:
    st.session_state['page'] = 'home'

# عرض القائمة العلوية (Navbar) بدلاً من الجانبية
views.render_navbar()

# منطق تسجيل الخروج (يتم استدعاؤه من views.py)
if st.session_state.page == 'logout':
    cookie_manager.delete("osoul_user", key="del_cookie")
    st.session_state.clear()
    st.rerun()

# جلب البيانات والتوجيه
fin_data = get_financial_summary()
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
