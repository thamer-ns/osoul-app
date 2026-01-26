import streamlit as st
import streamlit.components.v1 as components

def apply_custom_css():
    # 1. كود جافا سكريبت لإزالة العناوين الإنجليزية (Expand/Collapse) من المتصفح
    # هذا الكود يعمل في الخلفية ويمسح أي تلميح إنجليزي يظهر
    st.markdown("""
        <script>
        document.addEventListener('DOMContentLoaded', (event) => {
            const observer = new MutationObserver(() => {
                // البحث عن العناصر التي تحمل تلميحات إنجليزية وحذفها
                const elements = document.querySelectorAll('[title="Expand"], [title="Collapse"], [title="View fullscreen"], [aria-label="Expand"], [aria-label="Collapse"]');
                elements.forEach(el => {
                    el.removeAttribute('title');
                    el.removeAttribute('aria-label');
                });
            });
            observer.observe(document.body, { childList: true, subtree: true });
        });
        </script>
    """, unsafe_allow_html=True)

    # 2. تصميم CSS (الواجهة العربية الحيوية)
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        /* === أساسيات الواجهة (يمين) === */
        html, body, [class*="css"], p, div, label, input, button, textarea, span, h1, h2, h3 {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }
        
        /* إخفاء القائمة الجانبية */
        [data-testid="stSidebar"] { display: none !important; }
        
        /* === إخفاء بقايا التلميحات بصرياً === */
        div[role="tooltip"], .stTooltipHoverTarget > span {
            visibility: hidden !important;
            opacity: 0 !important;
            display: none !important;
        }
        
        /* إخفاء سهم القائمة المنسدلة (لأنه مصدر التلميح) */
        div[data-testid="stExpander"] details summary svg {
            display: none !important;
        }
        
        /* تنسيق القائمة المنسدلة لتعويض السهم */
        div[data-testid="stExpander"] {
            border: 1px solid #E5E7EB;
            border-radius: 12px;
            background-color: #FAFAFA;
            margin-bottom: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }
        div[data-testid="stExpander"] details summary {
            font-weight: 800 !important;
            color: #0052CC !important; /* لون أزرق للعنوان */
            padding-right: 15px !important;
        }

        /* === البطاقات الحيوية (KPI Cards) مع الأيقونات === */
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
        
        /* الحركة والتفاعل (Hover) */
        .kpi-card:hover {
            transform: translateY(-5px) scale(1.01);
            box-shadow: 0 15px 30px rgba(0,0,0,0.1);
            border-color: #BFDBFE;
        }
        
        /* الأيقونة الخلفية الباهتة */
        .kpi-icon-bg {
            position: absolute;
            left: -10px; 
            bottom: -15px;
            font-size: 5rem; 
            opacity: 0.08;
            transform: rotate(15deg);
            transition: all 0.3s ease;
            color: #1E293B;
            pointer-events: none; /* كي لا تعيق النص */
        }
        
        /* تحريك الأيقونة عند الماوس */
        .kpi-card:hover .kpi-icon-bg { 
            transform: rotate(0deg) scale(1.1); 
            opacity: 0.15;
            left: -5px;
        }
        
        .kpi-value { font-size: 1.8rem; font-weight: 900; color: #1E293B; direction: ltr; position: relative; z-index: 2; }
        .kpi-label { color: #64748B; font-size: 0.9rem; font-weight: 700; position: relative; z-index: 2; margin-bottom: 5px; }

        /* === صندوق تاسي (الأزرق المتدرج) === */
        .tasi-card {
            background: linear-gradient(135deg, #0052CC 0%, #0033A0 100%);
            border-radius: 20px; padding: 25px; color: white !important;
            display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 10px 25px rgba(0, 82, 204, 0.25); margin-bottom: 25px;
            transition: transform 0.3s ease;
        }
        .tasi-card:hover { transform: translateY(-3px); }

        /* === جداول البيانات (الرؤوس الزرقاء) === */
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
        
        /* === الأزرار والألوان === */
        .txt-green { color: #059669 !important; } .txt-red { color: #DC2626 !important; } .txt-blue { color: #2563EB !important; }
        .badge { padding: 4px 12px; border-radius: 99px; font-size: 0.75rem; font-weight: 800; }
        .badge-open { background: #DCFCE7; color: #166534; } .badge-closed { background: #F3F4F6; color: #4B5563; }
        
        div.stButton > button {
            width: 100%; border-radius: 12px; height: 50px; font-weight: 800; border: none;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05); background: white; color: #334155; transition: 0.2s;
        }
        div.stButton > button:hover { transform: translateY(-2px); box-shadow: 0 5px 10px rgba(0,0,0,0.1); color: #0052CC; }
        </style>
    """, unsafe_allow_html=True)
