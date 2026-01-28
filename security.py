import streamlit as st
import extra_streamlit_components as stx
import datetime
import time
from database import db_verify_user, db_create_user
from config import APP_NAME, APP_ICON

# =====================================================
# Cookie Manager (Singleton Pattern)
# =====================================================
@st.cache_resource(experimental_allow_widgets=True)
def get_manager():
    return stx.CookieManager(key="osoul_auth_main")

# =====================================================
# Login System
# =====================================================
def login_system():
    """
    نظام دخول ذكي يحافظ على الجلسة حتى بعد التحديث
    """
    st.markdown("""
        <style>
            .login-container { margin-top: 50px; text-align: center; }
            .login-header { color: #0052CC; font-size: 3rem; font-weight: bold; margin-bottom: 10px; }
            .login-sub { color: #666; font-size: 1.2rem; margin-bottom: 30px; }
        </style>
    """, unsafe_allow_html=True)

    cookie_manager = get_manager()
    
    # 1. جلب التوكن من الكوكيز
    # ننتظر قليلاً جداً لضمان وصول الكوكيز من المتصفح (خدعة مهمة في Streamlit)
    time.sleep(0.1) 
    cookies = cookie_manager.get_all()
    user_token = cookies.get("osoul_user")

    # 2. إذا وجدنا كوكيز، نقوم بتسجيل الدخول تلقائياً
    if user_token:
        st.session_state['username'] = user_token
        st.session_state['authenticated'] = True
        return True

    # 3. إذا كان المستخدم مسجل دخول في الجلسة الحالية (بدون كوكيز)
    if st.session_state.get('authenticated', False):
        return True

    # 4. عرض واجهة الدخول (فقط إذا فشلت الخطوات السابقة)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        st.markdown(f'<div class="login-header">{APP_ICON} {APP_NAME}</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-sub">نظام إدارة المحافظ الاستثمارية</div>', unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["🔒 تسجيل دخول", "👤 حساب جديد"])
        
        # --- تبويب الدخول ---
        with tab1:
            with st.form("login_form"):
                u = st.text_input("اسم المستخدم")
                p = st.text_input("كلمة المرور", type="password")
                remember = st.checkbox("تذكرني على هذا الجهاز", value=True)
                
                if st.form_submit_button("دخول", use_container_width=True, type="primary"):
                    if db_verify_user(u, p):
                        st.session_state['authenticated'] = True
                        st.session_state['username'] = u
                        
                        if remember:
                            # حفظ الكوكيز لمدة 30 يوم
                            expires = datetime.datetime.now() + datetime.timedelta(days=30)
                            cookie_manager.set("osoul_user", u, expires_at=expires)
                        
                        st.success("تم الدخول!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("بيانات الدخول غير صحيحة")

        # --- تبويب التسجيل ---
        with tab2:
            with st.form("signup_form"):
                nu = st.text_input("اسم مستخدم جديد")
                np = st.text_input("كلمة مرور جديدة", type="password")
                
                if st.form_submit_button("إنشاء حساب", use_container_width=True):
                    if len(nu) < 3:
                        st.warning("اسم المستخدم قصير جداً")
                    elif db_create_user(nu, np):
                        st.success("تم إنشاء الحساب! سجل دخولك الآن.")
                    else:
                        st.error("اسم المستخدم مستخدم مسبقاً")
            
        st.markdown('</div>', unsafe_allow_html=True)
    
    return False

# =====================================================
# Logout
# =====================================================
def logout():
    cookie_manager = get_manager()
    # حذف الكوكيز من المتصفح
    cookie_manager.delete("osoul_user")
    # تنظيف الجلسة الحالية
    st.session_state['authenticated'] = False
    st.session_state['username'] = None
    st.rerun()
