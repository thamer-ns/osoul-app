# styles.py
import streamlit as st
import textwrap


def apply_custom_css():
    """Inject global CSS.

    - Keeps your existing look/logic (RTL, sidebar-on-right, icons safety).
    - Adds light/dark theming via CSS variables.
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


            --fs-base: 15px;
            --fs-sm: 13px;
            --fs-xs: 12px;
            --lh-base: 1.75;
            --table-row-alt: rgba(226,232,240,0.04);
            --table-hover: rgba(96,165,250,0.10);

            /* polish */
            --radius-xl: 24px;
            --radius-lg: 18px;
            --radius-md: 14px;
            --radius-sm: 12px;
            --focus: 0 0 0 4px rgba(45,91,255,0.25);

            --table-bg: #0B1220;
            --table-head-bg: #111B2F;
            --table-head-txt: #BFDBFE;
            --table-cell-txt: #E5E7EB;
            --table-grid: rgba(148,163,184,0.22);
            --table-hover: rgba(96,165,250,0.07);
        """
    else:
        var_css = """
            --app-bg: #F6F8FB;
            --txt: #0F172A;
            --muted: #64748B;
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


            --fs-base: 15px;
            --fs-sm: 13px;
            --fs-xs: 12px;
            --lh-base: 1.75;
            --table-row-alt: rgba(2,6,23,0.02);
            --table-hover: rgba(37,99,235,0.06);

            /* polish */
            --radius-xl: 24px;
            --radius-lg: 18px;
            --radius-md: 14px;
            --radius-sm: 12px;
            --focus: 0 0 0 4px rgba(45,91,255,0.18);

            --table-bg: #ffffff;
            --table-head-bg: #EEF2FF;
            --table-head-txt: #1E3A8A;
            --table-cell-txt: #0F172A;
            --table-grid: rgba(15,23,42,0.08);
            --table-hover: rgba(37,99,235,0.05);
        """

    css = """
        <style>
        /* =====================================================
           Fonts
           ===================================================== */
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;600;700&display=swap');
        @import url('https://fonts.googleapis.com/icon?family=Material+Icons');

        /* ✅ Material Symbols (سبب expand_more كنص) */
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Sharp:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');

        :root {
            --font-ar: 'Cairo', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
        }

        /* =====================================================
           Theme variables
           ===================================================== */
        :root{
            __VAR_CSS__
        }

        /* ✅ App background for both themes */
        .stApp { background: var(--app-bg) !important; }

        /* =====================================================
           RTL + Cairo (مركزي) + حماية أيقونات Streamlit
           ===================================================== */
        html, body {
            direction: rtl !important;
            text-align: right !important;
        }

        .stApp {
            direction: rtl !important;
            text-align: right !important;
            color: var(--txt) !important;

            /* typography base */
            font-family: var(--font-ar) !important;
            font-size: var(--fs-base) !important;
            line-height: var(--lh-base) !important;
            -webkit-font-smoothing: antialiased;
            text-rendering: geometricPrecision;
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
        div[data-testid="stForm"] small { display: none !important; }

        /* تطبيق الخط بالوراثة */
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

        /* =====================================================
           Typography polish (بدون تغيير ترتيب/RTL)
           ===================================================== */
        .stApp h1{ font-size: 2.05rem !important; font-weight: 950 !important; line-height: 1.25 !important; margin-bottom: 0.35rem !important; }
        .stApp h2{ font-size: 1.65rem !important; font-weight: 950 !important; line-height: 1.3 !important; margin-bottom: 0.35rem !important; }
        .stApp h3{ font-size: 1.35rem !important; font-weight: 900 !important; line-height: 1.35 !important; }
        .stApp p, .stApp li{ font-size: 1rem !important; line-height: 1.95 !important; color: var(--txt) !important; }
        .stApp small, .stApp .os-muted{ line-height: 1.8 !important; }

        /* link readability */
        .stApp a{ color: var(--primary) !important; font-weight: 900 !important; text-decoration: none !important; }
        .stApp a:hover{ text-decoration: underline !important; }

        /* inputs look */
        div[data-baseweb="input"] input,
        div[data-baseweb="textarea"] textarea,
        div[data-baseweb="select"] input{
            border-radius: var(--radius-md) !important;
            border: 1px solid var(--border2) !important;
            background: var(--card-bg) !important;
            color: var(--txt) !important;
            min-height: 46px !important;
            padding: 10px 12px !important;
            font-weight: 700 !important;
        }
        div[data-baseweb="input"] input:focus,
        div[data-baseweb="textarea"] textarea:focus,
        div[data-baseweb="select"] input:focus{
            outline: none !important;
            box-shadow: var(--focus) !important;
            border-color: rgba(45,91,255,0.45) !important;
        }
        .stTextInput label, .stPassword label, .stNumberInput label, .stTextArea label,
        .stSelectbox label, .stMultiSelect label, .stDateInput label{
            font-weight: 900 !important;
            color: var(--txt) !important;
            font-size: 0.95rem !important;
        }

        /* GLOBAL RTL text enforcement (as before) */
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

        /* التبويبات */
        div[data-testid="stTabs"] [data-baseweb="tab-list"] {
            direction: rtl !important;
            unicode-bidi: plaintext !important;
            flex-direction: row-reverse !important;
            justify-content: flex-end !important;
            gap: 6px !important;
            padding-bottom: 6px !important;
            border-bottom: 1px solid var(--border) !important;
        }
        div[data-testid="stTabs"] [data-baseweb="tab"] {
            direction: rtl !important;
            text-align: right !important;
            unicode-bidi: plaintext !important;
            font-weight: 900 !important;
            font-size: 0.95rem !important;
            border-radius: 999px !important;
            padding: 10px 14px !important;
        }
        /* active tab highlight */
        div[data-testid="stTabs"] [aria-selected="true"]{
            background: rgba(45,91,255,0.10) !important;
            box-shadow: 0 8px 16px rgba(15,23,42,0.06) !important;
        }

        /* حقول الإدخال داخل الحقول */
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

        /* عناصر قياس Streamlit (مثل المؤشر العام TASI) */
        [data-testid="stMetric"]{
            border-radius: var(--radius-lg) !important;
            padding: 14px 14px !important;
        }
        [data-testid="stMetric"] [data-testid="stMetricLabel"]{
            color: var(--muted) !important;
            font-weight: 900 !important;
            font-size: 0.95rem !important;
        }
        [data-testid="stMetric"] [data-testid="stMetricValue"]{
            font-weight: 950 !important;
            font-size: 2.1rem !important;
            letter-spacing: 0.3px !important;
            color: var(--txt) !important;
        }
        [data-testid="stMetric"] [data-testid="stMetricDelta"]{
            font-weight: 900 !important;
            font-size: 0.95rem !important;
        }
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
           Sidebar collapsed control (كما هو)
           ===================================================== */
        div[data-testid="stSidebarCollapsedControl"],
        div[data-testid="collapsedControl"],
        [data-testid="collapsedControl"] {
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

        /* =====================================================
           UI Cleanup
           ===================================================== */
        #MainMenu { visibility: hidden !important; }
        footer { visibility: hidden !important; height: 0 !important; }
        header { display: block !important; }

        [data-testid="stElementToolbar"] { display: none !important; }
        div[role="tooltip"] { display: none !important; opacity: 0 !important; visibility: hidden !important; }
        button[title="View fullscreen"] { display: none !important; }


/* =====================================================
   Top bar cleanup (إخفاء أزرار Streamlit العلوية بدون كسر زر فتح القائمة)
   ===================================================== */
/* نُبقي <header> موجود لأن زر فتح القائمة يعتمد عليه */
header { display: block !important; }

/* إخفاء الزخرفة/الخط العلوي */
div[data-testid="stDecoration"] { display: none !important; }

/* إخفاء شريط الأدوات العلوي (Share / Star / …) */
div[data-testid="stToolbar"],
div[data-testid="stToolbarActions"],
div[data-testid="stAppToolbar"],
div[data-testid="stStatusWidget"] { display: none !important; }

/* إخفاء Toolbars/Tooltips داخل الصفحة */
[data-testid="stElementToolbar"] { display: none !important; }
div[role="tooltip"] { display: none !important; opacity: 0 !important; visibility: hidden !important; }
button[title="View fullscreen"] { display: none !important; }

/* =====================================================
   Sidebar collapsed control (زر فتح القائمة) — دائمًا ظاهر
   ===================================================== */
div[data-testid="stSidebarCollapsedControl"],
div[data-testid="collapsedControl"],
[data-testid="collapsedControl"]{
    position: fixed !important;
    top: 0.85rem !important;
    right: 0.85rem !important;
    left: auto !important;
    width: auto !important;
    height: auto !important;
    padding: 0 !important;
    margin: 0 !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    z-index: 100001 !important;
    pointer-events: auto !important;
}

div[data-testid="stSidebarCollapsedControl"]::before,
div[data-testid="stSidebarCollapsedControl"]::after,
div[data-testid="collapsedControl"]::before,
div[data-testid="collapsedControl"]::after,
[data-testid="collapsedControl"]::before,
[data-testid="collapsedControl"]::after{
    display: none !important;
    content: none !important;
}

div[data-testid="stSidebarCollapsedControl"] button,
div[data-testid="collapsedControl"] button,
[data-testid="collapsedControl"] button,
button[title="Open sidebar"],
button[aria-label="Open sidebar"]{
    pointer-events: auto !important;
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
}

div[data-testid="stSidebarCollapsedControl"] button *,
div[data-testid="collapsedControl"] button *,
[data-testid="collapsedControl"] button *{
    font-family: 'Material Symbols Rounded','Material Symbols Outlined','Material Symbols Sharp','Material Icons' !important;
    font-feature-settings: 'liga' 1 !important;
    -webkit-font-feature-settings: 'liga' 1 !important;
}


/* =====================================================
           Expander
           ===================================================== */
        div[data-testid="stExpander"]{
            border: 1px solid var(--border2) !important;
            border-radius: var(--radius-lg) !important;
            background: var(--card-bg) !important;
            box-shadow: 0 8px 18px rgba(15,23,42,0.06) !important;
            margin-bottom: 12px !important;
        }
        div[data-testid="stExpander"] details summary{
            font-weight: 950 !important;
            color: var(--primary) !important;
            padding: 12px 16px !important;
            border-radius: var(--radius-lg) !important;
        }
        div[data-testid="stExpander"] details summary:hover{
            background: rgba(37,99,235,0.06) !important;
        }

        /* =====================================================
           KPI Cards (polish)
           ===================================================== */
        .kpi-card {
            background: var(--card-bg) !important;
            border-radius: var(--radius-xl) !important;
            padding: 18px 18px !important;
            position: relative;
            overflow: hidden;
            border: 1px solid var(--border) !important;
            box-shadow: var(--shadow) !important;
            transition: all 0.22s ease;
            margin-bottom: 14px !important;
        }
        .kpi-card:hover {
            transform: translateY(-3px) !important;
            box-shadow: var(--shadow2) !important;
            border-color: rgba(37,99,235,0.30) !important;
        }
        .kpi-icon-bg {
            position: absolute;
            left: -10px;
            bottom: -18px;
            font-size: 5.0rem;
            opacity: 0.08;
            transform: rotate(10deg);
            transition: all 0.35s ease;
            color: var(--txt);
            pointer-events: none;
            filter: saturate(0.9);
        }
        .kpi-card:hover .kpi-icon-bg {
            transform: rotate(0deg) scale(1.08);
            opacity: 0.12;
            left: -6px;
        }
        .kpi-label{
            color: var(--muted) !important;
            font-size: 0.92rem !important;
            font-weight: 900 !important;
            margin-bottom: 6px !important;
        }
        .kpi-value{
            font-size: 1.85rem !important; /* أقل شوي عشان ما يكبر نصوص مثل "انتقل للتنويهات" */
            font-weight: 950 !important;
            color: var(--txt) !important;
            direction: ltr !important;
            text-align: left !important;
            letter-spacing: 0.15px;
            line-height: 1.25 !important;
        }

        /* =====================================================
           Tables (HTML tables مثل جدول الصفقات)
           - رجعناها أجمل + متوافقة مع الثيم
           ===================================================== */
        .finance-table{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            border: 1px solid var(--table-grid);
            border-radius: var(--radius-lg);
            overflow: hidden;
            background: var(--table-bg);
            margin-top: 14px;
            box-shadow: 0 8px 18px rgba(15,23,42,0.06);
        }
        .finance-table th{
            background: var(--table-head-bg) !important;
            color: var(--table-head-txt) !important;
            font-weight: 950;
            padding: 12px 12px;
            text-align: right;
            border-bottom: 1px solid var(--table-grid);
            white-space: nowrap;
            font-size: 0.90rem;
        }
        .finance-table td{
            padding: 11px 12px;
            text-align: right;
            border-bottom: 1px solid var(--table-grid);
            color: var(--table-cell-txt);
            font-weight: 750;
            white-space: nowrap;
            font-size: 0.92rem;
        }
        .finance-table tr:nth-child(even) td{
            background: rgba(148,163,184,0.05);
        }
        .finance-table tr:hover td{
            background: var(--table-hover) !important;
        }


        .txt-green { color: var(--green) !important; font-weight: 950 !important; }
        .txt-red   { color: var(--red) !important; font-weight: 950 !important; }
        .txt-blue  { color: var(--blue) !important; font-weight: 950 !important; }

        /* تمييز خلايا الحالة إذا كان بداخلها لون (للصفقات المفتوحة/المغلقة) */
        .finance-table td:has(.txt-green){ background: rgba(5,150,105,0.07) !important; }
        .finance-table td:has(.txt-red){ background: rgba(220,38,38,0.06) !important; }

        /* ✅ Pills optional (إذا كانت موجودة في كود الجدول) */
        .pill{
            display:inline-flex; align-items:center; gap:8px;
            padding: 4px 10px;
            border-radius: 999px;
            border: 1px solid var(--table-grid);
            background: rgba(148,163,184,0.06);
            font-weight: 950;
            font-size: 0.84rem;
            white-space: nowrap;
        }
        .pill-open{ background: rgba(5,150,105,0.12); border-color: rgba(5,150,105,0.25); color: var(--green); }
        .pill-open::before{ content:"●"; font-size: 10px; line-height: 1; }
        .pill-closed{ background: rgba(220,38,38,0.10); border-color: rgba(220,38,38,0.25); color: var(--red); }
        .pill-closed::before{ content:"●"; font-size: 10px; line-height: 1; }

        /* =====================================================
           Buttons (polish)
           ===================================================== */
        div.stButton > button{
            width: 100%;
            border-radius: var(--radius-md);
            height: 48px;
            font-weight: 950;
            border: 1px solid var(--border2);
            box-shadow: 0 6px 14px rgba(15,23,42,0.06);
            background: var(--card-bg);
            color: var(--txt);
            transition: 0.2s;
        }
        div.stButton > button:hover{
            transform: translateY(-2px);
            box-shadow: 0 12px 24px rgba(15,23,42,0.10);
            color: var(--primary);
            border-color: rgba(37,99,235,0.30);
        }
        div.stButton > button:focus{
            outline: none !important;
            box-shadow: var(--focus) !important;
        }

        /* =====================================================
           Report UI (Cards / Chips / Better JSON) - كما هو مع تحسين بسيط
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
            border-radius: var(--radius-lg);
            padding: 14px 14px;
            box-shadow: 0 8px 18px rgba(15,23,42,0.06);
        }
        .os-card:hover{ transform: translateY(-2px); box-shadow: 0 12px 30px rgba(15,23,42,.12); }

        .os-card-title{
            font-weight: 950;
            margin-bottom: 8px;
            color: var(--txt);
            display:flex;
            align-items:center;
            gap:8px;
            font-size: 1.05rem;
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
        .os-chip-green{ background: rgba(5,150,105,0.12); border-color: rgba(5,150,105,0.25); color: var(--green); }
        .os-chip-red{ background: rgba(220,38,38,0.10); border-color: rgba(220,38,38,0.25); color: var(--red); }
        .os-chip-blue{ background: rgba(37,99,235,0.10); border-color: rgba(37,99,235,0.22); color: var(--blue); }
        .os-chip-gray{ background: rgba(148,163,184,0.16); border-color: rgba(148,163,184,0.22); color: var(--txt); }
        .os-chip-amber{ background: rgba(245,158,11,0.14); border-color: rgba(245,158,11,0.22); color: var(--amber); }

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
            border-radius: var(--radius-lg) !important;
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
           ✅ GLOBAL TABLE THEME (مطابق لصورة 703)
           - يوحّد st.dataframe / st.table / HTML tables
           - يمنع تلوين الخلفيات (Heatmap) الذي شوّه الجداول (مثل 815)
           - يسمح لألوان النص/البادجات/الأيقونات بالظهور بدون كسرها
           ===================================================== */

        /* Container */
        div[data-testid="stDataFrame"],
        div[data-testid="stTable"]{
            border: 1px solid var(--table-grid) !important;
            border-radius: var(--table-radius) !important;
            overflow: hidden !important;
            background: var(--table-bg) !important;
            box-shadow: 0 10px 24px rgba(15,23,42,0.06) !important;
        }

        /* --- HTML tables inside Streamlit (st.table, st.dataframe(styler), and custom tables) --- */
        div[data-testid="stDataFrame"] table,
        div[data-testid="stTable"] table,
        table.finance-table,
        table.dataframe,
        .dataframe{
            width: 100% !important;
            border-collapse: separate !important;
            border-spacing: 0 !important;
            direction: rtl !important;
            background: var(--table-bg) !important;
        }

        /* Header cells */
        div[data-testid="stDataFrame"] thead th,
        div[data-testid="stTable"] thead th,
        table.finance-table thead th,
        table.dataframe thead th,
        .dataframe thead th,
        table.finance-table th,
        table.dataframe th,
        .dataframe th{
            background: var(--table-head-bg) !important;
            color: var(--table-head-txt) !important;
            font-weight: 950 !important;
            font-size: var(--fs-sm) !important;
            padding: 12px 12px !important;
            text-align: right !important;
            border-bottom: 1px solid var(--table-grid) !important;
            white-space: nowrap !important;
        }

        /* Body cells */
        div[data-testid="stDataFrame"] tbody td,
        div[data-testid="stTable"] tbody td,
        table.finance-table tbody td,
        table.dataframe tbody td,
        .dataframe tbody td,
        table.finance-table td,
        table.dataframe td,
        .dataframe td{
            font-size: var(--fs-sm) !important;
            font-weight: 800 !important;
            padding: 10px 12px !important;
            border-bottom: 1px solid var(--table-grid) !important;
            border-inline-start: 1px solid var(--table-grid) !important;
            text-align: right !important;
            white-space: nowrap !important;
            background-color: transparent !important; /* إزالة ألوان الخلفيات غير المرغوبة */
        }
        div[data-testid="stDataFrame"] tbody tr td:first-child,
        div[data-testid="stTable"] tbody tr td:first-child,
        table.finance-table tbody tr td:first-child,
        table.dataframe tbody tr td:first-child,
        .dataframe tbody tr td:first-child{
            border-inline-start: none !important;
        }

        /* Row stripes + hover */
        div[data-testid="stDataFrame"] tbody tr:nth-child(even) td,
        div[data-testid="stTable"] tbody tr:nth-child(even) td,
        table.finance-table tbody tr:nth-child(even) td,
        table.dataframe tbody tr:nth-child(even) td,
        .dataframe tbody tr:nth-child(even) td{
            background-color: var(--table-row-alt) !important;
        }
        div[data-testid="stDataFrame"] tbody tr:hover td,
        div[data-testid="stTable"] tbody tr:hover td,
        table.finance-table tbody tr:hover td,
        table.dataframe tbody tr:hover td,
        .dataframe tbody tr:hover td{
            background-color: var(--table-hover) !important;
        }

        /* --- Streamlit interactive DataFrame grid (newer versions) --- */
        div[data-testid="stDataFrame"] [role="columnheader"]{
            background: var(--table-head-bg) !important;
            color: var(--table-head-txt) !important;
            font-weight: 950 !important;
            font-size: var(--fs-sm) !important;
            border-bottom: 1px solid var(--table-grid) !important;
        }
        div[data-testid="stDataFrame"] [role="gridcell"]{
            font-size: var(--fs-sm) !important;
            font-weight: 800 !important;
            border-bottom: 1px solid var(--table-grid) !important;
            background-color: transparent !important;
        }
        div[data-testid="stDataFrame"] [role="rowgroup"] [role="row"]:nth-child(even) [role="gridcell"]{
            background-color: var(--table-row-alt) !important;
        }
        div[data-testid="stDataFrame"] [role="rowgroup"] [role="row"]:hover [role="gridcell"]{
            background-color: var(--table-hover) !important;
        }

        /* Badges / pills inside tables (إذا كانت الخلية تحتوي <span class="..."> ) */
        div[data-testid="stDataFrame"] .os-pill,
        div[data-testid="stTable"] .os-pill,
        .finance-table .os-pill{
            display: inline-flex !important;
            align-items: center !important;
            gap: 6px !important;
            padding: 4px 10px !important;
            border-radius: 999px !important;
            font-weight: 950 !important;
            font-size: var(--fs-xs) !important;
            line-height: 1.2 !important;
            border: 1px solid rgba(148,163,184,0.28) !important;
            background: var(--soft-bg) !important;
            white-space: nowrap !important;
        }
        div[data-testid="stDataFrame"] .os-pill.green,
        div[data-testid="stTable"] .os-pill.green,
        .finance-table .os-pill.green,
        div[data-testid="stDataFrame"] .os-pill-open,
        div[data-testid="stTable"] .os-pill-open,
        .finance-table .os-pill-open{
            background: rgba(5,150,105,0.14) !important;
            border-color: rgba(5,150,105,0.28) !important;
            color: #0F5132 !important;
        }
        div[data-testid="stDataFrame"] .os-pill.red,
        div[data-testid="stTable"] .os-pill.red,
        .finance-table .os-pill.red,
        div[data-testid="stDataFrame"] .os-pill-close,
        div[data-testid="stTable"] .os-pill-close,
        .finance-table .os-pill-close{
            background: rgba(220,38,38,0.14) !important;
            border-color: rgba(220,38,38,0.28) !important;
            color: #7F1D1D !important;
        }


/* =====================================================
           ✅ Score Ring
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
            background: var(--card-bg);
            border: 1px solid var(--border);
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
            border-radius: var(--radius-xl);
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
            background: var(--card-bg);
            border: 1px solid var(--border);
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

        /* Landing hero */
        .landing-hero{
            background: linear-gradient(135deg, rgba(45,91,255,.22), rgba(139,92,246,.16));
            border: 1px solid var(--border2);
            border-radius: var(--radius-xl);
            padding: 18px 18px;
            margin: 8px 0 14px 0;
        }
        .landing-title{
            font-size: 26px;
            font-weight: 950;
            letter-spacing: .2px;
            margin-bottom: 6px;
        }
        .landing-sub{
            color: var(--muted);
            font-size: 14px;
            line-height: 1.95;
            max-width: 820px;
            font-weight: 700;
        }

        /* =====================================================
           Sidebar on the RIGHT (RTL) — as-is
           ===================================================== */
        div[data-testid="stAppViewContainer"],
        div[data-testid="stAppViewContainer"] > div:first-child,
        div[data-testid="stAppViewContainer"] > div:first-child > div {
            flex-direction: row-reverse !important;
        }

        div[data-testid="stHorizontalBlock"] { flex-direction: row-reverse !important; }

        section[data-testid="stSidebar"] {
            order: 2 !important;
            right: 0 !important;
            left: auto !important;
            border-left: none !important;
            border-right: none !important;
            box-shadow: none !important;
        }

        section[data-testid="stSidebar"][aria-expanded="true"],
        div[data-testid="stSidebar"][aria-expanded="true"],
        [data-testid="stSidebar"][aria-expanded="true"],
        html:has(button[title="Close sidebar"]) section[data-testid="stSidebar"],
        html:has(button[aria-label="Close sidebar"]) section[data-testid="stSidebar"],
        html:has(button[title="Collapse sidebar"]) section[data-testid="stSidebar"],
        html:has(button[aria-label="Collapse sidebar"]) section[data-testid="stSidebar"] {
            border-left: 1px solid var(--border2) !important;
        }

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

        section[data-testid="stMain"],
        [data-testid="stMain"] { order: 1 !important; }

        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"] {
            right: 0.75rem !important;
            left: auto !important;
        }

        [data-baseweb],
        div[data-baseweb="select"],
        div[data-baseweb="popover"] {
            direction: rtl !important;
            text-align: right !important;
        }

        /* =====================================================
           RTL LAST-OVERRIDE (Do not move) — keep layout fixes
           ===================================================== */
        [data-testid="stTabs"]{ direction: rtl !important; }
        [data-testid="stTabs"] [data-baseweb="tab-list"],
        [data-testid="stTabs"] [role="tablist"]{
            direction: rtl !important;
            flex-direction: row-reverse !important;
            justify-content: flex-end !important;
            text-align: right !important;
        }
        [data-testid="stTabs"] [data-baseweb="tab"],
        [data-testid="stTabs"] [role="tab"]{
            direction: rtl !important;
            text-align: right !important;
        }

        div[data-testid="stHorizontalBlock"],
        div[data-testid="stColumns"],
        .stHorizontalBlock,
        .stColumns{
            direction: rtl !important;
            flex-direction: row !important;
        }

        form, form *{ direction: rtl !important; }
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

        [data-baseweb="input"] > div,
        [data-baseweb="textarea"] > div{
            flex-direction: row-reverse !important;
        }

        .kpi-icon-bg{
            right: -10px !important;
            left: auto !important;
        }
        .kpi-card:hover .kpi-icon-bg{
            right: -6px !important;
            left: auto !important;
        }

        .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
        .stApp [data-testid="stTitle"], .stApp [data-testid="stHeader"], .stApp [data-testid="stSubheader"],
        .stApp [data-testid="stMarkdownContainer"],
        .stApp [data-testid="stMarkdownContainer"] * {
            direction: rtl !important;
            text-align: right !important;
            unicode-bidi: plaintext !important;
        }

        /* Mobile tweaks */
        @media (max-width: 900px){
            .kpi-card{ padding: 16px 14px !important; border-radius: 18px !important; }
            .kpi-value{ font-size: 1.65rem !important; }
            [data-testid="stMetric"] [data-testid="stMetricValue"]{ font-size: 1.85rem !important; }
        }

        </style>
        """

    css = css.replace("__VAR_CSS__", var_css)
    st.markdown(textwrap.dedent(css).strip(), unsafe_allow_html=True)
