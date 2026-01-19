from pathlib import Path

# --- إعدادات الهوية ---
APP_NAME = "نماء | Namma"
APP_ICON = "💎"  # شعار جديد
DB_PATH = Path("stocks.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- لوحة الألوان المحسنة (Theme) ---
DEFAULT_COLORS = {
    'page_bg': '#F3F4F6',        # رمادي فاتح جداً للخلفية
    'card_bg': '#FFFFFF',        # أبيض للكروت
    'header_bg': '#FFFFFF',      # خلفية الهيدر
    'main_text': '#111827',      # أسود فحمي للنصوص
    'sub_text': '#6B7280',       # رمادي للنصوص الفرعية
    'primary': '#0F766E',        # تركوازي غامق (لون الثراء والنمو) بدلاً من الأزرق التقليدي
    'accent': '#0D9488',         # لون تمييز
    'success': '#10B981',        # أخضر للأرباح
    'danger': '#EF4444',         # أحمر للخسائر
    'border': '#E5E7EB',         # لون الحدود
}

# --- بيانات الشركات (كما هي) ---
TADAWUL_DB = {
    '2222': {'name': 'أرامكو السعودية', 'sector': 'الطاقة'},
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
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800;900&display=swap');
        
        /* تطبيق الخط على كامل الموقع */
        html, body, [class*="css"], p, div, label, input, textarea, th, td, h1, h2, h3, button {{
            font-family: 'Cairo', sans-serif !important; 
            direction: rtl;
        }}
        
        .stApp {{ background-color: {C['page_bg']} !important; }}
        
        /* تحسين شكل الأزرار في القائمة */
        div[data-testid="stHorizontalBlock"] button {{
            border-radius: 10px !important;
            border: none !important;
            font-weight: 700 !important;
            transition: all 0.3s ease;
        }}
        
        div[data-testid="stHorizontalBlock"] button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}

        /* تصميم الكروت */
        .kpi-box {{
            background-color: {C['card_bg']}; 
            border: 1px solid {C['border']}; 
            border-radius: 16px;
            padding: 20px; 
            text-align: right; 
            margin-bottom: 15px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            transition: transform 0.2s;
        }}
        .kpi-box:hover {{ transform: scale(1.02); }}
        
        .kpi-value {{ font-size: 1.5rem; font-weight: 800; color: {C['main_text']}; margin-top: 5px; }}
        
        /* تحسين الجداول */
        .finance-table {{ width: 100%; border-collapse: separate; border-spacing: 0 8px; margin-top: 5px; }}
        .finance-table th {{ 
            color: {C['sub_text']} !important; font-weight: 700 !important; font-size: 0.9rem !important;
            padding: 12px 8px !important; text-align: center; border-bottom: none;
        }}
        .finance-table td {{ 
            background-color: white; padding: 12px 8px !important; text-align: center;
            color: {C['main_text']}; font-weight: 600; font-size: 0.9rem !important;
            border-top: 1px solid {C['border']}; border-bottom: 1px solid {C['border']};
        }}
        .finance-table td:first-child {{ border-top-right-radius: 10px; border-bottom-right-radius: 10px; border-right: 1px solid {C['border']}; }}
        .finance-table td:last-child {{ border-top-left-radius: 10px; border-bottom-left-radius: 10px; border-left: 1px solid {C['border']}; }}
        .finance-table tr:hover td {{ background-color: #F9FAFB; }}

        /* العناوين */
        h1, h2, h3 {{
            color: {C['primary']} !important;
            font-weight: 900 !important;
            margin-bottom: 25px !important;
            text-align: right !important;
        }}
        
        /* إخفاء القائمة الجانبية والقوائم الافتراضية */
        [data-testid="stSidebar"] {{ display: none !important; }}
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        
        /* تحسين التبويبات Tabs */
        .stTabs [data-baseweb="tab-list"] {{ 
            gap: 15px; 
            background-color: white; 
            padding: 10px; 
            border-radius: 12px; 
            border: 1px solid {C['border']};
        }}
        .stTabs [data-baseweb="tab"] {{ height: 45px; border-radius: 8px; font-weight: bold; }}
        .stTabs [aria-selected="true"] {{ background-color: {C['primary']} !important; color: white !important; }}
    </style>
    """
