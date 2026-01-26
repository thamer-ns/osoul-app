import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        html, body, [class*="css"], p, div, label, input, textarea, th, td, h1, h2, h3, button {
            font-family: 'Cairo', sans-serif !important; 
            direction: rtl;
        }
        
        /* إخفاء القائمة الجانبية تماماً كما طلبت */
        [data-testid="stSidebar"] { display: none !important; }
        
        /* تنسيق الأزرار العلوية لتكون بجانب بعضها */
        div.stButton > button {
            width: 100%;
            border-radius: 8px;
            font-weight: bold;
            height: 45px;
        }

        /* تنسيق الجداول لتكون واسعة وواضحة */
        div[data-testid="stDataFrame"] {
            width: 100%;
            direction: rtl;
        }
        
        thead tr th:first-child { display:none }
        tbody th { display:none }
        
        /* صناديق KPI */
        .kpi-card {
            background-color: white;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #eee;
            text-align: center;
            box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
        }
        
        /* صندوق تاسي */
        .tasi-box {
            background: white;
            padding: 20px;
            border-radius: 12px;
            border: 1px solid #e0e0e0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.04);
        }
        </style>
    """, unsafe_allow_html=True)
