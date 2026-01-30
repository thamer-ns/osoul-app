# styles.py
import streamlit as st

def apply_custom_css():
    st.markdown(
        """
        <style>
        /* =========================================================
           Fonts
        ========================================================= */
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        @import url('https://fonts.googleapis.com/icon?family=Material+Icons');

        :root{
            --bg: #F6F8FC;
            --card: #FFFFFF;
            --text: #0F172A;
            --muted: #64748B;
            --line: rgba(148,163,184,.28);
            --shadow: 0 10px 25px rgba(2,6,23,.06);
            --shadow2: 0 18px 45px rgba(2,6,23,.10);
            --primary: #0B5FFF;
            --primary2: #0033A0;
            --good: #059669;
            --bad: #DC2626;
            --warn: #F59E0B;
            --radius: 20px;
        }

        /* =========================================================
           Global RTL + Typography (بدون التأثير على expander icons fix)
        ========================================================= */
        html, body, [class*="css"], p, div, label, input, button, textarea, span, h1, h2, h3, h4 {
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
            text-align: right !important;
        }

        /* Material Icons should stay LTR */
        .material-icons,
        [class*="material-icons"],
        i {
            font-family: 'Material Icons' !important;
            direction: ltr !important;
            text-align: center !important;
            font-weight: normal !important;
            font-style: normal !important;
            letter-spacing: normal !important;
            text-transform: none !important;
            white-space: nowrap !important;
            word-wrap: normal !important;
        }

        /* =========================================================
           App Background + layout width
        ========================================================= */
        .stApp {
            background: var(--bg) !important;
        }
        /* مركزية المحتوى وتحسين الهوامش */
        .block-container{
            padding-top: 1.2rem !important;
            padding-bottom: 2.0rem !important;
            max-width: 1200px !important;
        }

        /* Hide Streamlit Chrome */
        footer, header, #MainMenu { display:none !important; }
        [data-testid="stElementToolbar"]{ display:none !important; }
        button[title="View fullscreen"]{ display:none !important; }
        div[role="tooltip"]{ display:none !important; opacity:0 !important; visibility:hidden !important; }

        /* Sidebar */
        section[data-testid="stSidebar"]{
            border-right: none !important;
            border-left: none !important;
            box-shadow: none !important;
        }

        /* =========================================================
           Headers & Text
        ========================================================= */
        h1, h2, h3 {
            color: var(--text) !important;
            letter-spacing: -0.2px;
        }
        .muted { color: var(--muted) !important; }

        /* =========================================================
           Inputs / Select / TextArea / Date
        ========================================================= */
        /* container of widgets */
        div[data-testid="stTextInput"], 
        div[data-testid="stNumberInput"],
        div[data-testid="stDateInput"],
        div[data-testid="stTextArea"],
        div[data-testid="stSelectbox"],
        div[data-testid="stMultiSelect"]{
            background: transparent !important;
        }

        /* input box */
        .stTextInput input,
        .stNumberInput input,
        .stDateInput input,
        .stTextArea textarea{
            border-radius: 14px !important;
            border: 1px solid var(--line) !important;
            padding: 0.65rem 0.9rem !important;
            background: var(--card) !important;
            box-shadow: 0 1px 0 rgba(2,6,23,.03) !important;
            color: var(--text) !important;
        }

        /* selectbox */
        [data-testid="stSelectbox"] div[role="combobox"],
        [data-testid="stMultiSelect"] div[role="combobox"]{
            border-radius: 14px !important;
            border: 1px solid var(--line) !important;
            background: var(--card) !important;
            box-shadow: 0 1px 0 rgba(2,6,23,.03) !important;
        }

        /* widget labels */
        label, .stMarkdown p {
            color: var(--text) !important;
        }

        /* =========================================================
           Buttons (أوضح + تفاعل أفضل)
        ========================================================= */
        div.stButton > button{
            width: 100% !important;
            border-radius: 14px !important;
            height: 48px !important;
            font-weight: 900 !important;
            border: 1px solid rgba(37,99,235,.18) !important;
            background: var(--card) !important;
            color: var(--text) !important;
            box-shadow: 0 6px 16px rgba(2,6,23,.06) !important;
            transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
        }
        div.stButton > button:hover{
            transform: translateY(-2px);
            box-shadow: 0 14px 35px rgba(2,6,23,.12) !important;
            border-color: rgba(37,99,235,.35) !important;
            color: var(--primary) !important;
        }
        div.stButton > button:active{
            transform: translateY(0px);
            box-shadow: 0 8px 20px rgba(2,6,23,.10) !important;
        }

        /* Primary buttons (Streamlit type="primary") */
        button[kind="primary"]{
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary2) 100%) !important;
            color: #fff !important;
            border: none !important;
        }
        button[kind="primary"]:hover{
            filter: brightness(1.03);
        }

        /* =========================================================
           Tabs (أنظف + أوضح)
        ========================================================= */
        [data-testid="stTabs"]{
            background: transparent !important;
        }
        [data-testid="stTabs"] button{
            font-weight: 900 !important;
            border-radius: 14px !important;
        }

        /* =========================================================
           Expander (تحسين الشكل فقط بدون لمس نص/أيقونة expand)
        ========================================================= */
        div[data-testid="stExpander"]{
            border: 1px solid var(--line) !important;
            border-radius: 16px !important;
            background: rgba(255,255,255,.75) !important;
            box-shadow: 0 8px 20px rgba(2,6,23,.05) !important;
            overflow: hidden !important;
        }
        div[data-testid="stExpander"] details summary{
            padding: 12px 14px !important;
            font-weight: 900 !important;
            color: var(--primary2) !important;
            background: rgba(11,95,255,.04) !important;
        }
        div[data-testid="stExpander"] details{
            padding: 0 !important;
        }
        div[data-testid="stExpander"] details > div{
            padding: 10px 14px 14px 14px !important;
        }

        /* =========================================================
           KPI Cards + TASI Card (وضوح أعلى مثل اللي كان يعجبك)
        ========================================================= */
        .kpi-card{
            background: var(--card);
            border-radius: var(--radius);
            padding: 18px 18px;
            border: 1px solid rgba(148,163,184,.22);
            box-shadow: var(--shadow);
            position: relative;
            overflow: hidden;
            transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
            margin-bottom: 14px;
        }
        .kpi-card:hover{
            transform: translateY(-4px);
            box-shadow: var(--shadow2);
            border-color: rgba(37,99,235,.25);
        }
        .kpi-icon-bg{
            position:absolute;
            left:-16px;
            bottom:-26px;
            font-size: 6rem;
            opacity:.08;
            transform: rotate(10deg);
            color: #0F172A;
            pointer-events:none;
        }
        .kpi-label{
            color: var(--muted);
            font-size: .9rem;
            font-weight: 800;
            margin-bottom: 6px;
        }
        .kpi-value{
            font-size: 1.9rem;
            font-weight: 950;
            color: var(--text);
            direction:ltr;
            text-align:left;
            letter-spacing: .2px;
        }

        /* TASI Card */
        .tasi-card{
            background: radial-gradient(1200px 400px at 20% 20%, rgba(255,255,255,.25), transparent 55%),
                        linear-gradient(135deg, var(--primary) 0%, var(--primary2) 100%);
            border-radius: 26px;
            padding: 22px 22px;
            color: #fff !important;
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap: 14px;
            box-shadow: 0 18px 45px rgba(0, 82, 204, 0.28);
            margin-bottom: 18px;
            border: 1px solid rgba(255,255,255,.18);
        }
        .tasi-title{ font-weight: 900; opacity:.95; }
        .tasi-value{
            font-weight: 950;
            font-size: 2.2rem;
            direction:ltr;
            text-align:left;
            letter-spacing: .3px;
        }
        .tasi-delta{
            display:inline-flex;
            align-items:center;
            gap: 8px;
            padding: 6px 10px;
            border-radius: 999px;
            font-weight: 900;
            background: rgba(255,255,255,.16);
            border: 1px solid rgba(255,255,255,.20);
            direction:ltr;
        }

        /* =========================================================
           Tables (أوضح + سكرول لطيف)
        ========================================================= */
        .finance-table{
            width:100%;
            border-collapse: separate;
            border-spacing: 0;
            border: 1px solid rgba(148,163,184,.22);
            border-radius: 16px;
            overflow:hidden;
            background: var(--card);
            box-shadow: 0 10px 25px rgba(2,6,23,.05);
            margin-top: 12px;
        }
        .finance-table th{
            background: rgba(11,95,255,.06) !important;
            color: #1E40AF !important;
            font-weight: 900;
            padding: 14px;
            text-align: right;
            border-bottom: 1px solid rgba(148,163,184,.22);
            white-space: nowrap;
        }
        .finance-table td{
            padding: 12px 14px;
            border-bottom: 1px solid rgba(148,163,184,.14);
            color: #0F172A;
            font-weight: 700;
            white-space: nowrap;
        }
        .finance-table tr:hover td{
            background: rgba(11,95,255,.035);
        }

        .txt-green { color: var(--good) !important; font-weight: 900; }
        .txt-red { color: var(--bad) !important; font-weight: 900; }
        .txt-blue { color: #2563EB !important; font-weight: 900; }

        .badge-open{
            background: rgba(5,150,105,.12);
            color: #065F46;
            padding: 5px 12px;
            border-radius: 999px;
            font-size: .78rem;
            font-weight: 900;
            border: 1px solid rgba(5,150,105,.18);
        }
        .badge-closed{
            background: rgba(100,116,139,.12);
            color: #334155;
            padding: 5px 12px;
            border-radius: 999px;
            font-size: .78rem;
            font-weight: 900;
            border: 1px solid rgba(100,116,139,.18);
        }

        /* =========================================================
           Metric widget (st.metric) تحسين بسيط
        ========================================================= */
        [data-testid="stMetric"]{
            background: var(--card);
            border: 1px solid rgba(148,163,184,.22);
            border-radius: 18px;
            padding: 14px 16px;
            box-shadow: 0 10px 25px rgba(2,6,23,.05);
        }
        [data-testid="stMetricLabel"]{
            color: var(--muted) !important;
            font-weight: 900 !important;
        }
        [data-testid="stMetricValue"]{
            color: var(--text) !important;
            font-weight: 950 !important;
            direction:ltr !important;
            text-align:left !important;
        }

        /* =========================================================
           Mobile responsiveness
        ========================================================= */
        @media (max-width: 768px){
            .block-container{ padding-left: 0.9rem !important; padding-right: 0.9rem !important; }
            .kpi-value{ font-size: 1.6rem; }
            .tasi-value{ font-size: 1.9rem; }
        }

        </style>
        """,
        unsafe_allow_html=True,
    )