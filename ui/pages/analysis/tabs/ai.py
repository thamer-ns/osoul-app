# ui/pages/analysis/tabs/ai.py
# Wrapper tab: AI
# الهدف: توفير render_tab() المطلوبة من page.py مع الحفاظ على منطق/واجهة AI القديمة بدون تغييرها

from __future__ import annotations

import importlib
import streamlit as st


def _load_first_callable(module_name: str, candidates: list[str]):
    """يحاول يجيب أول دالة موجودة من قائمة أسماء محتملة."""
    mod = importlib.import_module(module_name)
    for name in candidates:
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    return None


def render_tab(symbol: str, fin: dict | None = None):
    """
    API ثابت للتبويب.
    - symbol: رمز السهم
    - fin: بيانات مالية/محفظة (اختياري)
    """

    # 1) نحاول AI الجديد (لو عندك منظم داخل مجلد ai)
    # (قد تكون سميت الدالة render_tab / view / render / render_ai_tab ... إلخ)
    try:
        fn = _load_first_callable(
            "ui.pages.analysis.ai.ai_tab",
            ["render_tab", "view", "render", "render_ai_tab", "view_ai_tab", "main", "run"],
        )
        if fn:
            # بعض الدوال تستقبل (symbol, fin) وبعضها (symbol) فقط
            try:
                return fn(symbol, fin)
            except TypeError:
                return fn(symbol)
    except Exception:
        pass

    # 2) نحاول AI القديم لو كان موجود في نفس مجلد analysis (الملف اللي كان قبل التقسيم)
    # ui/pages/analysis/ai_tab.py
    try:
        fn = _load_first_callable(
            "ui.pages.analysis.ai_tab",
            ["render_tab", "view", "render", "render_ai_tab", "view_ai_tab", "main", "run"],
        )
        if fn:
            try:
                return fn(symbol, fin)
            except TypeError:
                return fn(symbol)
    except Exception:
        pass

    # 3) آخر خيار: عرض رسالة واضحة بدل ما يطيح البرنامج
    st.warning("تعذر تحميل واجهة AI (الجديدة أو القديمة).")
    st.info("✅ تأكد أن أحد الملفات التالية يحتوي دالة render_tab أو view أو render:")
    st.code(
        "ui/pages/analysis/ai/ai_tab.py\n"
        "ui/pages/analysis/ai_tab.py",
        language="text",
    )
