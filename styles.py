import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
        
        /* 1. الأساسيات والخطوط (يمين إجباري) */
        html, body, [class*="css"], p, div, label, input, button, textarea, span, h1, h2, h3, h4, h5 {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }
        
        /* ============================================================
           الحل الجذري والنهائي لمشكلة النصوص الإنجليزية (Expand/Collapse)
           ============================================================ */
        
        /* 1. إخفاء أي عنصر يحمل سمة التلميح */
        div[data-baseweb="tooltip"], 
        div[role="tooltip"],
        .stTooltipHoverTarget > span {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }

        /* 2. إخفاء النص الصغير بجانب السهم في القوائم المنسدلة */
        /* هذه الحيلة تخفي النص وتترك الأيقونة أو العنوان العربي فقط */
        .streamlit-expanderHeader p {
            font-size: 1rem !important;
            font-weight: 700 !important;
        }
        
        /* إخفاء أيقونة التوسيع الافتراضية إذا كانت تسبب مشاكل، أو تلوينها */
        .streamlit-expanderHeader svg {
            color: #0052CC !important;
            /* display: none !important;  <-- فعل هذا السطر إذا أردت إخفاء السهم تماماً */
        }
        
        /* إخفاء النص الذي يظهر عند الهوفر على الهيدر */
        .streamlit-expanderHeader:hover {
            color: #0052CC !important;
        }

        /* 3. إخفاء القائمة الجانبية والأدوات العلوية */
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stToolbar"] { display: none !important; }
        footer { display: none !important; }

        /* ============================================================
           باقي التصميم الجميل الخاص بك (البطاقات والجداول)
           ============================================================ */

        /* تصميم الجداول (الرؤوس الزرقاء الفاتحة) */
        .finance-table {
            width: 100%; border-collapse: separate; border-spacing: 0;
            border: 1px solid #E5E7EB; border-radius: 12px;
            overflow: hidden; background: white; margin-top: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.02);
        }
        .finance-table th {
            background-color: #EFF6FF !important; color: #1E40AF !important;
            font-weight: 800; padding: 15px; text-align: right;
            border-bottom: 2px solid #DBEAFE;
        }
        .finance-table td {
            padding: 12px 15px; text-align: right; border-bottom: 1px solid #F1F5F9;
            color: #334155; font-weight: 600;
        }
        .finance-table tr:hover { background-color: #F8FAFC; }
        
        /* البطاقات الحيوية (KPI Cards) */
        .kpi-card {
            background-color: white; border-radius: 20px; padding: 25px 20px;
            position: relative; overflow: hidden; border: 1px solid #F3F4F6;
            box-shadow: 0 4px 6px rgba(0,0,0,0.02); margin-bottom: 15px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .kpi-card:hover {
            transform: translateY(-5px) scale(1.02);
            box-shadow: 0 15px 30px rgba(0,0,0,0.1); border-color: #BFDBFE;
        }
        .kpi-icon-bg {
            position: absolute; left: -10px; bottom: -10px;
            font-size: 4rem; opacity: 0.1; transform: rotate(15deg);
            transition: all 0.3s ease;
        }
        .kpi-card:hover .kpi-icon-bg { transform: rotate(0deg) scale(1.1); opacity: 0.2; }
        .kpi-value { font-size: 1.8rem; font-weight: 900; color: #1E293B; direction: ltr; position: relative; z-index: 2; }
        .kpi-label { color: #64748B; font-size: 0.9rem; font-weight: 700; position: relative; z-index: 2; }

        /* صندوق تاسي */
        .tasi-card {
            background: linear-gradient(135deg, #0052CC 0%, #0033A0 100%);
            border-radius: 20px; padding: 25px; color: white !important;
            display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 10px 25px rgba(0, 82, 204, 0.25); margin-bottom: 25px;
            transition: transform 0.3s ease;
        }
        .tasi-card:hover { transform: translateY(-3px); }

        /* الألوان والأزرار */
        .txt-green { color: #059669 !important; } 
        .txt-red { color: #DC2626 !important; } 
        .txt-blue { color: #2563EB !important; }
        .badge { padding: 4px 12px; border-radius: 99px; font-size: 0.75rem; font-weight: 800; }
        .badge-open { background: #DCFCE7; color: #166534; }
        .badge-closed { background: #F3F4F6; color: #4B5563; }
        
        div.stButton > button {
            width: 100%; border-radius: 12px; height: 50px; font-weight: 800; border: none;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05); background: white; color: #334155; transition: 0.2s;
        }
        div.stButton > button:hover { transform: translateY(-2px); box-shadow: 0 5px 10px rgba(0,0,0,0.1); color: #0052CC; }
        </style>
    """, unsafe_allow_html=True)
