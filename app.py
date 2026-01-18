import streamlit as st
import pandas as pd
from database import init_db
from logic import get_financial_summary
import views
import charts 
from config import DEFAULT_COLORS, PRESET_THEMES, get_master_styles, APP_NAME, APP_ICON
import hmac

# 1. إعداد الصفحة
st.set_page_config(page_title=APP_NAME, layout="wide", page_icon=APP_ICON, initial_sidebar_state="collapsed")

# --- دالة التحقق من الأمان (جديد) ---
def check_password():
    """Returns `True` if the user had a correct password."""

    def password_entered():
        # التحقق من كلمة المرور الموجودة في Secrets
        if hmac.compare_digest(st.session_state["password"], st.secrets["passwords"]["my_password"]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # لا نحتفظ بكلمة المرور في الذاكرة
        else:
            st.session_state["password_correct"] = False

    # إذا تم التحقق مسبقاً بنجاح
    if st.session_state.get("password_correct", False):
        return True

    # عرض حقل إدخال كلمة المرور
    st.markdown(
        """
        <style>
        .stTextInput > div > div > input {
            text-align: center; 
            font-family: 'Courier New', Courier, monospace;
        }
        </style>
        """, unsafe_allow_html=True
    )
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown(f"<h1 style='text-align: center;'>🔒 {APP_NAME} - محمي</h1>", unsafe_allow_html=True)
        st.info("يرجى إدخال كلمة المرور للوصول إلى البيانات المالية")
        st.text_input("كلمة المرور", type="password", on_change=password_entered, key="password")
        
        if "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("😕 كلمة المرور غير صحيحة")

    return False

# 2. تنفيذ الحماية قبل تحميل أي شيء
if not check_password():
    st.stop()  # توقف هنا إذا لم تكن كلمة المرور صحيحة

# ---------------------------------------------------------
# ما بعد هذا الخط لا يعمل إلا بعد تسجيل الدخول الصحيح
# ---------------------------------------------------------

# 3. تهيئة الألوان
if 'custom_colors' not in st.session_state:
    st.session_state.custom_colors = DEFAULT_COLORS.copy()
else:
    for key, value in DEFAULT_COLORS.items():
        if key not in st.session_state.custom_colors:
            st.session_state.custom_colors[key] = value

if 'init' not in st.session_state:
    init_db()
    st.session_state['init'] = True
    st.session_state['page'] = 'home'

C = st.session_state.custom_colors

# 4. CSS
st.markdown(get_master_styles(C), unsafe_allow_html=True)

# 5. التشغيل
views.render_navbar()

page = st.session_state.page
fin_data = get_financial_summary()

if page == 'home': views.view_dashboard(fin_data)
elif page == 'spec': views.view_portfolio(fin_data, "مضاربة")
elif page == 'invest': views.view_portfolio(fin_data, "استثمار")
elif page == 'cash': views.view_liquidity()
elif page == 'analysis': charts.view_analysis(fin_data)
elif page == 'add': views.view_add_trade()
elif page == 'settings': views.view_settings()
