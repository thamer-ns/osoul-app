import streamlit as st
import extra_streamlit_components as stx
import datetime
import time
from database import db_verify_user, db_create_user
from config import APP_NAME, APP_ICON

# التعديل هنا: حذفنا experimental_allow_widgets لأنها تسبب خطأ في النسخ الحديثة
@st.cache_resource
def get_manager():
    return stx.CookieManager(key="osoul_auth_manager")

def login_system():
    """
    نظام إدارة الدخول. يعيد True إذا كان المستخدم مسجلاً، وإلا يعرض نموذج الدخول ويعيد False.
    """
    # 1. إذا كان مسجلاً في الجلسة الحالية، انتهينا
    if 'username' in st.session_state:
        return True

    # 2. محاولة استرجاع المستخدم من الكوكيز (تذكرني)
    cookie_manager = get_manager()
    
    # انتظار قصير لضمان قراءة الكوكيز
    time.sleep(0.1)
    
    cookie_user = cookie_manager.get('osoul_user')
    if cookie_user:
        st.session_state.username = cookie_user
        return True

    # 3. عرض واجهة الدخول إذا لم ينجح ما سبق
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(f"<h1 style='text-align: center; color: #0052CC;'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
        st.markdown("<h5 style='text-align: center; color: #5E6C84;'>نظام إدارة المحافظ الاستثمارية</h5>", unsafe_allow_html=True)
        st.markdown("---")

        t1, t2 = st.tabs(["🔒 تسجيل دخول", "👤 حساب جديد"])
        
        # تبويب الدخول
        with t1:
            with st.form("login_form"):
                u = st.text_input("اسم المستخدم")
                p = st.text_input("كلمة المرور", type="password")
                
                if st.form_submit_button("دخول", use_container_width=True, type="primary"):
                    if db_verify_user(u, p):
                        st.session_state.username = u
                        # حفظ الكوكيز لمدة 30 يوم
                        expires = datetime.datetime.now() + datetime.timedelta(days=30)
                        cookie_manager.set('osoul_user', u, expires_at=expires)
                        st.rerun()
                    else:
                        st.error("اسم المستخدم أو كلمة المرور غير صحيحة")

        # تبويب التسجيل
        with t2:
            with st.form("signup_form"):
                nu = st.text_input("اختر اسم مستخدم")
                np = st.text_input("اختر كلمة مرور", type="password")
                
                if st.form_submit_button("إنشاء حساب جديد", use_container_width=True):
                    if len(nu) < 3 or len(np) < 3:
                        st.warning("يجب أن تكون البيانات 3 أحرف على الأقل")
                    elif db_create_user(nu, np):
                        st.success("تم إنشاء الحساب بنجاح! يمكنك الدخول الآن.")
                    else:
                        st.error("اسم المستخدم مسجل مسبقاً، اختر اسماً آخر.")
    
    return False

def logout():
    """تسجيل الخروج: حذف الكوكيز وتنظيف الجلسة"""
    try:
        cookie_manager = get_manager()
        cookie_manager.delete('osoul_user')
    except:
        pass
        
    # حذف جميع متغيرات الجلسة
    for key in list(st.session_state.keys()):
        del st.session_state[key]
        
    st.rerun()
