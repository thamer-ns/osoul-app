# styles.py
import streamlit as st
import textwrap


def apply_custom_css():
    """Inject global CSS.

    - Keeps your existing look.
    - Adds **Light/Dark** theme support (no feature removal).
      Theme key: `st.session_state['ui_theme']` in {"light", "dark"}.
    """

    theme = (st.session_state.get("ui_theme") or "light").strip().lower()
    if theme not in ("light", "dark"):
        theme = "light"

    # ✅ CSS variables are the safest way to theme Streamlit without breaking logic.
    if theme == "dark":
        var_css = """
            --app-bg: #071018;
            --txt: #E5E7EB;
            --muted: #9CA3AF;
            --primary: #2D5BFF;
            --accent: #00D4FF;
            --border: rgba(148,163,184,0.18);
            --border2: rgba(148,163,184,0.28);
            --card-bg: #0B1220;
            --soft-bg: #0F172A;
            --shadow: 0 10px 25px rgba(0,0,0,0.35);
            --shadow2: 0 20px 45px rgba(0,0,0,0.45);
            --green: #34D399;
            --red: #F87171;
            --blue: #60A5FA;
            --amber: #FBBF24;
        """
    else:
        var_css = """
            --app-bg: #F6F8FB;
            --txt: #0F172A;
            --muted: #9CA3AF;
            --primary: #2D5BFF;
            --accent: #00D4FF;
            --border: rgba(15,23,42,0.12);
            --border2: rgba(15,23,42,0.18);
            --card-bg: #ffffff;
            --soft-bg: #F8FAFC;
            --shadow: 0 10px 25px rgba(15,23,42,0.10);
            --shadow2: 0 20px 45px rgba(15,23,42,0.12);
            --green: #059669;
            --red: #DC2626;
            --blue: #2563EB;
            --amber: #F59E0B;
        """

    css = """
        <style>
        /* =====================================================
           Fonts
           ===================================================== */
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        @import url('https://fonts.googleapis.com/icon?family=Material+Icons');

        /* ✅ Material Symbols (سبب expand_more كنص) */
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Sharp:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');

        :root {
            --font-ar: 'IBM Plex Sans Arabic', 'Cairo', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
        }


        /* =====================================================
           Theme variables (لتحسين الوضوح)
           ===================================================== */
        :root{
            __VAR_CSS__
        }

        /* ✅ App background for both themes */
        .stApp { background: var(--app-bg) !important; }

                /* =====================================================
           RTL + Cairo (مركزي) + حماية أيقونات Streamlit
           - نثبت RTL بشكل عام (حتى صفحة الدخول والتبويبات)
           - نطبق Cairo على واجهة Streamlit فقط
           - نستثني Material Icons/Symbols حتى لا تظهر كنص مثل keyboard_double_arrow_left
           ===================================================== */
        html, body {
            direction: rtl !important;
            text-align: right !important;
        }

        .stApp {
            direction: rtl !important;
            text-align: right !important;
            color: var(--txt) !important;
        }

        /* تقوية RTL داخل حاويات Streamlit (بعضها يفرض LTR افتراضيًا) */
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stSidebar"],
        [data-testid="stVerticalBlock"],
        [data-testid="stHorizontalBlock"],
        .block-container {
            direction: rtl !important;
            text-align: right !important;
        }

        /* عناصر الإدخال يجب أن تتبع RTL */
        input, textarea, select {
            direction: rtl !important;
            text-align: right !important;
        }

        /* إخفاء تلميح Streamlit الإنجليزي أسفل الفورم (لا يؤثر على Enter) */
        div[data-testid="stForm"] small {
            display: none !important;
        }

        /* تطبيق Cairo بالوراثة (بدون كسر Material Icons ligatures) */
        .stApp {
            font-family: 'Cairo', sans-serif !important;
        }
        .stApp input,
        .stApp textarea,
        .stApp select,
        .stApp button,
        .stApp label,
        .stApp p,
        .stApp span,
        .stApp a,
        .stApp li,
        .stApp th,
        .stApp td,
        .stApp h1,
        .stApp h2,
        .stApp h3,
        .stApp h4,
        .stApp h5,
        .stApp h6 {
            font-family: inherit !important;
        }

        

/* ✅ GLOBAL_TEXT_RTL_FORCE: تثبيت اتجاه العناوين/النصوص/التبويبات بدون تخريب التنسيق */
.stApp h1,
.stApp h2,
.stApp h3,
.stApp h4,
.stApp h5,
.stApp h6,
.stApp [data-testid="stTitle"],
.stApp [data-testid="stHeader"],
.stApp [data-testid="stSubheader"],
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stMarkdownContainer"] * {
    direction: rtl !important;
    text-align: right !important;
    unicode-bidi: plaintext !important;
}

/* التبويبات (تسجيل الدخول/إنشاء حساب/سجل السحوبات/الصفقات القائمة...) */
div[data-testid="stTabs"] [data-baseweb="tab-list"] {
    direction: rtl !important;
    unicode-bidi: plaintext !important;
    /* اجعل ترتيب التبويبات من اليمين لليسار وثبّت محاذاتها */
    flex-direction: row-reverse !important;
    justify-content: flex-end !important;
}
div[data-testid="stTabs"] [data-baseweb="tab"] {
    direction: rtl !important;
    text-align: right !important;
    unicode-bidi: plaintext !important;
}

/* حقول الإدخال (اسم المستخدم/كلمة المرور...): العنوان + النص داخل الحقل */
.stTextInput label,
.stPassword label,
.stNumberInput label,
.stTextArea label,
.stSelectbox label,
.stMultiSelect label,
.stDateInput label {
    direction: rtl !important;
    text-align: right !important;
    unicode-bidi: plaintext !important;
    width: 100% !important;
}
.stTextInput input,
.stPassword input,
.stNumberInput input,
.stTextArea textarea,
.stSelectbox input,
.stMultiSelect input,
.stDateInput input {
    direction: rtl !important;
    text-align: right !important;
    unicode-bidi: plaintext !important;
}
.stTextInput input::placeholder,
.stPassword input::placeholder,
.stNumberInput input::placeholder,
.stTextArea textarea::placeholder,
.stSelectbox input::placeholder,
.stMultiSelect input::placeholder,
.stDateInput input::placeholder {
    direction: rtl !important;
    text-align: right !important;
}

/* عناصر قياس Streamlit (مثل المؤشر العام TASI) */
[data-testid="stMetric"],
[data-testid="stMetric"] * {
    direction: rtl !important;
    text-align: right !important;
    unicode-bidi: plaintext !important;
}

/* Code/JSON blocks يجب أن تبقى LTR */
        pre, code, .stCode, .stMarkdown pre, .stMarkdown code {
            direction: ltr !important;
            text-align: left !important;
        }

        /* إصلاح أيقونات Streamlit/Material (Ligatures) */
        .material-icons,
        .material-symbols-outlined,
        .material-symbols-rounded,
        .material-symbols-sharp,
        [class*="material-symbols"],
        [data-testid="stIconMaterial"],
        [data-testid="stIconMaterial"] *,
        span[translate="no"] {
            font-family: 'Material Symbols Rounded','Material Symbols Outlined','Material Symbols Sharp','Material Icons' !important;
            font-feature-settings: 'liga' 1 !important;
            -webkit-font-feature-settings: 'liga' 1 !important;
            direction: ltr !important;
            text-align: center !important;
            letter-spacing: normal !important;
        }

        /* =====================================================
           Sidebar collapsed control: منع ظهور الخط/الشريط عند طيّ القائمة
           ===================================================== */
        div[data-testid="stSidebarCollapsedControl"],
        div[data-testid="collapsedControl"],
        [data-testid="collapsedControl"] {
            /* اجعل الحاوية 0x0 حتى لا تتحول إلى خط عمودي */
            width: 0 !important;
            height: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            overflow: visible !important;
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            pointer-events: none !important;
            z-index: 100000 !important;
        }

        div[data-testid="stSidebarCollapsedControl"]::before,
        div[data-testid="stSidebarCollapsedControl"]::after,
        div[data-testid="collapsedControl"]::before,
        div[data-testid="collapsedControl"]::after,
        [data-testid="collapsedControl"]::before,
        [data-testid="collapsedControl"]::after {
            display: none !important;
            content: none !important;
        }

        div[data-testid="stSidebarCollapsedControl"] button,
        div[data-testid="collapsedControl"] button,
        [data-testid="collapsedControl"] button,
        button[title="Open sidebar"],
        button[aria-label="Open sidebar"] {
            pointer-events: auto !important;
            position: fixed !important;
            top: 0.85rem !important;
            right: 0.85rem !important;
            left: auto !important;
            width: 42px !important;
            height: 42px !important;
            min-width: 42px !important;
            min-height: 42px !important;
            padding: 0 !important;
            border-radius: 999px !important;
            border: 1px solid var(--border2) !important;
            background: var(--card-bg) !important;
            box-shadow: 0 10px 24px rgba(15,23,42,0.10) !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            z-index: 100001 !important;
        }

        /* ضمان أن أيقونة زر الفتح لا تتحول إلى نص (keyboard_double_arrow_left) */
        div[data-testid="stSidebarCollapsedControl"] button *,
        div[data-testid="collapsedControl"] button *,
        [data-testid="collapsedControl"] button * {
            font-family: 'Material Symbols Rounded','Material Symbols Outlined','Material Symbols Sharp','Material Icons' !important;
            font-feature-settings: 'liga' 1 !important;
            -webkit-font-feature-settings: 'liga' 1 !important;
        }

        /* إزالة أي خط/مقبض resizing بالقائمة */
        div[data-testid="stSidebarResizer"],
        div[data-testid="stSidebarResizeHandle"],
        div[data-testid="stSidebarResizeHandle"] *,
        section[data-testid="stSidebar"] div[style*="cursor: col-resize"] {
            display: none !important;
        }

        section[data-testid="stSidebar"] {
            border-right: none !important;
            border-left: none !important;
            box-shadow: none !important;
        }

/* Tabs: اجعل ترتيب الألسنة RTL */
[data-testid="stTabs"] [role="tablist"]{
    flex-direction: row-reverse !important;
    justify-content: flex-start !important;
}


/* =====================================================
           Material Icons / Symbols fixes
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

        .material-symbols-outlined,
        .material-symbols-rounded,
        .material-symbols-sharp,
        [class*="material-symbols"] {
            font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Symbols Sharp' !important;
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
   UI Cleanup
   ===================================================== */
/* لا نخفي <header> لأن زر فتح الـSidebar عند الطيّ يعتمد عليه */
#MainMenu { visibility: hidden !important; }
footer { visibility: hidden !important; height: 0 !important; }

/* لا نخفي <header> لأن زر فتح الـSidebar يعتمد عليه */
header { display: block !important; }

/* إخفاء Toolbars */
[data-testid="stElementToolbar"] { display: none !important; }
div[role="tooltip"] { display: none !important; opacity: 0 !important; visibility: hidden !important; }
button[title="View fullscreen"] { display: none !important; }

/* إزالة خط الـResizer الذي يظهر عند طيّ القائمة */
div[data-testid="stSidebarResizer"],
div[data-testid="stSidebarResizeHandle"],
div[data-testid="stSidebarResizeHandle"] * {
    display: none !important;
}

section[data-testid="stSidebar"] {
    border-right: none !important;
    border-left: none !important;
    box-shadow: none !important;
}

/* =====================================================
   Expander (رفع التباين)
           ===================================================== */
        div[data-testid="stExpander"]{
            border: 1px solid var(--border2) !important;
            border-radius: 14px !important;
            background: var(--card-bg) !important;
            box-shadow: 0 8px 18px rgba(15,23,42,0.06) !important;
            margin-bottom: 12px !important;
        }
        div[data-testid="stExpander"] details summary{
            font-weight: 900 !important;
            color: var(--primary) !important;
            padding: 12px 16px !important;
        }
        div[data-testid="stExpander"] details summary:hover{
            background: rgba(37,99,235,0.06) !important;
        }

        /* =====================================================
           KPI Cards
           ===================================================== */
        .kpi-card {
            background: var(--card-bg) !important;
            border-radius: 22px !important;
            padding: 22px 20px !important;
            position: relative;
            overflow: hidden;
            border: 1px solid var(--border) !important;
            box-shadow: var(--shadow) !important;
            transition: all 0.25s ease;
            margin-bottom: 16px !important;
        }
        .kpi-card:hover {
            transform: translateY(-4px) !important;
            box-shadow: var(--shadow2) !important;
            border-color: rgba(37,99,235,0.30) !important;
        }
        .kpi-icon-bg {
            position: absolute;
            left: -10px;
            bottom: -18px;
            font-size: 5.2rem;
            opacity: 0.10;
            transform: rotate(12deg);
            transition: all 0.35s ease;
            color: var(--txt);
            pointer-events: none;
        }
        .kpi-card:hover .kpi-icon-bg {
            transform: rotate(0deg) scale(1.12);
            opacity: 0.16;
            left: -4px;
        }
        .kpi-label{
            color: var(--muted) !important;
            font-size: 0.95rem !important;
            font-weight: 800 !important;
            margin-bottom: 6px !important;
        }
        .kpi-value{
            font-size: 2.05rem !important;
            font-weight: 950 !important;
            color: var(--txt) !important;
            direction: ltr !important;
            text-align: left !important;
            letter-spacing: 0.2px;
        }

        /* =====================================================
           Tables (أوضح) - HTML Tables (مثل جدول الصفقات)
           ===================================================== */
        .finance-table{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            border: 1px solid var(--border2);
            border-radius: 14px;
            overflow: hidden;
            background: #fff;
            margin-top: 14px;
            box-shadow: 0 8px 18px rgba(15,23,42,0.06);
        }
        .finance-table th{
            background: #F1F5FF !important;
            color: #1E40AF !important;
            font-weight: 900;
            padding: 14px;
            text-align: right;
            border-bottom: 2px solid rgba(37,99,235,0.18);
            white-space: nowrap;
        }
        .finance-table td{
            padding: 12px 14px;
            text-align: right;
            border-bottom: 1px solid rgba(15,23,42,0.08);
            color: #0F172A;
            font-weight: 700;
            white-space: nowrap;
        }
        .finance-table tr:hover td{
            background: rgba(37,99,235,0.04);
        }

        .txt-green { color: var(--green) !important; font-weight: 900 !important; }
        .txt-red   { color: var(--red) !important; font-weight: 900 !important; }
        .txt-blue  { color: var(--blue) !important; font-weight: 900 !important; }

        /* =====================================================
           Buttons
           ===================================================== */
        div.stButton > button{
            width: 100%;
            border-radius: 14px;
            height: 50px;
            font-weight: 900;
            border: 1px solid rgba(15,23,42,0.10);
            box-shadow: 0 6px 14px rgba(15,23,42,0.06);
            background: #fff;
            color: #0F172A;
            transition: 0.2s;
        }
        div.stButton > button:hover{
            transform: translateY(-2px);
            box-shadow: 0 12px 24px rgba(15,23,42,0.10);
            color: var(--primary);
            border-color: rgba(37,99,235,0.30);
        }

        /* =====================================================
           ✅ Report UI (Cards / Chips / Better JSON)
           ===================================================== */
        .os-grid{
            display:grid;
            grid-template-columns: repeat(12, 1fr);
            gap: 12px;
            margin-top: 8px;
            margin-bottom: 8px;
        }
        .os-col-12{ grid-column: span 12; }
        .os-col-6{ grid-column: span 6; }
        .os-col-4{ grid-column: span 4; }
        .os-col-3{ grid-column: span 3; }
        @media (max-width: 900px){
            .os-col-6,.os-col-4,.os-col-3{ grid-column: span 12; }
        }

        .os-card{
            transition: transform .15s ease, box-shadow .15s ease;
            background: var(--card-bg);
            border: 1px solid var(--border2);
            border-radius: 16px;
            padding: 14px 14px;
            box-shadow: 0 8px 18px rgba(15,23,42,0.06);
        }
        .os-card-title{
            font-weight: 950;
            margin-bottom: 8px;
            color: var(--txt);
            display:flex;
            align-items:center;
            gap:8px;
        }
        .os-muted{
            color: var(--muted);
            font-weight: 800;
            font-size: 0.92rem;
        }

        .os-chip{
            display:inline-flex;
            align-items:center;
            gap:8px;
            padding: 6px 10px;
            border-radius: 999px;
            border: 1px solid var(--border2);
            background: var(--soft-bg);
            font-weight: 900;
            font-size: 0.82rem;
            margin: 4px 4px 0 0;
            white-space: nowrap;
        }
        .os-chip .mi{
            font-family: 'Material Symbols Rounded' !important;
            font-size: 18px;
            line-height: 1;
        }
        .os-chip-green{ background:#DCFCE7; border-color: rgba(5,150,105,0.25); color:#166534; }
        .os-chip-red{ background:#FEE2E2; border-color: rgba(220,38,38,0.25); color:#991B1B; }
        .os-chip-blue{ background:#DBEAFE; border-color: rgba(37,99,235,0.25); color:#1E40AF; }
        .os-chip-gray{ background:#F3F4F6; border-color: rgba(55,65,81,0.18); color:#374151; }
        .os-chip-amber{ background:#FEF3C7; border-color: rgba(245,158,11,0.28); color:#92400E; }

        .os-kv{
            display:flex;
            justify-content:space-between;
            gap:12px;
            padding: 8px 0;
            border-bottom: 1px dashed rgba(15,23,42,0.12);
        }
        .os-kv:last-child{ border-bottom:none; }
        .os-k{ color: var(--muted); font-weight: 900; }
        .os-v{ color: var(--txt); font-weight: 950; direction:ltr; text-align:left; }

        /* ✅ تحسين شكل st.json / code blocks */
        div[data-testid="stJson"] pre,
        div[data-testid="stCodeBlock"] pre{
            background: #0B1220 !important;
            color: #E5E7EB !important;
            border-radius: 14px !important;
            border: 1px solid rgba(255,255,255,0.10) !important;
            padding: 14px !important;
            font-size: 0.85rem !important;
            line-height: 1.55 !important;
            direction: ltr !important;
            text-align: left !important;
            overflow-x: auto !important;
            max-height: 420px;
        }
        div[data-testid="stJson"] pre code,
        div[data-testid="stCodeBlock"] pre code{
            color: #E5E7EB !important;
            direction:ltr !important;
            text-align:left !important;
        }

        /* =====================================================
           ✅ GLOBAL TABLE THEME (الحل لمشكلتك)
           كل جداول Streamlit الحالية + المستقبلية (st.dataframe / st.table)
           بتصير مثل جدول الصفقات
           ===================================================== */

        /* الحاوية */
        div[data-testid="stDataFrame"],
        div[data-testid="stTable"]{
            border: 1px solid var(--border2) !important;
            border-radius: 14px !important;
            overflow: hidden !important;
            background: #fff !important;
            box-shadow: 0 8px 18px rgba(15,23,42,0.06) !important;
        }

        /* رأس الجدول */
        div[data-testid="stDataFrame"] thead tr th,
        div[data-testid="stTable"] thead tr th{
            background: #F1F5FF !important;
            color: #1E40AF !important;
            font-weight: 900 !important;
            border-bottom: 2px solid rgba(37,99,235,0.18) !important;
            text-align: right !important;
            white-space: nowrap !important;
        }

        /* خلايا */
        div[data-testid="stDataFrame"] tbody tr td,
        div[data-testid="stTable"] tbody tr td{
            color: #0F172A !important;
            font-weight: 700 !important;
            border-bottom: 1px solid rgba(15,23,42,0.08) !important;
            text-align: right !important;
            white-space: nowrap !important;
        }

        /* Hover */
        div[data-testid="stDataFrame"] tbody tr:hover td,
        div[data-testid="stTable"] tbody tr:hover td{
            background: rgba(37,99,235,0.04) !important;
        }

        /* إزالة حدود داخلية مزعجة */
        div[data-testid="stDataFrame"] *{ border-color: rgba(15,23,42,0.08) !important; }

        /* =====================================================
           ✅ Score Ring (دائري) - للاستخدام داخل shared.py
           ===================================================== */
        .os-ring{
            width: 98px;
            height: 98px;
            border-radius: 50%;
            display:grid;
            place-items:center;
            position:relative;
            background: conic-gradient(var(--ring-color) calc(var(--p)*1%), rgba(15,23,42,0.10) 0);
        }
        .os-ring::before{
            content:"";
            width: 74px;
            height: 74px;
            border-radius: 50%;
            background: #fff;
            border: 1px solid rgba(15,23,42,0.10);
            position:absolute;
        }
        .os-ring .os-ring-text{
            position:relative;
            font-weight: 950;
            direction:ltr;
            text-align:center;
        }
        .os-ring .os-ring-sub{
            position:relative;
            font-size: 0.78rem;
            font-weight: 900;
            color: var(--muted);
            margin-top: 2px;
        }

        /* =====================================================
           ✅ App Header (Logo + Title + Subtitle)
           ===================================================== */
        .os-app-header{
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:16px;
            padding: 14px 16px;
            border-radius: 18px;
            border: 1px solid var(--border2);
            background: linear-gradient(135deg, rgba(11,87,208,0.06), rgba(99,102,241,0.05));
            box-shadow: 0 10px 24px rgba(15,23,42,0.06);
            margin: 10px 0 14px 0;
        }
        .os-app-header .os-h-left{
            display:flex;
            align-items:center;
            gap:12px;
            min-width: 0;
        }
        .os-app-header .os-h-logo{
            width: 52px;
            height: 52px;
            border-radius: 14px;
            background: #fff;
            border: 1px solid rgba(15,23,42,0.10);
            overflow:hidden;
            display:grid;
            place-items:center;
            flex: 0 0 auto;
        }
        .os-app-header .os-h-logo img{ width:100%; height:100%; object-fit:contain; }
        .os-app-header .os-h-title{
            font-size: 1.35rem;
            font-weight: 950;
            line-height: 1.15;
            margin: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .os-app-header .os-h-sub{
            margin-top: 4px;
            color: var(--muted);
            font-weight: 800;
            font-size: 0.92rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .os-app-header .os-h-right{
            display:flex;
            gap:8px;
            flex-wrap:wrap;
            justify-content:flex-end;
        }
        @media (max-width: 900px){
            .os-app-header{ flex-direction: column; align-items: stretch; }
            .os-app-header .os-h-right{ justify-content:flex-start; }
        }

        /* =====================================================
           Mobile tweaks
           ===================================================== */
        @media (max-width: 900px){
            .kpi-card{ padding: 18px 16px !important; border-radius: 18px !important; }
            .kpi-value{ font-size: 1.85rem !important; }
        }
        /* Card hover */
.os-card:hover{transform: translateY(-2px); box-shadow: 0 12px 30px rgba(0,0,0,.35);}

/* Landing hero */
.landing-hero{
    background: linear-gradient(135deg, rgba(45,91,255,.25), rgba(139,92,246,.18));
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 20px;
    padding: 22px 22px;
    margin: 8px 0 14px 0;
}
.landing-title{
    font-size: 28px;
    font-weight: 800;
    letter-spacing: .2px;
    margin-bottom: 6px;
}
.landing-sub{
    color: var(--muted);
    font-size: 14px;
    line-height: 1.9;
    max-width: 820px;
}


        /* =====================================================
           Sidebar on the RIGHT (RTL)
        ===================================================== */

        /* Streamlit markup changes between versions; cover common wrappers */
        div[data-testid="stAppViewContainer"],
        div[data-testid="stAppViewContainer"] > div:first-child,
        div[data-testid="stAppViewContainer"] > div:first-child > div {
            flex-direction: row-reverse !important;
        }

        /* أعكس ترتيب الأعمدة/الـcolumns لتكون من اليمين لليسار */
        div[data-testid="stHorizontalBlock"] {
            flex-direction: row-reverse !important;
        }

        /* Force sidebar to live on the right */
        section[data-testid="stSidebar"] {
            order: 2 !important;
            right: 0 !important;
            left: auto !important;

            /* ✅ الحل الأساسي: لا تضع Border داخلي ثابت
               لأنه يتحول إلى خط عند طي القائمة في بعض نسخ Streamlit */
            border-left: none !important;
            border-right: none !important;
            box-shadow: none !important;
        }

        /* فاصل يظهر فقط عندما تكون القائمة "مفتوحة" (وجود زر Close/Collapse) */
        
        /* إذا كانت نسخة Streamlit تضع aria-expanded على الـSidebar */
        section[data-testid="stSidebar"][aria-expanded="true"],
        div[data-testid="stSidebar"][aria-expanded="true"],
        [data-testid="stSidebar"][aria-expanded="true"],
html:has(button[title="Close sidebar"]) section[data-testid="stSidebar"],
        html:has(button[aria-label="Close sidebar"]) section[data-testid="stSidebar"],
        html:has(button[title="Collapse sidebar"]) section[data-testid="stSidebar"],
        html:has(button[aria-label="Collapse sidebar"]) section[data-testid="stSidebar"] {
            border-left: 1px solid var(--border2) !important;
        }

        /* ✅ When sidebar is collapsed: remove any remaining strip/line */
        section[data-testid="stSidebar"][aria-expanded="false"],
        div[data-testid="stSidebar"][aria-expanded="false"],
        [data-testid="stSidebar"][aria-expanded="false"] {
            width: 0 !important;
            min-width: 0 !important;
            max-width: 0 !important;
            flex: 0 0 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            overflow: hidden !important;
            transform: translateX(100%) !important;
            border: none !important;
            box-shadow: none !important;
        }

        section[data-testid="stSidebar"][aria-expanded="false"] *,
        div[data-testid="stSidebar"][aria-expanded="false"] *,
        [data-testid="stSidebar"][aria-expanded="false"] * {
            display: none !important;
        }

        /* Fallback (إذا لم يظهر aria-expanded في بعض نسخ Streamlit) */
        html:has(button[title="Open sidebar"]) section[data-testid="stSidebar"],
        html:has(button[aria-label="Open sidebar"]) section[data-testid="stSidebar"],
        html:has(button[title="Open sidebar"]) div[data-testid="stSidebar"],
        html:has(button[aria-label="Open sidebar"]) div[data-testid="stSidebar"] {
            width: 0 !important;
            min-width: 0 !important;
            max-width: 0 !important;
            flex: 0 0 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            overflow: hidden !important;
            transform: translateX(100%) !important;
            border: none !important;
            box-shadow: none !important;
        }

        html:has(button[title="Open sidebar"]) section[data-testid="stSidebar"] *,
        html:has(button[aria-label="Open sidebar"]) section[data-testid="stSidebar"] *,
        html:has(button[title="Open sidebar"]) div[data-testid="stSidebar"] *,
        html:has(button[aria-label="Open sidebar"]) div[data-testid="stSidebar"] * {
            display: none !important;
        }

        /* Keep main content on the left */
        section[data-testid="stMain"],
        [data-testid="stMain"] {
            order: 1 !important;
        }

        /* Collapsed control button on the top-right */
        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"] {
            right: 0.75rem !important;
            left: auto !important;
        }

        /* BaseWeb (Streamlit widgets) يميل لفرض LTR */
        [data-baseweb],
        div[data-baseweb="select"],
        div[data-baseweb="popover"] {
            direction: rtl !important;
            text-align: right !important;
        }



/* =====================================================
   RTL LAST-OVERRIDE (Do not move)
   - BaseWeb Tabs + Streamlit Columns are still behaving LTR in some views.
   - This block intentionally overrides earlier rules with MAX priority.
   ===================================================== */

/* 1) Streamlit Tabs (BaseWeb) — rely on `direction: rtl` (better underline positioning) */
[data-testid="stTabs"]{
  direction: rtl !important;
}
[data-testid="stTabs"] [data-baseweb="tab-list"],
[data-testid="stTabs"] [role="tablist"]{
  direction: rtl !important;
  flex-direction: row-reverse !important;   /* force RTL visual order */
  justify-content: flex-end !important; /* keep tabs aligned to the RIGHT */
  text-align: right !important;
}
[data-testid="stTabs"] [data-baseweb="tab"],
[data-testid="stTabs"] [role="tab"]{
  direction: rtl !important;
  text-align: right !important;
}

/* 2) Streamlit Columns — rely on rtl flow instead of row-reverse */
div[data-testid="stHorizontalBlock"],
div[data-testid="stColumns"],
.stHorizontalBlock,
.stColumns{
  direction: rtl !important;
  flex-direction: row !important;  /* rtl makes first column appear on the RIGHT */
}

/* 3) Widget labels — guarantee RTL in forms (login/register) */
form, form *{
  direction: rtl !important;
}
div[data-testid="stTextInput"],
div[data-testid="stTextInput"] label,
div[data-testid="stTextInput"] p,
div[data-testid="stSelectbox"],
div[data-testid="stSelectbox"] label,
div[data-testid="stSelectbox"] p,
div[data-testid="stCheckbox"],
div[data-testid="stCheckbox"] label,
div[data-testid="stCheckbox"] p{
  direction: rtl !important;
  text-align: right !important;
}

/* 4) BaseWeb inputs — icon/prefix on RIGHT */
[data-baseweb="input"] > div,
[data-baseweb="textarea"] > div{
  flex-direction: row-reverse !important;
}

/* 5) KPI icon background on RIGHT */
.kpi-icon-bg{
  right: -10px !important;
  left: auto !important;
}
.kpi-card:hover .kpi-icon-bg{
  right: -4px !important;
  left: auto !important;
}



/* 6) Force headings/text RTL (fix st.title/st.header misalignment) */
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stApp [data-testid="stTitle"], .stApp [data-testid="stHeader"], .stApp [data-testid="stSubheader"],
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stMarkdownContainer"] * {
  direction: rtl !important;
  text-align: right !important;
  unicode-bidi: plaintext !important;
}


/* =====================================================
   Typography polish (Arabic-first)
   - تحسين الخط، الارتفاع بين السطور، وحجم العناوين
   - بدون تغيير أي منطق/اتجاه RTL أو توزيع العناصر
   ===================================================== */

.stApp{
  -webkit-font-smoothing: antialiased !important;
  -moz-osx-font-smoothing: grayscale !important;
  text-rendering: optimizeLegibility !important;
  font-size: 16px !important;
  line-height: 1.85 !important;
}

/* نصوص عامة */
.stApp p,
.stApp li,
.stApp label,
.stApp small,
.stApp .stMarkdown,
.stApp [data-testid="stMarkdownContainer"]{
  line-height: 1.9 !important;
  font-weight: 700 !important;
}

.stApp [data-testid="stMarkdownContainer"] p{
  margin: 0.35rem 0 0.70rem !important;
  color: var(--txt) !important;
}

/* عناوين */
.stApp h1,
.stApp [data-testid="stTitle"]{
  font-size: clamp(1.85rem, 2.6vw, 2.45rem) !important;
  font-weight: 950 !important;
  line-height: 1.25 !important;
  margin: 0.35rem 0 0.65rem !important;
}
.stApp h2,
.stApp [data-testid="stHeader"]{
  font-size: clamp(1.45rem, 2.1vw, 2.05rem) !important;
  font-weight: 950 !important;
  line-height: 1.28 !important;
  margin: 0.30rem 0 0.55rem !important;
}
.stApp h3,
.stApp [data-testid="stSubheader"]{
  font-size: clamp(1.15rem, 1.7vw, 1.55rem) !important;
  font-weight: 900 !important;
  line-height: 1.32 !important;
  margin: 0.25rem 0 0.45rem !important;
}

/* مسافات أفضل للفواصل */
.stApp hr{
  margin: 1.10rem 0 !important;
  border-color: rgba(15,23,42,0.10) !important;
}

/* Labels & Inputs */
.stApp label{
  font-size: 0.98rem !important;
  font-weight: 900 !important;
  color: var(--txt) !important;
  margin-bottom: 6px !important;
}

.stApp input,
.stApp textarea,
.stApp select{
  font-size: 1.02rem !important;
  font-weight: 800 !important;
  line-height: 1.6 !important;
}

/* BaseWeb inputs padding (يحسن شكل حقول تسجيل الدخول والبحث) */
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea{
  padding: 0.70rem 0.90rem !important;
  border-radius: 14px !important;
}

/* Buttons */
div.stButton > button{
  font-size: 1.02rem !important;
  letter-spacing: 0.15px !important;
}

/* Tabs */
[data-testid="stTabs"] [data-baseweb="tab"],
[data-testid="stTabs"] [role="tab"]{
  font-size: 0.98rem !important;
  font-weight: 900 !important;
  padding: 10px 16px !important;
}

/* Metrics (مثل TASI) */
[data-testid="stMetricLabel"]{
  font-size: 0.98rem !important;
  font-weight: 900 !important;
  color: var(--muted) !important;
}
[data-testid="stMetricValue"]{
  font-size: 2.10rem !important;
  font-weight: 950 !important;
  line-height: 1.15 !important;
  letter-spacing: 0.2px !important;
  font-variant-numeric: tabular-nums !important;
}
[data-testid="stMetricDelta"]{
  font-weight: 900 !important;
  font-variant-numeric: tabular-nums !important;
}

/* KPI cards */
.kpi-label{
  font-size: 1.00rem !important;
  font-weight: 900 !important;
}
.kpi-value{
  font-size: clamp(1.70rem, 2.2vw, 2.15rem) !important;
  line-height: 1.10 !important;
  font-variant-numeric: tabular-nums !important;
}

/* App header */
.os-app-header .os-h-title{
  font-size: 1.45rem !important;
  font-weight: 950 !important;
}
.os-app-header .os-h-sub{
  font-size: 0.98rem !important;
  line-height: 1.7 !important;
}


</style>
        """

    # Insert theme variables safely without turning the whole CSS into an f-string.
    css = css.replace("__VAR_CSS__", var_css)

    st.markdown(textwrap.dedent(css).strip(), unsafe_allow_html=True)
