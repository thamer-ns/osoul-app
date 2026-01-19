# config.py
from pathlib import Path
from data_source import TADAWUL_DB  # <--- هذا هو الربط السحري!

# --- إعدادات الهوية ---
APP_NAME = "أصولي"
APP_ICON = "🏛️"
DB_PATH = Path("stocks.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الألوان ---
DEFAULT_COLORS = {
    'page_bg': '#F9FAFB',
    'card_bg': '#FFFFFF',
    'main_text': '#111827',
    'sub_text': '#6B7280',
    'primary': '#0e6ba8',
    'success': '#10B981',
    'danger': '#EF4444',
    'border': '#E5E7EB',
}

def get_css(C):
    # ... (نفس كود CSS السابق تماماً) ...
    # (انسخ دالة get_css من ردي السابق في data_source.py وضعها هنا)
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
