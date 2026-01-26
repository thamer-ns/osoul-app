import streamlit as st

def apply_custom_css():
    # === 1) JavaScript قاتل للتلميحات الإنجليزية (يعمل باستمرار) ===
    st.markdown("""
    <script>
    (function () {
        function nukeTooltips() {
            // إزالة أي title أو aria-label إنجليزي
            document.querySelectorAll('*').forEach(el => {
                const t = el.getAttribute('title');
                const a = el.getAttribute('aria-label');

                if (t && /expand|collapse|fullscreen|view/i.test(t)) {
                    el.removeAttribute('title');
                }
                if (a && /expand|collapse|fullscreen|view/i.test(a)) {
                    el.removeAttribute('aria-label');
                }
            });

            // حذف أي tooltip موجود فعلياً
            document.querySelectorAll(
                '[role="tooltip"], div[data-baseweb="tooltip"], .stTooltipHoverTarget'
            ).forEach(el => el.remove());
        }

        // شغّلها فوراً
        nukeTooltips();

        // وراقب أي تحديث جديد (Streamlit يعيد الرسم كثيراً)
        const obs = new MutationObserver(nukeTooltips);
        obs.observe(document.body, { childList: true, subtree: true });
    })();
    </script>
    """, unsafe_allow_html=True)

    # === 2) CSS (التصميم + تعطيل أي Tooltip بصرياً) ===
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');

    /* الأساسيات RTL */
    html, body, [class*="css"], p, div, span, label, input, button, textarea, h1, h2, h3 {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl !important;
        text-align: right !important;
    }

    /* قتل أي Tooltip بصرياً (احتياط إضافي) */
    [role="tooltip"],
    div[data-baseweb="tooltip"],
    .stTooltipHoverTarget,
    .stTooltipHoverTarget > span {
        display: none !important;
        opacity: 0 !important;
        visibility: hidden !important;
        pointer-events: none !important;
    }

    /* منع المتصفح نفسه من إظهار أي تلميح */
    * {
        -webkit-user-select: text;
    }

    /* إخفاء السهم (مصدر Expand) */
    div[data-testid="stExpander"] details summary svg {
        display: none !important;
    }

    /* تعطيل hover tooltip من الجذر */
    div[data-testid], button, svg {
        pointer-events: auto;
    }

    /* ===== التصميم الحيوي (كما كان) ===== */
    .kpi-card {
        background: white;
        border-radius: 20px;
        padding: 25px 20px;
        position: relative;
        overflow: hidden;
        border: 1px solid #F3F4F6;
        box-shadow: 0 4px 6px rgba(0,0,0,0.03);
        transition: all 0.3s ease;
        margin-bottom: 15px;
    }

    .kpi-card:hover {
        transform: translateY(-6px) scale(1.01);
        box-shadow: 0 16px 30px rgba(0,0,0,0.12);
        border-color: #BFDBFE;
    }

    .kpi-icon-bg {
        position: absolute;
        left: -15px;
        bottom: -20px;
        font-size: 5.5rem;
        opacity: 0.08;
        transform: rotate(15deg);
        transition: all 0.3s ease;
        pointer-events: none;
    }

    .kpi-card:hover .kpi-icon-bg {
        transform: rotate(0deg) scale(1.15);
        opacity: 0.15;
    }

    .kpi-value {
        font-size: 1.8rem;
        font-weight: 900;
        direction: ltr;
        z-index: 2;
        position: relative;
    }

    .kpi-label {
        font-size: 0.9rem;
        font-weight: 700;
        color: #64748B;
        z-index: 2;
        position: relative;
    }

    /* صندوق تاسي */
    .tasi-card {
        background: linear-gradient(135deg, #0052CC, #0033A0);
        border-radius: 20px;
        padding: 25px;
        color: white;
        box-shadow: 0 12px 30px rgba(0,82,204,0.3);
        transition: transform .3s;
    }

    .tasi-card:hover { transform: translateY(-3px); }

    /* الجداول */
    .finance-table th {
        background: #F0F8FF !important;
        font-weight: 800;
    }

    </style>
    """, unsafe_allow_html=True)
