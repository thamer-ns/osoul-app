import streamlit as st
import extra_streamlit_components as stx
import datetime
import time
from database import db_verify_user, db_create_user
from config import APP_NAME, APP_ICON

# --- 1. Validation Helper ---
def validate_trade_inputs(quantity, price):
    try:
        q = float(quantity)
        p = float(price)
    except:
        return False, "الرجاء إدخال أرقام صحيحة"
    if q <= 0 or p <= 0:
        return False, "القيم يجب أن تكون أكبر من صفر"
    return True, ""

# --- 2. Cookie Manager ---
def get_manager():
    if "_cookie_manager" not in st.session_state:
        st.session_state._cookie_manager = stx.CookieManager(key="osoul_auth_manager")
    return st.session_state._cookie_manager

# --- 3. Login System (This is what app.py needs!) ---
def login_system():
    # 1. Check Session
    if st.session_state.get("username"):
        return True

    # 2. Check Cookies
    cookie_manager = get_manager()
    time.sleep(0.1)
    cookie_user = cookie_manager.get("osoul_user")
    if cookie_user:
        st.session_state.username = cookie_user
        st.session_state['authenticated'] = True 
        return True

    # 3. Show Login UI
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(f"<h1 style='text-align:center;color:#0052CC'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
        t1, t2 = st.tabs(["🔒 دخول", "👤 تسجيل"])
        
        with t1:
            with st.form("login_form"):
                u = st.text_input("المستخدم")
                p = st.text_input("كلمة المرور", type="password")
                rem = st.checkbox("تذكرني", value=True)
                if st.form_submit_button("دخول", type="primary"):
                    if db_verify_user(u, p):
                        st.session_state.username = u
                        if rem:
                            expires = datetime.datetime.now() + datetime.timedelta(days=30)
                            cookie_manager.set("osoul_user", u, expires_at=expires)
                        st.success("تم الدخول")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("خطأ في البيانات")

        with t2:
            with st.form("signup_form"):
                nu = st.text_input("مستخدم جديد")
                np = st.text_input("كلمة مرور جديدة", type="password")
                if st.form_submit_button("إنشاء"):
                    if db_create_user(nu, np):
                        st.success("تم الإنشاء! سجل دخولك الآن.")
                    else:
                        st.error("حدث خطأ")
    
    return False

def logout():
    try:
        get_manager().delete("osoul_user")
    except: pass
    st.session_state.clear()
    st.rerun()
