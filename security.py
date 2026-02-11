# security.py
import datetime
import os
import re
import time
import hmac
import hashlib
import base64

import extra_streamlit_components as stx
import streamlit as st

from config import APP_ICON, APP_NAME
from database import db_create_user, db_verify_user, db_user_exists, fetch_table

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
    if len(p) < 8:
        return False, "كلمة المرور يجب أن تكون 8 أحرف على الأقل"
    # حد أدنى من التعقيد: حرف + رقم (بدون تعقيد مزعج)
    if not re.search(r"[A-Za-z]", p) or not re.search(r"\d", p):
        return False, "كلمة المرور يجب أن تحتوي على حرف ورقم على الأقل"
    return True, ""


def _user_exists_in_db(username: str):
    """Return True/False if known, or None if DB error."""
    try:
        exists = db_user_exists(username)
        if exists is not None:
            return bool(exists)
        df = fetch_table("users")
        if df is None or df.empty or "username" not in df.columns:
            return False
        return (df["username"].astype(str) == str(username)).any()
    except Exception:
        return None


# ============================================================
# 2) Cookie Manager
# ============================================================


def get_manager():
    if "_cookie_manager" not in st.session_state:
        # مهم: key ثابت حتى لا تتغير الكوكي عند rerun
        st.session_state._cookie_manager = stx.CookieManager(key="osoul_auth_manager")
    return st.session_state._cookie_manager


def _get_cookie_user(cookie_manager):
    try:
        return cookie_manager.get("osoul_user")
    except Exception:
        return None


# ============================================================
# ✅ 2.5) Auth Bootstrap (حل إعادة تسجيل الدخول عند تحديث الصفحة)
# ============================================================



# ============================================================
# 2.5) Signed Auth Token (HMAC) for stable login across refresh
# ============================================================

def _get_auth_secret() -> str:
    """Prefer st.secrets['AUTH_SECRET'] or env AUTH_SECRET.

    In production, you SHOULD set a stable secret (Streamlit secrets or env).
    If missing, we generate a per-server-run random secret (safer than a static fallback).
    """
    try:
        s = st.secrets.get("AUTH_SECRET")  # type: ignore[attr-defined]
        if s:
            return str(s)
    except Exception:
        pass

    s = os.environ.get("AUTH_SECRET", "")
    if s:
        return s

    # Dev fallback:
    # نستخدم مفتاحاً ثابتاً على مستوى *السيرفر process* (وليس session_state)
    # حتى لا تنكسر التوكن عند Refresh (Refresh ينشئ session جديدة).
    global _PROCESS_DEV_AUTH_SECRET  # type: ignore[name-defined]
    try:
        _PROCESS_DEV_AUTH_SECRET
    except Exception:
        _PROCESS_DEV_AUTH_SECRET = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8").rstrip("=")

    # تحذير مرة واحدة لكل جلسة
    if not st.session_state.get("_warned_missing_auth_secret"):
        st.session_state["_warned_missing_auth_secret"] = True
        try:
            st.warning(
                "تنبيه: AUTH_SECRET غير مضبوط. تم استخدام مفتاح مؤقت للتطوير (ستُسجَّل الخروج عند إعادة تشغيل السيرفر فقط)."
            )
        except Exception:
            pass

    return str(_PROCESS_DEV_AUTH_SECRET)


def _sign(payload: str) -> str:
    key = _get_auth_secret().encode("utf-8")
    sig = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")


def _make_auth_token(username: str, ttl_days: int = 30) -> str:
    u = (username or "").strip()
    exp = int(time.time()) + int(ttl_days * 86400)

    # v2: base64-encode username to avoid delimiter issues (e.g., dot in username)
    u_b64 = base64.urlsafe_b64encode(u.encode("utf-8")).decode("utf-8").rstrip("=")
    payload = f"v2.{u_b64}.{exp}"
    sig = _sign(payload)
    return f"{payload}.{sig}"


def _verify_auth_token(token: str) -> str | None:
    try:
        parts = (token or "").split(".")
        if len(parts) < 4:
            return None

        ver = parts[0]

        # v2: v2.<u_b64>.<exp>.<sig>
        if ver == "v2":
            if len(parts) != 4:
                return None
            _, u_b64, exp_s, sig = parts
            exp = int(exp_s)
            if time.time() > exp:
                return None
            payload = f"v2.{u_b64}.{exp}"
            expected = _sign(payload)
            if not hmac.compare_digest(expected, sig):
                return None
            pad = "=" * (-len(u_b64) % 4)
            return base64.urlsafe_b64decode(u_b64 + pad).decode("utf-8")

        # v1 (legacy): v1.<username_with_possible_dots>.<exp>.<sig>
        if ver == "v1":
            if len(parts) < 4:
                return None
            sig = parts[-1]
            exp_s = parts[-2]
            u = ".".join(parts[1:-2])
            exp = int(exp_s)
            if time.time() > exp:
                return None
            payload = f"v1.{u}.{exp}"
            expected = _sign(payload)
            return u if hmac.compare_digest(expected, sig) else None

        return None
    except Exception:
        return None


