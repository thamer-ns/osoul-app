import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
        
        /* 1. إجبار الاتجاه لليمين لكل شيء */
        html, body, [class*="css"], div, p, span, h1, h2, h3, h4, h5, h6, input, button, label {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }
        
        /* 2. إصلاح جداول البيانات */
        div[data-testid="stDataFrame"] { width: 100%; direction: rtl; }
        div[data-testid="stDataFrame"] th { text-align: right !important; }
        div[data-testid="stDataFrame"] td { text-align: right !important; }
        
        /* 3. إخفاء القائمة الجانبية */
        [data-testid="stSidebar"] { display: none !important; }
        
        /* 4. صندوق تاسي (الأزرق المتدرج) */
        .tasi-card {
            background: linear-gradient(135deg, #0052CC 0%, #0033A0 100%);
            color: white !important;
            padding: 20px 25px;
            border-radius: 16px;
            box-shadow: 0 10px 20px rgba(0, 82, 204, 0.2);
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            transition: transform 0.3s ease;
        }
        .tasi-card:hover { transform: translateY(-3px); }
        .tasi-val { font-size: 2.2rem; font-weight: 900; color: white; direction: ltr; }
        .tasi-lbl { font-size: 1rem; opacity: 0.9; color: #E3F2FD; }
        
        /* 5. بطاقات المعلومات (KPI Boxes) الحيوية */
        .kpi-card {
            background-color: white;
            padding: 20px;
            border-radius: 16px;
            border: 1px solid #F0F0F0;
            text-align: right; /* تأكيد اليمين */
            box-shadow: 0 4px 6px rgba(0,0,0,0.02);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        .kpi-card:hover {
            box-shadow: 0 10px 15px rgba(0,0,0,0.08);
            transform: translateY(-5px);
            border-color: #0052CC;
        }
        .kpi-icon {
            font-size: 1.5rem;
            position: absolute;
            left: 15px;
            top: 15px;
            opacity: 0.1;
            transform: scale(2);
        }
        .kpi-label { color: #64748B; font-size: 0.85rem; font-weight: 700; margin-bottom: 8px; }
        .kpi-value { font-size: 1.5rem; font-weight: 800; color: #1E293B; direction: ltr; display: inline-block; }
        
        /* ألوان القيم */
        .txt-blue { color: #0052CC !important; }
        .txt-green { color: #10B981 !important; }
        .txt-red { color: #EF4444 !important; }
        
        /* 6. جداول HTML المخصصة */
        .finance-table { width: 100%; border-collapse: separate; border-spacing: 0; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.03); margin-top: 15px; }
        .finance-table th { background: #F8FAFC; color: #334155; padding: 15px; font-weight: 800; border-bottom: 2px solid #E2E8F0; }
        .finance-table td { padding: 12px 15px; border-bottom: 1px solid #F1F5F9; color: #1E293B; font-weight: 600; }
        .finance-table tr:hover { background-color: #F1F5F9; }
        
        /* شارات الحالة */
        .badge { padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 800; }
        .badge-open { background: #DCFCE7; color: #166534; }
        .badge-closed { background: #F3F4F6; color: #475569; }
        
        /* أزرار التنقل */
        div.stButton > button { width: 100%; border-radius: 10px; height: 50px; font-weight: 800; border: none; box-shadow: 0 2px 4px rgba(0,0,0,0.05); transition: 0.2s; }
        div.stButton > button:hover { transform: scale(1.02); box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        </style>
    """, unsafe_allow_html=True)
