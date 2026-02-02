# ui/pages/analysis/__init__.py
"""
Analysis package
✅ المصدر الرسمي للتحليل داخل: ui.pages.analysis
"""

try:
    from ui.pages.analysis.page import view_analysis  # noqa: F401
except Exception:
    # نخليه ما يكسر import الباكيج بالكامل أثناء التطوير
    view_analysis = None
