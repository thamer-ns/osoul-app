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

# --- بيانات الشركات (مختصرة لعدم الإطالة، نفس السابق) ---
TADAWUL_DB = {
    '2222': {'name': 'أرامكو السعودية', 'sector': 'الطاقة'},
    '2010': {'name': 'سابك', 'sector': 'المواد الأساسية'},
    '1120': {'name': 'الراجحي', 'sector': 'البنوك'},
    '1180': {'name': 'الأهلي', 'sector': 'البنوك'},
    # ... (باقي الشركات كما هي في الكود السابق)
}

def get_css(C):
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        html, body, [class*="css"], p, div, label, input, textarea, th, td {{
            font-family: 'Cairo', sans-serif !important; direction: rtl;
        }}
        
        .stApp {{ background-color: {C['page_bg']} !important; }}
        
        /* === تصميم متجاوب للقائمة العلوية (Navbar) === */
        /* استهداف الحاوية الأفقية للأزرار */
        div[data-testid="stHorizontalBlock"] {{
            display: flex !important;
            flex-wrap: wrap !important; /* السماح بالالتفاف في الشاشات الصغيرة */
            justify-content: center !important;
            gap: 5px !important;
        }}
        
        /* تنسيق الأزرار */
        div[data-testid="stHorizontalBlock"] button {{
            white-space: nowrap !important;
            padding: 0.2rem 0.5rem !important;
            font-size: 0.85rem !important;
            min-width: 80px !important; /* عرض أدنى لضمان قراءة النص */
            flex: 1 1 auto !important; /* تمدد تلقائي */
            margin: 2px !important;
        }}
        
        /* === تحسين الجداول للجوال === */
        .finance-table {{ width: 100%; border-collapse: separate; border-spacing: 0 4px; margin-top: 5px; }}
        
        .finance-table th {{ 
            color: #0e6ba8 !important;
            font-weight: 800 !important;
            font-size: 0.8rem !important;
            padding: 8px 4px !important;
            text-align: center;
            background-color: transparent;
            border-bottom: 2px solid #F3F4F6;
            white-space: nowrap !important;
        }}
        
        .finance-table td {{ 
            background-color: white;
            padding: 6px 4px !important;
            text-align: center;
            color: #374151;
            font-weight: 600;
            font-size: 0.75rem !important;
            border-top: 1px solid #F3F4F6;
            border-bottom: 1px solid #F3F4F6;
            white-space: nowrap !important;
        }}
        
        /* جعل الجدول قابلاً للتمرير أفقياً في الجوال */
        div[style*="overflow-x: auto"] {{
            -webkit-overflow-scrolling: touch;
        }}

        /* === تحسين العناوين === */
        h1, h2, h3, h4 {{
            font-family: 'Cairo', sans-serif !important;
            color: #1F2937 !important;
            border-right: 5px solid {C['primary']};
            padding-right: 15px;
            margin-bottom: 20px !important;
            font-weight: 800 !important;
            text-align: right !important;
            width: 100%;
        }}
        
        /* تكيف حجم الخط في الجوال */
        @media (max-width: 600px) {{
            h1 {{ font-size: 1.5rem !important; }}
            h2 {{ font-size: 1.2rem !important; }}
            h3 {{ font-size: 1rem !important; }}
            .kpi-value {{ font-size: 1.1rem !important; }}
        }}

        .kpi-box {{
            background-color: {C['card_bg']}; border: 1px solid {C['border']}; border-radius: 12px;
            padding: 10px; text-align: right; margin-bottom: 10px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        .kpi-value {{ font-size: 1.3rem; font-weight: 800; color: {C['main_text']}; }}
        
        .tasi-box {{
            background: white; padding: 15px; border-radius: 12px; border: 1px solid {C['border']};
            display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;
        }}
        
        [data-testid="stSidebar"] {{ display: none !important; }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 10px; }}
        .stTabs [data-baseweb="tab"] {{ height: 40px; white-space: nowrap; }}
        
        div[data-testid="stExpander"] {{
            background-color: white; border-radius: 8px; border: 1px solid #E5E7EB;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }}
    </style>
    """
