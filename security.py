import streamlit as st
from database import db_verify_user, db_create_user
import time

def login_system():
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if st.session_state.logged_in:
        return True

    # تصميم شاشة الدخول
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    
    with c2:
        st.markdown("""
        <div style="text-align: center; margin-bottom: 20px;">
            <div style="font-size: 4rem;">💎</div>
            <h1 style="color: #0052CC;">نظام أصولي</h1>
            <p style="color: #666;">بوابتك الذكية لإدارة الاستثمارات</p>
        </div>
        """, unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["تسجيل دخول", "إنشاء حساب"])
        
        with tab1:
            with st.form("login_form"):
                u = st.text_input("اسم المستخدم")
                p = st.text_input("كلمة المرور", type="password")
                if st.form_submit_button("دخول", use_container_width=True):
                    if db_verify_user(u, p):
                        st.session_state.logged_in = True
                        st.session_state.username = u
                        st.success("تم الدخول بنجاح!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("اسم المستخدم أو كلمة المرور غير صحيحة")

        with tab2:
            with st.form("register_form"):
                new_u = st.text_input("اسم مستخدم جديد")
                new_p = st.text_input("كلمة مرور جديدة", type="password")
                if st.form_submit_button("تسجيل جديد", use_container_width=True):
                    if new_u and new_p:
                        if db_create_user(new_u, new_p):
                            st.success("تم إنشاء الحساب! يمكنك تسجيل الدخول الآن.")
                        else:
                            st.error("حدث خطأ (ربما الاسم مستخدم سابقاً).")
                    else:
                        st.warning("الرجاء تعبئة الحقول.")
    
    return False

def logout():
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.rerun()
