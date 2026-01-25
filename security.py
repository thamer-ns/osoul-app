import streamlit as st
import extra_streamlit_components as stx
import datetime
import time
from database import init_db, db_verify_user, db_create_user
from config import APP_NAME, APP_ICON

def get_manager():
    return stx.CookieManager(key="cookie_manager_app")

def login_system():
    # تهيئة القاعدة عند بدء التشغيل
    init_db()
    
    cookie_manager = get_manager()
    
    # 1. فحص الجلسة
    if st.session_state.get("logged_in", False):
        return True
    
    # 2. فحص الكوكيز
    time.sleep(0.1)
    try:
        cookie_user = cookie_manager.get(cookie="osoul_user")
        if cookie_user:
            st.session_state["logged_in"] = True
            st.session_state["username"] = cookie_user
            return True
    except: pass

    # 3. واجهة الدخول
    st.markdown(f"<h1 style='text-align: center; color: #0052CC;'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["تسجيل الدخول", "إنشاء حساب"])
    
    with tab1:
        with st.form("login"):
            u = st.text_input("اسم المستخدم", key="l_u")
            p = st.text_input("كلمة المرور", type="password", key="l_p")
            if st.form_submit_button("دخول", use_container_width=True):
                if db_verify_user(u, p):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = u
                    cookie_manager.set('osoul_user', u, expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                    st.rerun()
                else:
                    st.error("بيانات خاطئة")

    with tab2:
        with st.form("signup"):
            nu = st.text_input("اسم مستخدم جديد", key="s_u")
            np = st.text_input("كلمة مرور جديدة", type="password", key="s_p")
            if st.form_submit_button("إنشاء حساب", use_container_width=True):
                if nu and np:
                    if db_create_user(nu, np):
                        st.success("تم الإنشاء! يمكنك الدخول الآن.")
                    else:
                        st.error("اسم المستخدم موجود مسبقاً.")
                else:
                    st.warning("أكمل البيانات")
    
    return False

def logout():
    try:
        manager = get_manager()
        manager.delete("osoul_user")
    except: pass
    st.session_state.clear()
    st.rerun()
