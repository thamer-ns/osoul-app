from pathlib import Path

# --- إعدادات أساسية ---
APP_NAME = "أصولي"
APP_ICON = "🏛️"
DB_PATH = Path("stocks.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الهوية البصرية (مطابقة للصورة) ---
DEFAULT_COLORS = {
    'page_bg': '#F8F9FA',      # خلفية فاتحة جداً
    'card_bg': '#FFFFFF',
    'main_text': '#1F2937',
    'sub_text': '#6B7280',
    'primary': '#0e6ba8',      # اللون الأزرق المستخدم في عناوين الجدول
    'success': '#10B981',      # أخضر للأرباح
    'danger': '#EF4444',       # أحمر للخسائر
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
}

def get_css(C):
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        html, body, [class*="css"], p, h1, h2, h3, h4, div, label, button, input, textarea, th, td {{
            font-family: 'Cairo', sans-serif !important; direction: rtl;
        }}
        
        .stApp {{ background-color: {C['page_bg']} !important; }}
        
        /* تصميم الجدول ليطابق الصورة */
        .finance-table {{ width: 100%; border-collapse: separate; border-spacing: 0 5px; margin-top: 10px; }}
        
        .finance-table th {{ 
            color: #0e6ba8 !important; /* اللون الأزرق للعناوين */
            font-weight: 800 !important;
            font-size: 0.95rem;
            padding: 15px 10px;
            text-align: center;
            background-color: transparent;
            border-bottom: 2px solid #F3F4F6;
        }}
        
        .finance-table td {{ 
            background-color: white;
            padding: 12px 10px;
            text-align: center;
            color: #374151;
            font-weight: 600;
            font-size: 0.9rem;
            border-top: 1px solid #F3F4F6;
            border-bottom: 1px solid #F3F4F6;
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
            background: white; padding: 20px; border-radius: 12px; border: 1px solid {C['border']};
            display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;
        }}
        
        [data-testid="stSidebar"] {{ display: none !important; }}
    </style>
    """
