import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        /* 1. استيراد الخطوط */
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        @import url('https://fonts.googleapis.com/icon?family=Material+Icons');

        /* 2. تطبيق الخط العربي والاتجاه على (النصوص فقط) */
        /* حصرنا التأثير هنا لكي لا يتأثر ترتيب الحقول أو الأيقونات */
        html, body, p, h1, h2, h3, h4, h5, h6, label, input, button, textarea, 
        .stMarkdown, .stSelectbox div, .stNumberInput input, .stTab {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }

        /* 3. ✅ إصلاح الأيقونات (السر في هذا الجزء) */
        /* استهداف دقيق جداً للأيقونات في الأزرار، القوائم، والاكسباندر */
        .material-icons,
        [class*="material-icons"],
        [data-testid="stExpander"] summary span,
        [data-testid="stPopover"] button span,
        [data-testid="stPopoverBody"] span,
        [data-testid="stHeader"] i,
        i {
            font-family: 'Material Icons' !important;
            direction: ltr !important; /* الأيقونات يجب أن تكون LTR لتظهر الرموز */
            text-align: center !important;
            display: inline-block !important;
            font-weight: normal !important;
            font-style: normal !important;
            line-height: 1 !important;
            text-transform: none !important;
            white-space: nowrap !important;
            word-wrap: normal !important;
            vertical-align: middle !important;
        }

        /* 4. تنظيف الواجهة (إخفاء العناصر غير الضرورية فقط) */
        [data-testid="stSidebar"], footer, header, #MainMenu { display: none !important; }
        [data-testid="stElementToolbar"] { display: none !important; }
        div[role="tooltip"] { display: none !important; }

        /* 5. تصميم البطاقات (KPI) - حافظنا على نفس شكلك المفضل */
        .kpi-card {
            background-color: white; border-radius: 20px; padding: 25px 20px;
            position: relative; overflow: hidden; border: 1px solid #F3F4F6;
            box-shadow: 0 4px 6px rgba(0,0,0,0.02); margin-bottom: 15px;
        }
        .kpi-icon-bg {
            position: absolute; left: -15px; bottom: -20px; font-size: 5.5rem;
            opacity: 0.08; transform: rotate(15deg); color: #1E293B; pointer-events: none;
        }
        .kpi-value { font-size: 1.8rem; font-weight: 900; color: #1E293B; direction: ltr; }

        /* 6. تنسيق الجداول (Finance Table) */
        .finance-table {
            width: 100%; border-collapse: separate; border-spacing: 0;
            border: 1px solid #E5E7EB; border-radius: 12px; overflow: hidden;
            background: white; margin-top: 15px;
        }
        .finance-table th { background-color: #F0F8FF !important; color: #1E40AF !important; padding: 15px; }
        .finance-table td { padding: 12px 15px; border-bottom: 1px solid #F1F5F9; }

        /* 7. الأزرار العامة */
        div.stButton > button {
            width: 100%; border-radius: 12px; height: 50px; font-weight: 800;
            background: white; color: #334155; transition: 0.2s;
        }
        div.stButton > button:hover { color: #0052CC; transform: translateY(-2px); }

        /* بطاقة تاسي */
        .tasi-card {
            background: linear-gradient(135deg, #0052CC 0%, #0033A0 100%);
            border-radius: 20px; padding: 25px; color: white !important;
            display: flex; justify-content: space-between; align-items: center;
        }
        </style>
    """, unsafe_allow_html=True)
