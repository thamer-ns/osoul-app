from pathlib import Path

# --- إعدادات الهوية ---
APP_NAME = "أصولي"
APP_ICON = "🏛️"
DB_PATH = Path("stocks.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الألوان (نفس الألوان الأصلية الجميلة) ---
DEFAULT_COLORS = {
    'page_bg': '#F8F9FA',        # خلفية بيضاء مريحة
    'card_bg': '#FFFFFF',
    'main_text': '#172B4D',      # كحلي غامق للنصوص
    'sub_text': '#5E6C84',       # رمادي للنصوص الفرعية
    'primary': '#0052CC',        # الأزرق الرسمي
    'success': '#006644',        # أخضر غامق ومريح للعين
    'danger': '#DE350B',         # أحمر واضح للخسارة
    'border': '#DFE1E6',         # حدود ناعمة
}

def get_css(C):
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
        
        html, body, [class*="css"], button, input, select, textarea {{
            font-family: 'Cairo', sans-serif !important; 
            direction: rtl;
        }}
        
        .stApp {{ background-color: {C['page_bg']} !important; }}
        
        /* --- تصميم الجداول الاحترافي (المطلوب) --- */
        .finance-table-container {{
            overflow-x: auto;
            border-radius: 8px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
            border: 1px solid {C['border']};
            background: white;
            margin-bottom: 20px;
        }}
        
        .finance-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        
        .finance-table th {{
            background-color: #F4F5F7;
            color: {C['sub_text']};
            font-weight: 700;
            padding: 12px 16px;
            text-align: right;
            border-bottom: 2px solid {C['border']};
            white-space: nowrap;
        }}
        
        .finance-table td {{
            padding: 12px 16px;
            color: {C['main_text']};
            border-bottom: 1px solid {C['border']};
            text-align: right;
            vertical-align: middle;
        }}
        
        .finance-table tr:last-child td {{ border-bottom: none; }}
        .finance-table tr:hover td {{ background-color: #FAFBFC; }}

        /* --- الكروت KPI --- */
        .kpi-box {{
            background: {C['card_bg']};
            border: 1px solid {C['border']};
            border-radius: 8px;
            padding: 16px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
            text-align: right;
        }}
        .kpi-label {{ color: {C['sub_text']}; font-size: 0.85rem; font-weight: 600; margin-bottom: 4px; }}
        .kpi-val {{ color: {C['main_text']}; font-size: 1.4rem; font-weight: 800; direction: ltr; }}
        
        /* إخفاء العناصر المزعجة */
        [data-testid="stSidebar"] {{ display: none; }}
        .stDeployButton {{ display: none; }}
        
        /* تنسيق التبويبات */
        .stTabs [data-baseweb="tab-list"] {{ gap: 20px; border-bottom: 1px solid {C['border']}; }}
        .stTabs [data-baseweb="tab"] {{ font-weight: bold; border: none !important; background: none !important; }}
        .stTabs [aria-selected="true"] {{ color: {C['primary']} !important; border-bottom: 3px solid {C['primary']} !important; }}
        
    </style>
    """
