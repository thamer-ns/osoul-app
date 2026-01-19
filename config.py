from pathlib import Path

# --- إعدادات الهوية ---
APP_NAME = "أصولي"
APP_ICON = "🏛️"    # تغيير الجوهرة إلى رمز "الأصول/المبنى المالي" ليعبر عن الاسم
DB_PATH = Path("stocks.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الألوان (تدرجات الأزرق البنكي) ---
DEFAULT_COLORS = {
    'page_bg': '#F9FAFB',
    'card_bg': '#FFFFFF',
    'main_text': '#111827',
    'sub_text': '#6B7280',
    'primary': '#0e6ba8',        # أزرق استثماري وقور
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
        
        /* تصميم اللوقو الجديد (مربع أيقونة التطبيق) */
        .app-logo-box {{
            background: linear-gradient(135deg, {C['primary']}, #0284c7);
            width: 48px;
            height: 48px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.8rem;
            color: white;
            box-shadow: 0 4px 6px -1px rgba(14, 107, 168, 0.3);
            margin-left: 10px;
        }}
        
        .logo-text {{
            font-size: 1.6rem;
            font-weight: 900;
            color: {C['primary']};
            letter-spacing: -0.5px;
        }}
        
        /* تحسينات عامة */
        div[data-testid="stHorizontalBlock"] button {{
            border-radius: 8px !important;
            font-weight: 700 !important;
            border: 1px solid transparent;
        }}
        div[data-testid="stHorizontalBlock"] button:hover {{
            background-color: white !important;
            border-color: {C['border']} !important;
            color: {C['primary']} !important;
        }}
        
        /* الكروت والجداول */
        .kpi-box {{
            background-color: {C['card_bg']}; 
            border: 1px solid {C['border']}; 
            border-radius: 12px;
            padding: 15px; 
            text-align: right; 
            margin-bottom: 10px;
        }}
        .kpi-value {{ font-size: 1.3rem; font-weight: 800; color: {C['main_text']}; }}
        
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
        
        [data-testid="stSidebar"] {{ display: none !important; }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 10px; }}
        .stTabs [data-baseweb="tab"] {{ height: 40px; border-radius: 6px; }}
        .stTabs [aria-selected="true"] {{ background-color: {C['primary']} !important; color: white !important; }}
    </style>
    """
