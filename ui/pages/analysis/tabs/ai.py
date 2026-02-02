# ui/pages/analysis/tabs/ai.py
import streamlit as st
import importlib
import inspect
from typing import Any, Callable, Optional, Tuple, List


CANDIDATE_MODULES: List[str] = [
    # Old/legacy common paths (حسب اللي ظهر عندك بالهيكلة)
    "ui.pages.analysis.ai_tab",
    "ui.pages.analysis.ai.ai_tab",
    "ui.pages.analysis.ai.main",
    "ui.pages.analysis.ai",  # package (قد يكون فيه export)
]

CANDIDATE_FUNC_NAMES: List[str] = [
    # أكثر أسماء شائعة لدوال التبويب
    "render_tab",
    "view",
    "render",
    "render_ai_tab",
    "view_ai",
    "show",
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
    # 1) جرّب الأسماء المتوقعة
    for name in CANDIDATE_FUNC_NAMES:
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn

    # 2) fallback: أي دالة “واضحة” داخل الملف (غير خاصة)
    # نختار أول callable اسمها ما يبدأ بـ "_" وتقبل على الأقل وسيط واحد
    for name in dir(mod):
        if name.startswith("_"):
            continue
        obj = getattr(mod, name, None)
        if callable(obj):
            try:
                sig = inspect.signature(obj)
                if len(sig.parameters) >= 1:
                    return obj
            except Exception:
                return obj

    return None


def _call_flex(fn: Callable, symbol: str, fin: dict, company_name: str, sector: str):
    """
    ينادي دالة قديمة مهما كان توقيعها:
    - (symbol, fin, company_name=?, sector=?)
    - (symbol, fin)
    - (symbol)
    """
    # 1) جرّب التوقيع الكامل
    try:
        return fn(symbol, fin, company_name=company_name, sector=sector)
    except TypeError:
        pass
    except Exception as e:
        raise e

    # 2) جرّب بدون company/sector
    try:
        return fn(symbol, fin)
    except TypeError:
        pass
    except Exception as e:
        raise e

    # 3) جرّب symbol فقط
    try:
        return fn(symbol)
    except TypeError:
        pass
    except Exception as e:
        raise e

    # 4) إذا ما نجح أي شيء، اعرض معلومات
    raise TypeError("No compatible signature found for legacy AI tab function.")


def render_tab(symbol: str, fin: dict, company_name: str = "", sector: str = ""):
    """
    Bridge: يعرض نفس واجهة AI القديمة بدون تغيير UI.
    """
    mod, mod_name, import_errors = _import_first_available()

    if not mod:
        st.error("تعذر تحميل واجهة AI القديمة: لم أستطع استيراد أي مسار متوقع.")
        with st.expander("تفاصيل محاولات الاستيراد"):
            st.code(import_errors or "No details", language="text")
        st.info("✅ تأكد أن ملف ai_tab.py موجود بأحد هذه المسارات:\n- ui/pages/analysis/ai_tab.py\n- ui/pages/analysis/ai/ai_tab.py")
        return

    fn = _find_callable(mod)
    if not fn:
        st.error(f"تم استيراد الموديول بنجاح ({mod_name}) لكن لم أجد دالة عرض مناسبة داخله.")
        with st.expander("الدوال الموجودة في الملف"):
            names = [n for n in dir(mod) if not n.startswith("_")]
            st.write(names)
        st.info("✅ افتح ملف ai_tab.py وشوف اسم الدالة الأساسية حق العرض (مثل render_ai_tab أو render_tab...)")
        return

    try:
        return _call_flex(fn, symbol, fin, company_name, sector)
    except Exception as e:
        st.error("تعذر تشغيل واجهة AI القديمة رغم العثور على الدالة.")
        st.write(str(e))
        with st.expander("تشخيص"):
            st.write("Imported module:", mod_name)
            st.write("Chosen function:", getattr(fn, "__name__", "unknown"))
            try:
                st.write("Signature:", str(inspect.signature(fn)))
            except Exception:
                pass
        return
