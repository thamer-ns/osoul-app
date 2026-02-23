# views/navbar.py
import base64
from pathlib import Path
from typing import Optional

import streamlit as st


def _logo_data_uri(rel_path: str = 'assets/logo_mark.png') -> str:
    """Inline logo as data URI (works on Streamlit Cloud)."""
    p = Path(rel_path)
    if not p.exists():
        return ''
    try:
        b64 = base64.b64encode(p.read_bytes()).decode('utf-8')
        return f'data:image/png;base64,{b64}'
    except Exception:
        return ''


# =========================================================
# ✅ هذه المفاتيح MUST تطابق الراوتر في views/__init__.py
# =========================================================
NAV_MAIN = [
    ('الرئيسية', 'home'),
    ('التحليل', 'analysis'),
    ('محفظة المضاربة', 'spec'),
    ('محفظة الاستثمار', 'invest'),
    ('الإعدادات', 'settings'),
]

NAV_MORE = [
    ('الصكوك', 'sukuk'),
    ('سجل الكاش', 'cash'),
    ('الاختبار الخلفي', 'backtest'),
    ('نبض المحفظة', 'pulse'),
    ('الإشارات', 'signals'),
    ('إضافة صفقة', 'add'),
    ('أدوات', 'tools'),
    ('تحديث الأسعار', 'update'),
]

_ALLOWED = {k for _, k in (NAV_MAIN + NAV_MORE)}


def _safe_get_query_page() -> Optional[str]:
    """Read st.query_params['page'] safely across Streamlit versions."""
    try:
        qp = st.query_params
        val = qp.get('page', None)
        if isinstance(val, list):
            val = val[0] if val else None
        if val is None:
            return None
        val = str(val).strip().lower()
        return val if val in _ALLOWED else None
    except Exception:
        try:
            qp = st.experimental_get_query_params()
            val = qp.get('page', [None])
            val = val[0] if isinstance(val, list) else val
            if val is None:
                return None
            val = str(val).strip().lower()
            return val if val in _ALLOWED else None
        except Exception:
            return None


def _safe_set_query_page(page: str):
    """Set query param if supported (new/old Streamlit)."""
    try:
        st.query_params['page'] = page
        return
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at views/navbar.py:75')
    try:
        st.experimental_set_query_params(page=page)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at views/navbar.py:79')


def sync_page_from_query_params_once():
    """Sync deep-link ?page=... to session_state exactly once."""
    if st.session_state.get('_synced_page_from_qp_once'):
        return

    st.session_state['_synced_page_from_qp_once'] = True

    qp_page = _safe_get_query_page()
    if qp_page and ('page' not in st.session_state):
        st.session_state['page'] = qp_page
    elif qp_page and st.session_state.get('page') != qp_page:
        st.session_state['page'] = qp_page


def _go(page_key: str):
    """Navigate reliably: session_state + query params + rerun."""
    if page_key not in _ALLOWED:
        page_key = 'home'

    st.session_state['page'] = page_key
    _safe_set_query_page(page_key)
    st.rerun()


def render_navbar():
    """Navbar متوافق مع الراوتر الحالي ويحافظ على التصميم السابق."""
    sync_page_from_query_params_once()

    if 'page' not in st.session_state:
        st.session_state['page'] = 'home'

    current = st.session_state.get('page', 'home')
    if current not in _ALLOWED:
        current = 'home'
        st.session_state['page'] = 'home'

    # -------------------------------
    # Main nav row (التصميم السابق)
    # -------------------------------
    cols = st.columns(len(NAV_MAIN))
    for i, (label, key) in enumerate(NAV_MAIN):
        is_active = (key == current)
        text = f'✅ {label}' if is_active else label
        if cols[i].button(text, use_container_width=True, key=f'nav_main_{key}'):
            _go(key)

    # -------------------------------
    # More nav (اختياري)
    # -------------------------------
    with st.expander('المزيد', expanded=False):
        cols2 = st.columns(4)
        for idx, (label, key) in enumerate(NAV_MORE):
            c = cols2[idx % 4]
            is_active = (key == current)
            text = f'✅ {label}' if is_active else label
            if c.button(text, use_container_width=True, key=f'nav_more_{key}'):
                _go(key)
