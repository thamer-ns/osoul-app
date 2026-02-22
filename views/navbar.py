import streamlit as st

# ✅ مفاتيح الصفحات كما في views/__init__.py (router)
NAV_MAIN = [
    ("الرئيسية", "home"),
    ("محفظة المضاربة", "spec"),
    ("محفظة الاستثمار", "invest"),
    ("الصكوك", "sukuk"),
    ("التحليل", "analysis"),
    ("الاختبار الخلفي", "backtest"),
]
NAV_MORE = [
    ("نبض المحفظة", "pulse"),
    ("الإشارات", "signals"),
    ("سجل الكاش", "cash"),
    ("إضافة صفقة", "add"),
    ("أدوات", "tools"),
    ("الإعدادات", "settings"),
    ("تحديث الأسعار", "update"),
]

_ALLOWED = {k for _, k in NAV_MAIN + NAV_MORE}

_ICONS = {
    "home": "🏠",
    "spec": "⚡",
    "invest": "💼",
    "sukuk": "🕌",
    "analysis": "📊",
    "backtest": "🧪",
    "pulse": "💓",
    "signals": "⚡",
    "cash": "💵",
    "add": "➕",
    "tools": "🧰",
    "settings": "⚙️",
    "update": "🔄",
}


def _safe_set_query_page(page_key: str):
    """حفظ الصفحة في query params (يدعم Streamlit الجديد/القديم)."""
    try:
        st.query_params["page"] = page_key
    except Exception:
        try:
            st.experimental_set_query_params(page=page_key)
        except Exception:
            pass


def _safe_get_query_page():
    """قراءة الصفحة من query params (يدعم Streamlit الجديد/القديم)."""
    try:
        qp = st.query_params
        v = qp.get("page")
        if isinstance(v, list):
            v = v[0] if v else None
        return v
    except Exception:
        try:
            qp = st.experimental_get_query_params()
            v = qp.get("page", [None])
            return v[0] if isinstance(v, list) else v
        except Exception:
            return None


def sync_page_from_query_params_once():
    """Sync page from query params once on session start."""
    if st.session_state.get("_synced_qp_once"):
        return
    st.session_state["_synced_qp_once"] = True

    qp_page = _safe_get_query_page()
    if qp_page in _ALLOWED:
        st.session_state["page"] = qp_page


def _go(page_key: str):
    """Update session_state + query params + rerun."""
    if page_key not in _ALLOWED:
        page_key = "home"

    st.session_state["page"] = page_key
    _safe_set_query_page(page_key)
    st.rerun()


def _format_label(key: str) -> str:
    icon = _ICONS.get(key, "•")
    label = next((lbl for lbl, k in NAV_MAIN + NAV_MORE if k == key), key)
    return f"{icon} {label}"


def render_navbar():
    """
    ✅ تنقّل ثابت عبر Sidebar (يمين الشاشة) + طي/فتح طبيعي من Streamlit
    يحل: عدم ظهور القائمة / عدم القدرة على تغيير الصفحات.
    """
    sync_page_from_query_params_once()

    if "page" not in st.session_state:
        st.session_state["page"] = "home"

    current = st.session_state.get("page", "home")
    if current not in _ALLOWED:
        current = "home"
        st.session_state["page"] = "home"

    keys = [k for _, k in NAV_MAIN + NAV_MORE]
    if current not in keys:
        current = "home"

    with st.sidebar:
        st.markdown("### 🧭 القائمة")

        chosen = st.radio(
            "تنقّل",
            options=keys,
            index=keys.index(current),
            format_func=_format_label,
            key="nav_page",
            label_visibility="collapsed",
        )

        st.divider()
        st.caption("أصولي • منصة الذكاء الكمي للأسواق")

    if chosen != current:
        _go(chosen)
