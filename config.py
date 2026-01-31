# config.py
import streamlit as st
from pathlib import Path

# ==========================================
# 1. هوية التطبيق
# ==========================================
APP_NAME = "أصولي"
APP_ICON = "🏛️"
VERSION = "1.0.0"

# ==========================================
# 2. المسارات (Paths)
# ==========================================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = BASE_DIR / "backups"

# إنشاء المجلدات للنسخ الاحتياطي والملفات المؤقتة
DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# 3. إعدادات قاعدة البيانات (Database Config)
# ==========================================
# محاولة جلب الرابط من الـ Secrets، وإذا لم يوجد نتركه فارغاً ليتم التعامل معه في database.py
try:
    # ندعم التسميتين الشائعتين
    DB_CONNECTION_URL = st.secrets.get("DATABASE_URL") or st.secrets["postgres"]["url"]
except (FileNotFoundError, KeyError):
    DB_CONNECTION_URL = None  # سيتم التعامل مع الخطأ في database.py

# ==========================================
# 4. الثوابت المالية
# ==========================================
COMMISSION_RATE = 0.00155  # عمولة التداول (شامل الضريبة)
VAT_RATE = 0.15

# ==========================================
# 5. المظهر (UI Theme)
# ==========================================
DEFAULT_COLORS = {
    'primary': '#0052CC',
    'page_bg': '#F4F6F8',
    'card_bg': '#FFFFFF',
    'main_text': '#172B4D',
    'sub_text': '#6B778C',
    'success': '#006644',
    'danger': '#DE350B',
    'warning': '#FF991F',
    'border': '#DFE1E6'
}

CHART_COLORS = {
    'candle_up': '#26a69a',
    'candle_down': '#ef5350',
    'sma_50': '#FF9800',
    'sma_200': '#2962FF',
    'support': '#00C853',
    'resistance': '#D50000',
    'grid': '#E1E4E8'
}
