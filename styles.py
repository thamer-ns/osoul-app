import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
        
        /* 1. تعميم الخط والاتجاه */
        html, body, [class*="css"], p, div, label, input, button, textarea {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }
        
        /* 2. إخفاء القائمة الجانبية */
        [data-testid="stSidebar"] { display: none !important; }
        
        /* 3. إخفاء تلميحات Streamlit الإنجليزية المزعجة */
        div[data-testid="stExpander"] details summary svg {
            display: none !important; /* إخفاء السهم الصغير إذا كان يسبب مشاكل */
        }
        div[data-testid="stExpander"] details summary:hover {
            color: #0052CC !important;
        }
        /* إخفاء نص "Expand" الذي يظهر عند الماوس */
        [data-testid="stTooltipHoverTarget"] > span {
            display: none !important;
        }

        /* 4. تصميم الجداول (الرأس الأزرق) */
        .finance-table {
            width: 100%; border-collapse: separate; border-spacing: 0;
            border: 1px solid #E5E7EB; border-radius: 8px;
            overflow: hidden; background: white; margin-top: 10px;
        }
        .finance-table th {
            background-color: #F0F8FF !important; color: #1e3a8a !important;
            font-weight: 700; padding: 12px 15px; text-align: right;
            border-bottom: 2px solid #BFDBFE;
        }
        .finance-table td {
            padding: 12px 15px; text-align: right;
            border-bottom: 1px solid #F3F4F6; color: #374151; font-weight: 500;
        }
        
        /* 5. الألوان والشارات */
        .badge-open { background: #DCFCE7; color: #166534; padding: 2px 8px; border-radius: 10px; font-size: 0.8rem; }
        .badge-closed { background: #F3F4F6; color: #4B5563; padding: 2px 8px; border-radius: 10px; font-size: 0.8rem; }
        .val-pos { color: #059669; font-weight: 700; direction: ltr; }
        .val-neg { color: #DC2626; font-weight: 700; direction: ltr; }
        .val-blue { color: #0052CC; font-weight: 700; direction: ltr; }

        /* 6. صندوق تاسي */
        .tasi-box {
            background: linear-gradient(135deg, #0052CC 0%, #0033A0 100%);
            padding: 20px; border-radius: 15px; color: white !important;
            display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 4px 15px rgba(0,82,204,0.2); margin-bottom: 20px;
        }

        /* 7. أزرار التنقل */
        div.stButton > button {
            width: 100%; border-radius: 8px; height: 45px; font-weight: bold;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        </style>
    """, unsafe_allow_html=True)
