from pathlib import Path

# --- إعدادات أساسية ---
APP_NAME = "أصولي"
APP_ICON = "🏛️"
DB_PATH = Path("stocks.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الهوية البصرية ---
DEFAULT_COLORS = {
    'page_bg': '#F8F9FA',
    'card_bg': '#FFFFFF',
    'main_text': '#1F2937',
    'sub_text': '#6B7280',
    'primary': '#0e6ba8',
    'success': '#10B981',
    'danger': '#EF4444',
    'border': '#E5E7EB',
    'input_bg': '#FFFFFF'
}

# --- بيانات الشركات ---
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
    '4001': {'name': 'العثيم', 'sector': 'تجزئة الأغذية'},
    '2020': {'name': 'سابك للمغذيات', 'sector': 'المواد الأساسية'},
    '4263': {'name': 'سال', 'sector': 'النقل'},
    '2270': {'name': 'سدافكو', 'sector': 'إنتاج الأغذية'},
    '4164': {'name': 'النهدي', 'sector': 'تجزئة الأغذية والأدوية'},
    '4007': {'name': 'الحمادي', 'sector': 'الرعاية الصحية'},
    '1150': {'name': 'الإنماء', 'sector': 'البنوك'},
    '3060': {'name': 'أسمنت ينبع', 'sector': 'المواد الأساسية'},
    '3040': {'name': 'أسمنت القصيم', 'sector': 'المواد الأساسية'},
}

def get_css(C):
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        html, body, [class*="css"], p, div, label, button, input, textarea, th, td {{
            font-family: 'Cairo', sans-serif !important; direction: rtl;
        }}
        
        .stApp {{ background-color: {C['page_bg']} !important; }}
        
        /* تحسين العناوين - محاذاة لليمين */
        h1, h2, h3, h4 {{
            font-family: 'Cairo', sans-serif !important;
            color: #1F2937 !important;
            border-right: 5px solid {C['primary']};
            padding-right: 15px;
            margin-bottom: 20px !important;
            font-weight: 800 !important;
            text-align: right !important; /* إجبار المحاذاة لليمين */
            width: 100%;
        }}

        /* تنسيق الجدول المحسن */
        .finance-table {{ width: 100%; border-collapse: separate; border-spacing: 0 4px; margin-top: 5px; }}
        
        .finance-table th {{ 
            color: #0e6ba8 !important;
            font-weight: 800 !important;
            font-size: 0.85rem !important;
            padding: 10px 5px !important;
            text-align: center;
            background-color: transparent;
            border-bottom: 2px solid #F3F4F6;
            white-space: nowrap !important;
        }}
        
        .finance-table td {{ 
            background-color: white;
            padding: 8px 5px !important;
            text-align: center;
            color: #374151;
            font-weight: 600;
            font-size: 0.82rem !important;
            border-top: 1px solid #F3F4F6;
            border-bottom: 1px solid #F3F4F6;
            white-space: nowrap !important;
        }}
        
        .finance-table tr:hover td {{ background-color: #F9FAFB; }}

        /* الكروت العلوية */
        .kpi-box {{
            background-color: {C['card_bg']}; border: 1px solid {C['border']}; border-radius: 12px;
            padding: 15px; text-align: right; margin-bottom: 10px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        .kpi-value {{ font-size: 1.3rem; font-weight: 800; color: {C['main_text']}; }}
        
        /* المؤشر */
        .tasi-box {{
            background: white; padding: 15px; border-radius: 12px; border: 1px solid {C['border']};
            display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;
        }}
        
        [data-testid="stSidebar"] {{ display: none !important; }}
        
        /* تحسين التبويبات وقوائم الفرز */
        .stTabs [data-baseweb="tab-list"] {{ gap: 10px; }}
        .stTabs [data-baseweb="tab"] {{ height: 40px; white-space: nowrap; }}
        
        /* تنسيق Expander الفرز */
        div[data-testid="stExpander"] {{
            background-color: white;
            border-radius: 8px;
            border: 1px solid #E5E7EB;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }}
    </style>
    """
