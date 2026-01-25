import streamlit as st
from config import APP_NAME, APP_ICON
from styles import apply_custom_css 
from security import login_system, logout
from views import router

st.set_page_config(
    page_title=APP_NAME, 
    page_icon=APP_ICON, 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

apply_custom_css()

if 'page' not in st.session_state:
    st.session_state.page = 'home'

if login_system():
    if st.session_state.page == 'logout':
        logout()
    else:
        router()
