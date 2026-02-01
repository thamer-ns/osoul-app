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

        /* ✅ Material Symbols (سبب expand_more كنص) */
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Sharp:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');

        /* =====================================================
           Theme variables (لتحسين الوضوح)
           ===================================================== */
        :root{
            --txt: #0F172A;
            --muted: #64748B;
            --primary: #0B57D0;      /* أزرق أوضح */
            --primary2: #083A9B;
            --border: rgba(15,23,42,0.12);
            --border2: rgba(15,23,42,0.18);
            --card-bg: #ffffff;
            --soft-bg: #F8FAFC;
            --shadow: 0 10px 25px rgba(15,23,42,0.10);
            --shadow2: 0 20px 45px rgba(15,23,42,0.12);
            --green: #059669;
            --red: #DC2626;
            --blue: #2563EB;
        }

        /* =====================================================
           Base RTL + Cairo
           (بدون كسر الأيقونات)
           ===================================================== */
        html, body, [class*="css"], p, div, label, input, button, textarea, h1,h2,h3,h4,h5,h6 {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
            color: var(--txt);
        }

        /* ✅ طبّق Cairo على span لكن استثنِ أيقونات Material */
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
           UI Cleanup
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
           KPI Cards (أقوى/أوضح مثل قبل)
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
            opacity: 0.10;              /* ✅ كان منخفض—رفعناه شوي */
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
            font-size: 2.05rem !important;   /* ✅ أوضح */
            font-weight: 950 !important;
            color: var(--txt) !important;
            direction: ltr !important;
            text-align: left !important;
            letter-spacing: 0.2px;
        }

        /* =====================================================
           TASI Card (أوضح + Badge أجمل)
           ===================================================== */
        .tasi-card{
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary2) 100%) !important;
            border-radius: 22px !important;
            padding: 26px !important;
            color: #fff !important;
            display:flex;
            justify-content:space-between;
            align-items:center;
            box-shadow: 0 16px 38px rgba(11,87,208,0.28) !important;
            margin-bottom: 22px !important;
            border: 1px solid rgba(255,255,255,0.14) !important;
        }
        .tasi-card *{
            color:#fff !important;
        }
        /* لو عندك داخلها رقم كبير اعطه بروز */
        .tasi-card .tasi-number{
            font-size: 3.2rem !important;
            font-weight: 950 !important;
            direction:ltr !important;
            text-align:left !important;
            letter-spacing: 0.5px;
            text-shadow: 0 2px 10px rgba(0,0,0,0.12);
        }
        .tasi-card .tasi-sub{
            opacity: 0.92;
            font-weight: 800;
        }
        .tasi-card .tasi-badge{
            display:inline-flex;
            align-items:center;
            gap:8px;
            padding: 6px 12px;
            border-radius: 999px;
            background: rgba(255,255,255,0.18);
            border: 1px solid rgba(255,255,255,0.20);
            font-weight: 900;
            direction:ltr;
        }

        /* =====================================================
           Tables (أوضح)
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

        .badge-open{
            background: #DCFCE7;
            color: #166534;
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 900;
            border: 1px solid rgba(5,150,105,0.20);
        }
        .badge-closed{
            background: #F3F4F6;
            color: #374151;
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 900;
            border: 1px solid rgba(55,65,81,0.14);
        }

        /* Buttons */
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

        /* Grid container لعرض بطاقات جنب بعض */
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

        /* Card */
        .os-card{
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

        /* Chips / Badges */
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

        /* Key/Value rows */
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
           Mobile tweaks (مثل صورك على الجوال)
           ===================================================== */
        @media (max-width: 900px){
            .kpi-card{ padding: 18px 16px !important; border-radius: 18px !important; }
            .kpi-value{ font-size: 1.85rem !important; }
            .tasi-card{ padding: 20px !important; border-radius: 18px !important; }
            .tasi-card .tasi-number{ font-size: 2.6rem !important; }
        }
        </style>
        """,
        unsafe_allow_html=True
    )