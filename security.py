import streamlit as st
import extra_streamlit_components as stx
import datetime, time
from database import db_verify_user, db_create_user
from config import APP_NAME, APP_ICON

@st.cache_resource(experimental_allow_widgets=True)
def get_manager(): return stx.CookieManager(key="auth")

def login_system():
    if 'username' in st.session_state: return True
    mgr = get_manager(); time.sleep(0.1); u = mgr.get('user')
    if u: st.session_state.username = u; return True

    c1,c2,c3 = st.columns([1,2,1])
    with c2:
        st.markdown(f"<h1 style='text-align:center;'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
        t1, t2 = st.tabs(["دخول", "جديد"])
        with t1:
            with st.form("l"):
                u=st.text_input("مستخدم"); p=st.text_input("رمز", type="password")
                if st.form_submit_button("دخول", use_container_width=True):
                    if db_verify_user(u,p): 
                        st.session_state.username=u; mgr.set('user',u,expires_at=datetime.datetime.now()+datetime.timedelta(days=30)); st.rerun()
                    else: st.error("خطأ")
        with t2:
            with st.form("s"):
                nu=st.text_input("مستخدم"); np=st.text_input("رمز", type="password")
                if st.form_submit_button("إنشاء", use_container_width=True):
                    if db_create_user(nu,np): st.success("تم"); st.info("سجل دخولك الآن")
                    else: st.error("موجود")
    return False

def logout():
    try: get_manager().delete('user')
    except: pass
    for k in list(st.session_state.keys()): del st.session_state[k]
    st.rerun()
