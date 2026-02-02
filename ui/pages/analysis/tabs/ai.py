# ui/pages/analysis/tabs/ai.py
import importlib
import inspect
from typing import Any, Callable, Optional, Tuple, List

import streamlit as st


# ✅ استورد الملفات اللي فعلاً ممكن تحتوي دالة عرض
# (لا تحط "ui.pages.analysis.ai" لأنه package وغالبًا ما يصدّر دوال)
CANDIDATE_MODULES: List[str] = [
    "ui.pages.analysis.ai.ai_tab",   # الجديد (داخل مجلد ai)
    "ui.pages.analysis.ai_tab",      # القديم (قبل التقسيم)
    "ui.pages.analysis.ai.main",     # احتياط إذا عندك main.py داخل ai
]

# أسماء دوال شائعة للتبويب
CANDIDATE_FUNC_NAMES: List[str] = [
    "render_tab",
    "render_ai_tab",
    "view_ai_tab",
    "view",
    "render",
    "main",
    "run",
]


def _import_first_available() -> Tuple[Optional[Any], Optional[str], str]:
    errors = []
    for mod_name in CANDIDATE_MODULES:
        try:
            mod = importlib.import_module(mod_name)
            return mod, mod_name, ""
        except Exception as e:
            errors.append(f"{mod_name}: {repr(e)}")
    return None, None, "\n".join(errors)


def _find_callable(mod: Any) -> Optional[Callable]:
    # 1) جرّب الأسماء المعروفة
    for name in CANDIDATE_FUNC_NAMES:
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn

    # 2) fallback: أي callable غير خاص
    for name in dir(mod):
        if name.startswith("_"):
            continue
        obj = getattr(mod, name, None)
        if callable(obj):
            return obj

    return None


def _call_signature_aware(fn: Callable, **kwargs):
    """
    ينادي fn بأمان:
    - إذا الدالة تقبل **kwargs => نعطيها كل شيء
    - وإلا نعطيها فقط المفاتيح اللي موجودة في توقيع الدالة
    """
    try:
        sig = inspect.signature(fn)
        params = sig.parameters

        # إذا فيها **kwargs
        for p in params.values():
            if p.kind == inspect.Parameter.VAR_KEYWORD:
                return fn(**kwargs)

        filtered = {k: v for k, v in kwargs.items() if k in params}
        return fn(**filtered)

    except TypeError as e:
        # fallback: نجرب طرق شائعة بدون kwargs
        symbol = kwargs.get("symbol")
        fin = kwargs.get("fin")

        try:
            return fn(symbol, fin)
        except Exception:
            try:
                return fn(symbol)
            except Exception:
                raise e


def render_tab(
    symbol: str,
    fin: dict,
    company_name: str = "",
    sector: str = "",
    **extra_kwargs,
):
    """
    ✅ هذه الدالة هي اللي page.py يتوقعها
    وتقبل company_name + sector عشان ما يطلع TypeError
    """
    mod, mod_name, import_errors = _import_first_available()

    if not mod:
        st.error("تعذر تحميل واجهة AI: لم أستطع استيراد أي مسار متوقع.")
        with st.expander("تفاصيل محاولات الاستيراد"):
            st.code(import_errors or "No details", language="text")
        st.info(
            "✅ تأكد أن أحد هذه الملفات موجود وفيه دالة عرض:\n"
            "- ui/pages/analysis/ai/ai_tab.py\n"
            "- ui/pages/analysis/ai_tab.py"
        )
        return

    fn = _find_callable(mod)
    if not fn:
        st.error(f"تم استيراد الموديول بنجاح ({mod_name}) لكن لم أجد دالة عرض مناسبة داخله.")
        with st.expander("الدوال الموجودة في الملف"):
            names = [n for n in dir(mod) if not n.startswith("_")]
            st.write(names)
        st.info("✅ افتح ملف ai_tab.py وشوف اسم الدالة الأساسية للعرض.")
        return

    # نبني kwargs ونعطي الدالة حسب توقيعها
    kwargs = {
        "symbol": symbol,
        "fin": fin,
        "company_name": company_name,
        "sector": sector,
        **(extra_kwargs or {}),
    }

    try:
        return _call_signature_aware(fn, **kwargs)
    except Exception as e:
        st.error("تعذر تشغيل واجهة AI رغم العثور على الدالة.")
        st.write(str(e))
        with st.expander("تشخيص"):
            st.write("Imported module:", mod_name)
            st.write("Chosen function:", getattr(fn, "__name__", "unknown"))
            try:
                st.write("Signature:", str(inspect.signature(fn)))
            except Exception:
                pass
        return
