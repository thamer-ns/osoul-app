from pathlib import Path

# --- إعدادات النظام ---
APP_NAME = "أصولي"
APP_ICON = "📈"
DB_PATH = Path("stocks.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الهوية البصرية (تصميم نظيف وعصري) ---
DEFAULT_COLORS = {
    'page_bg': '#F5F7FA',          # رمادي فاتح جداً للخلفية (أريح للعين من الأبيض الناصع)
    'card_bg': '#FFFFFF',          # أبيض للبطاقات
    'main_text': '#1F2937',        # أسود فحمي (أوضح للقراءة)
    'sub_text': '#6B7280',         # رمادي متوسط
    'primary': '#2563EB',          # أزرق ملكي (لون تطبيقات حديث)
    'success': '#10B981',          # أخضر زاهي
    'danger': '#EF4444',           # أحمر واضح
    'border': '#E5E7EB',           # حدود ناعمة
    'input_bg': '#F9FAFB',         # خلفية الحقول رمادي خفيف جداً
    'header_bg': '#FFFFFF'
}

PRESET_THEMES = { "أصولي (الافتراضي)": DEFAULT_COLORS }

# --- الأوزان المستهدفة للقطاعات ---
SECTOR_TARGETS = {
    'المواد الأساسية': 30.0, 'البنوك': 17.0, 'الطاقة': 25.0,
    'تجزئة وتوزيع السلع الاستهلاكية': 6.0, 'تجزئة السلع الكمالية': 8.0,
    'الرعاية الصحية': 5.0, 'إنتاج الأغذية': 9.0, 'التطبيقات وخدمات التقنية': 7.0,
    'النقل': 2.0, 'إدارة وتطوير العقارات': 5.0, 'التأمين': 0.0
}

# قاعدة البيانات (قائمة الأسهم السعودية)
TADAWUL_DB = {
    '2222': {'name': 'أرامكو', 'sector': 'الطاقة'}, '2030': {'name': 'المصافي', 'sector': 'الطاقة'},
    '4030': {'name': 'البحري', 'sector': 'الطاقة'}, '4200': {'name': 'الدريس', 'sector': 'الطاقة'},
    '2380': {'name': 'بترو رابغ', 'sector': 'الطاقة'}, '2223': {'name': 'لوبريف', 'sector': 'الطاقة'},
    '2381': {'name': 'الحفر العربية', 'sector': 'الطاقة'}, '2382': {'name': 'أديس', 'sector': 'الطاقة'},
    '2081': {'name': 'الخريف', 'sector': 'الطاقة'}, '2010': {'name': 'سابك', 'sector': 'المواد الأساسية'},
    '2020': {'name': 'سابك للمغذيات', 'sector': 'المواد الأساسية'}, '2290': {'name': 'ينساب', 'sector': 'المواد الأساسية'},
    '2310': {'name': 'سبكيم', 'sector': 'المواد الأساسية'}, '2350': {'name': 'كيان', 'sector': 'المواد الأساسية'},
    '2250': {'name': 'المجموعة السعودية', 'sector': 'المواد الأساسية'}, '2060': {'name': 'التصنيع', 'sector': 'المواد الأساسية'},
    '2170': {'name': 'اللجين', 'sector': 'المواد الأساسية'}, '2330': {'name': 'المتقدمة', 'sector': 'المواد الأساسية'},
    '1211': {'name': 'معادن', 'sector': 'المواد الأساسية'}, '3030': {'name': 'أسمنت السعودية', 'sector': 'المواد الأساسية'},
    '3040': {'name': 'أسمنت القصيم', 'sector': 'المواد الأساسية'}, '3050': {'name': 'أسمنت الجنوب', 'sector': 'المواد الأساسية'},
    '3060': {'name': 'أسمنت ينبع', 'sector': 'المواد الأساسية'}, '3010': {'name': 'أسمنت العربية', 'sector': 'المواد الأساسية'},
    '3020': {'name': 'أسمنت اليمامة', 'sector': 'المواد الأساسية'}, '3080': {'name': 'أسمنت الشرقية', 'sector': 'المواد الأساسية'},
    '3090': {'name': 'أسمنت تبوك', 'sector': 'المواد الأساسية'}, '3091': {'name': 'أسمنت الجوف', 'sector': 'المواد الأساسية'},
    '3001': {'name': 'أسمنت حائل', 'sector': 'المواد الأساسية'}, '3002': {'name': 'أسمنت نجران', 'sector': 'المواد الأساسية'},
    '3003': {'name': 'أسمنت المدينة', 'sector': 'المواد الأساسية'}, '3004': {'name': 'أسمنت الشمالية', 'sector': 'المواد الأساسية'},
    '3005': {'name': 'أسمنت أم القرى', 'sector': 'المواد الأساسية'}, '3007': {'name': 'أسمنت الرياض', 'sector': 'المواد الأساسية'},
    '1120': {'name': 'الراجحي', 'sector': 'البنوك'}, '1180': {'name': 'الأهلي', 'sector': 'البنوك'},
    '1010': {'name': 'الرياض', 'sector': 'البنوك'}, '1150': {'name': 'الإنماء', 'sector': 'البنوك'},
    '1060': {'name': 'الأول (ساب)', 'sector': 'البنوك'}, '1020': {'name': 'الجزيرة', 'sector': 'البنوك'},
    '1030': {'name': 'الاستثمار', 'sector': 'البنوك'}, '1050': {'name': 'الفرنسي', 'sector': 'البنوك'},
    '1080': {'name': 'العربي', 'sector': 'البنوك'}, '1140': {'name': 'البلاد', 'sector': 'البنوك'},
    '7010': {'name': 'STC', 'sector': 'الأتصالات'}, '7020': {'name': 'موبايلي', 'sector': 'الأتصالات'},
    '7030': {'name': 'زين', 'sector': 'الأتصالات'}, '7040': {'name': 'عذيب', 'sector': 'الأتصالات'},
    '5110': {'name': 'الكهرباء', 'sector': 'المرافق العامة'}, '2082': {'name': 'أكوا باور', 'sector': 'المرافق العامة'},
    '2083': {'name': 'مرافق', 'sector': 'المرافق العامة'}, '4002': {'name': 'المواساة', 'sector': 'الرعاية الصحية'},
    '4004': {'name': 'دله', 'sector': 'الرعاية الصحية'}, '4007': {'name': 'الحمادي', 'sector': 'الرعاية الصحية'},
    '4013': {'name': 'سليمان الحبيب', 'sector': 'الرعاية الصحية'}, '4164': {'name': 'النهدي', 'sector': 'الرعاية الصحية'},
    '2280': {'name': 'المراعي', 'sector': 'إنتاج الأغذية'}, '2050': {'name': 'صافولا', 'sector': 'إنتاج الأغذية'},
    '2270': {'name': 'سدافكو', 'sector': 'إنتاج الأغذية'}, '4001': {'name': 'العثيم', 'sector': 'تجزئة الأغذية'},
    '4190': {'name': 'جرير', 'sector': 'السلع الكمالية'}, '4003': {'name': 'اكسترا', 'sector': 'السلع الكمالية'},
    '4160': {'name': 'ثمار', 'sector': 'تجزئة الأغذية'}, '2281': {'name': 'تنمية', 'sector': 'إنتاج الأغذية'},
    '7202': {'name': 'سلوشنز', 'sector': 'التقنية'}, '7203': {'name': 'علم', 'sector': 'التقنية'},
    '4263': {'name': 'سال', 'sector': 'النقل'}, '4031': {'name': 'سيسكو', 'sector': 'النقل'},
    '4260': {'name': 'بدجت', 'sector': 'النقل'}, '4261': {'name': 'ذيب', 'sector': 'النقل'},
    '4220': {'name': 'إعمار', 'sector': 'العقارات'}, '4300': {'name': 'دار الأركان', 'sector': 'العقارات'},
    '4250': {'name': 'جبل عمر', 'sector': 'العقارات'}, '4090': {'name': 'طيبة', 'sector': 'العقارات'},
    '4321': {'name': 'المراكز', 'sector': 'إدارة وتطوير العقارات'}, '8010': {'name': 'التعاونية', 'sector': 'التأمين'},
    '8230': {'name': 'الراجحي تكافل', 'sector': 'التأمين'}, '8210': {'name': 'بوبا', 'sector': 'التأمين'},
}

def get_master_styles(C):
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        /* === 1. الإعدادات العامة (تحسين الخطوط والاتجاه) === */
        html, body, [class*="css"], p, h1, h2, h3, h4, div, label, button, input, textarea {{
            font-family: 'Cairo', sans-serif !important;
            direction: rtl;
            color: {C['main_text']} !important;
        }}
        
        /* === 2. إصلاح أيقونات الجوال والاكسباندر === */
        .material-icons, [data-testid="stExpanderToggleIcon"], svg, span[class^="css-"] {{
            font-family: sans-serif !important;
            direction: ltr !important;
        }}
        
        /* === 3. خلفية التطبيق النظيفة === */
        .stApp, [data-testid="stAppViewContainer"] {{
            background-color: {C['page_bg']} !important;
        }}
        [data-testid="stHeader"] {{
            background-color: transparent !important;
        }}
        
        /* === 4. إخفاء القوائم الجانبية تماماً === */
        [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{
            display: none !important;
            width: 0 !important;
        }}
        
        /* === 5. تحسين حقول الإدخال (تصميم يشبه الآيفون) === */
        input, .stTextInput input, .stNumberInput input, .stSelectbox, div[data-baseweb="select"] > div {{
            background-color: {C['input_bg']} !important;
            color: {C['main_text']} !important;
            border: 1px solid {C['border']} !important;
            border-radius: 12px !important; /* زوايا دائرية */
            padding: 10px !important;
            direction: rtl;
            font-weight: 600;
        }}
        div[data-baseweb="select"] > div:hover, input:hover {{
            border-color: {C['primary']} !important;
        }}
        
        /* === 6. الجداول (بطاقات نظيفة) === */
        .finance-table {{
            width: 100%; border-collapse: separate; border-spacing: 0;
            background-color: {C['card_bg']}; 
            border: 1px solid {C['border']};
            border-radius: 16px; /* زوايا ناعمة */
            overflow: hidden; 
            margin-bottom: 25px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.02); /* ظل خفيف */
        }}
        .finance-table th {{ 
            color: {C['sub_text']} !important; padding: 15px; 
            text-align: center; border-bottom: 1px solid {C['border']}; 
            font-weight: 800; font-size: 0.9rem;
            background-color: #F9FAFB;
        }}
        .finance-table td {{ 
            padding: 12px; text-align: center; border-bottom: 1px solid {C['border']}; 
            color: {C['main_text']} !important; font-weight: 700;
        }}

        /* === 7. البطاقات (KPIs) - تصميم التطبيقات === */
        .kpi-box {{
            background-color: {C['card_bg']};
            border: 1px solid {C['border']};
            border-radius: 16px;
            padding: 20px;
            text-align: right;
            margin-bottom: 15px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.03); /* ظل جميل */
            transition: transform 0.2s; /* حركة عند اللمس */
        }}
        .kpi-box:hover {{
            transform: translateY(-2px);
        }}
        .kpi-title {{ font-size: 0.9rem; color: {C['sub_text']} !important; margin-bottom: 8px; font-weight: 600; }}
        .kpi-value {{ font-size: 1.6rem; font-weight: 900; color: {C['main_text']} !important; direction: ltr; display: inline-block; }}
        
        /* === 8. الأزرار (كبيرة ومريحة للمس) === */
        div.stButton > button:first-child {{
            border-radius: 12px; 
            border: 1px solid {C['border']};
            padding: 0.6rem 1rem;
            font-weight: 700;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            transition: all 0.2s;
        }}
        div.stButton > button:hover {{
            border-color: {C['primary']};
            color: {C['primary']};
            transform: scale(1.02);
        }}
        button[kind="primary"] {{
            background-color: {C['primary']} !important;
            color: white !important; 
            border: none !important;
            box-shadow: 0 4px 10px rgba(37, 99, 235, 0.2) !important; /* ظل ملون للزر الأساسي */
        }}
        
        /* === 9. إعدادات خاصة للجوال (Mobile Responsive) === */
        @media only screen and (max-width: 600px) {{
            /* تكبير النصوص في الجوال */
            html, body {{ font-size: 16px !important; }}
            
            /* جعل الأزرار العلوية قابلة للسحب أفقياً بدلاً من التكدس */
            [data-testid="column"] {{
                min-width: 25% !important; /* عرض مناسب للزر */
                flex: 1 1 auto !important;
            }}
            
            /* تحسين الهوامش */
            .block-container {{ padding-top: 1rem !important; padding-left: 1rem !important; padding-right: 1rem !important; }}
            
            /* تكبير الأرقام */
            .kpi-value {{ font-size: 1.4rem !important; }}
        }}

        /* إخفاء الهوامش الزائدة */
        #MainMenu, footer {{ visibility: hidden; }}
    </style>
    """
