import streamlit as st

def apply_custom_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
        
        html, body, [class*="css"], [data-testid="stAppViewContainer"] {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl;
        }
        
        /* إخفاء القائمة الجانبية */
        [data-testid="stSidebar"] { display: none; }
        .block-container { padding-top: 1rem; padding-bottom: 5rem; }

        /* تنسيق العناوين */
        h1, h2, h3, h4 { color: #172B4D; text-align: right; font-weight: 800; }
        
        /* إخفاء العناوين الإنجليزية للحقول */
        div[data-testid="stSelectbox"] > label, div[data-testid="stTextInput"] > label,
        div[data-testid="stNumberInput"] > label, div[data-testid="stDateInput"] > label { 
            display: none; 
        }
        
        /* تنسيق الحقول */
        input, .stTextInput input, .stNumberInput input, .stSelectbox, .stDateInput input {
            border-radius: 8px !important;
            padding: 8px !important;
            border: 1px solid #DFE1E6 !important;
            text-align: right !important;
            font-family: 'Cairo' !important;
        }

        /* تنسيق الجداول المتقدم */
        .finance-table-container {
            background-color: white;
            border-radius: 12px;
            border: 1px solid #DFE1E6;
            overflow-x: auto;
            margin-bottom: 20px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.03);
        }
        .finance-table { width: 100%; border-collapse: collapse; min-width: 800px; }
        .finance-table th {
            background-color: #F4F5F7;
            color: #5E6C84;
            font-weight: 700;
            padding: 12px 15px;
            text-align: right;
            border-bottom: 2px solid #DFE1E6;
            white-space: nowrap !important;
        }
        .finance-table td {
            padding: 12px 15px;
            text-align: right;
            border-bottom: 1px solid #DFE1E6;
            color: #172B4D;
            white-space: nowrap !important;
            font-size: 0.9rem;
        }
        .finance-table tr:hover { background-color: #FAFBFC; }
        
        /* البطاقات */
        .kpi-box {
            background-color: white;
            border: 1px solid #DFE1E6;
            border-radius: 12px;
            padding: 15px;
            text-align: right;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
            transition: transform 0.2s;
        }
        .kpi-box:hover { transform: translateY(-2px); }
        
        /* صندوق تاسي */
        .tasi-box {
            background: linear-gradient(135deg, #0052CC 0%, #0747A6 100%);
            padding: 20px;
            border-radius: 16px;
            color: white !important;
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 20px;
            box-shadow: 0 4px 12px rgba(0, 82, 204, 0.2);
        }
        
        /* الناف بار */
        .navbar-box {
            background-color: white;
            padding: 10px 20px;
            border-radius: 16px;
            border: 1px solid #DFE1E6;
            margin-bottom: 20px;
            display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.03);
        }
    </style>
    """, unsafe_allow_html=True)
