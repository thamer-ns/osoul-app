import streamlit as st
import extra_streamlit_components as stx
import datetime
import time
from database import db_verify_user, db_create_user
from config import APP_NAME, APP_ICON

# === START ADDITION: Input Validation ===
def validate_trade_inputs(quantity, price):
    """
    التحقق من صحة مدخلات التداول.
    تعيد (True, "") في حال النجاح، أو (False, "رسالة الخطأ").
    """
    try:
        q = float(quantity)
        p = float(price)
    except:
        return False, "الرجاء إدخال أرقام صحيحة"
        
    if q <= 0:
        return False, "⚠️ الكمية يجب أن تكون أكبر من صفر"
    if p <= 0:
        return False, "⚠️ السعر يجب أن يكون أكبر من صفر"
    if q * p > 100000000: # مثال: حد أقصى للحماية من الأخطاء الكارثية
        return False, "⚠️ قيمة الصفقة تبدو ضخمة جداً، يرجى التأكد!"
        
    return True, ""
# === END ADDITION ===

def get_manager():
    if "_cookie_manager" not in st.session_state:
        st.session_state._cookie_manager = stx.CookieManager(key="osoul_auth_manager")
    return st.session_state._cookie_manager

def login_system():
    """نظام إدارة الدخول والمصادقة"""
    
    # 1. فحص الجلسة الحالية (الأسرع)
    if st.session_state.get("username"):
        return True

    cookie_manager = get_manager()
    time.sleep(0.1) # استقرار الكوكيز

    # 2. فحص الكوكيز
    cookie_user = cookie_manager.get("osoul_user")
    if cookie_user:
        st.session_state.username = cookie_user
        st.session_state['authenticated'] = True 
        return True

    # 3. واجهة الدخول
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(f"<h1 style='text-align:center;color:#0052CC'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
        st.markdown("<h5 style='text-align:center;color:#5E6C84'>نظام إدارة المحافظ الاستثمارية</h5>", unsafe_allow_html=True)
        st.markdown("---")

        t1, t2 = st.tabs(["🔒 تسجيل دخول", "👤 حساب جديد"])

        with t1:
            with st.form("login_form", clear_on_submit=False):
                u = st.text_input("اسم المستخدم").strip()
                p = st.text_input("كلمة المرور", type="password")
                remember = st.checkbox("تذكرني على هذا الجهاز", value=True)

                if st.form_submit_button("دخول", use_container_width=True, type="primary"):
                    if not u or not p:
                        st.warning("البيانات ناقصة")
                    elif db_verify_user(u, p):
                        st.session_state.username = u
                        st.session_state['authenticated'] = True
                        if remember:
                            expires = datetime.datetime.now() + datetime.timedelta(days=30)
                            cookie_manager.set("osoul_user", u, expires_at=expires)
                        st.success("تم الدخول"); time.sleep(0.5); st.rerun()
                    else:
                        st.error("بيانات غير صحيحة")

        with t2:
            with st.form("signup_form", clear_on_submit=True):
                nu = st.text_input("اختر اسم مستخدم").strip()
                np = st.text_input("اختر كلمة مرور", type="password")
                if st.form_submit_button("إنشاء حساب"):
                    if len(nu) < 3 or len(np) < 6:
                        st.warning("الاسم قصير أو كلمة المرور ضعيفة")
                    elif db_create_user(nu, np):
                        st.success("تم الإنشاء، سجل دخولك الآن")
                    else:
                        st.error("المستخدم موجود مسبقاً")
    return False

def logout():
    try:
        cookie_manager = get_manager()
        cookie_manager.delete("osoul_user")
    except: pass
    st.session_state.clear()
    st.rerun()
