from pathlib import Path

# --- إعدادات الهوية ---
APP_NAME = "أصولي"  # الاسم كما طلبت
APP_ICON = "💎"    # الأيقونة (الجوهرة) لتعبر عن قيمة الأصول
DB_PATH = Path("stocks.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الألوان ---
DEFAULT_COLORS = {
    'page_bg': '#F9FAFB',
    'card_bg': '#FFFFFF',
    'main_text': '#111827',
    'sub_text': '#6B7280',
    'primary': '#0284c7',        # أزرق سماوي غامق (لون الثقة والمال)
    'success': '#10B981',
    'danger': '#EF4444',
    'border': '#E5E7EB',
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
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        html, body, [class*="css"], p, div, label, input, textarea, th, td, h1, h2, h3, button {{
            font-family: 'Cairo', sans-serif !important; 
            direction: rtl;
        }}
        
        .stApp {{ background-color: {C['page_bg']} !important; }}
        
        /* تصميم اللوقو النصي */
        .logo-text {{
            background: -webkit-linear-gradient(45deg, {C['primary']}, #0ea5e9);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 900;
            font-size: 1.8rem;
            letter-spacing: -1px;
        }}
        
        /* الأزرار العلوية */
        div[data-testid="stHorizontalBlock"] button {{
            border-radius: 8px !important;
            border: 1px solid transparent !important;
            transition: 0.2s;
            font-weight: 700 !important;
        }}
        div[data-testid="stHorizontalBlock"] button:hover {{
            border-color: {C['primary']} !important;
            background-color: {C['page_bg']} !important;
            color: {C['primary']} !important;
        }}

        /* الكروت */
        .kpi-box {{
            background-color: {C['card_bg']}; 
            border: 1px solid {C['border']}; 
            border-radius: 12px;
            padding: 15px; 
            text-align: right; 
            margin-bottom: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.03);
        }}
        .kpi-value {{ font-size: 1.3rem; font-weight: 800; color: {C['main_text']}; }}
        
        /* الجداول */
        .finance-table {{ width: 100%; border-collapse: separate; border-spacing: 0 4px; margin-top: 5px; }}
        .finance-table th {{ 
            color: {C['sub_text']} !important; font-weight: 700 !important; font-size: 0.85rem !important;
            padding: 10px !important; text-align: center; border-bottom: 2px solid {C['border']};
        }}
        .finance-table td {{ 
            background-color: white; padding: 10px !important; text-align: center;
            color: {C['main_text']}; font-weight: 600; font-size: 0.85rem !important;
            border-top: 1px solid {C['border']}; border-bottom: 1px solid {C['border']};
        }}
        .finance-table tr:hover td {{ background-color: #F3F4F6; }}
        
        /* إخفاء العناصر غير المرغوبة */
        [data-testid="stSidebar"] {{ display: none !important; }}
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        
        /* التبويبات */
        .stTabs [data-baseweb="tab-list"] {{ gap: 10px; }}
        .stTabs [data-baseweb="tab"] {{ height: 40px; border-radius: 6px; }}
        .stTabs [aria-selected="true"] {{ background-color: {C['primary']} !important; color: white !important; }}
    </style>
    """
