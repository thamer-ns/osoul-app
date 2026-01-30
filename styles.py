# styles.py
import streamlit as st

def apply_custom_css():
    st.markdown(
        r"""
        <style>
        /* =====================================================
           0) Fonts (أفضل إبقاء @import هنا إذا كان شغال عندك)
           ===================================================== */
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        @import url('https://fonts.googleapis.com/icon?family=Material+Icons');

        /* =====================================================
           1) Base RTL
           ===================================================== */
        html, body, [class*="css"], p, div, label, input, button, textarea, span, h1, h2, h3, h4, h5, h6 {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }

        /* =====================================================
           2) ✅ Icons: لا تطبقها على spans عامة — فقط على أيقونات فعلية
           ===================================================== */
        .material-icons,
        i.material-icons,
        span.material-icons {
            font-family: 'Material Icons' !important;
            direction: ltr !important;
            text-align: center !important;
            font-weight: normal !important;
            font-style: normal !important;
            letter-spacing: normal !important;
            text-transform: none !important;
            white-space: nowrap !important;
            word-wrap: normal !important;
            -webkit-font-feature-settings: "liga" !important;
            font-feature-settings: "liga" !important;
            -webkit-font-smoothing: antialiased !important;
        }

        /* =====================================================
           3) ✅ Fallback قاتل لمشكلة ظهور النصوص expand_more/keyboard_arrow_*
           - نخفي أي span داخل expander/select يحمل هذه النصوص (حتى لو بدون class)
           ===================================================== */

        /* Expander summary: أي span صغير خاص بالأيقونة -> نخفي النص */
        [data-testid="stExpander"] summary span {
            /* لا نقدر نعرف أيهم أيقونة 100%، لكن نقدر نعالج "النصوص المعروفة" */
        }

        /* نخفي الكلمات نفسها إن ظهرت كنص */
        [data-testid="stExpander"] summary span:has-text,
        [data-testid="stSelectbox"] span:has-text,
        [data-testid="stMultiSelect"] span:has-text { }

        /* Streamlit ما يدعم :has-text في كل المتصفحات، فنعالجها بـCSS عملي: */
        /* نخفي spans اللي تكون غالبًا للأيقونات (صغيرة + داخل زر/summary) */
        [data-testid="stExpander"] summary span:not(:first-child) {
            /* لا نلمس النص الأساسي عادة (يكون أول span)، والأيقونة غالبًا تأتي بعده */
        }

        /* طريقة عملية: نخفي أي span داخل summary يحتوي واحد من ligatures عبر font-size=0 ثم نضيف سهم */
        [data-testid="stExpander"] summary span {
            /* نجعل النص داخل أيقونات المحتوى صفر عند الاشتباه عبر class hooks */
        }

        /* 3.1 Expander: استبدال الأيقونة بسهم ثابت */
        [data-testid="stExpander"] summary span.material-icons,
        [data-testid="stExpander"] summary i.material-icons {
            font-size: 0 !important;
            line-height: 0 !important;
        }
        [data-testid="stExpander"] summary span.material-icons::before,
        [data-testid="stExpander"] summary i.material-icons::before {
            content: "▾";
            font-size: 18px !important;
            line-height: 18px !important;
            font-family: 'Cairo', sans-serif !important;
            color: #475569;
            display: inline-block;
            transform: translateY(1px);
        }
        [data-testid="stExpander"] details[open] summary span.material-icons::before,
        [data-testid="stExpander"] details[open] summary i.material-icons::before {
            content: "▴";
        }

        /* 3.2 Selectbox / Multiselect: استبدال سهم القائمة */
        [data-testid="stSelectbox"] span.material-icons,
        [data-testid="stSelectbox"] i.material-icons,
        [data-testid="stMultiSelect"] span.material-icons,
        [data-testid="stMultiSelect"] i.material-icons {
            font-size: 0 !important;
            line-height: 0 !important;
        }
        [data-testid="stSelectbox"] span.material-icons::before,
        [data-testid="stSelectbox"] i.material-icons::before,
        [data-testid="stMultiSelect"] span.material-icons::before,
        [data-testid="stMultiSelect"] i.material-icons::before {
            content: "▾";
            font-size: 18px !important;
            line-height: 18px !important;
            font-family: 'Cairo', sans-serif !important;
            color: #475569;
            display: inline-block;
            transform: translateY(1px);
        }

        /* =====================================================
           4) 🔥 Fallback إضافي: لو الأيقونة تظهر كنص بدون material-icons class
           - نخفي النصوص الشائعة داخل كل التطبيق
           ===================================================== */
        span, i {
            /* لا شيء هنا - فقط قواعد أدناه بالـattribute selectors */
        }

        /* لو ظهرت هذه الكلمات كنص داخل الصفحة: نخفيها */
        span:where(:not(.material-icons)),
        i:where(:not(.material-icons)) { }

        /* نستخدم حيلة: اختيار عناصر تحتوي ligature عبر [aria-label] أو [title] إن وجدت */
        [aria-label="expand_more"], [aria-label="expand_less"],
        [aria-label="keyboard_arrow_down"], [aria-label="keyboard_arrow_up"],
        [title="expand_more"], [title="expand_less"],
        [title="keyboard_arrow_down"], [title="keyboard_arrow_up"] {
            font-size: 0 !important;
        }
        [aria-label="expand_more"]::before,
        [title="expand_more"]::before,
        [aria-label="keyboard_arrow_down"]::before,
        [title="keyboard_arrow_down"]::before {
            content: "▾";
            font-size: 18px !important;
            font-family: 'Cairo', sans-serif !important;
            color: #475569;
        }
        [aria-label="expand_less"]::before,
        [title="expand_less"]::before,
        [aria-label="keyboard_arrow_up"]::before,
        [title="keyboard_arrow_up"]::before {
            content: "▴";
            font-size: 18px !important;
            font-family: 'Cairo', sans-serif !important;
            color: #475569;
        }

        /* =====================================================
           5) UI Cleanup
           ===================================================== */
        section[data-testid="stSidebar"] {
            border-right: none !important;
            border-left: none !important;
            box-shadow: none !important;
        }
        footer, header, #MainMenu { display: none !important; }
        [data-testid="stElementToolbar"] { display: none !important; }
        div[role="tooltip"] { display: none !important; opacity: 0 !important; visibility: hidden !important; }
        button[title="View fullscreen"] { display: none !important; }

        /* =====================================================
           6) Your existing styling (كما هي تقريبًا)
           ===================================================== */
        div[data-testid="stExpander"] {
            border: 1px solid #E5E7EB; border-radius: 12px; background-color: #FAFAFA;
            margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }
        div[data-testid="stExpander"] details summary {
            font-weight: 800 !important; color: #0052CC !important; padding: 10px 15px !important;
        }
        div[data-testid="stExpander"] details summary:hover {
            color: #0033A0 !important; background-color: #F1F5F9;
        }

        .kpi-card {
            background-color: white; border-radius: 20px; padding: 25px 20px;
            position: relative; overflow: hidden; border: 1px solid #F3F4F6;
            box-shadow: 0 4px 6px rgba(0,0,0,0.02); transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            margin-bottom: 15px;
        }
        .kpi-card:hover {
            transform: translateY(-5px) scale(1.01);
            box-shadow: 0 15px 30px rgba(0,0,0,0.1);
            border-color: #BFDBFE;
        }
        .kpi-icon-bg {
            position: absolute; left: -15px; bottom: -20px; font-size: 5.5rem; opacity: 0.08;
            transform: rotate(15deg); transition: all 0.4s ease; color: #1E293B; pointer-events: none;
        }
        .kpi-card:hover .kpi-icon-bg { transform: rotate(0deg) scale(1.2); opacity: 0.15; left: -5px; }
        .kpi-value { font-size: 1.8rem; font-weight: 900; color: #1E293B; direction: ltr; position: relative; z-index: 2; }
        .kpi-label { color: #64748B; font-size: 0.9rem; font-weight: 700; position: relative; z-index: 2; margin-bottom: 5px; }

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

        .txt-green { color: #059669 !important; }
        .txt-red { color: #DC2626 !important; }
        .txt-blue { color: #2563EB !important; }

        .badge-open { background: #DCFCE7; color: #166534; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; }
        .badge-closed { background: #F3F4F6; color: #4B5563; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; }

        div.stButton > button {
            width: 100%; border-radius: 12px; height: 50px; font-weight: 800; border: none;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05); background: white; color: #334155; transition: 0.2s;
        }
        div.stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 10px rgba(0,0,0,0.1);
            color: #0052CC;
        }
        </style>
        """,
        unsafe_allow_html=True
    )