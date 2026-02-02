# ui/pages/analysis/__init__.py
# الهدف: تصدير view_analysis فقط بدون أي imports جانبية تسبب تكرار/سايد-إفكت

from ui.pages.analysis.page import view_analysis  # noqa: F401
