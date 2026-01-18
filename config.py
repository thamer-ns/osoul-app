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
# يمكنك إضافة المزيد من الشركات هنا
TADAWUL_DB = {
    '2222': {'name': 'أرامكو', 'sector': 'الطاقة'},
    '1120': {'name': 'الراجحي', 'sector': 'البنوك'},
    '1180': {'name': 'الأهلي', 'sector': 'البنوك'},
    '2010': {'name': 'سابك', 'sector': 'المواد الأساسية'},
    '7010': {'name': 'STC', 'sector': 'الأتصالات'},
    # ... (يمكنك نسخ بقية القائمة من الكود القديم هنا)
}

def get_master_styles(C):
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        html, body, [class*="css"], .stMarkdown, h1, h2, h3, h4, p, label, div, span, th, td, button, input {{
            font-family: 'Cairo', sans-serif !important; direction: rtl; color: {C['main_text']} !important;
        }}
        .stApp {{ background-color: {C['page_bg']} !important; }}
        input, .stTextInput input, .stNumberInput input, .stDateInput input {{
            background-color: #ffffff !important; color: {C['main_text']} !important; border-color: {C['border']} !important;
        }}
        .kpi-box {{
            background-color: white; border: 1px solid {C['border']}; border-radius: 12px;
            padding: 15px; text-align: right; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }}
        .finance-table {{ width: 100%; border-collapse: separate; border-spacing: 0; background-color: white; border-radius: 12px; overflow: hidden; margin-bottom: 20px; }}
        .finance-table th {{ background-color: {C['header_bg']}; color: {C['primary']}; padding: 12px; font-weight: 800; }}
        .finance-table td {{ padding: 10px; border-bottom: 1px solid {C['border']}; }}
    </style>
    """
