import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl;
        }
        
        /* تصميم الجداول (واسع وأنيق) */
        div[data-testid="stDataFrame"] {
            width: 100%;
            direction: rtl;
        }
        div[data-testid="stDataFrame"] table {
            width: 100%;
        }
        div[data-testid="stDataFrame"] th {
            background-color: #f0f2f6;
            color: #31333F;
            font-weight: 700;
            text-align: right !important;
        }
        div[data-testid="stDataFrame"] td {
            text-align: right !important;
        }
        
        /* القوائم */
        [data-testid="stSidebar"] { display: none; }
        
        /* الأزرار العلوية */
        div.stButton > button {
            width: 100%;
            border-radius: 8px;
            font-weight: bold;
        }
        
        /* البطاقات */
        .kpi-card {
            background: white; padding: 15px; border-radius: 10px;
            border: 1px solid #e0e0e0; text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        </style>
    """, unsafe_allow_html=True)
