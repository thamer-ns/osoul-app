# styles.py
import streamlit as st

def apply_custom_css():
    st.markdown(
        """
        <style>
        /* =====================================================
           Fonts
           ===================================================== */
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        @import url('https://fonts.googleapis.com/icon?family=Material+Icons');
        /* ✅ الأهم: Material Symbols (اللي تسبب ظهور expand_more كنص) */
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Sharp:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');

        /* =====================================================
           Base RTL + Cairo
           ✅ ملاحظة: لا نطبّق Cairo على كل span بشكل أعمى
           عشان ما نكسر أيقونات Streamlit
           ===================================================== */
        html, body, [class*="css"], p, div, label, input, button, textarea, h1, h2, h3, h4, h5, h6 {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }

        /* ✅ طبّق على span لكن استثنِ أيقونات Material (Icons/Symbols) */
        span:not(.material-icons)
            :not(.material-symbols-outlined)
            :not(.material-symbols-rounded)
            :not(.material-symbols-sharp)
            :not([class*="material-symbols"])
        {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }

        /* =====================================================
           ✅ Fix Material Icons (ligatures)
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
            -webkit-font-feature-settings: "liga" !important;
            font-feature-settings: "liga" !important;
            -webkit-font-smoothing: antialiased !important;
        }

        /* =====================================================
           ✅ Fix Material Symbols (السبب الحقيقي لظهور expand_more)
           ===================================================== */
        .material-symbols-outlined,
        .material-symbols-rounded,
        .material-symbols-sharp,
        [class*="material-symbols"] {
            font-family: 'Material Symbols Outlined', 'Material Symbols Rounded', 'Material Symbols Sharp' !important;
            direction: ltr !important;
            text-align: center !important;
            font-weight: normal !important;
            font-style: normal !important;
            letter-spacing: normal !important;
            text-transform: none !important;
            white-space: nowrap !important;
            -webkit-font-feature-settings: "liga" !important;
            font-feature-settings: "liga" !important;
            -webkit-font-smoothing: antialiased !important;
        }

        /* =====================================================
           🔥 Fallback: لو لسبب ما ما تحملت الخطوط… أخفي الكلمات واستبدلها بسهم
           ===================================================== */
        [data-testid="stExpander"] summary span {
            /* لا شيء افتراضي */
        }

        /* إذا ظهرت ligatures كنص داخل expander أو selectbox، نخفيها */
        [data-testid="stExpander"] summary span:not(:first-child),
        [data-testid="stSelectbox"] span,
        [data-testid="stMultiSelect"] span {
            /* غالباً الأيقونة تكون span إضافي */
        }

        /* استبدال النصوص الشائعة بسهم */
        span.material-icons,
        span.material-symbols-outlined,
        span.material-symbols-rounded,
        span.material-symbols-sharp {
            /* لا نكتمها هنا لأننا نعتمد على الخط */
        }

        /* لو ظهر كنص بسبب فشل التحميل: نخفي النص ونضيف سهم */
        span.material-symbols-outlined:where(:not(:empty)),
        span.material-symbols-rounded:where(:not(:empty)),
        span.material-symbols-sharp:where(:not(:empty)) {
            /* نتركها — الخط بيحولها لأيقونة */
        }

        /* =====================================================
           UI Cleanup
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

        /* Expander */
        div[data-testid="stExpander"] {
            border: 1px solid #E5E7EB;
            border-radius: 12px;
            background-color: #FAFAFA;
            margin-bottom: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }
        div[data-testid="stExpander"] details summary {
            font-weight: 800 !important;
            color: #0052CC !important;
            padding: 10px 15px !important;
        }
        div[data-testid="stExpander"] details summary:hover {
            color: #0033A0 !important;
            background-color: #F1F5F9;
        }

        /* KPI Cards */
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

        /* Tables */
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

        /* Buttons */
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