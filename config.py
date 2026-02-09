# config.py
# إعدادات عامة لتطبيق "أصولي".
# هذا الملف مطلوب لأن app.py و security.py و backtester.py وبعض الواجهات تعتمد عليه.

from __future__ import annotations

import os

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
