# views/navbar.py
import streamlit as st

# =========================================================
# ✅ هذه المفاتيح MUST تطابق الراوتر في views/__init__.py
# =========================================================
NAV_MAIN = [
    ("الرئيسية", "home"),
    ("تحليل", "analysis"),
    ("محفظة مضاربة", "spec"),
    ("محفظة استثمار", "invest"),
    ("الإعدادات", "settings"),
]

NAV_MORE = [
    ("الصكوك", "sukuk"),
    ("الكاش", "cash"),
    ("باك تست", "backtest"),
    ("نبض", "pulse"),
    ("إضافة عملية", "add"),
    ("أدوات", "tools"),
    ("تحديث الأسعار", "update"),
]

# كل المفاتيح المسموحة
_ALLOWED = {k for _, k in (NAV_MAIN + NAV_MORE)}


def _safe_get_query_page() -> str | None:
    """
    Read st.query_params.get('page') safely across Streamlit versions.
    Returns None if unavailable.
    """
    try:
        qp = st.query_params
        val = qp.get("page", None)
        if isinstance(val, list):
            val = val[0] if val else None
        if val is None:
            return None
        val = str(val).strip().lower()
        return val if val in _ALLOWED else None
    except Exception:
        return None


def _safe_set_query_page(page: str):
    """Set query param if supported."""
    try:
        st.query_params["page"] = page
    except Exception:
        pass


def sync_page_from_query_params_once():
    """
    ✅ مهم:
    - إذا المستخدم فتح رابط فيه ?page=analysis مثلًا
    - نخلي الراوتر يشوفها بتحويلها إلى st.session_state.page
    - ننفّذ مرة واحدة فقط حتى ما نخرب التنقل الداخلي
    """
    if st.session_state.get("_synced_page_from_qp_once"):
        return

    st.session_state["_synced_page_from_qp_once"] = True

    qp_page = _safe_get_query_page()
    if qp_page and ("page" not in st.session_state):
        st.session_state["page"] = qp_page
    elif qp_page and st.session_state.get("page") != qp_page:
        # إذا الرابط فيه صفحة مختلفة عن الحالية -> اعتمد الرابط
        st.session_state["page"] = qp_page


def _go(page_key: str):
    """Navigate reliably: session_state + query params + rerun."""
    if page_key not in _ALLOWED:
        page_key = "home"

    st.session_state["page"] = page_key
    _safe_set_query_page(page_key)
    st.rerun()


def render_navbar():
    """
    Navbar متوافق 100% مع الراوتر الحالي في views/__init__.py
    بدون تعديل أي ملف آخر.
    """
    # ✅ مزامنة اختيارية من query params -> session_state
    sync_page_from_query_params_once()

    # ✅ ضمان وجود page
    if "page" not in st.session_state:
        st.session_state["page"] = "home"

    current = st.session_state.get("page", "home")
    if current not in _ALLOWED:
        current = "home"
        st.session_state["page"] = "home"

    # -------------------------------
    # Brand header (خفيف)
    # -------------------------------
    st.markdown(
        """
        <div style="
            position: sticky; top: 0; z-index: 999;
            background: #ffffffcc;
            backdrop-filter: blur(8px);
            border-bottom: 1px solid rgba(15,23,42,0.10);
            padding: 10px 0 12px 0;
            margin: -10px 0 12px 0;
        ">
          <div style="max-width:1280px;margin:0 auto;padding:0 18px;display:flex;align-items:center;gap:10px;">
            <div style="
                width:36px;height:36px;border-radius:12px;
                background: linear-gradient(135deg,#0B57D0,#059669);
                box-shadow: 0 10px 25px rgba(15,23,42,0.10);
            "></div>
            <div>
              <div style="font-weight:900;font-size:16px;line-height:1;">أصولي</div>
              <div style="font-size:12px;color:#64748B;font-weight:800;line-height:1.1;">لوحة التحليل والاستثمار</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------------
    # Main nav row
    # -------------------------------
    cols = st.columns(len(NAV_MAIN))
    for i, (label, key) in enumerate(NAV_MAIN):
        is_active = (key == current)
        text = f"✅ {label}" if is_active else label
        if cols[i].button(text, use_container_width=True, key=f"nav_main_{key}"):
            _go(key)

    # -------------------------------
    # More nav (اختياري)
    # -------------------------------
    with st.expander("المزيد", expanded=False):
        cols2 = st.columns(4)
        for idx, (label, key) in enumerate(NAV_MORE):
            c = cols2[idx % 4]
            is_active = (key == current)
            text = f"✅ {label}" if is_active else label
            if c.button(text, use_container_width=True, key=f"nav_more_{key}"):
                _go(key)
