
#security.py
import streamlit as st
import extra_streamlit_components as stx
import datetime
import time
import re

from database import db_verify_user, db_create_user, fetch_table
from config import APP_NAME, APP_ICON


# ============================================================
# 1) Validation Helpers
# ============================================================

def validate_trade_inputs(quantity, price):
    try:
        q = float(quantity)
        p = float(price)
    except Exception:
        return False, "الرجاء إدخال أرقام صحيحة"
    if q <= 0 or p <= 0:
        return False, "القيم يجب أن تكون أكبر من صفر"
    return True, ""


def _validate_username(u: str):
    """
    قواعد بسيطة:
    - 3 إلى 30 حرف
    - أحرف/أرقام/._-
    """
    u = (u or "").strip()
    if len(u) < 3:
        return False, "اسم المستخدم قصير جداً"
    if len(u) > 30:
        return False, "اسم المستخدم طويل جداً"
    if not re.match(r"^[A-Za-z0-9._-]+$", u):
        return False, "اسم المستخدم يسمح فقط بـ: أحرف/أرقام/._-"
    return True, ""


def _validate_password(p: str):
    p = (p or "")
    if len(p) < 6:
        return False, "كلمة المرور قصيرة جداً (6 أحرف على الأقل)"
    return True, ""


def _user_exists_in_db(username: str) -> bool:
    """
    تحقق سريع (بدون كسر لو الجدول غير موجود).
    """
    try:
        df = fetch_table("users")  # database.py يعالج case
        if df is None or df.empty or "username" not in df.columns:
            return False
        return (df["username"].astype(str) == str(username)).any()
    except Exception:
        return False


# ============================================================
# 2) Cookie Manager
# ============================================================

def get_manager():
    if "_cookie_manager" not in st.session_state:
        st.session_state._cookie_manager = stx.CookieManager(key="osoul_auth_manager")
    return st.session_state._cookie_manager


def _get_cookie_user(cookie_manager):
    """
    بعض بيئات Streamlit تحتاج rerun قبل ما تكون الكوكي جاهزة.
    بدل sleep، نجرب قراءة فورية وإذا ما نجحت نكمل طبيعي.
    """
    try:
        return cookie_manager.get("osoul_user")
    except Exception:
        return None


# ============================================================
# 3) Rate limiting (session only)
# ============================================================

def _rate_limit_ok():
    """
    يمنع محاولات كثيرة خلال وقت قصير:
    - 5 محاولات خلال 60 ثانية -> قفل مؤقت 30 ثانية
    """
    now = time.time()
    s = st.session_state

    attempts = s.get("_login_attempts", [])
    attempts = [t for t in attempts if now - t < 60]
    s["_login_attempts"] = attempts

    locked_until = s.get("_login_locked_until", 0.0)
    if now < locked_until:
        remaining = int(locked_until - now)
        return False, f"محاولات كثيرة. انتظر {remaining} ثانية."

    if len(attempts) >= 5:
        s["_login_locked_until"] = now + 30
        return False, "محاولات كثيرة. تم القفل مؤقتاً 30 ثانية."

    return True, ""


def _register_login_attempt():
    s = st.session_state
    attempts = s.get("_login_attempts", [])
    attempts.append(time.time())
    s["_login_attempts"] = attempts


# ============================================================
# 4) Login System (used by app.py)
# ============================================================

def login_system():
    # 1) Session check
    if st.session_state.get("username") and st.session_state.get("authenticated") is True:
        return True

    # 2) Cookie check
    cookie_manager = get_manager()
    cookie_user = _get_cookie_user(cookie_manager)

    if cookie_user:
        # ✅ تحقق من وجود المستخدم بالـDB (يمنع كوكي قديمة/غير صالحة)
        if _user_exists_in_db(cookie_user):
            st.session_state.username = cookie_user
            st.session_state["authenticated"] = True
            return True
        else:
            # كوكي قديمة: احذفها
            try:
                cookie_manager.delete("osoul_user")
            except Exception:
                pass

    # 3) Show Login UI
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(
            f"<h1 style='text-align:center;color:#0052CC'>{APP_ICON} {APP_NAME}</h1>",
            unsafe_allow_html=True
        )

        t1, t2 = st.tabs(["🔒 دخول", "👤 تسجيل"])

        # ---------------------
        # Login Tab
        # ---------------------
        with t1:
            with st.form("login_form"):
                u = st.text_input("المستخدم", key="login_user")
                p = st.text_input("كلمة المرور", type="password", key="login_pass")
                rem = st.checkbox("تذكرني", value=True)

                if st.form_submit_button("دخول", type="primary"):
                    ok, msg = _rate_limit_ok()
                    if not ok:
                        st.error(msg)
                        return False

                    u = (u or "").strip()
                    p = (p or "")

                    if not u or not p:
                        st.error("أدخل اسم المستخدم وكلمة المرور.")
                        _register_login_attempt()
                        return False

                    # ✅ تحقق
                    if db_verify_user(u, p):
                        st.session_state.username = u
                        st.session_state["authenticated"] = True

                        if rem:
                            expires = datetime.datetime.now() + datetime.timedelta(days=30)
                            try:
                                cookie_manager.set("osoul_user", u, expires_at=expires)
                            except Exception:
                                pass

                        st.success("تم الدخول")
                        st.rerun()
                    else:
                        st.error("خطأ في البيانات")
                        _register_login_attempt()

        # ---------------------
        # Signup Tab
        # ---------------------
        with t2:
            with st.form("signup_form"):
                nu = st.text_input("مستخدم جديد", key="signup_user")
                npw = st.text_input("كلمة مرور جديدة", type="password", key="signup_pass")

                if st.form_submit_button("إنشاء"):
                    nu = (nu or "").strip()
                    npw = (npw or "")

                    ok_u, msg_u = _validate_username(nu)
                    if not ok_u:
                        st.error(msg_u)
                        return False

                    ok_p, msg_p = _validate_password(npw)
                    if not ok_p:
                        st.error(msg_p)
                        return False

                    # ✅ لا تسمح بتسجيل نفس المستخدم
                    if _user_exists_in_db(nu):
                        st.error("اسم المستخدم موجود مسبقاً.")
                        return False

                    if db_create_user(nu, npw):
                        st.success("تم الإنشاء! سجل دخولك الآن.")
                    else:
                        st.error("حدث خطأ أثناء إنشاء المستخدم.")

    return False


# ============================================================
# 5) Logout
# ============================================================

def logout():
    try:
        get_manager().delete("osoul_user")
    except Exception:
        pass

    # ✅ لا تمسح كل شيء، فقط مفاتيح الدخول
    for k in ["username", "authenticated", "_login_attempts", "_login_locked_until"]:
        if k in st.session_state:
            del st.session_state[k]

    st.rerun()