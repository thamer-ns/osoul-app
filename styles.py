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

        /* تنسيق الجداول الفاخر */
        .finance-table-container {
            background-color: white;
            border-radius: 12px;
            border: 1px solid #DFE1E6;
            overflow-x: auto;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.02);
        }
        .finance-table { width: 100%; border-collapse: collapse; min-width: 900px; }
        .finance-table th {
            background-color: #F4F5F7;
            color: #172B4D;
            font-weight: 800;
            padding: 14px 15px;
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
            font-size: 0.95rem;
            font-weight: 600;
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
        .kpi-box:hover { transform: translateY(-3px); border-color: #0052CC; }
        
        /* صندوق تاسي */
        .tasi-box {
            background: linear-gradient(135deg, #0052CC 0%, #0747A6 100%);
            padding: 25px;
            border-radius: 16px;
            color: white !important;
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 20px;
            box-shadow: 0 8px 20px rgba(0, 82, 204, 0.25);
        }
        
        /* الناف بار */
        .navbar-box {
            background-color: white;
            padding: 12px 25px;
            border-radius: 16px;
            border: 1px solid #DFE1E6;
            margin-bottom: 25px;
            display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 4px 10px rgba(0,0,0,0.03);
        }
    </style>
    """, unsafe_allow_html=True)
