import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        /* 1. إعدادات الخط والاتجاه */
        html, body, [class*="css"], p, div, label, input, button, textarea, span, h1, h2, h3, h4, h5, h6 {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }

        /* 2. إخفاء القوائم والهوامش الافتراضية */
        [data-testid="stSidebar"] { display: none !important; }
        footer { display: none !important; }
        #MainMenu { display: none !important; }
        header { display: none !important; }

        /* ============================================================
           3. المنطقة المحظورة (إخفاء العناصر الإنجليزية)
           ============================================================ */
        
        /* إخفاء شريط أدوات الجداول والشارتات (Search, Download, Fullscreen) */
        [data-testid="stElementToolbar"] { display: none !important; }
        [data-testid="stToolbar"] { display: none !important; }
        
        /* إخفاء حاوية التلميحات (Tooltips) بالكامل */
        div[role="tooltip"] { display: none !important; visibility: hidden !important; opacity: 0 !important; }
        [data-testid="stTooltipHoverTarget"] > div { display: none !important; }

        /* إخفاء الأزرار التي تحتوي على نصوص إنجليزية في تلميحاتها */
        button[title*="View fullscreen"], 
        button[title*="Expand"], 
        button[title*="Collapse"],
        button[aria-label*="Options"] {
            display: none !important;
        }

        /* إخفاء علامة "keyboard" التي تظهر أحياناً في الحقول */
        div[data-testid="stMarkdownContainer"] p:contains("Press Enter to apply") { display: none !important; }
        
        /* إخفاء أيقونة تكبير الصور */
        button[title="View fullscreen"] { display: none !important; }

        /* ============================================================ */

        /* 4. تنسيق الاكسباندر (Expander) */
        div[data-testid="stExpander"] {
            border: 1px solid #E5E7EB; border-radius: 12px; background-color: #FAFAFA;
            margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }
        div[data-testid="stExpander"] details summary {
            font-weight: 800 !important; color: #0052CC !important; padding: 10px 15px !important;
        }
        /* إخفاء التلميح الخاص بالسهم */
        div[data-testid="stExpander"] details summary svg title { display: none !important; }

        /* 5. تنسيق البطاقات (KPI Cards) */
        .kpi-card {
            background-color: white; border-radius: 20px; padding: 25px 20px;
            position: relative; overflow: hidden; border: 1px solid #F3F4F6;
            box-shadow: 0 4px 6px rgba(0,0,0,0.02); margin-bottom: 15px;
            transition: all 0.3s;
        }
        .kpi-card:hover { transform: translateY(-5px); box-shadow: 0 15px 30px rgba(0,0,0,0.1); border-color: #BFDBFE; }
        
        .kpi-icon-bg {
            position: absolute; left: -15px; bottom: -20px; font-size: 5.5rem; 
            opacity: 0.08; transform: rotate(15deg); color: #1E293B; pointer-events: none;
        }
        
        .kpi-value { font-size: 1.8rem; font-weight: 900; color: #1E293B; direction: ltr; }
        .kpi-label { color: #64748B; font-size: 0.9rem; font-weight: 700; margin-bottom: 5px; }

        /* 6. تنسيق الجداول */
        .finance-table {
            width: 100%; border-collapse: separate; border-spacing: 0;
            border: 1px solid #E5E7EB; border-radius: 12px; overflow: hidden;
            background: white; margin-top: 15px;
        }
        .finance-table th { background-color: #F0F8FF !important; color: #1E40AF !important; padding: 15px; }
        .finance-table td { padding: 12px 15px; border-bottom: 1px solid #F1F5F9; color: #334155; }
        
        /* 7. الألوان والبادجات */
        .txt-green { color: #059669 !important; } .txt-red { color: #DC2626 !important; } .txt-blue { color: #2563EB !important; }
        .badge-open { background: #DCFCE7; color: #166534; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; }
        .badge-closed { background: #F3F4F6; color: #4B5563; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; }
        
        /* 8. الأزرار */
        div.stButton > button {
            width: 100%; border-radius: 12px; height: 50px; font-weight: 800; border: none;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05); background: white; color: #334155;
        }
        div.stButton > button:hover { transform: translateY(-2px); color: #0052CC; }

        /* بطاقة تاسي */
        .tasi-card {
            background: linear-gradient(135deg, #0052CC 0%, #0033A0 100%);
            border-radius: 20px; padding: 25px; color: white !important;
            display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 10px 25px rgba(0, 82, 204, 0.25); margin-bottom: 25px;
        }
        </style>
    """, unsafe_allow_html=True)
