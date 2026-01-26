import streamlit as st
import extra_streamlit_components as stx
import datetime
import time
from database import init_db, db_verify_user, db_create_user
from config import APP_NAME, APP_ICON

def get_manager():
    return stx.CookieManager(key="osoul_cookie_mgr")

def login_system():
    init_db()
    cookie_manager = get_manager()
    
    # 1. فحص الجلسة
    if st.session_state.get("logged_in", False):
        return True
    
    # 2. فحص الكوكيز (تأخير بسيط لضمان التحميل)
    time.sleep(0.1)
    cookie_user = cookie_manager.get(cookie="osoul_user")
    
    if cookie_user:
        st.session_state["logged_in"] = True
        st.session_state["username"] = cookie_user
        return True

    # 3. شاشة الدخول
    st.markdown(f"<h1 style='text-align: center; color: #0052CC;'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["🔒 دخول", "✨ تسجيل"])
    
    with t1:
        with st.form("login_form"):
            u = st.text_input("اسم المستخدم")
            p = st.text_input("كلمة المرور", type="password")
            if st.form_submit_button("دخول", type="primary", use_container_width=True):
                if db_verify_user(u, p):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = u
                    cookie_manager.set('osoul_user', u, expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                    st.success("تم!"); time.sleep(0.5); st.rerun()
                else: st.error("بيانات خاطئة")

    with t2:
        with st.form("signup_form"):
            nu = st.text_input("اسم مستخدم جديد")
            np = st.text_input("كلمة مرور", type="password")
            if st.form_submit_button("تسجيل", type="secondary", use_container_width=True):
                res = db_create_user(nu, np)
                if res: st.success("تم الإنشاء! سجل دخولك الآن.")
                else: st.error("حدث خطأ")
    
    return False

def logout():
    try:
        manager = get_manager()
        manager.delete("osoul_user")
    except: pass
    st.session_state.clear()
    st.rerun()
