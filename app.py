import streamlit as st
import extra_streamlit_components as stx
import datetime
import time
from database import init_db, db_verify_user, db_create_user
from config import APP_NAME, APP_ICON
from styles import apply_custom_css
from views import router

st.set_page_config(page_title=APP_NAME, page_icon=APP_ICON, layout="wide")
apply_custom_css()

def get_manager():
    return stx.CookieManager(key="cookie_manager_app")

def login_system():
    init_db()
    cookie_manager = get_manager()
    
    if st.session_state.get("logged_in", False):
        return True
    
    time.sleep(0.1)
    cookie_user = cookie_manager.get(cookie="osoul_user")
    if cookie_user:
        st.session_state["logged_in"] = True
        st.session_state["username"] = cookie_user
        return True

    st.markdown(f"<h1 style='text-align: center; color: #0e6ba8;'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
    
    tab_login, tab_signup = st.tabs(["🔒 تسجيل الدخول", "✨ حساب جديد"])
    
    with tab_login:
        with st.form("login_form"):
            u = st.text_input("اسم المستخدم", key="login_username")
            p = st.text_input("كلمة المرور", type="password", key="login_password")
            if st.form_submit_button("دخول", type="primary", use_container_width=True):
                if db_verify_user(u, p):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = u
                    cookie_manager.set('osoul_user', u, expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                    st.success("تم الدخول!"); time.sleep(0.5); st.rerun()
                else:
                    st.error("بيانات الدخول غير صحيحة")

    with tab_signup:
        with st.form("signup_form"):
            new_u = st.text_input("اسم مستخدم جديد", key="signup_user")
            new_p = st.text_input("كلمة مرور", type="password", key="signup_pass")
            if st.form_submit_button("إنشاء حساب", type="secondary", use_container_width=True):
                # التحديث هنا: استلام النجاح والرسالة
                success, msg = db_create_user(new_u, new_p)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
    return False

if __name__ == "__main__":
    if login_system():
        router()
