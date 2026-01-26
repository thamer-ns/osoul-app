import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        /* 1. استيراد الخطوط */
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        @import url('https://fonts.googleapis.com/icon?family=Material+Icons');

        /* 2. تطبيق الخط العربي والاتجاه (بدون المساس بالحاويات الهيكلية) */
        html, body, p, label, input, button, textarea, h1, h2, h3, h4, 
        [data-testid="stMarkdownContainer"] p {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }

        /* 3. ✅ الحل الجذري للأيقونات (القائمة المنبثقة والاكسباندر) */
        /* استهدفنا الـ span الذي يحتوي على النصوص البرمجية للأيقونات حصراً */
        .material-icons,
        [class*="material-icons"],
        [data-testid="stExpander"] summary span,
        [data-testid="stPopover"] button span,
        [data-testid="stPopoverBody"] span,
        i {
            font-family: 'Material Icons' !important;
            direction: ltr !important;
            text-align: center !important;
            display: inline-block !important;
            line-height: 1 !important;
            vertical-align: middle !important;
            font-weight: normal !important;
            letter-spacing: normal !important;
            text-transform: none !important;
            white-space: nowrap !important;
        }

        /* 4. تنظيف الواجهة */
        [data-testid="stSidebar"], footer, header, #MainMenu { display: none !important; }
        [data-testid="stElementToolbar"] { display: none !important; }
        div[role="tooltip"] { display: none !important; }
        button[title="View fullscreen"] { display: none !important; }

        /* 5. تنسيق الاكسباندر (Expander) */
        div[data-testid="stExpander"] {
            border: 1px solid #E5E7EB; border-radius: 12px; background-color: #FAFAFA;
            margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }
        div[data-testid="stExpander"] details summary {
            font-weight: 800 !important; color: #0052CC !important; padding: 10px 15px !important;
            flex-direction: row-reverse; /* لضمان بقاء السهم في مكانه الصحيح */
        }

        /* 6. تنسيق البطاقات (KPI Cards) */
        .kpi-card {
            background-color: white; border-radius: 20px; padding: 25px 20px;
            position: relative; overflow: hidden; border: 1px solid #F3F4F6;
            box-shadow: 0 4px 6px rgba(0,0,0,0.02); transition: all 0.3s;
            margin-bottom: 15px;
        }
        .kpi-icon-bg {
            position: absolute; left: -15px; bottom: -20px; font-size: 5.5rem; opacity: 0.08;
            transform: rotate(15deg); color: #1E293B; pointer-events: none;
        }
        .kpi-value { font-size: 1.8rem; font-weight: 900; color: #1E293B; direction: ltr; position: relative; z-index: 2; }
        .kpi-label { color: #64748B; font-size: 0.9rem; font-weight: 700; position: relative; z-index: 2; margin-bottom: 5px; }

        /* 7. تنسيق الجداول */
        .finance-table {
            width: 100%; border-collapse: separate; border-spacing: 0;
            border: 1px solid #E5E7EB; border-radius: 12px; overflow: hidden;
            background: white; margin-top: 15px;
        }
        .finance-table th { background-color: #F0F8FF !important; color: #1E40AF !important; font-weight: 800; padding: 15px; }
        .finance-table td { padding: 12px 15px; border-bottom: 1px solid #F1F5F9; font-weight: 600; }
        
        /* 8. الأزرار */
        div.stButton > button {
            width: 100%; border-radius: 12px; height: 50px; font-weight: 800; border: none;
            background: white; color: #334155; transition: 0.2s; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        div.stButton > button:hover { transform: translateY(-2px); color: #0052CC; }

        .tasi-card {
            background: linear-gradient(135deg, #0052CC 0%, #0033A0 100%);
            border-radius: 20px; padding: 25px; color: white !important;
            display: flex; justify-content: space-between; align-items: center;
        }
        </style>
    """, unsafe_allow_html=True)
