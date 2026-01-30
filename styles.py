# styles.py
import streamlit as st

def apply_custom_css():
    st.markdown(
        """
        <!-- تحميل الخطوط عبر LINK (أفضل من @import داخل style) -->
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>

        <!-- Cairo -->
        <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap" rel="stylesheet">

        <!-- Material Icons + Material Symbols (للاحتياط حسب إصدار Streamlit) -->
        <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
        <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:FILL,GRAD,opsz,wght@0,0,24,400" rel="stylesheet">

        <style>
        /* =====================================================
           1) قواعد عامة RTL بدون كسر الأيقونات
           ===================================================== */
        html, body {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }

        /* طبّق خط Cairo على معظم العناصر لكن استثنِ عناصر الأيقونات */
        p, div, label, input, button, textarea, span, h1, h2, h3, h4, h5, h6 {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }

        /* استثناء صريح للأيقونات حتى لا تتحول إلى نص */
        .material-icons,
        .material-symbols-outlined,
        i.material-icons,
        span.material-icons,
        span.material-symbols-outlined {
            font-family: 'Material Icons' !important;
            direction: ltr !important;
            text-align: center !important;
            font-weight: normal !important;
            font-style: normal !important;
            letter-spacing: normal !important;
            text-transform: none !important;
            white-space: nowrap !important;
            word-wrap: normal !important;
            -webkit-font-smoothing: antialiased !important;
            font-feature-settings: "liga" !important; /* مهم للـ ligatures */
        }

        /* =====================================================
           2) تنظيف الواجهة
           ===================================================== */
        footer, header, #MainMenu { display: none !important; }
        [data-testid="stElementToolbar"] { display: none !important; }
        div[role="tooltip"] { display: none !important; opacity: 0 !important; visibility: hidden !important; }
        button[title="View fullscreen"] { display: none !important; }

        section[data-testid="stSidebar"] {
            border-right: none !important;
            border-left: none !important;
            box-shadow: none !important;
        }

        /* =====================================================
           3) Fix حاسم لمشكلة ظهور expand_more / keyboard_arrow_*
           (Fallback حتى لو خط الأيقونات لم يحمل)
           ===================================================== */

        /* Expander: أخفِ النص ligature وحط سهم بديل */
        [data-testid="stExpander"] details summary span.material-icons,
        [data-testid="stExpander"] details summary span.material-symbols-outlined {
            font-size: 0 !important;   /* يخفي expand_more كنص */
            line-height: 0 !important;
        }
        [data-testid="stExpander"] details summary span.material-icons::before,
        [data-testid="stExpander"] details summary span.material-symbols-outlined::before {
            content: "▾";
            font-size: 18px !important;
            line-height: 18px !important;
            font-family: 'Cairo', sans-serif !important; /* سهم عادي */
            color: #475569;
            display: inline-block;
            transform: translateY(1px);
        }
        [data-testid="stExpander"] details[open] summary span.material-icons::before,
        [data-testid="stExpander"] details[open] summary span.material-symbols-outlined::before {
            content: "▴";
        }

        /* Select / Multiselect (أحيانًا يظهر keyboard_arrow_down كنص) */
        [data-testid="stSelectbox"] span.material-icons,
        [data-testid="stSelectbox"] span.material-symbols-outlined,
        [data-testid="stMultiSelect"] span.material-icons,
        [data-testid="stMultiSelect"] span.material-symbols-outlined {
            font-size: 0 !important;
            line-height: 0 !important;
        }
        [data-testid="stSelectbox"] span.material-icons::before,
        [data-testid="stSelectbox"] span.material-symbols-outlined::before,
        [data-testid="stMultiSelect"] span.material-icons::before,
        [data-testid="stMultiSelect"] span.material-symbols-outlined::before {
            content: "▾";
            font-size: 18px !important;
            line-height: 18px !important;
            font-family: 'Cairo', sans-serif !important;
            color: #475569;
            display: inline-block;
            transform: translateY(1px);
        }

        /* =====================================================
           4) تنسيقاتك الحالية (بطاقات وجداول... بدون تغيير جوهري)
           ===================================================== */

        /* Expander */
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

        /* KPI Cards */
        .kpi-card {
            background-color: white; border-radius: 20px; padding: 25px 20px;
            position: relative; overflow: hidden; border: 1px solid #F3F4F6;
            box-shadow: 0 4px 6px rgba(0,0,0,0.02); transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            margin-bottom: 15px;
        }
        .kpi-card:hover {
            transform: translateY(-5px) scale(1.01); box-shadow: 0 15px 30px rgba(0,0,0,0.1); border-color: #BFDBFE;
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

        div.stButton > button {
            width: 100%; border-radius: 12px; height: 50px; font-weight: 800; border: none;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05); background: white; color: #334155; transition: 0.2s;
        }
        div.stButton > button:hover { transform: translateY(-2px); box-shadow: 0 5px 10px rgba(0,0,0,0.1); color: #0052CC; }
        </style>
        """,
        unsafe_allow_html=True
    )