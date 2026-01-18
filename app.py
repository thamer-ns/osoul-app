import streamlit as st
from config import APP_NAME, APP_ICON, DEFAULT_COLORS, get_css
from security import login_system, logout
from views import router

st.set_page_config(page_title=APP_NAME, layout="wide", page_icon=APP_ICON, initial_sidebar_state="collapsed")

if 'custom_colors' not in st.session_state:
    st.session_state.custom_colors = DEFAULT_COLORS.copy()
    
if 'page' not in st.session_state:
    st.session_state.page = 'home'

st.markdown(get_css(st.session_state.custom_colors), unsafe_allow_html=True)

if login_system():
    if st.session_state.page == 'logout':
        logout()
    else:
        router()
