import streamlit as st

def apply_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
        
        /* تعميم الخط */
        html, body, [class*="css"], p, div, label, input, button {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl;
        }
        
        /* إخفاء القائمة الجانبية */
        [data-testid="stSidebar"] { display: none !important; }
        
        /* === تصميم الجداول (مطابق للصور) === */
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
        
        /* الرأس الأزرق الفاتح كما في الصور */
        .finance-table th {
            background-color: #F0F8FF !important; /* لون سماوي فاتح */
            color: #1e3a8a !important; /* كحلي */
            font-weight: 700;
            padding: 12px 15px;
            text-align: right;
            border-bottom: 2px solid #BFDBFE;
            font-size: 0.95rem;
        }
        
        .finance-table td {
            padding: 12px 15px;
            text-align: right;
            border-bottom: 1px solid #F3F4F6;
            color: #374151;
            font-size: 0.9rem;
            font-weight: 500;
        }
        
        /* الصف الأخير بدون خط */
        .finance-table tr:last-child td { border-bottom: none; }
        
        /* تأثير عند المرور */
        .finance-table tr:hover { background-color: #F9FAFB; }
        
        /* === الشارات (Badges) === */
        .badge-open {
            background-color: #DCFCE7; color: #166534;
            padding: 4px 12px; border-radius: 9999px;
            font-size: 0.75rem; font-weight: 800;
        }
        .badge-closed {
            background-color: #F3F4F6; color: #4B5563;
            padding: 4px 12px; border-radius: 9999px;
            font-size: 0.75rem; font-weight: 800;
        }
        
        /* === الأرقام الملونة === */
        .val-pos { color: #059669; font-weight: 700; direction: ltr; }
        .val-neg { color: #DC2626; font-weight: 700; direction: ltr; }
        .val-neu { color: #374151; font-weight: 600; direction: ltr; }
        .val-blue { color: #2563EB; font-weight: 700; direction: ltr; }
        
        /* === بطاقات الملخص العلوية === */
        .summary-card {
            background: white; padding: 15px; border-radius: 12px;
            border: 1px solid #E5E7EB; text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        </style>
    """, unsafe_allow_html=True)
