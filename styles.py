import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');

        html, body, [class*="css"], [data-testid="stAppViewContainer"] {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl;
        }

        h1, h2, h3, h4, h5, h6 {
            font-family: 'Cairo', sans-serif !important;
            text-align: right !important;
            color: #1e293b;
            padding-bottom: 10px;
        }

        div[data-testid="stDataFrame"] table {
            direction: rtl;
            width: 100%;
        }
        
        div[data-testid="stDataFrame"] th {
            text-align: right !important;
            background-color: #f1f5f9;
            color: #0f172a;
            font-weight: 700;
            white-space: nowrap !important;
        }
        
        div[data-testid="stDataFrame"] td {
            text-align: right !important;
            white-space: nowrap !important;
            font-size: 15px;
            font-family: 'Cairo', sans-serif !important;
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        
        [data-testid="stSidebar"] { display: none !important; }
        
        /* تنسيق التبويبات */
        .stTabs [data-baseweb="tab-list"] { gap: 10px; }
        .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #fff; border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .stTabs [aria-selected="true"] { background-color: #e6f0ff !important; color: #0052cc !important; border: 1px solid #0052cc; }
        </style>
    """, unsafe_allow_html=True)
