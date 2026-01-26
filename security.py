import streamlit as st
import extra_streamlit_components as stx
import datetime
import time
from database import init_db, db_verify_user, db_create_user
from config import APP_NAME, APP_ICON

def get_manager():
    return stx.CookieManager(key="auth_cookie")

def login_system():
    # التأكد من قاعدة البيانات
    if 'db_check' not in st.session_state:
        init_db()
        st.session_state.db_check = True

    cookie_manager = get_manager()
    
    # محاولة استرجاع المستخدم من الكوكيز
    if 'username' not in st.session_state:
        time.sleep(0.2) # انتظار تحميل الكوكيز
        user = cookie_manager.get('osoul_user')
        if user:
            st.session_state.username = user
            return True

    # واجهة الدخول
    st.markdown(f"<h1 style='text-align: center; color: #0052CC;'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["تسجيل دخول", "حساب جديد"])
    
    with t1:
        with st.form("login"):
            u = st.text_input("اسم المستخدم")
            p = st.text_input("كلمة المرور", type="password")
            if st.form_submit_button("دخول"):
                if db_verify_user(u, p):
                    st.session_state.username = u
                    cookie_manager.set('osoul_user', u, expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                    st.rerun()
                else:
                    st.error("خطأ في البيانات")

    with t2:
        with st.form("signup"):
            nu = st.text_input("مستخدم جديد")
            np = st.text_input("كلمة مرور", type="password")
            if st.form_submit_button("إنشاء حساب"):
                if db_create_user(nu, np):
                    st.success("تم الإنشاء! يمكنك الدخول الآن.")
                else:
                    st.error("المستخدم موجود مسبقاً")
    
    return False if 'username' not in st.session_state else True

def logout():
    try:
        mgr = get_manager()
        mgr.delete('osoul_user')
    except: pass
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()
