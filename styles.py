import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
        
        /* 1. الأساسيات والخطوط (يمين إجباري) */
        html, body, [class*="css"], p, div, label, input, button, textarea, span, h1, h2, h3 {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }
        
        /* === الحل الجذري لمشكلة الكلام الإنجليزي (Expand/Collapse) === */
        /* يخفي أي تلميح (Tooltip) يظهر عند مرور الماوس */
        div[role="tooltip"], 
        .stTooltipHoverTarget > span,
        div[data-baseweb="tooltip"] {
            display: none !important;
            opacity: 0 !important;
            visibility: hidden !important;
        }
        
        /* إخفاء القائمة الجانبية */
        [data-testid="stSidebar"] { display: none !important; }

        /* === 2. تصميم الجداول (الرؤوس الزرقاء الفاتحة) === */
        .finance-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            border: 1px solid #E5E7EB;
            border-radius: 8px;
            overflow: hidden;
            margin-top: 10px;
            background-color: white;
        }
        
        .finance-table th {
            background-color: #F0F8FF !important; /* أزرق فاتح جداً */
            color: #1e3a8a !important; /* كحلي */
            font-weight: 700;
            padding: 12px 15px;
            text-align: right;
            border-bottom: 2px solid #BFDBFE;
            font-size: 0.95rem;
            white-space: nowrap;
        }
        
        .finance-table td {
            padding: 12px 15px;
            text-align: right;
            border-bottom: 1px solid #F3F4F6;
            color: #374151;
            font-size: 0.9rem;
            font-weight: 500;
        }
        
        .finance-table tr:last-child td { border-bottom: none; }
        .finance-table tr:hover { background-color: #F9FAFB; }
        
        /* === 3. البطاقات الحيوية (KPI Cards) === */
        .kpi-card {
            background: white; padding: 15px; border-radius: 12px;
            border: 1px solid #E5E7EB; text-align: right;
            box-shadow: 0 2px 5px rgba(0,0,0,0.02);
            transition: transform 0.2s;
            position: relative; overflow: hidden; margin-bottom: 10px;
        }
        .kpi-card:hover { transform: translateY(-3px); box-shadow: 0 5px 15px rgba(0,0,0,0.08); }
        
        .kpi-bg-icon {
            position: absolute; left: 10px; bottom: 5px;
            font-size: 3rem; opacity: 0.1; transform: rotate(10deg);
        }

        /* === 4. صندوق تاسي (الأزرق المتدرج) === */
        .tasi-card {
            background: linear-gradient(135deg, #0052CC 0%, #0033A0 100%);
            padding: 20px; border-radius: 15px; color: white !important;
            display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 4px 15px rgba(0,82,204,0.2); margin-bottom: 20px;
        }
        
        /* === 5. الشارات والألوان === */
        .badge-open { background-color: #DCFCE7; color: #166534; padding: 4px 12px; border-radius: 99px; font-size: 0.75rem; font-weight: 800; }
        .badge-closed { background-color: #F3F4F6; color: #4B5563; padding: 4px 12px; border-radius: 99px; font-size: 0.75rem; font-weight: 800; }
        .val-pos { color: #059669; font-weight: 700; direction: ltr; }
        .val-neg { color: #DC2626; font-weight: 700; direction: ltr; }
        .val-neu { color: #374151; font-weight: 600; direction: ltr; }
        .val-blue { color: #2563EB; font-weight: 700; direction: ltr; }
        
        /* أزرار التنقل */
        div.stButton > button {
            width: 100%; border-radius: 10px; height: 45px; font-weight: bold;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        </style>
    """, unsafe_allow_html=True)
