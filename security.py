import streamlit as st
import extra_streamlit_components as stx
import datetime
import time
from database import init_db, db_verify_user, db_create_user
from config import APP_NAME, APP_ICON

# --- التعديل هنا: تم إزالة @st.cache_resource نهائياً ---
# لأن مدير الكوكيز يجب أن يتم تحميله مع كل تحديث للصفحة لضمان الاتصال
def get_manager():
    return stx.CookieManager(key="cookie_manager_app")

def login_system():
    init_db()
    # تأخير بسيط جداً لضمان تحميل المكونات
    time.sleep(0.1)
    
    # استدعاء المدير مباشرة بدون كاش
    cookie_manager = get_manager()
    
    # التحقق مما إذا كان المستخدم مسجل دخول بالفعل في الجلسة
    if st.session_state.get("logged_in", False): return True
    
    # محاولة جلب المستخدم من الكوكيز
    try:
        cookie_user = cookie_manager.get(cookie="osoul_user")
        if cookie_user:
            st.session_state["logged_in"] = True
            st.session_state["username"] = cookie_user
            return True
    except: pass

    # واجهة تسجيل الدخول
    st.markdown(f"<h1 style='text-align: center; color: #0052CC;'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["تسجيل الدخول", "حساب جديد"])
    
    with t1:
        u = st.text_input("المستخدم", key="l_u")
        p = st.text_input("كلمة المرور", type="password", key="l_p")
        if st.button("دخول", type="primary", use_container_width=True):
            if db_verify_user(u, p):
                st.session_state["logged_in"] = True
                st.session_state["username"] = u
                # حفظ الكوكيز لمدة 30 يوم
                cookie_manager.set('osoul_user', u, expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                st.rerun()
            else:
                st.error("بيانات خاطئة")

    with t2:
        nu = st.text_input("اسم مستخدم جديد", key="r_u")
        np = st.text_input("رمز سري جديد", type="password", key="r_p")
        if st.button("إنشاء حساب", type="secondary", use_container_width=True):
            if nu and np:
                if db_create_user(nu, np):
                    st.success("تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن.")
                else:
                    st.error("اسم المستخدم موجود مسبقاً")
            else:
                st.warning("الرجاء تعبئة جميع الحقول")

    return False

def logout():
    try:
        get_manager().delete("osoul_user")
    except: pass
    st.session_state.clear()
    st.rerun()
