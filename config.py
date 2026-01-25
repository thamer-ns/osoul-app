from pathlib import Path

# --- إعدادات النظام ---
APP_NAME = "أصولي"
APP_ICON = "📈"
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- الهوية البصرية (Theme) ---
DEFAULT_COLORS = {
    'page_bg': '#F4F6F8',       # خلفية رمادية فاتحة جداً
    'card_bg': '#FFFFFF',       # بطاقات بيضاء
    'main_text': '#172B4D',     # كحلي غامق للنصوص
    'sub_text': '#5E6C84',      # رمادي متوسط
    'primary': '#0052CC',       # أزرق قوي
    'success': '#36B37E',       # أخضر مريح
    'danger': '#FF5630',        # أحمر برتقالي
    'border': '#DFE1E6',        # حدود ناعمة
    'input_bg': '#FFFFFF',
    'header_bg': '#FAFBFC'
}
