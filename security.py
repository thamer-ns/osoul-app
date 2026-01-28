import streamlit as st
import extra_streamlit_components as stx
import datetime
from database import db_verify_user, db_create_user
from config import APP_NAME, APP_ICON

# =====================================================
# Cookie Manager
# التغيير: استخدام session_state بدلاً من cache_resource لضمان استقرار المكون
# =====================================================
def get_manager():
    if "_cookie_manager" not in st.session_state:
        st.session_state._cookie_manager = stx.CookieManager(key="osoul_auth_manager")
    return st.session_state._cookie_manager

# =====================================================
# Login System
# =====================================================
def login_system():
    """
    نظام إدارة الدخول.
    - يعيد True إذا كان المستخدم مسجلاً
    - يعرض واجهة الدخول إذا لم يكن مسجلاً
    """
    
    # 1. فحص الجلسة الحالية (Session Check)
    if st.session_state.get("username"):
        return True

    cookie_manager = get_manager()

    # 2. فحص الكوكيز (تذكرني)
    # ملاحظة: قد تحتاج لضغط زر تحديث الصفحة أحياناً ليعمل هذا الجزء إذا كان الاتصال بطيئاً
    cookie_user = cookie_manager.get("osoul_user")
    if cookie_user:
        st.session_state.username = cookie_user
        return True

    # 3. عرض واجهة الدخول (Login UI)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(
            f"<h1 style='text-align:center;color:#0052CC'>{APP_ICON} {APP_NAME}</h1>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<h5 style='text-align:center;color:#5E6C84'>نظام إدارة المحافظ الاستثمارية</h5>",
            unsafe_allow_html=True,
        )
        st.markdown("---")

        t1, t2 = st.tabs(["🔒 تسجيل دخول", "👤 حساب جديد"])

        # ---------------- Login ----------------
        with t1:
            with st.form("login_form", clear_on_submit=False):
                u = st.text_input("اسم المستخدم")
                p = st.text_input("كلمة المرور", type="password")
                
                if st.form_submit_button("دخول", use_container_width=True, type="primary"):
                    if not u or not p:
                        st.warning("الرجاء إدخال اسم المستخدم وكلمة المرور")
                    elif db_verify_user(u, p):
                        st.session_state.username = u
                        # صلاحية الكوكيز 30 يوم
                        expires = datetime.datetime.now() + datetime.timedelta(days=30)
                        cookie_manager.set("osoul_user", u, expires_at=expires)
                        st.rerun()
                    else:
                        st.error("اسم المستخدم أو كلمة المرور غير صحيحة")

        # ---------------- Signup ----------------
        with t2:
            with st.form("signup_form", clear_on_submit=True):
                nu = st.text_input("اختر اسم مستخدم")
                np = st.text_input("اختر كلمة مرور", type="password")
                
                if st.form_submit_button("إنشاء حساب جديد", use_container_width=True):
                    if len(nu) < 3 or len(np) < 6:
                        st.warning("يجب أن يكون اسم المستخدم 3 أحرف على الأقل، وكلمة المرور 6 أحرف.")
                    elif db_create_user(nu, np):
                        st.success("تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن.")
                    else:
                        st.error("اسم المستخدم مسجل مسبقاً، الرجاء اختيار اسم آخر.")
    
    return False

# =====================================================
# Logout
# =====================================================
def logout():
    """تسجيل الخروج الآمن: حذف الكوكيز وتنظيف الجلسة"""
    try:
        cookie_manager = get_manager()
        cookie_manager.delete("osoul_user")
    except Exception:
        pass
    
    # مسح كامل الجلسة
    st.session_state.clear()
    st.rerun()
