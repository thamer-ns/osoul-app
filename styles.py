import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
        
        /* 1. الأساسيات (يمين) */
        html, body, [class*="css"], p, div, label, input, button, textarea, span {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }
        
        /* 2. === إخفاء الإنجليزي والتلميحات (صارم جداً) === */
        div[role="tooltip"], .stTooltipHoverTarget > span, div[data-baseweb="tooltip"] {
            display: none !important;
            opacity: 0 !important;
            visibility: hidden !important;
        }
        /* إخفاء سهم القائمة المنسدلة */
        div[data-testid="stExpander"] details summary svg { display: none !important; }
        
        /* إخفاء القائمة الجانبية */
        [data-testid="stSidebar"] { display: none !important; }

        /* 3. === البطاقات الحيوية (KPI Cards) مع الأيقونات === */
        .kpi-card {
            background-color: white;
            border-radius: 20px;
            padding: 25px 20px;
            position: relative;
            overflow: hidden; /* مهم لقص الأيقونة الخلفية */
            border: 1px solid #F3F4F6;
            box-shadow: 0 4px 6px rgba(0,0,0,0.02);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); /* نعومة الحركة */
            margin-bottom: 15px;
        }
        
        /* حركة البطاقة عند مرور الماوس */
        .kpi-card:hover {
            transform: translateY(-7px) scale(1.01);
            box-shadow: 0 15px 30px rgba(0,0,0,0.1);
            border-color: #BFDBFE;
        }
        
        /* الأيقونة الخلفية الباهتة (التي تسأل عنها) */
        .kpi-icon-bg {
            position: absolute;
            left: -15px; 
            bottom: -20px;
            font-size: 5.5rem; 
            opacity: 0.07; /* شفافية عالية */
            transform: rotate(15deg);
            transition: all 0.4s ease;
            color: #1E293B;
            pointer-events: none;
        }
        
        /* حركة الأيقونة عند الماوس */
        .kpi-card:hover .kpi-icon-bg { 
            transform: rotate(0deg) scale(1.2); 
            opacity: 0.15;
            left: -5px;
        }
        
        .kpi-value { font-size: 1.8rem; font-weight: 900; color: #1E293B; direction: ltr; position: relative; z-index: 2; }
        .kpi-label { color: #64748B; font-size: 0.9rem; font-weight: 700; position: relative; z-index: 2; margin-bottom: 5px; }

        /* 4. صندوق تاسي المتدرج */
        .tasi-card {
            background: linear-gradient(135deg, #0052CC 0%, #0033A0 100%);
            border-radius: 20px; padding: 25px; color: white !important;
            display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 10px 25px rgba(0, 82, 204, 0.25); margin-bottom: 25px;
            transition: transform 0.3s ease;
        }
        .tasi-card:hover { transform: translateY(-3px); }

        /* 5. الجداول الزرقاء */
        .finance-table {
            width: 100%; border-collapse: separate; border-spacing: 0;
            border: 1px solid #E5E7EB; border-radius: 12px;
            overflow: hidden; background: white; margin-top: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.02);
        }
        .finance-table th {
            background-color: #F0F8FF !important; color: #1E40AF !important;
            font-weight: 800; padding: 15px; text-align: right;
            border-bottom: 2px solid #DBEAFE;
        }
        .finance-table td {
            padding: 12px 15px; text-align: right; border-bottom: 1px solid #F1F5F9;
            color: #334155; font-weight: 600;
        }
        .finance-table tr:hover { background-color: #F8FAFC; }
        
        /* 6. الأزرار والألوان */
        .txt-green { color: #059669 !important; } .txt-red { color: #DC2626 !important; } .txt-blue { color: #2563EB !important; }
        .badge { padding: 4px 12px; border-radius: 99px; font-size: 0.75rem; font-weight: 800; }
        .badge-open { background: #DCFCE7; color: #166534; } .badge-closed { background: #F3F4F6; color: #4B5563; }
        
        div.stButton > button {
            width: 100%; border-radius: 12px; height: 50px; font-weight: 800; border: none;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05); background: white; color: #334155; transition: 0.2s;
        }
        div.stButton > button:hover { transform: translateY(-2px); box-shadow: 0 5px 10px rgba(0,0,0,0.1); color: #0052CC; }
        
        /* تنسيق القوائم المنسدلة */
        div[data-testid="stExpander"] { border: 1px solid #E5E7EB; border-radius: 12px; background-color: #FAFAFA; margin-bottom: 10px; }
        div[data-testid="stExpander"] details summary { font-family: 'Cairo'; font-weight: 700; color: #1F293B; }
        div[data-testid="stExpander"] details summary:hover { color: #0052CC !important; }
        </style>
    """, unsafe_allow_html=True)
