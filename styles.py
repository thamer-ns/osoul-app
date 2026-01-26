import streamlit as st

def apply_custom_css():
    # === الحل الجذري: كود جافاسكربت يراقب الصفحة ويحذف النصوص الإنجليزية فور ظهورها ===
    st.markdown("""
        <script>
        (function() {
            // قائمة الكلمات الإنجليزية المزعجة التي نريد إخفاء عناصرها
            const badTexts = [
                "expand more", "expand less", "collapse", "fullscreen", 
                "view fullscreen", "limit", "keyboard", "options"
            ];

            function cleanUpInterface() {
                // 1. تنظيف التلميحات (Tooltips) والعناوين (Titles)
                const elements = document.querySelectorAll('[title], [aria-label], [data-testid="stTooltipHoverTarget"]');
                elements.forEach(el => {
                    const title = (el.getAttribute('title') || "").toLowerCase();
                    const aria = (el.getAttribute('aria-label') || "").toLowerCase();
                    
                    // إذا وجدنا كلمة إنجليزية، نحذف الخاصية تماماً
                    if (badTexts.some(txt => title.includes(txt))) {
                        el.removeAttribute('title');
                    }
                    if (badTexts.some(txt => aria.includes(txt))) {
                        el.removeAttribute('aria-label');
                    }
                });

                // 2. إخفاء أشرطة أدوات الجداول (Dataframes Toolbar)
                const toolbars = document.querySelectorAll('[data-testid="stElementToolbar"]');
                toolbars.forEach(tb => tb.style.display = 'none');

                // 3. إخفاء أيقونات محددة بناءً على الأيقونة نفسها (SVGs)
                // نحاول إخفاء أزرار التوسيع (Expanders) الصغيرة التي تظهر بجانب الجداول
                const buttons = document.querySelectorAll('button');
                buttons.forEach(btn => {
                    if(btn.innerText.includes("Limit") || btn.innerText.includes("Show more")) {
                        btn.style.display = 'none';
                    }
                });
            }

            // تشغيل التنظيف كل نصف ثانية للتأكد من العناصر الجديدة
            setInterval(cleanUpInterface, 500);
        })();
        </script>
        
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        /* === 1. إخفاء العناصر الإنجليزية عبر CSS === */
        
        /* إخفاء شريط الأدوات العائم فوق الجداول */
        [data-testid="stElementToolbar"] { display: none !important; }
        
        /* إخفاء التلميحات (Tooltips) */
        div[role="tooltip"] { display: none !important; opacity: 0 !important; }
        
        /* إخفاء أيقونة تكبير الصور والشارتات */
        button[title="View fullscreen"] { display: none !important; }
        
        /* إخفاء كلمة "Press Enter to apply" في حقول الإدخال */
        .st-emotion-cache-1ae8s89 { display: none !important; } /* قد يختلف الكلاس، لذا سنعتمد على JS أكثر */

        /* === 2. التنسيق العام (عربي) === */
        html, body, [class*="css"], p, div, label, input, button, textarea, span, h1, h2, h3 {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }

        /* إخفاء القائمة الجانبية والهيدر */
        [data-testid="stSidebar"], header, footer { display: none !important; }

        /* === 3. تنسيق البطاقات والجداول (نفس التصميم السابق) === */
        
        /* Expander */
        div[data-testid="stExpander"] {
            border: 1px solid #E5E7EB; border-radius: 12px; background-color: #FAFAFA;
            margin-bottom: 10px;
        }
        div[data-testid="stExpander"] details summary {
            font-weight: 800 !important; color: #0052CC !important; padding: 10px 15px !important;
        }
        /* إخفاء أيقونة السهم الافتراضية المزعجة واستبدالها أو ترك النص فقط */
        div[data-testid="stExpander"] details summary svg { opacity: 0.5; } 

        /* KPI Cards */
        .kpi-card {
            background-color: white; border-radius: 20px; padding: 25px 20px;
            position: relative; overflow: hidden; border: 1px solid #F3F4F6;
            margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);
        }
        .kpi-icon-bg {
            position: absolute; left: -15px; bottom: -20px; font-size: 5.5rem;
            opacity: 0.08; transform: rotate(15deg); color: #1E293B; pointer-events: none;
        }
        .kpi-value { font-size: 1.8rem; font-weight: 900; color: #1E293B; direction: ltr; }
        .kpi-label { color: #64748B; font-size: 0.9rem; font-weight: 700; margin-bottom: 5px; }

        /* Tables */
        .finance-table {
            width: 100%; border-collapse: separate; border-spacing: 0;
            border: 1px solid #E5E7EB; border-radius: 12px; overflow: hidden;
            background: white; margin-top: 15px;
        }
        .finance-table th { background-color: #F0F8FF !important; color: #1E40AF !important; padding: 15px; }
        .finance-table td { padding: 12px 15px; border-bottom: 1px solid #F1F5F9; color: #334155; }

        /* Buttons & Inputs */
        div.stButton > button {
            width: 100%; border-radius: 12px; height: 50px; font-weight: 800; border: none;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05); background: white; color: #334155;
        }
        div.stButton > button:hover { transform: translateY(-2px); color: #0052CC; }
        
        /* TASI Card */
        .tasi-card {
            background: linear-gradient(135deg, #0052CC 0%, #0033A0 100%);
            border-radius: 20px; padding: 25px; color: white !important;
            display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 10px 25px rgba(0, 82, 204, 0.25); margin-bottom: 25px;
        }
        
        /* Badges */
        .txt-green { color: #059669 !important; } .txt-red { color: #DC2626 !important; }
        .badge-open { background: #DCFCE7; color: #166534; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; }
        .badge-closed { background: #F3F4F6; color: #4B5563; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; }
        </style>
    """, unsafe_allow_html=True)
