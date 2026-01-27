import streamlit as st
import streamlit.components.v1 as components  # ضروري لتشغيل كود إخفاء الإنجليزي

def apply_custom_css():
    # 1. كود CSS (التصميم، الخطوط، وإصلاح الواجهة)
    st.markdown("""
        <style>
        /* استيراد الخطوط */
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        @import url('https://fonts.googleapis.com/icon?family=Material+Icons');

        /* تعميم الخط العربي والاتجاه */
        html, body, [class*="css"], p, div, label, input, button, textarea, span, h1, h2, h3, h4, h5, h6 {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }

        /* إصلاح اتجاه الأيقونات لتظهر بشكل صحيح */
        .material-icons, [class*="material-icons"], i, 
        [data-testid="stExpander"] details summary span,
        [data-testid="stPopover"] button span {
            direction: ltr !important;
            font-family: 'Material Icons' !important;
        }

        /* إزالة الخط العمودي والظل عند القائمة الجانبية */
        section[data-testid="stSidebar"] {
            border-right: none !important;
            border-left: none !important;
            box-shadow: none !important;
        }
        
        /* إخفاء الهوامش العلوية والسفلية وأشرطة الأدوات */
        footer, header, [data-testid="stElementToolbar"] { display: none !important; }
        
        /* إخفاء التلميحات المزعجة (Tooltips) */
        div[role="tooltip"] { display: none !important; visibility: hidden !important; }

        /* تنسيق البطاقات (KPI Cards) */
        .kpi-card {
            background-color: white; border-radius: 15px; padding: 20px;
            border: 1px solid #F1F5F9; box-shadow: 0 2px 4px rgba(0,0,0,0.03);
            margin-bottom: 10px; position: relative; overflow: hidden;
        }
        .kpi-value { font-size: 1.6rem; font-weight: 800; color: #1E293B; direction: ltr; }
        .kpi-label { color: #64748B; font-size: 0.85rem; font-weight: 700; margin-bottom: 5px; }
        
        /* أيقونة خلفية باهتة */
        .kpi-icon-bg {
            position: absolute; left: -10px; bottom: -15px; font-size: 5rem;
            opacity: 0.05; color: #334155; pointer-events: none;
        }

        /* تنسيق الجداول */
        .finance-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        .finance-table th { background: #F8FAFC; padding: 12px; color: #475569; font-size: 0.85rem; }
        .finance-table td { padding: 12px; border-bottom: 1px solid #F1F5F9; font-weight: 600; color: #334155; }
        
        /* ألوان النصوص */
        .txt-green { color: #10B981 !important; }
        .txt-red { color: #EF4444 !important; }
        .txt-blue { color: #3B82F6 !important; }
        
        /* تحسين الأزرار */
        div.stButton > button {
            border-radius: 10px; height: 45px; font-weight: 700; border: none;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05); background: white; color: #334155;
        }
        div.stButton > button:hover { color: #0052CC; background: #F8FAFC; }
        </style>
    """, unsafe_allow_html=True)

    # 2. كود جافا سكريبت (هذا الجزء كان ناقصاً عندك وهو الحل الجذري للنصوص الإنجليزية)
    components.html("""
    <script>
        const observer = new MutationObserver((mutations) => {
            // الكلمات التي نريد حذفها
            const badWords = /expand|collapse|fullscreen|view|zoom|more|less|keyboard|ar|double_arrow|sidebar/i;
            
            function clean(node) {
                if (!node) return;
                // حذف التلميحات (Tooltips) التي تظهر عند تمرير الماوس
                if (node.getAttribute && node.getAttribute('title') && badWords.test(node.getAttribute('title'))) {
                    node.removeAttribute('title');
                }
                if (node.getAttribute && node.getAttribute('aria-label') && badWords.test(node.getAttribute('aria-label'))) {
                    node.removeAttribute('aria-label');
                }
                // إخفاء أيقونات الأسهم المشوهة إذا ظهرت كنص
                if (node.innerText && badWords.test(node.innerText) && node.innerText.length < 20) {
                    if (node.tagName === 'SPAN' || node.tagName === 'I') {
                        node.style.opacity = '0';
                    }
                }
            }

            mutations.forEach((mutation) => {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === 1) { 
                        clean(node);
                        node.querySelectorAll('*').forEach(clean);
                    }
                });
            });
        });

        // تشغيل المراقبة
        observer.observe(window.parent.document.body, { childList: true, subtree: true });
    </script>
    """, height=0, width=0)
