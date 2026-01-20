from pathlib import Path
from data_source import TADAWUL_DB 

# --- إعدادات الهوية ---
APP_NAME = "أصولي"
APP_ICON = "🏛️"
DB_PATH = Path("stocks.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الألوان (استعادة الثيم الأصلي من الكود المرفق) ---
DEFAULT_COLORS = {
    'primary': '#0052CC',       # الأزرق الأصلي
    'page_bg': '#F4F6F8',       # الخلفية الأصلية
    'card_bg': '#FFFFFF',
    'main_text': '#172B4D',     # لون النص الأصلي
    'sub_text': '#6B7280',
    'success': '#006644',       # أخضر داكن (أكثر احترافية)
    'danger': '#DE350B',        # أحمر داكن
    'border': '#DFE1E6',
}

def get_css(C):
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        html, body, [class*="css"], p, div, label, input, textarea, th, td, h1, h2, h3, button {{
            font-family: 'Cairo', sans-serif !important; 
            direction: rtl;
            color: {C['main_text']};
        }}
        
        .stApp {{ background-color: {C['page_bg']} !important; }}
        
        /* تصميم اللوقو الأصلي */
        .app-logo-box {{
            background: linear-gradient(135deg, {C['primary']}, #0065FF);
            width: 48px; height: 48px; border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            font-size: 1.8rem; color: white;
            box-shadow: 0 4px 6px -1px rgba(0, 82, 204, 0.3);
            margin-left: 10px;
        }}
        .logo-text {{
            font-size: 1.6rem; font-weight: 900; color: {C['primary']}; letter-spacing: -0.5px;
        }}
        
        /* تحسينات الأزرار لتشبه التصميم الأصلي */
        div[data-testid="stHorizontalBlock"] button {{
            border-radius: 6px !important; font-weight: 700 !important; border: none;
            transition: all 0.2s;
        }}
        
        /* الكروت KPI */
        .kpi-box {{
            background-color: {C['card_bg']}; 
            border: 1px solid {C['border']}; 
            border-radius: 8px; 
            padding: 16px; 
            text-align: right; 
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
            margin-bottom: 10px;
        }}
        .kpi-value {{ font-size: 1.4rem; font-weight: 800; color: {C['main_text']}; direction: ltr; }}
        
        /* الجداول (التصميم الأصلي مع دعم القوائم المالية) */
        .finance-table {{ width: 100%; border-collapse: separate; border-spacing: 0 4px; margin-top: 5px; }}
        .finance-table th {{ 
            color: {C['sub_text']} !important; font-weight: 700 !important; font-size: 0.85rem !important;
            padding: 10px !important; text-align: center; border-bottom: 2px solid {C['border']};
            background-color: transparent;
        }}
        .finance-table td {{ 
            background-color: white; padding: 12px !important; text-align: center;
            color: {C['main_text']}; font-weight: 600; font-size: 0.9rem !important;
            border-top: 1px solid {C['border']}; border-bottom: 1px solid {C['border']};
            border-radius: 4px; /* زوايا دائرية للصفوف */
        }}
        
        [data-testid="stSidebar"] {{ display: none !important; }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 20px; }}
        .stTabs [data-baseweb="tab"] {{ height: 40px; border: none; font-weight: bold; }}
        .stTabs [aria-selected="true"] {{ color: {C['primary']} !important; border-bottom: 3px solid {C['primary']} !important; background: transparent !important; }}
    </style>
    """