def _bootstrap_auth_from_cookie():
    """
    الهدف:
    - بعض بيئات Streamlit/مكوّن الكوكي قد يرجع None أو "" في أول تشغيل/أول rerun (الكوكي غير جاهزة بعد).
    - هذا يسبب ظهور شاشة الدخول بعد Refresh حتى لو كانت الكوكي موجودة.
    الحل:
    - قراءة (osoul_auth) + (osoul_user) مع تطبيع القيم.
    - إعطاء 1–2 rerun فقط عند غياب القيم (أو كانت ""/null) ثم إيقاف المحاولة لتجنب حلقة لا نهائية.
    """
    s = st.session_state

    # إذا سبق تفعيل جلسة صحيحة لا نلمسها
    if s.get("authenticated") is True and s.get("username"):
        s["_auth_bootstrapped"] = True
        return

    # نفّذ bootstrap مرة واحدة (أو مرتين عند الحاجة للكوكي)
    if s.get("_auth_bootstrapped") is True:
        return

    tries = int(s.get("_auth_bootstrap_tries", 0))
    cm = get_manager()

    def _norm(v):
        if v is None:
            return None
        v = str(v).strip()
        if v == "" or v.lower() in {"none", "null", "undefined"}:
            return None
        return v

    cookie_user = _norm(_get_cookie_user(cm))

    # ✅ أولاً: توكن موقّع (لا يعتمد على DB)
    # ملاحظة: النسخ الجديدة تكتب osoul_auth_v2 بينما بعض النسخ القديمة تكتب osoul_auth
    cookie_token = None
    for key in ("osoul_auth_v2", "osoul_auth"):
        try:
            cookie_token = _norm(cm.get(key))
        except Exception:
            cookie_token = None
        if cookie_token:
            break

    if cookie_token:
        u = _verify_auth_token(cookie_token)
        if u:
            s["username"] = u
            s["authenticated"] = True
            s["_auth_bootstrapped"] = True
            return

    # توافق رجعي: كوكي اسم المستخدم القديمة (يتطلب تحقق من وجود المستخدم)
    if cookie_user:
        exists = _user_exists_in_db(cookie_user)
        if exists is True:
            s["username"] = cookie_user
            s["authenticated"] = True
            s["_auth_bootstrapped"] = True
            return
        elif exists is False:
            # كوكي قديمة/غير صالحة: احذفها
            try:
                cm.delete("osoul_user")
            except Exception:
                pass
        else:
            # DB غير متاح مؤقتاً: لا نحذف الكوكي ولا نكرر محاولة مزعجة
            s["_auth_bootstrapped"] = True
            return

    # إذا الكوكي غير جاهزة بعد (None/"") أعط محاولة rerun إضافية (بحد أقصى مرتين)
    if (cookie_token is None and cookie_user is None) and tries < 2:
        s["_auth_bootstrap_tries"] = tries + 1
        st.rerun()

    # بعدها نثبت أنها bootstrapped حتى لا نعيد نفس الدوامة
    s["_auth_bootstrapped"] = True


# ============================================================
# 3) Rate limiting (session only)
# ============================================================


def _rate_limit_ok():
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
    # ✅ bootstrap cookies once (prevents relogin on refresh)
    _bootstrap_auth_from_cookie()

    # 1) Session check
    if st.session_state.get("username") and st.session_state.get("authenticated") is True:
        return True

    # 2) Show Login UI
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        # ✅ لا نطبع مسار الصورة كنص داخل العنوان (كان يظهر مثل: mount/src/...png)
        _icon_path = APP_ICON if isinstance(APP_ICON, str) else ""
        if _icon_path and _icon_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) and os.path.exists(_icon_path):
            st.image(_icon_path, width=90)
            st.markdown(
                f"<h1 style='text-align:center;color:#0052CC;margin-top:-10px'>{APP_NAME}</h1>",
                unsafe_allow_html=True,
            )
            st.caption("Auth v3")
        else:
            # إذا كان APP_ICON إيموجي أو نص قصير
            st.markdown(
                f"<h1 style='text-align:center;color:#0052CC'>{APP_ICON} {APP_NAME}</h1>",
                unsafe_allow_html=True,
            )
            st.caption("Auth v3")

        t1, t2 = st.tabs(["🔒 دخول", "👤 تسجيل"])

        # ---------------------
        # Login Tab
        # ---------------------
        with t1:
            with st.form("login_form"):
                u = st.text_input("المستخدم", key="login_user")
                p = st.text_input("كلمة المرور", type="password", key="login_pass")
                rem = st.checkbox("تذكرني", value=True, key="remember_me")

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

                    if db_verify_user(u, p):
                        st.session_state["username"] = u
                        st.session_state["authenticated"] = True

                        # ✅ حفظ الجلسة عبر الكوكي:
                        # - إذا "تذكرني" مفعّل: كوكي 30 يوم
                        # - إذا غير مفعّل: Session cookie (تبقى بعد Refresh وتختفي عند إغلاق المتصفح)
                        try:
                            expires = None
                            if rem:
                                expires = datetime.datetime.now() + datetime.timedelta(days=30)
                            token = _make_auth_token(u)
                            cm = get_manager()
                            cm.set("osoul_auth_v2", token, expires_at=expires)
                            # ✅ توافق رجعي + ضمان bootstrap حتى لو نسخة قديمة تقرأ osoul_auth
                            cm.set("osoul_auth", token, expires_at=expires)
                            # legacy cookies kept for reading only
                            # توافق رجعي: الاسم القديم
                            cm.set("osoul_user", u, expires_at=expires)
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
        get_manager().delete("osoul_auth_v2")
        get_manager().delete("osoul_auth")  # legacy
    except Exception:
        pass

    # ✅ لا تمسح كل شيء، فقط مفاتيح الدخول
    for k in [
        "username",
        "authenticated",
        "_login_attempts",
        "_login_locked_until",
        "_auth_bootstrapped",
        "_auth_bootstrap_tries",
    ]:
        if k in st.session_state:
            del st.session_state[k]

    st.rerun()
