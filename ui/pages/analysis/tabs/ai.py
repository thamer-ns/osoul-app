# ui/pages/analysis/tabs/ai.py
import importlib
import inspect
from typing import Any, Callable, Optional, Tuple, List

import streamlit as st


# =========================
# 1) Import by module path
# =========================
CANDIDATE_MODULES: List[str] = [
    "ui.pages.analysis.ai.ai_tab",
    "ui.pages.analysis.ai_tab",
    "ui.pages.analysis.ai.main",
    # احتياط (بعض المشاريع يكون بدون ui.)
    "pages.analysis.ai.ai_tab",
    "pages.analysis.ai_tab",
]

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


# =========================
# 2) Import by file path (strong fallback)
# =========================
def _import_from_path() -> Tuple[Optional[Any], Optional[str], str]:
    """
    يحاول تحميل ai_tab.py مباشرة من المسار على القرص
    حتى لو كانت مشاكل packages/__init__.py
    """
    try:
        from pathlib import Path
        from importlib.machinery import SourceFileLoader
        from importlib.util import spec_from_loader, module_from_spec
    except Exception as e:
        return None, None, f"Path import prerequisites failed: {repr(e)}"

    errors = []

    try:
        # هذا الملف: .../ui/pages/analysis/tabs/ai.py
        here = Path(__file__).resolve()
        analysis_dir = here.parents[1]  # .../ui/pages/analysis
        cand_files = [
            analysis_dir / "ai" / "ai_tab.py",
            analysis_dir / "ai_tab.py",
        ]

        for fpath in cand_files:
            try:
                if not fpath.exists():
                    errors.append(f"{str(fpath)}: NOT FOUND")
                    continue

                module_name = f"_legacy_ai_tab_{fpath.stem}_{abs(hash(str(fpath)))}"
                loader = SourceFileLoader(module_name, str(fpath))
                spec = spec_from_loader(module_name, loader)
                if spec is None:
                    errors.append(f"{str(fpath)}: spec is None")
                    continue

                mod = module_from_spec(spec)
                loader.exec_module(mod)
                return mod, str(fpath), ""
            except Exception as e:
                errors.append(f"{str(fpath)}: {repr(e)}")

    except Exception as e:
        errors.append(f"Path resolve failed: {repr(e)}")

    return None, None, "\n".join(errors)


def _find_callable(mod: Any) -> Optional[Callable]:
    # 1) جرّب الأسماء المتوقعة
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
    ينادي الدالة حسب توقيعها:
    - إذا فيها **kwargs => نعطيها كل شيء
    - وإلا نعطيها فقط المفاتيح الموجودة في التوقيع
    """
    try:
        sig = inspect.signature(fn)
        params = sig.parameters

        # إذا تقبل **kwargs
        for p in params.values():
            if p.kind == inspect.Parameter.VAR_KEYWORD:
                return fn(**kwargs)

        filtered = {k: v for k, v in kwargs.items() if k in params}
        return fn(**filtered)

    except TypeError as e:
        # fallback: طرق شائعة
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
    ✅ entry point الذي page.py يتوقعه
    """
    # أولاً: محاولة import بالمسار
    mod, mod_name, import_errors = _import_first_available()

    # إذا فشل: حمّل من المسار على القرص
    if not mod:
        mod, mod_name, path_errors = _import_from_path()
        if not mod:
            st.error("تعذر تحميل واجهة AI: لم أستطع استيراد أي مسار متوقع أو تحميل الملف من المسار.")
            with st.expander("تفاصيل محاولات الاستيراد (module paths)"):
                st.code(import_errors or "No details", language="text")
            with st.expander("تفاصيل محاولات التحميل من المسار (file paths)"):
                st.code(path_errors or "No details", language="text")
            st.info(
                "✅ المطلوب الآن:\n"
                "1) افتح expander اللي فوق وانسخ لي أول سطر Error واضح (غالبًا SyntaxError/ImportError)\n"
                "2) أو ارسل محتوى الملف الموجود فعليًا:\n"
                "- ui/pages/analysis/ai/ai_tab.py أو ui/pages/analysis/ai_tab.py"
            )
            return

    fn = _find_callable(mod)
    if not fn:
        st.error(f"تم تحميل ملف AI بنجاح ({mod_name}) لكن لم أجد دالة عرض مناسبة داخله.")
        with st.expander("الدوال الموجودة في الملف"):
            names = [n for n in dir(mod) if not n.startswith("_")]
            st.write(names)
        st.info("✅ افتح ai_tab.py وارسلي اسم الدالة الأساسية حق العرض (أو ارسل الملف كامل وأنا أضبطه).")
        return

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
            st.write("Loaded from:", mod_name)
            st.write("Chosen function:", getattr(fn, "__name__", "unknown"))
            try:
                st.write("Signature:", str(inspect.signature(fn)))
            except Exception:
                pass
        return
