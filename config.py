from pathlib import Path

# --- إعدادات الهوية ---
APP_NAME = "أصولي"
APP_ICON = "🏛️"
DB_PATH = Path("stocks.db")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الألوان (الثيم الموحد) ---
DEFAULT_COLORS = {
    'page_bg': '#F3F4F6',        
    'card_bg': '#FFFFFF',        
    'main_text': '#111827',      
    'sub_text': '#6B7280',       
    'primary': '#0e6ba8',        
    'success': '#10B981',        
    'danger': '#EF4444',         
    'border': '#E5E7EB',         
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
        
        /* اللوقو */
        .app-logo-box {{
            background: linear-gradient(135deg, {C['primary']}, #0284c7);
            width: 48px; height: 48px; border-radius: 12px;
            display: flex; align-items: center; justify-content: center;
            font-size: 1.8rem; color: white;
            box-shadow: 0 4px 6px -1px rgba(14, 107, 168, 0.3);
            margin-left: 10px;
        }}
        .logo-text {{ font-size: 1.6rem; font-weight: 900; color: {C['primary']}; }}
        
        /* الكروت KPI */
        .kpi-box {{
            background-color: {C['card_bg']}; border: 1px solid {C['border']}; 
            border-radius: 12px; padding: 20px; text-align: right; 
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1); transition: all 0.2s;
        }}
        .kpi-box:hover {{ transform: translateY(-2px); box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }}
        .kpi-value {{ font-size: 1.5rem; font-weight: 800; color: {C['main_text']}; margin-top: 5px; direction: ltr; }}
        
        /* تصميم الجداول الموحد */
        .finance-table {{ width: 100%; border-collapse: separate; border-spacing: 0; margin-top: 10px; border: 1px solid {C['border']}; border-radius: 12px; overflow: hidden; }}
        .finance-table th {{ 
            background-color: #F9FAFB; color: {C['sub_text']} !important; font-weight: 700 !important; 
            padding: 15px !important; text-align: center; border-bottom: 1px solid {C['border']};
        }}
        .finance-table td {{ 
            background-color: white; padding: 12px !important; text-align: center;
            color: {C['main_text']}; font-weight: 600; font-size: 0.9rem !important;
            border-bottom: 1px solid {C['border']};
        }}
        .finance-table tr:last-child td {{ border-bottom: none; }}
        
        /* إخفاء السايدبار */
        [data-testid="stSidebar"] {{ display: none !important; }}
        
        /* التبويبات */
        .stTabs [data-baseweb="tab-list"] {{ gap: 10px; background: transparent; }}
        .stTabs [data-baseweb="tab"] {{ 
            height: 45px; border-radius: 8px; background: white; border: 1px solid {C['border']}; padding: 0 20px;
        }}
        .stTabs [aria-selected="true"] {{ 
            background-color: {C['primary']} !important; color: white !important; border-color: {C['primary']} !important;
        }}
    </style>
    """
