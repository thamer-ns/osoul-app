from pathlib import Path

# --- إعدادات أساسية ---
APP_NAME = "أصولي"
APP_ICON = "🏛️"
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الهوية البصرية ---
DEFAULT_COLORS = {
    'page_bg': '#F5F7FA',
    'card_bg': '#FFFFFF',
    'main_text': '#1F2937',
    'sub_text': '#6B7280',
    'primary': '#2563EB',
    'success': '#10B981',
    'danger': '#EF4444',
    'border': '#E5E7EB',
    'input_bg': '#F9FAFB'
}

# --- دالة الستايل (CSS) ---
def get_css():
    C = DEFAULT_COLORS
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');
        
        html, body, [class*="css"], p, h1, h2, h3, h4, div, label, button, input, textarea, span {{
            font-family: 'Cairo', sans-serif !important; 
            direction: rtl; 
            color: {C['main_text']};
        }}
        
        .stApp {{ background-color: {C['page_bg']} !important; }}
        
        /* تحسين القائمة الجانبية */
        [data-testid="stSidebar"] {{
            background-color: {C['card_bg']} !important;
            border-left: 1px solid {C['border']};
        }}
        
        /* تحسين الحقول والأزرار */
        input, .stTextInput input, .stNumberInput input, .stSelectbox, .stDateInput input {{
            background-color: {C['input_bg']} !important; 
            border-radius: 12px !important; 
            border: 1px solid {C['border']} !important;
            padding: 10px !important;
        }}
        
        /* بطاقة المؤشر */
        .tasi-box {{
            background: linear-gradient(135deg, {C['card_bg']} 0%, #F8FAFC 100%);
            padding: 20px; 
            border-radius: 16px; 
            border: 1px solid {C['border']};
            display: flex; 
            justify-content: space-between; 
            align-items: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05); 
            margin-bottom: 20px;
        }}
        
        /* البطاقات الرقمية */
        .kpi-box {{
            background-color: {C['card_bg']}; 
            border: 1px solid {C['border']}; 
            border-radius: 16px;
            padding: 20px; 
            text-align: right; 
            margin-bottom: 15px; 
            box-shadow: 0 2px 5px rgba(0,0,0,0.02); 
            transition: transform 0.2s;
        }}
        .kpi-box:hover {{ transform: translateY(-2px); }}
        .kpi-value {{ 
            font-size: 1.4rem; 
            font-weight: 900; 
            direction: ltr; 
            display: inline-block; 
        }}
        
        /* الجداول */
        .finance-table-container {{
            background-color: {C['card_bg']};
            border-radius: 16px;
            border: 1px solid {C['border']};
            overflow: hidden;
            margin-bottom: 25px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.02);
        }}
        .finance-table {{ width: 100%; border-collapse: separate; border-spacing: 0; }}
        .finance-table th {{ 
            background-color: #F9FAFB; padding: 15px; text-align: right; 
            color: {C['sub_text']}; font-size: 0.9rem; font-weight: 700;
            border-bottom: 1px solid {C['border']};
        }}
        .finance-table td {{ 
            padding: 12px 15px; text-align: right; 
            border-bottom: 1px solid {C['border']}; font-size: 0.9rem; vertical-align: middle;
        }}
        .finance-table tr:last-child td {{ border-bottom: none; }}
    </style>
    """
