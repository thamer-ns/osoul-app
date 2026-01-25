import streamlit as st

def apply_custom_css():
    st.markdown("""
    <style>
        /* 1. استيراد خط Cairo */
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');

        /* 2. تعميم الخط والاتجاه */
        html, body, [class*="css"], [data-testid="stAppViewContainer"] {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl;
        }

        /* 3. تنسيق العناوين */
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Cairo', sans-serif !important;
            text-align: right !important;
            color: #172B4D; 
        }

        /* 4. إخفاء القائمة الجانبية والعناصر المزعجة */
        [data-testid="stSidebar"] { display: none; }
        .block-container { padding-top: 2rem; padding-bottom: 5rem; }
        
        /* 5. تحسين الحقول والقوائم */
        input, .stTextInput input, .stNumberInput input, .stSelectbox, .stDateInput input {
            border-radius: 10px !important;
            padding: 10px !important;
            font-family: 'Cairo' !important;
        }
        
        /* إخفاء عناوين القوائم المنسدلة (الحل الجذري للكلام الإنجليزي) */
        div[data-testid="stSelectbox"] > label { display: none; }
        div[data-testid="stTextInput"] > label { display: none; }
        div[data-testid="stNumberInput"] > label { display: none; }
        div[data-testid="stDateInput"] > label { display: none; }

        /* 6. تنسيق الجداول (HTML Tables) */
        .finance-table-container {
            background-color: white;
            border-radius: 12px;
            border: 1px solid #DFE1E6;
            overflow-x: auto;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        .finance-table { width: 100%; border-collapse: collapse; min-width: 600px; }
        .finance-table th {
            background-color: #F4F5F7;
            color: #5E6C84;
            font-weight: 700;
            padding: 12px 15px;
            text-align: right;
            border-bottom: 2px solid #DFE1E6;
            white-space: nowrap;
        }
        .finance-table td {
            padding: 12px 15px;
            text-align: right;
            border-bottom: 1px solid #DFE1E6;
            color: #172B4D;
            white-space: nowrap;
        }
        .finance-table tr:hover { background-color: #FAFBFC; }
        
        /* 7. بطاقة تاسي */
        .tasi-box {
            background: linear-gradient(135deg, #0052CC 0%, #172B4D 100%);
            padding: 25px;
            border-radius: 16px;
            color: white !important;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            box-shadow: 0 4px 15px rgba(0, 82, 204, 0.2);
        }
        
        /* 8. بطاقات KPI */
        .kpi-box {
            background-color: white;
            border: 1px solid #DFE1E6;
            border-radius: 12px;
            padding: 20px;
            text-align: right;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
            transition: transform 0.2s;
        }
        .kpi-box:hover { transform: translateY(-3px); }
        
        /* 9. الناف بار */
        .navbar-box {
            background-color: white;
            padding: 15px 20px;
            border-radius: 16px;
            border: 1px solid #DFE1E6;
            margin-bottom: 25px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.03);
        }
    </style>
    """, unsafe_allow_html=True)
