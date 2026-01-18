from pathlib import Path

# --- إعدادات النظام ---
APP_NAME = "أصولي"
APP_ICON = "📈"
DB_PATH = Path("stocks.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الهوية البصرية ---
DEFAULT_COLORS = {
    'page_bg': '#F4F6F8',
    'card_bg': '#FFFFFF',
    'main_text': '#172B4D',
    'sub_text': '#5E6C84',
    'primary': '#0052CC',
    'success': '#36B37E',
    'danger': '#FF5630',
    'border': '#DFE1E6',
    'input_bg': '#FFFFFF',
    'header_bg': '#FAFBFC'
}

THEME = DEFAULT_COLORS
PRESET_THEMES = { "أصولي (الافتراضي)": DEFAULT_COLORS }

# --- الأوزان المستهدفة للقطاعات ---
SECTOR_TARGETS = {
    'المواد الأساسية': 30.0,
    'البنوك': 17.0,
    'الطاقة': 25.0,
    'تجزئة وتوزيع السلع الاستهلاكية': 6.0,
    'تجزئة السلع الكمالية': 8.0,
    'الرعاية الصحية': 5.0,
    'إنتاج الأغذية': 9.0,
    'التطبيقات وخدمات التقنية': 7.0,
    'النقل': 2.0,
    'إدارة وتطوير العقارات': 5.0,
    'التأمين': 0.0
}

def get_master_styles(C):
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        html, body, [class*="css"], .stMarkdown, h1, h2, h3, h4, p, label, div, span, th, td, button, input {{
            font-family: 'Cairo', sans-serif !important;
            direction: rtl; 
            color: {C['main_text']} !important; 
        }}

        .stApp {{ background-color: {C['page_bg']} !important; }}
        [data-testid="stHeader"] {{ background-color: {C['page_bg']} !important; }}

        /* === إصلاح الحقول السوداء === */
        input, .stTextInput input, .stNumberInput input, .stDateInput input, [data-baseweb="input"] {{
            background-color: #ffffff !important; 
            color: {C['main_text']} !important;
            border-color: {C['border']} !important;
            caret-color: {C['primary']} !important;
        }}
        div[data-baseweb="input"] > div {{
            background-color: #ffffff !important;
            color: {C['main_text']} !important;
        }}
        
        /* القوائم المنسدلة */
        div[data-baseweb="select"] > div {{
            background-color: #ffffff !important;
            color: {C['main_text']} !important;
            border: 1px solid {C['border']} !important;
        }}
        div[data-baseweb="popover"], div[data-baseweb="menu"], ul[role="listbox"] {{
            background-color: #ffffff !important;
        }}
        li[role="option"] {{
            color: {C['main_text']} !important;
            background-color: #ffffff !important;
        }}
        
        [data-baseweb="select"] svg {{ fill: {C['sub_text']} !important; }}

        /* الأزرار */
        button, [kind="primary"], [kind="secondary"] {{
            background-color: {C['card_bg']} !important;
            color: {C['sub_text']} !important;
            border: 1px solid {C['border']} !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02) !important;
        }}
        [data-testid="stFormSubmitButton"] > button {{
            background-color: {C['primary']} !important;
            color: white !important;
        }}

        /* الجداول */
        .finance-table {{
            width: 100%; border-collapse: separate; border-spacing: 0;
            background-color: white; border: 1px solid {C['border']};
            border-radius: 12px; overflow: hidden; margin-bottom: 20px;
            font-size: 0.95rem;
        }}
        .finance-table th {{ 
            color: {C['primary']} !important; padding: 12px; 
            text-align: center; border-bottom: 2px solid {C['border']}; font-weight: 800; 
        }}
        .finance-table td {{ 
            padding: 10px; text-align: center; border-bottom: 1px solid {C['border']}; 
            color: {C['main_text']} !important; font-weight: 600;
        }}

        /* بطاقات العرض */
        .kpi-box {{
            background-color: white;
            border: 1px solid {C['border']};
            border-radius: 12px;
            padding: 15px;
            text-align: right;
            margin-bottom: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }}
        .kpi-title {{ font-size: 0.85rem; color: {C['sub_text']} !important; margin-bottom: 5px; }}
        .kpi-value {{ font-size: 1.3rem; font-weight: 800; color: {C['main_text']} !important; direction: ltr; display: inline-block; }}
        
        .section-header {{
            color: {C['primary']} !important; font-weight: 800; font-size: 1.1rem; 
            margin-top: 25px; margin-bottom: 15px; border-bottom: 2px solid {C['border']}; 
            padding-bottom: 5px;
        }}
        
        .tasi-box {{
            background: linear-gradient(135deg, {C['primary']} 0%, #091E42 100%) !important;
            padding: 30px; border-radius: 20px; margin-bottom: 30px; 
            display: flex; justify-content: space-between; align-items: center;
        }}
        .tasi-box * {{ color: #ffffff !important; }}
    </style>
    """
