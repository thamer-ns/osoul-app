from pathlib import Path

# --- إعدادات النظام ---
APP_NAME = "أصولي"
APP_ICON = "💎"
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الهوية البصرية ---
DEFAULT_COLORS = {
    'page_bg': '#F4F6F8',       
    'card_bg': '#FFFFFF',       
    'main_text': '#172B4D',     
    'sub_text': '#5E6C84',      
    'primary': '#0052CC',       
    'success': '#36B37E',       
    'danger': '#FF5630',        
    'border': '#DFE1E6',        
    'input_bg': '#FFFFFF',
    'header_bg': '#FAFBFC'
}
