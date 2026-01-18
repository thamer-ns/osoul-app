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

PRESET_THEMES = { "أصولي (الافتراضي)": DEFAULT_COLORS }

# --- الأوزان المستهدفة للقطاعات ---
SECTOR_TARGETS = {
    'المواد الأساسية': 30.0, 'البنوك': 17.0, 'الطاقة': 25.0,
    'تجزئة وتوزيع السلع الاستهلاكية': 6.0, 'تجزئة السلع الكمالية': 8.0,
    'الرعاية الصحية': 5.0, 'إنتاج الأغذية': 9.0, 'التطبيقات وخدمات التقنية': 7.0,
    'النقل': 2.0, 'إدارة وتطوير العقارات': 5.0, 'التأمين': 0.0
}

# --- قاعدة بيانات تداول (مختصرة) ---
TADAWUL_DB = {
    '2222': {'name': 'أرامكو', 'sector': 'الطاقة'},
    '1120': {'name': 'الراجحي', 'sector': 'البنوك'},
    '1180': {'name': 'الأهلي', 'sector': 'البنوك'},
    '2010': {'name': 'سابك', 'sector': 'المواد الأساسية'},
    '7010': {'name': 'STC', 'sector': 'الأتصالات'},
}

def get_master_styles(C):
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        /* إجبار الخط والاتجاه على كافة العناصر */
        html, body, [class*="css"], [data-testid="stAppViewContainer"], [data-testid="stSidebar"], button, input, select, textarea, div {{
            font-family: 'Cairo', sans-serif !important;
            direction: rtl !important;
        }}
        
        /* خلفية التطبيق */
        [data-testid="stAppViewContainer"] {{
            background-color: {C['page_bg']} !important;
        }}
        [data-testid="stHeader"] {{
            background-color: {C['page_bg']} !important;
        }}

        /* إصلاح الأزرار في الناف بار */
        div.stButton > button:first-child {{
            width: 100%;
            border-radius: 8px;
            font-weight: bold;
            border: 1px solid {C['border']};
            background-color: {C['card_bg']};
            color: {C['sub_text']};
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }}
        
        /* تمييز الزر النشط (Primary) */
        div.stButton > button[kind="primary"] {{
            background-color: {C['primary']} !important;
            color: white !important;
            border: none !important;
        }}

        /* إصلاح الحقول البيضاء */
        input, .stTextInput input, .stNumberInput input, .stDateInput input {{
            background-color: #ffffff !important;
            color: {C['main_text']} !important;
            border-color: {C['border']} !important;
            text-align: right !important;
        }}
        
        /* تنسيق الجداول والبطاقات */
        .kpi-box {{
            background-color: white;
            border: 1px solid {C['border']};
            border-radius: 12px;
            padding: 15px;
            text-align: right;
            margin-bottom: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }}
        
        /* إخفاء القوائم المزعجة الافتراضية */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        
        /* إصلاح تباعد الأعمدة */
        [data-testid="column"] {{
            padding: 0 5px !important;
        }}
    </style>
    """
