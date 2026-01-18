import streamlit as st
import extra_streamlit_components as stx
import datetime
import time
from database import init_db, db_verify_user, db_create_user
from config import APP_NAME, APP_ICON

@st.cache_resource(experimental_allow_widgets=True)
def get_manager():
    return stx.CookieManager(key="cookie_manager_app")

def login_system():
    init_db()
    cookie_manager = get_manager()
    time.sleep(0.1)
    
    if st.session_state.get("logged_in", False): return True
    
    cookie_user = cookie_manager.get(cookie="osoul_user")
    if cookie_user:
        st.session_state["logged_in"] = True
        st.session_state["username"] = cookie_user
        return True

    st.markdown(f"<h1 style='text-align: center; color: #0052CC;'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["تسجيل الدخول", "حساب جديد"])
    with t1:
        u = st.text_input("المستخدم", key="l_u")
        p = st.text_input("كلمة المرور", type="password", key="l_p")
        if st.button("دخول", type="primary", use_container_width=True):
            if db_verify_user(u, p):
                st.session_state["logged_in"] = True
                st.session_state["username"] = u
                cookie_manager.set('osoul_user', u, expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                st.rerun()
            else: st.error("بيانات خاطئة")
    with t2:
        nu = st.text_input("اسم جديد", key="r_u")
        np = st.text_input("رمز سري", type="password", key="r_p")
        if st.button("إنشاء", type="secondary", use_container_width=True):
            if nu and np:
                if db_create_user(nu, np): st.success("تم الإنشاء")
                else: st.error("موجود مسبقاً")
    return False

def logout():
    get_manager().delete("osoul_user")
    st.session_state.clear()
    st.rerun()
