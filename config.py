from pathlib import Path

# --- إعدادات أساسية ---
APP_NAME = "أصولي برو"
APP_ICON = "🏛️"
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الهوية البصرية (Theme) ---
DEFAULT_COLORS = {
    'primary': '#0052CC',       # الأزرق الرسمي
    'page_bg': '#F4F6F8',       # رمادي فاتح
    'card_bg': '#FFFFFF',       # أبيض
    'main_text': '#172B4D',     # كحلي غامق
    'sub_text': '#5E6C84',      # رمادي
    'success': '#006644',       # أخضر
    'danger': '#DE350B',        # أحمر
    'warning': '#FFAB00',       # برتقالي للتحذيرات
    'border': '#DFE1E6',        # حدود ناعمة
    'input_bg': '#FAFBFC'       # خلفية الحقول
}

def get_css():
    C = DEFAULT_COLORS
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        html, body, [class*="css"], p, h1, h2, h3, h4, div, label, button, input, textarea, span, th, td {{
            font-family: 'Cairo', sans-serif !important; 
            direction: rtl; 
            color: {C['main_text']};
        }}
        
        .stApp {{ background-color: {C['page_bg']} !important; }}
        
        /* إخفاء القائمة الجانبية */
        [data-testid="stSidebar"] {{ display: none !important; }}
        
        /* البطاقات العامة */
        .kpi-box {{
            background-color: {C['card_bg']}; 
            border: 1px solid {C['border']}; 
            border-radius: 12px;
            padding: 16px; 
            text-align: right; 
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            transition: transform 0.2s;
        }}
        .kpi-box:hover {{ transform: translateY(-2px); }}
        
        /* بطاقات الأسعار (Pulse) */
        .ticker-card {{
            background-color: {C['card_bg']};
            border-radius: 10px;
            padding: 15px;
            border-left: 4px solid {C['primary']};
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            margin-bottom: 10px;
        }}
        
        /* الجداول */
        .finance-table-container {{
            background-color: {C['card_bg']};
            border-radius: 8px;
            border: 1px solid {C['border']};
            overflow: hidden;
            margin-bottom: 20px;
        }}
        .finance-table {{ width: 100%; border-collapse: collapse; }}
        .finance-table th {{ 
            background-color: #FAFBFC; padding: 12px 15px; text-align: right; 
            color: {C['sub_text']}; font-size: 0.85rem; font-weight: 700;
            border-bottom: 2px solid {C['border']}; white-space: nowrap;
        }}
        .finance-table td {{ 
            padding: 12px 15px; text-align: right; 
            border-bottom: 1px solid {C['border']}; font-size: 0.9rem; font-weight: 600;
        }}
        
        /* تحسين التبويبات */
        .stTabs [data-baseweb="tab-list"] {{ gap: 8px; }}
        .stTabs [data-baseweb="tab"] {{
            height: 45px; border-radius: 8px; background-color: white; border: 1px solid {C['border']};
        }}
        .stTabs [aria-selected="true"] {{
            background-color: {C['primary']} !important; color: white !important;
        }}
    </style>
    """
