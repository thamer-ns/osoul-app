from pathlib import Path

# --- إعدادات أساسية ---
APP_NAME = "أصولي"
APP_ICON = "📈"
DB_PATH = Path("stocks.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الهوية البصرية ---
DEFAULT_COLORS = {
    'page_bg': '#F5F7FA',
    'card_bg': '#FFFFFF',
    'main_text': '#1F2937',
    'sub_text': '#6B7280',
    'primary': '#2563EB',
    'success': '#10B981',
    'danger': '#EF4444',
    'border': '#E5E7EB',
    'input_bg': '#F9FAFB'
}

PRESET_THEMES = { "أصولي (الافتراضي)": DEFAULT_COLORS }

# --- البيانات الثابتة ---
SECTOR_TARGETS = {
    'المواد الأساسية': 30.0, 'البنوك': 17.0, 'الطاقة': 25.0,
    'تجزئة وتوزيع السلع الاستهلاكية': 6.0, 'تجزئة السلع الكمالية': 8.0,
    'الرعاية الصحية': 5.0, 'إنتاج الأغذية': 9.0, 'التطبيقات وخدمات التقنية': 7.0,
    'النقل': 2.0, 'إدارة وتطوير العقارات': 5.0, 'التأمين': 0.0
}

TADAWUL_DB = {
    '2222': {'name': 'أرامكو', 'sector': 'الطاقة'},
    '2010': {'name': 'سابك', 'sector': 'المواد الأساسية'},
    '1120': {'name': 'الراجحي', 'sector': 'البنوك'},
    '1180': {'name': 'الأهلي', 'sector': 'البنوك'},
    '7010': {'name': 'STC', 'sector': 'الأتصالات'},
    '5110': {'name': 'الكهرباء', 'sector': 'المرافق العامة'},
    '4013': {'name': 'سليمان الحبيب', 'sector': 'الرعاية الصحية'},
    '2280': {'name': 'المراعي', 'sector': 'إنتاج الأغذية'},
    '4190': {'name': 'جرير', 'sector': 'السلع الكمالية'},
    '7202': {'name': 'سلوشنز', 'sector': 'التقنية'},
}

def get_css(C):
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        html, body, [class*="css"], p, h1, h2, h3, h4, div, label, button, input, textarea {{
            font-family: 'Cairo', sans-serif !important; direction: rtl; color: {C['main_text']} !important;
        }}
        
        .stApp {{ background-color: {C['page_bg']} !important; }}
        
        input, .stTextInput input, .stNumberInput input, .stSelectbox {{
            background-color: {C['input_bg']} !important; border-radius: 12px !important; border: 1px solid {C['border']} !important;
        }}
        
        /* تصميم بطاقة TASI */
        .tasi-box {{
            background: linear-gradient(135deg, {C['card_bg']} 0%, #F8FAFC 100%);
            padding: 20px; border-radius: 16px; border: 1px solid {C['border']};
            display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px;
        }}
        
        /* تصميم بطاقات KPI المحسنة */
        .kpi-box {{
            background-color: {C['card_bg']}; border: 1px solid {C['border']}; border-radius: 16px;
            padding: 20px; text-align: right; margin-bottom: 15px; 
            box-shadow: 0 2px 5px rgba(0,0,0,0.02); transition: transform 0.2s;
        }}
        .kpi-box:hover {{ transform: translateY(-2px); }}
        
        .kpi-value {{ font-size: 1.5rem; font-weight: 900; direction: ltr; display: inline-block; }}
        
        .finance-table {{ width: 100%; border-collapse: separate; background-color: {C['card_bg']}; border-radius: 16px; overflow: hidden; margin-bottom: 25px; }}
        .finance-table th {{ background-color: #F9FAFB; padding: 15px; text-align: center; color: {C['sub_text']}; }}
        .finance-table td {{ padding: 12px; text-align: center; border-bottom: 1px solid {C['border']}; }}
        
        button[kind="primary"] {{ background-color: {C['primary']} !important; color: white !important; border: none !important; box-shadow: 0 4px 10px rgba(37, 99, 235, 0.2); }}
        [data-testid="stSidebar"] {{ display: none !important; }}
    </style>
    """
