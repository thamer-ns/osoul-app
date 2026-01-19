import streamlit as st
import extra_streamlit_components as stx
import datetime
import time
from database import init_db, db_verify_user, db_create_user
from config import APP_NAME, APP_ICON

def get_manager():
    return stx.CookieManager(key="cookie_manager_app")

def login_system():
    # التأكد من تهيئة قاعدة البيانات
    init_db()
    
    # إدارة الكوكيز
    cookie_manager = get_manager()
    
    # 1. فحص الجلسة الحالية (Session State)
    if st.session_state.get("logged_in", False):
        return True
    
    # 2. فحص الكوكيز (للدخول التلقائي)
    time.sleep(0.1) # مهلة بسيطة للكوكيز
    cookie_user = cookie_manager.get(cookie="osoul_user")
    if cookie_user:
        st.session_state["logged_in"] = True
        st.session_state["username"] = cookie_user
        return True

    # 3. واجهة تسجيل الدخول / التسجيل
    st.markdown(f"<h1 style='text-align: center; color: #0e6ba8;'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
    
    # استخدام تبويبات لفصل العمليتين بوضوح
    tab_login, tab_signup = st.tabs(["🔒 تسجيل الدخول", "✨ حساب جديد"])
    
    # --- تبويب الدخول ---
    with tab_login:
        with st.form("login_form"):
            u = st.text_input("اسم المستخدم", key="login_username")
            p = st.text_input("كلمة المرور", type="password", key="login_password")
            submitted = st.form_submit_button("دخول", type="primary", use_container_width=True)
            
            if submitted:
                if db_verify_user(u, p):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = u
                    cookie_manager.set('osoul_user', u, expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                    st.success("تم تسجيل الدخول بنجاح!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("اسم المستخدم أو كلمة المرور غير صحيحة")

    # --- تبويب التسجيل (تم عزله تماماً) ---
    with tab_signup:
        st.markdown("### إنشاء حساب جديد")
        with st.form("signup_form"):
            new_u = st.text_input("اختر اسم مستخدم", key="signup_user")
            new_p = st.text_input("اختر كلمة مرور", type="password", key="signup_pass")
            # زر الإنشاء
            create_submitted = st.form_submit_button("إنشاء الحساب", type="secondary", use_container_width=True)
            
            if create_submitted:
                if new_u and new_p:
                    if db_create_user(new_u, new_p):
                        st.success("تم إنشاء الحساب بنجاح! يمكنك الآن تسجيل الدخول في التبويب المجاور.")
                    else:
                        st.error("اسم المستخدم هذا موجود مسبقاً، الرجاء اختيار اسم آخر.")
                else:
                    st.warning("الرجاء تعبئة جميع الحقول.")

    return False

def logout():
    try:
        manager = get_manager()
        manager.delete("osoul_user")
    except: pass
    
    st.session_state.clear()
    st.rerun()
