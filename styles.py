import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        /* 1. الأساسيات والخطوط */
        html, body, [class*="css"], p, div, label, input, button, textarea, span {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }
        
        /* إخفاء القائمة الجانبية والعناصر المزعجة */
        [data-testid="stSidebar"] { display: none !important; }
        div[data-testid="stExpander"] details summary svg { display: none !important; }
        [data-testid="stTooltipHoverTarget"] > span { display: none !important; }

        /* 2. البطاقات الحيوية (KPI Cards) - التصميم الذي تحبه */
        .kpi-card {
            background-color: white;
            border-radius: 20px;
            padding: 25px 20px;
            position: relative;
            overflow: hidden;
            border: 1px solid #F3F4F6;
            box-shadow: 0 4px 6px rgba(0,0,0,0.02);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            margin-bottom: 15px;
        }
        
        /* التفاعل والحركة عند مرور الماوس */
        .kpi-card:hover {
            transform: translateY(-5px) scale(1.02);
            box-shadow: 0 15px 30px rgba(0,0,0,0.1);
            border-color: #BFDBFE;
        }
        
        /* الأيقونة الخلفية الكبيرة */
        .kpi-icon-bg {
            position: absolute;
            left: -10px;
            bottom: -10px;
            font-size: 4rem;
            opacity: 0.1;
            transform: rotate(15deg);
            transition: all 0.3s ease;
        }
        .kpi-card:hover .kpi-icon-bg {
            transform: rotate(0deg) scale(1.1);
            opacity: 0.2;
        }
        
        .kpi-value {
            font-size: 1.8rem;
            font-weight: 900;
            color: #1E293B;
            direction: ltr;
            position: relative;
            z-index: 2;
        }
        
        .kpi-label {
            color: #64748B;
            font-size: 0.9rem;
            font-weight: 700;
            position: relative;
            z-index: 2;
        }

        /* 3. صندوق تاسي (الأزرق الفخم) */
        .tasi-card {
            background: linear-gradient(135deg, #0052CC 0%, #0033A0 100%);
            border-radius: 20px;
            padding: 25px;
            color: white !important;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 10px 25px rgba(0, 82, 204, 0.25);
            margin-bottom: 25px;
            transition: transform 0.3s ease;
        }
        .tasi-card:hover { transform: translateY(-3px); }

        /* 4. الجداول الاحترافية */
        .finance-table {
            width: 100%; border-collapse: separate; border-spacing: 0;
            border: 1px solid #E5E7EB; border-radius: 12px;
            overflow: hidden; background: white; margin-top: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.02);
        }
        .finance-table th {
            background-color: #EFF6FF !important; /* أزرق فاتح جداً */
            color: #1E40AF !important; /* كحلي */
            font-weight: 800; padding: 15px; text-align: right;
            border-bottom: 2px solid #DBEAFE;
        }
        .finance-table td {
            padding: 12px 15px; text-align: right;
            border-bottom: 1px solid #F1F5F9; color: #334155; font-weight: 600;
        }
        .finance-table tr:hover { background-color: #F8FAFC; }
        
        /* 5. الألوان المخصصة */
        .txt-green { color: #059669 !important; }
        .txt-red { color: #DC2626 !important; }
        .txt-blue { color: #2563EB !important; }
        
        /* شارات الحالة */
        .badge { padding: 4px 12px; border-radius: 99px; font-size: 0.75rem; font-weight: 800; }
        .badge-open { background: #DCFCE7; color: #166534; }
        .badge-closed { background: #F3F4F6; color: #4B5563; }

        /* أزرار التنقل */
        div.stButton > button {
            width: 100%; border-radius: 12px; height: 50px; font-weight: 800;
            border: none; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            background: white; color: #334155;
            transition: 0.2s;
        }
        div.stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 10px rgba(0,0,0,0.1);
            color: #0052CC;
        }
        div.stButton > button:focus { border: 2px solid #0052CC; color: #0052CC; }
        </style>
    """, unsafe_allow_html=True)
