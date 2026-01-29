import streamlit as st
import extra_streamlit_components as stx
import datetime
import time
from database import db_verify_user, db_create_user
from config import APP_NAME, APP_ICON

# =====================================================
# 🛡️ 1. نظام التحقق من المدخلات (الجزء الذي كان ناقصاً)
# =====================================================
def validate_trade_inputs(quantity, price):
    """
    دالة مركزية لفحص صحة مدخلات الصفقات قبل إرسالها لقاعدة البيانات.
    تمنع الأخطاء الشائعة (القيم الصفرية، السالبة، النصوص).
    """
    # 1. فحص هل القيم أرقام؟
    try:
        q = float(quantity)
        p = float(price)
    except (ValueError, TypeError):
        return False, "⚠️ الرجاء إدخال أرقام صحيحة في خانة الكمية والسعر"
        
    # 2. فحص المنطق (لا يوجد سعر أو كمية صفرية أو سالبة)
    if q <= 0:
        return False, "⚠️ الكمية يجب أن تكون أكبر من صفر"
    if p <= 0:
        return False, "⚠️ السعر يجب أن يكون أكبر من صفر"
        
    # 3. فحص الحماية من الأرقام الفلكية (اختياري لمنع الأخطاء غير المقصودة)
    if q * p > 1000000000: # مليار
        return False, "⚠️ قيمة الصفقة ضخمة جداً! يرجى التأكد من الأرقام."
        
    return True, ""

# =====================================================
# 🍪 2. Cookie Manager
# =====================================================
def get_manager():
    if "_cookie_manager" not in st.session_state:
        st.session_state._cookie_manager = stx.CookieManager(key="osoul_auth_manager")
    return st.session_state._cookie_manager

# =====================================================
# 🔐 3. Login System
# =====================================================
def login_system():
    """نظام إدارة الدخول والمصادقة"""
    
    # 1. فحص الجلسة الحالية (الأسرع)
    if st.session_state.get("username"):
        return True

    cookie_manager = get_manager()
    time.sleep(0.1) # انتظار استقرار الكوكيز

    # 2. فحص الكوكيز (تذكرني)
    cookie_user = cookie_manager.get("osoul_user")
    if cookie_user:
        st.session_state.username = cookie_user
        st.session_state['authenticated'] = True 
        return True

    # 3. عرض واجهة الدخول
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(f"<h1 style='text-align:center;color:#0052CC'>{APP_ICON} {APP_NAME}</h1>", unsafe_allow_html=True)
        st.markdown("<h5 style='text-align:center;color:#5E6C84'>نظام إدارة المحافظ الاستثمارية</h5>", unsafe_allow_html=True)
        st.markdown("---")

        t1, t2 = st.tabs(["🔒 تسجيل دخول", "👤 حساب جديد"])

        # --- Login ---
        with t1:
            with st.form("login_form", clear_on_submit=False):
                u = st.text_input("اسم المستخدم").strip() # strip لإزالة المسافات الزائدة
                p = st.text_input("كلمة المرور", type="password")
                remember = st.checkbox("تذكرني على هذا الجهاز", value=True)

                if st.form_submit_button("دخول", use_container_width=True, type="primary"):
                    if not u or not p:
                        st.warning("الرجاء إدخال البيانات")
                    elif db_verify_user(u, p):
                        st.session_state.username = u
                        st.session_state['authenticated'] = True
                        
                        if remember:
                            expires = datetime.datetime.now() + datetime.timedelta(days=30)
                            cookie_manager.set("osoul_user", u, expires_at=expires)
                        
                        st.success("تم الدخول بنجاح")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("بيانات غير صحيحة")

        # --- Signup ---
        with t2:
            with st.form("signup_form", clear_on_submit=True):
                nu = st.text_input("اختر اسم مستخدم").strip()
                np = st.text_input("اختر كلمة مرور", type="password")
                
                if st.form_submit_button("إنشاء حساب جديد", use_container_width=True):
                    # تحسين: التحقق من صحة اسم المستخدم
                    if len(nu) < 3:
                        st.warning("اسم المستخدم قصير جداً")
                    elif len(np) < 6:
                        st.warning("كلمة المرور يجب أن تكون 6 خانات على الأقل")
                    elif not nu.isalnum():
                        st.warning("اسم المستخدم يجب أن يحتوي على أحرف وأرقام فقط")
                    elif db_create_user(nu, np):
                        st.success("تم إنشاء الحساب! يمكنك الدخول الآن.")
                    else:
                        st.error("اسم المستخدم مسجل مسبقاً")
    
    return False

# =====================================================
# 🚪 4. Logout
# =====================================================
def logout():
    try:
        cookie_manager = get_manager()
        cookie_manager.delete("osoul_user")
    except Exception:
        pass
    
    st.session_state.clear()
    st.rerun()
