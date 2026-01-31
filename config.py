# config.py
import streamlit as st
from pathlib import Path

# ==========================================
# 1. هوية التطبيق (App Identity)
# ==========================================
APP_NAME = "أصولي"
APP_ICON = "🏛️"
VERSION = "1.0.0"

# ==========================================
# 2. إعدادات الملفات والمجلدات (Paths)
# ==========================================
# استخدام Path يجعل الكود يعمل بامتياز سواء على Windows أو Linux/Mac
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = BASE_DIR / "backups"

# التأكد من وجود المجلدات (إنشاءها تلقائياً إذا لم تكن موجودة)
DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# ملف قاعدة البيانات المحلي (احتياطي أو في حال استخدام SQLite مستقبلاً)
DB_NAME = "osoli_data.db"
DB_PATH = DATA_DIR / DB_NAME

# ==========================================
# 3. إعدادات قاعدة البيانات (Database Config)
# ==========================================
# محاولة جلب الرابط من الـ Secrets لدعم PostgreSQL
try:
    # ندعم التسميتين الشائعتين في Streamlit Cloud أو Local
    DB_CONNECTION_URL = st.secrets.get("DATABASE_URL") or st.secrets["postgres"]["url"]
except (FileNotFoundError, KeyError):
    # في حال عدم وجود Secrets، نتركها فارغة ليتم التعامل مع الخطأ في database.py
    DB_CONNECTION_URL = None

# ==========================================
# 4. الثوابت المالية (Financial Constants)
# ==========================================
# عمولة التداول (السوق السعودي مثلاً 0.00155 شامل الضريبة)
COMMISSION_RATE = 0.00155 
VAT_RATE = 0.15

# ==========================================
# 5. ألوان الواجهة (UI Theme)
# ==========================================
DEFAULT_COLORS = {
    'primary': '#0052CC',      # اللون الرئيسي (أزرق)
    'page_bg': '#F4F6F8',      # خلفية الصفحة (رمادي فاتح جداً)
    'card_bg': '#FFFFFF',      # خلفية البطاقات
    'main_text': '#172B4D',    # النص الرئيسي
    'sub_text': '#6B778C',     # النص الفرعي
    'success': '#006644',      # نجاح/ربح
    'danger': '#DE350B',       # خطأ/خسارة
    'warning': '#FF991F',      # تنبيه
    'border': '#DFE1E6'        # الحدود
}

# ==========================================
# 6. ألوان الرسوم البيانية (Chart Theme)
# ==========================================
# توحيد الألوان المستخدمة في Plotly لضمان التناسق
CHART_COLORS = {
    'candle_up': '#26a69a',    # شمعة صاعدة (أخضر تداول)
    'candle_down': '#ef5350',  # شمعة هابطة (أحمر تداول)
    'sma_50': '#FF9800',       # متوسط 50 (برتقالي)
    'sma_200': '#2962FF',      # متوسط 200 (أزرق)
    'support': '#00C853',      # خط دعم
    'resistance': '#D50000',   # خط مقاومة
    'golden_ratio': '#FFD700', # النسبة الذهبية
    'grid': '#E1E4E8'          # الشبكة الخلفية
}
