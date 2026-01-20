from pathlib import Path
from data_source import TADAWUL_DB 

# --- إعدادات الهوية ---
APP_NAME = "أصولي"
APP_ICON = "🏛️"
DB_PATH = Path("stocks.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الألوان الموحدة ---
DEFAULT_COLORS = {
    'primary': '#0052CC',       # الأزرق (للعناوين والأزرار)
    'page_bg': '#F4F5F7',       # خلفية الصفحة (رمادي مائل للأزرق خفيف جداً)
    'card_bg': '#FFFFFF',       # خلفية الجداول والكروت
    'main_text': '#172B4D',     # لون النص الأساسي (كحلي غامق)
    'sub_text': '#5E6C84',      # لون النص الفرعي
    'success': '#006644',       # أخضر (للأرباح)
    'danger': '#DE350B',        # أحمر (للخسائر)
    'border': '#DFE1E6',        # لون الحدود
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
        
        /* --- 1. حاوية الجدول الموحدة (The Container) --- */
        .finance-table-container {{
            background-color: {C['card_bg']};
            border: 1px solid {C['border']};
            border-radius: 8px;          /* زوايا دائرية */
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05); /* ظل خفيف */
            overflow: hidden;            /* لضمان قص الزوايا */
            margin-bottom: 20px;
        }}

        /* --- 2. الجدول نفسه --- */
        .finance-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}

        /* --- 3. رأس الجدول (Header) --- */
        .finance-table th {{
            background-color: #FAFBFC;   /* رمادي فاتح جداً */
            color: {C['sub_text']} !important;
            font-weight: 700 !important;
            padding: 12px 16px !important;
            text-align: right;
            border-bottom: 2px solid {C['border']};
            white-space: nowrap;         /* منع التفاف النص */
        }}

        /* --- 4. خلايا الجدول (Rows) --- */
        .finance-table td {{
            background-color: {C['card_bg']};
            padding: 12px 16px !important;
            text-align: right;
            border-bottom: 1px solid {C['border']};
            color: {C['main_text']};
            font-weight: 600;
            vertical-align: middle;
        }}

        /* تأثير عند مرور الماوس */
        .finance-table tr:hover td {{
            background-color: #F4F5F7 !important;
        }}

        /* إزالة الخط من آخر صف */
        .finance-table tr:last-child td {{
            border-bottom: none;
        }}

        /* --- عناصر أخرى (كروت KPI والناف بار) --- */
        .app-logo-box {{
            background: linear-gradient(135deg, {C['primary']}, #0065FF);
            width: 48px; height: 48px; border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            font-size: 1.8rem; color: white;
            box-shadow: 0 4px 6px -1px rgba(0, 82, 204, 0.3);
            margin-left: 10px;
        }}
        .logo-text {{ font-size: 1.6rem; font-weight: 900; color: {C['primary']}; }}
        
        .kpi-box {{
            background-color: {C['card_bg']}; border: 1px solid {C['border']}; 
            border-radius: 8px; padding: 16px; text-align: right; 
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }}
        .kpi-value {{ font-size: 1.4rem; font-weight: 800; color: {C['main_text']}; direction: ltr; }}
        
        [data-testid="stSidebar"] {{ display: none !important; }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 20px; }}
        .stTabs [data-baseweb="tab"] {{ height: 40px; border: none; font-weight: bold; }}
        .stTabs [aria-selected="true"] {{ color: {C['primary']} !important; border-bottom: 3px solid {C['primary']} !important; background: transparent !important; }}
    </style>
    """
