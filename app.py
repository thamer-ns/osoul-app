import streamlit as st
from config import get_css, APP_NAME, APP_ICON
from database import init_db
from views import router

st.set_page_config(page_title=APP_NAME, page_icon=APP_ICON, layout="wide")
st.markdown(get_css(), unsafe_allow_html=True)

if 'init' not in st.session_state:
    init_db()
    st.session_state.init = True

if 'page' not in st.session_state: st.session_state.page = 'home'

router()
