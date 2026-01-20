# styles.py
import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        /* 1. استيراد خط Cairo لدعم العربية والأرقام بشكل ممتاز */
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');

        /* 2. تعميم الخط والاتجاه على كامل التطبيق */
        html, body, [class*="css"], [data-testid="stAppViewContainer"] {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl;
        }

        /* 3. تنسيق العناوين (بدون رموز، لون مريح، محاذاة يمين) */
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Cairo', sans-serif !important;
            text-align: right !important;
            color: #1e293b; /* لون كحلي غامق رسمي */
            padding-bottom: 10px;
        }

        /* 4. تنسيق الجداول (أهم جزء) */
        /* إجبار النص على البقاء في سطر واحد */
        div[data-testid="stDataFrame"] table {
            direction: rtl;
            width: 100%;
        }
        
        div[data-testid="stDataFrame"] th {
            text-align: right !important;
            background-color: #f1f5f9; /* لون خلفية العناوين */
            color: #0f172a;
            font-weight: 700;
            white-space: nowrap !important; /* ممنوع النزول لسطر ثاني */
        }
        
        div[data-testid="stDataFrame"] td {
            text-align: right !important;
            white-space: nowrap !important; /* ممنوع النزول لسطر ثاني */
            font-size: 15px;
            font-family: 'Cairo', sans-serif !important;
        }

        /* 5. إخفاء هوامش وعناصر غير ضرورية */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        
        /* إخفاء زر القائمة الافتراضي في الجداول لتحسين المظهر */
        button[title="View fullscreen"] {
            visibility: visible;
        }
        </style>
    """, unsafe_allow_html=True)
