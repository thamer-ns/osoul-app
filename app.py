import streamlit as st
import extra_streamlit_components as stx
import datetime
import time
from database import init_db, db_verify_user, db_create_user
from config import APP_NAME, APP_ICON, get_css
from views import router

st.set_page_config(page_title=APP_NAME, layout="wide", page_icon=APP_ICON, initial_sidebar_state="collapsed")

if 'custom_colors' not in st.session_state:
    from config import DEFAULT_COLORS
    st.session_state.custom_colors = DEFAULT_COLORS.copy()

if 'page' not in st.session_state:
    st.session_state.page = 'home'

st.markdown(get_css(st.session_state.custom_colors), unsafe_allow_html=True)

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

    st.markdown(f"<h1 style='text-align: center; color: #0e6ba8;'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
    t1, t2 = st.tabs(["دخول", "تسجيل"])
    
    with t1:
        with st.form("l_form"):
            u = st.text_input("مستخدم")
            p = st.text_input("كلمة مرور", type="password")
            if st.form_submit_button("دخول"):
                if db_verify_user(u, p):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = u
                    cookie_manager.set('osoul_user', u, expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                    st.rerun()
                else: st.error("خطأ")
    with t2:
        with st.form("s_form"):
            u = st.text_input("مستخدم جديد")
            p = st.text_input("كلمة مرور", type="password")
            if st.form_submit_button("تسجيل"):
                if db_create_user(u, p): st.success("تم")
                else: st.error("مستخدم موجود")
    return False

if login_system():
    if st.session_state.page == 'logout':
        get_manager().delete("osoul_user")
        st.session_state.clear()
        st.rerun()
    else:
        router()
