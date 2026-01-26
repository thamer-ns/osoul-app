import streamlit as st
import time
from database import db_verify_user, db_create_user

def login_system():
    # تهيئة حالة الدخول
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    if st.session_state.logged_in:
        return True

    st.markdown("<br><br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    
    with c2:
        st.markdown("""
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #0052CC;">💎 أصولي</h1>
            <p style="color: #5E6C84;">بوابتك الذكية للاستثمار</p>
        </div>
        """, unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["تسجيل دخول", "مستخدم جديد"])
        
        with tab1:
            with st.form("login"):
                u = st.text_input("اسم المستخدم")
                p = st.text_input("كلمة المرور", type="password")
                if st.form_submit_button("دخول", use_container_width=True):
                    if db_verify_user(u, p):
                        st.session_state.logged_in = True
                        st.session_state.username = u
                        st.success("تم الدخول!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("بيانات خاطئة")
        
        with tab2:
            with st.form("signup"):
                nu = st.text_input("اسم مستخدم جديد")
                np = st.text_input("كلمة مرور جديدة", type="password")
                if st.form_submit_button("إنشاء حساب", use_container_width=True):
                    if nu and np:
                        if db_create_user(nu, np):
                            st.success("تم إنشاء الحساب، يمكنك الدخول الآن")
                        else:
                            st.error("اسم المستخدم موجود مسبقاً")
                    else:
                        st.warning("الرجاء تعبئة الحقول")

    return False

def logout():
    st.session_state.logged_in = False
    st.rerun()
