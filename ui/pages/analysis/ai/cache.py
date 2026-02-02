# ui/pages/analysis/ai/cache.py
import streamlit as st


def _cache() -> dict:
    return st.session_state.setdefault("_ai_rep_cache", {})


def make_key(symbol: str, tf: str) -> str:
    s = (symbol or "").strip()
    t = (tf or "").strip()
    return f"{s}|{t}"


def get(symbol: str, tf: str):
    c = _cache()
    return c.get(make_key(symbol, tf))


def set(symbol: str, tf: str, rep):
    c = _cache()
    c[make_key(symbol, tf)] = rep
    st.session_state["_ai_rep_cache"] = c


def clear_symbol(symbol: str):
    c = _cache()
    prefix = f"{(symbol or '').strip()}|"
    for k in list(c.keys()):
        if k.startswith(prefix):
            del c[k]
    st.session_state["_ai_rep_cache"] = c


def get_or_generate(symbol: str, tf: str, generator_fn, spinner_text: str = "جاري توليد تقرير المستشار..."):
    """
    Uses session cache unless:
      - missing
      - or generated rep is an error dict containing __error__ or __trace__ (then don't cache)
    """
    cached = get(symbol, tf)
    if cached is not None:
        return cached

    with st.spinner(spinner_text):
        rep = generator_fn()

    # لا نخزن تقارير الخطأ
    if isinstance(rep, dict) and (rep.get("__error__") or rep.get("__trace__")):
        return rep

    set(symbol, tf, rep)
    return rep
