import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
        
        html, body, [class*="css"], p, div, label, input, button {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl;
        }
        
        /* إخفاء القائمة الجانبية */
        [data-testid="stSidebar"] { display: none !important; }
        
        /* === صندوق تاسي (التصميم القديم الجميل) === */
        .tasi-box {
            background: linear-gradient(135deg, #0052CC 0%, #0747A6 100%);
            padding: 20px;
            border-radius: 16px;
            color: white !important;
            display: flex; 
            justify-content: space-between; 
            align-items: center;
            margin-bottom: 20px;
            box-shadow: 0 4px 12px rgba(0, 82, 204, 0.2);
        }
        
        /* === جداول البيانات === */
        .finance-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            border: 1px solid #E5E7EB;
            border-radius: 8px;
            overflow: hidden;
            background: white;
            margin-top: 10px;
        }
        .finance-table th {
            background-color: #F0F8FF !important;
            color: #1e3a8a !important;
            font-weight: 700;
            padding: 12px 15px;
            text-align: right;
            border-bottom: 2px solid #BFDBFE;
        }
        .finance-table td {
            padding: 12px 15px;
            text-align: right;
            border-bottom: 1px solid #F3F4F6;
            color: #374151;
            font-weight: 500;
        }
        .finance-table tr:last-child td { border-bottom: none; }
        .finance-table tr:hover { background-color: #F9FAFB; }
        
        /* الشارات والألوان */
        .badge-open { background-color: #DCFCE7; color: #166534; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 800; }
        .badge-closed { background-color: #F3F4F6; color: #4B5563; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 800; }
        .val-pos { color: #059669; font-weight: 700; direction: ltr; }
        .val-neg { color: #DC2626; font-weight: 700; direction: ltr; }
        .val-neu { color: #374151; font-weight: 600; direction: ltr; }
        .val-blue { color: #2563EB; font-weight: 700; direction: ltr; }

        div.stButton > button { width: 100%; border-radius: 8px; font-weight: bold; height: 45px; }
        </style>
    """, unsafe_allow_html=True)
