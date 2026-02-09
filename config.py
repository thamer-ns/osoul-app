# config.py
# إعدادات عامة لتطبيق "أصولي".
# هذا الملف مطلوب لأن app.py و security.py و backtester.py وبعض الواجهات تعتمد عليه.

from __future__ import annotations

import os

# ============================================================
# 🔐 Database URL
# ============================================================
# Streamlit Cloud يمرر secrets عبر st.secrets، أو يمكن تمريره كمتغير بيئة.
# نُبقي الأسماء القديمة/الجديدة معًا لتفادي أخطاء الاستيراد بين النسخ.
def _get_secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st  # type: ignore

        # 1) direct key
        v = st.secrets.get(key)
        if v:
            return str(v)

        # 2) common alternates
        if key == "DATABASE_URL":
            for alt in ("database_url", "db_url", "POSTGRES_URL", "POSTGRES_URI"):
                vv = st.secrets.get(alt)
                if vv:
                    return str(vv)

            # 3) streamlit connections style
            # connections:
            #   postgresql:
            #     url: "..."
            conns = st.secrets.get("connections") or {}
            if isinstance(conns, dict):
                for name in ("postgresql", "postgres", "db"):
                    item = conns.get(name) or {}
                    if isinstance(item, dict) and item.get("url"):
                        return str(item.get("url"))

            # 4) classic section style
            pg = st.secrets.get("postgresql") or {}
            if isinstance(pg, dict) and pg.get("url"):
                return str(pg.get("url"))

        return default
    except Exception:
        return default


# الاسم الذي تستخدمه Streamlit Cloud عادةً
DATABASE_URL = os.getenv("DATABASE_URL") or _get_secret("DATABASE_URL", "")

# توافق مع نسخ سابقة كانت تبحث عن DB_CONNECTION_URL
DB_CONNECTION_URL = os.getenv("DB_CONNECTION_URL") or DATABASE_URL

# ============================================================
# 🏷️ هوية التطبيق
# ============================================================
APP_NAME = os.getenv("APP_NAME", "أصولي")

# APP_ICON يمكن أن يكون إيموجي أو مسار صورة.
# نفضّل assets/logo_mark.png إن كان موجودًا.
_DEFAULT_ICON_PATH = "assets/logo_mark.png"
if os.path.exists(_DEFAULT_ICON_PATH):
    APP_ICON = _DEFAULT_ICON_PATH
else:
    APP_ICON = os.getenv("APP_ICON", "📈")

# ============================================================
# 🎨 ألوان افتراضية للاستخدام داخل الواجهات
# ============================================================
DEFAULT_COLORS = {
    "primary": "#0052CC",
    "success": "#1E8E3E",
    "warning": "#F9AB00",
    "danger": "#D93025",
    "info": "#1E88E5",
    "muted": "#6B7280",
}

# ============================================================
# 🖼️ مسارات الشعارات (تُستخدم في settings و CSS)
# ============================================================
LOGO_FULL_PATH = os.getenv("LOGO_FULL_PATH", "assets/logo_full.png")
LOGO_MARK_PATH = os.getenv("LOGO_MARK_PATH", "assets/logo_mark.png")
LOGO_APP_PATH = os.getenv("LOGO_APP_PATH", "assets/logo_app.png")

# ============================================================
# 💼 إعدادات التداول/المختبر
# ============================================================
# نسبة العمولة الافتراضية (مثال: 0.0015 = 0.15%)
try:
    COMMISSION_RATE = float(os.getenv("COMMISSION_RATE", "0.0015"))
except Exception:
    COMMISSION_RATE = 0.0015
