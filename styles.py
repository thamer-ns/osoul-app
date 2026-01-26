import streamlit as st

def apply_custom_css():
    # === 1. JavaScript (الحل النهائي) ===
    # نستخدم st.markdown لنكون في نفس سياق الصفحة (وليس iframe)
    st.markdown("""
        <script>
        (function() {
            // دالة تقوم بتفريغ السمات بدلاً من حذفها (لخداع React)
            function killTooltips() {
                // 1. استهداف جميع العناصر التي قد تحمل تلميحات
                const elements = document.querySelectorAll('[title], [aria-label], [data-testid="stExpander"] summary');
                
                const badWords = /expand|collapse|fullscreen|view|zoom|keyboard|more|less|open|close|options|menu/i;
                
                elements.forEach(el => {
                    // معالجة العنوان title
                    if (el.hasAttribute('title')) {
                        const t = el.getAttribute('title');
                        if (t && badWords.test(t)) {
                            el.setAttribute('title', ''); // تفريغ القيمة
                        }
                    }
                    
                    // معالجة aria-label
                    if (el.hasAttribute('aria-label')) {
                        const a = el.getAttribute('aria-label');
                        if (a && badWords.test(a)) {
                            el.setAttribute('aria-label', ''); // تفريغ القيمة
                        }
                    }
                });

                // 2. إخفاء قسري لأي عنصر tooltip عائم يظهر في الصفحة
                const floatingTooltips = document.querySelectorAll('div[role="tooltip"], .stTooltipHoverTarget');
                floatingTooltips.forEach(ft => {
                    ft.style.visibility = 'hidden';
                    ft.style.opacity = '0';
                    ft.style.display = 'none';
                });
            }

            // تشغيل الدالة فوراً
            killTooltips();

            // تشغيل الدالة مع كل تغيير في الصفحة (MutationObserver)
            const observer = new MutationObserver(() => {
                killTooltips();
            });
            observer.observe(document.body, { childList: true, subtree: true, attributes: true });

            // حزام أمان: تشغيل كل نصف ثانية للتأكد من العناصر العنيدة
            setInterval(killTooltips, 500);
        })();
        </script>
    """, unsafe_allow_html=True)

    # === 2. CSS (التصميم والإخفاء القسري) ===
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        /* إجبار الخط والاتجاه */
        html, body, [class*="css"], p, div, label, input, button, textarea, span, h1, h2, h3, a {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }

        /* === المنطقة النووية: إخفاء العناصر المسببة للمشاكل === */
        
        /* 1. إخفاء الهيدر بالكامل (مصدر keyboard shortcuts) */
        header, [data-testid="stHeader"] {
            display: none !important;
            height: 0 !important;
            visibility: hidden !important;
            z-index: -1 !important;
        }
        
        /* 2. إخفاء شريط الأدوات العائم بجانب العناصر */
        [data-testid="stElementToolbar"], [data-testid="stToolbar"] {
            display: none !important;
        }
        
        /* 3. إخفاء التلميحات العائمة (Tooltips) */
        div[role="tooltip"], .stTooltipHoverTarget > span {
            visibility: hidden !important;
            opacity: 0 !important;
            display: none !important;
        }

        /* 4. تنظيف القوائم المنسدلة (Expanders) */
        div[data-testid="stExpander"] details summary svg { display: none !important; }
        div[data-testid="stExpander"] details summary {
            list-style: none !important;
            color: #0052CC !important;
            font-weight: 800 !important;
        }
        div[data-testid="stExpander"] details summary::-webkit-details-marker {
            display: none !important;
        }

        /* تنسيق عام */
        [data-testid="stSidebar"] { display: none !important; }
        
        /* تنسيق البطاقات (نفس السابق) */
        .kpi-card { background: white; border-radius: 20px; padding: 25px 20px; border: 1px solid #F3F4F6; box-shadow: 0 4px 6px rgba(0,0,0,0.02); transition: 0.3s; margin-bottom: 15px; position: relative; overflow: hidden; }
        .kpi-card:hover { transform: translateY(-5px); box-shadow: 0 15px 30px rgba(0,0,0,0.1); border-color: #BFDBFE; }
        .kpi-icon-bg { position: absolute; left: -15px; bottom: -20px; font-size: 5.5rem; opacity: 0.08; transform: rotate(15deg); color: #1E293B; pointer-events: none; }
        .kpi-card:hover .kpi-icon-bg { transform: rotate(0deg) scale(1.2); opacity: 0.15; left: -5px; }
        .kpi-value { font-size: 1.8rem; font-weight: 900; color: #1E293B; direction: ltr; position: relative; z-index: 2; }
        .kpi-label { color: #64748B; font-size: 0.9rem; font-weight: 700; position: relative; z-index: 2; margin-bottom: 5px; }
        
        .tasi-card { background: linear-gradient(135deg, #0052CC 0%, #0033A0 100%); border-radius: 20px; padding: 25px; color: white !important; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 10px 25px rgba(0, 82, 204, 0.25); margin-bottom: 25px; transition: transform 0.3s ease; }
        .tasi-card:hover { transform: translateY(-3px); }
        
        .finance-table { width: 100%; border-collapse: separate; border-spacing: 0; border: 1px solid #E5E7EB; border-radius: 12px; overflow: hidden; background: white; margin-top: 15px; }
        .finance-table th { background: #F0F8FF !important; color: #1E40AF !important; font-weight: 800; padding: 15px; text-align: right; border-bottom: 2px solid #DBEAFE; }
        .finance-table td { padding: 12px 15px; text-align: right; border-bottom: 1px solid #F1F5F9; color: #334155; font-weight: 600; }
        .finance-table tr:hover { background: #F8FAFC; }
        
        .txt-green { color: #059669 !important; } .txt-red { color: #DC2626 !important; } .txt-blue { color: #2563EB !important; }
        .badge-open { background: #DCFCE7; color: #166534; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; }
        .badge-closed { background: #F3F4F6; color: #4B5563; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; }
        
        div.stButton > button { width: 100%; border-radius: 12px; height: 50px; font-weight: 800; border: none; box-shadow: 0 2px 4px rgba(0,0,0,0.05); background: white; color: #334155; transition: 0.2s; }
        div.stButton > button:hover { transform: translateY(-2px); box-shadow: 0 5px 10px rgba(0,0,0,0.1); color: #0052CC; }
        </style>
    """, unsafe_allow_html=True)
