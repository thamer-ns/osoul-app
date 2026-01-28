import streamlit as st
from config import APP_NAME, APP_ICON
from styles import apply_custom_css
from security import login_system
from views import router
from database import init_db

st.set_page_config(page_title=APP_NAME, page_icon=APP_ICON, layout="wide", initial_sidebar_state="collapsed")
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>", unsafe_allow_html=True)

if 'db_initialized' not in st.session_state:
    try: init_db(); st.session_state['db_initialized']=True
    except Exception as e: st.error(f"DB Error: {e}"); st.stop()

apply_custom_css()

if 'page' not in st.session_state: st.session_state.page = 'home'

if login_system(): router()
