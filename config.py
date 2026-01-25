from pathlib import Path

# --- إعدادات النظام ---
APP_NAME = "أصولي"
APP_ICON = "💎"
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الهوية البصرية (Theme) ---
DEFAULT_COLORS = {
    'page_bg': '#F4F6F8',       # خلفية رمادية فاتحة جداً
    'card_bg': '#FFFFFF',       # خلفية البطاقات بيضاء
    'main_text': '#172B4D',     # نص داكن
    'sub_text': '#5E6C84',      # نص رمادي
    'primary': '#0052CC',       # أزرق رئيسي (ترايدنت)
    'success': '#36B37E',       # أخضر نجاح
    'danger': '#FF5630',        # أحمر خطر
    'border': '#DFE1E6',        # حدود ناعمة
    'input_bg': '#FFFFFF',
    'header_bg': '#FAFBFC'
}
