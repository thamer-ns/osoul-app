import streamlit as st
import pandas as pd
from database import init_db, create_user, verify_user
from logic import get_financial_summary
import views
import charts 
from config import DEFAULT_COLORS, PRESET_THEMES, get_master_styles, APP_NAME, APP_ICON
import time

# 1. إعداد الصفحة
st.set_page_config(page_title=APP_NAME, layout="wide", page_icon=APP_ICON, initial_sidebar_state="collapsed")

# --- نظام تسجيل الدخول الجديد ---
def login_system():
    # تهيئة قاعدة البيانات
    init_db()
    
    # التحقق هل المستخدم مسجل دخول بالفعل؟
    if st.session_state.get("logged_in", False):
        return True

    st.markdown(
        """
        <style>
        .stTextInput input { text-align: center; }
        .auth-container { max-width: 400px; margin: 0 auto; padding: 20px; border-radius: 10px; background-color: #f0f2f6; }
        </style>
        """, unsafe_allow_html=True
    )

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(f"<h1 style='text-align: center; color: #0052CC;'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
        
        tab_login, tab_register = st.tabs(["🔑 تسجيل الدخول", "👤 إنشاء حساب جديد"])
        
        with tab_login:
            st.markdown("##### الدخول للحساب الشخصي")
            username_in = st.text_input("اسم المستخدم", key="login_user")
            password_in = st.text_input("الرمز السري (PIN)", type="password", key="login_pass")
            
            if st.button("دخول", type="primary", use_container_width=True):
                if verify_user(username_in, password_in):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username_in
                    st.success("تم الدخول بنجاح! جاري التحميل...")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("اسم المستخدم أو الرمز غير صحيح")
            
            st.markdown("---")
            st.markdown("<div style='text-align: center; color: gray;'>أو الدخول السريع</div>", unsafe_allow_html=True)
            if st.button("G تسجيل الدخول عبر Google", use_container_width=True):
                st.info("خدمة Google Login تتطلب إعدادات API خاصة. حالياً يرجى استخدام الدخول التقليدي.")

        with tab_register:
            st.markdown("##### إنشاء حساب جديد")
            new_user = st.text_input("اختر اسم مستخدم", key="reg_user")
            new_pass = st.text_input("اختر رمزاً سرياً", type="password", key="reg_pass")
            
            if st.button("إنشاء الحساب", type="primary", use_container_width=True):
                if new_user and new_pass:
                    if create_user(new_user, new_pass):
                        st.success("تم إنشاء الحساب بنجاح! يمكنك الآن تسجيل الدخول.")
                    else:
                        st.error("اسم المستخدم هذا موجود مسبقاً.")
                else:
                    st.warning("الرجاء تعبئة جميع الحقول.")
            
            st.markdown("---")
            if st.button("G إنشاء حساب عبر Google", use_container_width=True):
                st.info("قريباً..")

    return False

# 2. تنفيذ الحماية
if not login_system():
    st.stop()

# ---------------------------------------------------------
# المحتوى المحمي (يعمل فقط بعد الدخول)
# ---------------------------------------------------------

# عرض ترحيب بالمستخدم
st.sidebar.success(f"مرحباً, {st.session_state.get('username', 'User')}")
if st.sidebar.button("تسجيل الخروج"):
    st.session_state["logged_in"] = False
    st.rerun()

# 3. تهيئة المتغيرات الأساسية (هنا كان الخطأ وتم إصلاحه)
if 'page' not in st.session_state:
    st.session_state['page'] = 'home'

if 'custom_colors' not in st.session_state:
    st.session_state.custom_colors = DEFAULT_COLORS.copy()
else:
    for key, value in DEFAULT_COLORS.items():
        if key not in st.session_state.custom_colors:
            st.session_state.custom_colors[key] = value

C = st.session_state.custom_colors

# 4. CSS
st.markdown(get_master_styles(C), unsafe_allow_html=True)

# 5. التشغيل
views.render_navbar()

# توجيه الصفحات
page = st.session_state.page
fin_data = get_financial_summary()

if page == 'home': views.view_dashboard(fin_data)
elif page == 'spec': views.view_portfolio(fin_data, "مضاربة")
elif page == 'invest': views.view_portfolio(fin_data, "استثمار")
elif page == 'cash': views.view_liquidity()
elif page == 'analysis': charts.view_analysis(fin_data)
elif page == 'add': views.view_add_trade()
elif page == 'settings': views.view_settings()
