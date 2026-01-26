from pathlib import Path

APP_NAME = "أصولي"
APP_ICON = "🏛️"
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_COLORS = {
    'primary': '#0052CC',
    'page_bg': '#F4F6F8',
    'card_bg': '#FFFFFF',
    'main_text': '#172B4D',
    'sub_text': '#5E6C84',
    'success': '#006644',
    'danger': '#DE350B',
    'border': '#DFE1E6',
    'input_bg': '#FFFFFF',
}
