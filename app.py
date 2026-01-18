import streamlit as st
import pandas as pd
from database import init_db
from logic import get_financial_summary
import views
import charts 
from config import DEFAULT_COLORS, PRESET_THEMES, get_master_styles

# 1. إعداد الصفحة
st.set_page_config(page_title="أصولي", layout="wide", page_icon="🏛️", initial_sidebar_state="collapsed")

# 2. تهيئة الألوان
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

# 3. CSS (تطبيق الحل النهائي للسواد)
st.markdown(get_master_styles(C), unsafe_allow_html=True)

# 4. التشغيل
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