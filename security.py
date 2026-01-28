import streamlit as st
import extra_streamlit_components as stx
import datetime
import time  # ✅ إضافة مكتبة الوقت
from database import db_verify_user, db_create_user
from config import APP_NAME, APP_ICON

# =====================================================
# Cookie Manager
# هذا الجزء سليم وممتاز لتجنب الـ Crashes
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
    """
    
    # 1. فحص الجلسة الحالية (الأسرع)
    if st.session_state.get("username"):
        return True

    cookie_manager = get_manager()

    # ✅ الإضافة الوحيدة للأفضل: 
    # انتظار جزء من الثانية لضمان وصول الكوكيز من المتصفح قبل الحكم
    time.sleep(0.1)

    # 2. فحص الكوكيز (تذكرني)
    cookie_user = cookie_manager.get("osoul_user")
    if cookie_user:
        st.session_state.username = cookie_user
        # تحديث الحالة لتجنب إعادة التحميل المستمر
        st.session_state['authenticated'] = True 
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
                
                # إضافة زر "تذكرني" كخيار إضافي (ميزة للأفضل)
                remember = st.checkbox("تذكرني على هذا الجهاز", value=True)

                if st.form_submit_button("دخول", use_container_width=True, type="primary"):
                    if not u or not p:
                        st.warning("الرجاء إدخال اسم المستخدم وكلمة المرور")
                    elif db_verify_user(u, p):
                        st.session_state.username = u
                        st.session_state['authenticated'] = True
                        
                        if remember:
                            # صلاحية الكوكيز 30 يوم
                            expires = datetime.datetime.now() + datetime.timedelta(days=30)
                            cookie_manager.set("osoul_user", u, expires_at=expires)
                        
                        st.success("تم الدخول بنجاح")
                        time.sleep(0.5) # انتظار بسيط لتثبيت الكوكيز
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
    """تسجيل الخروج الآمن"""
    try:
        cookie_manager = get_manager()
        cookie_manager.delete("osoul_user")
    except Exception:
        pass
    
    st.session_state.clear()
    st.rerun()
