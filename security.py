# security.py
import datetime
import os
import re
import time
import hmac
import hashlib
import base64
import textwrap

try:
    import extra_streamlit_components as stx  # type: ignore
    _HAS_COOKIE_MANAGER = True
except Exception:
    stx = None  # type: ignore
    _HAS_COOKIE_MANAGER = False

import streamlit as st

import config
from config import APP_ICON, APP_NAME, LOGO_FULL_PATH
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
    if not re.match(r"^[A-Za-z0-9_\-\.]+$", u):
        return False, "اسم المستخدم يجب أن يحتوي أحرف/أرقام/._- فقط"
    return True, ""


def _validate_password(password: str, mode: str = "login"):
    """Password policy.
    - login: accept legacy passwords/PINs without forcing new length.
    - register/change: prefer strong password (MIN_PASSWORD_LEN) or legacy numeric PIN (>=6) if enabled.
    """
    p = _norm(password)

    if len(p) < 1:
        return False, "أدخل كلمة المرور"
    if len(p) > 200:
        return False, "كلمة المرور طويلة جداً"

    allow_legacy = getattr(config, "ALLOW_LEGACY_PIN", True)

    if mode == "login":
        # لا نكسر الحسابات القديمة: نقبل كلمة المرور كما هي ثم نتحقق من الهاش في قاعدة البيانات
        return True, ""

    # register / change
    if allow_legacy and p.isdigit():
        if len(p) < 6:
            return False, "الرمز قصير جداً (6 أرقام على الأقل)"
        return True, ""

    min_len = int(getattr(config, "MIN_PASSWORD_LEN", 8) or 8)
    if len(p) < min_len:
        extra = " (أو استخدم PIN رقمي 6 أرقام للحسابات القديمة)" if allow_legacy else ""
        return False, f"كلمة المرور قصيرة جداً ({min_len} أحرف على الأقل){extra}"

    # توجيه بسيط لتحسين الأمان (بدون كسر المستخدمين)
    if not re.search(r"[A-Za-z]", p) or not re.search(r"\d", p):
        return False, "يفضّل أن تحتوي كلمة المرور على حروف وأرقام لزيادة الأمان"

    return True, ""
def _norm(s):
    return (s or "").strip()


# ============================================================
# 2) Cookie Manager (Defensive)
# ============================================================

def _get_cookie_manager():
    """
    Cookie manager is optional and can fail on some deployments.
    We keep everything defensive so the app never crashes.
    """
    if not _HAS_COOKIE_MANAGER:
        return None
    try:
        if "_cookie_manager" not in st.session_state:
            # key ثابت لتجنب مشاكل re-mounting
            st.session_state._cookie_manager = stx.CookieManager(key="osoul_auth_manager")
        return st.session_state._cookie_manager
    except Exception:
        return None


def _get_cookie_user(cookie_manager):
    try:
        if not cookie_manager:
            return None
        # بعض الإصدارات تغيرت تواقيعها؛ نستخدم keyword args لتفادي Mapping.get crash
        try:
            return cookie_manager.get(cookie="osoul_user")  # type: ignore
        except TypeError:
            return cookie_manager.get("osoul_user")  # type: ignore
    except Exception:
        return None


def _set_cookie(cookie_manager, key: str, value: str, days: int = 30):
    """
    Set cookie safely.
    - Uses unique widget keys to prevent Streamlit key collisions.
    - Uses keyword args where possible for compatibility.
    """
    if not cookie_manager:
        return False
    try:
        exp = datetime.datetime.utcnow() + datetime.timedelta(days=int(days))
        # extra_streamlit_components expects datetime in some versions
        try:
            cookie_manager.set(  # type: ignore
                cookie=key,
                val=value,
                expires_at=exp,
                key=f"ck_set_{key}_{int(time.time()*1000)}",
            )
        except TypeError:
            # fallback to positional signature
            cookie_manager.set(  # type: ignore
                key,
                value,
                exp,
                key=f"ck_set_{key}_{int(time.time()*1000)}",
            )
        return True
    except Exception:
        return False


def _delete_cookie(cookie_manager, key: str):
    if not cookie_manager:
        return False
    try:
        # delete via setting expired cookie
        past = datetime.datetime.utcnow() - datetime.timedelta(days=1)
        try:
            cookie_manager.set(  # type: ignore
                cookie=key,
                val="",
                expires_at=past,
                key=f"ck_del_{key}_{int(time.time()*1000)}",
            )
        except TypeError:
            cookie_manager.set(  # type: ignore
                key,
                "",
                past,
                key=f"ck_del_{key}_{int(time.time()*1000)}",
            )
        return True
    except Exception:
        return False


# ============================================================
# 3) Auth Token (Signed) for persistent login
# ============================================================

def _auth_secret() -> str:
    """
    Return the secret used to sign auth cookies.
    Order:
      1) st.secrets["AUTH_SECRET"]
      2) env AUTH_SECRET
      3) fallback (weak) - not recommended for production
    """
    s = None
    try:
        s = st.secrets.get("AUTH_SECRET", None)
    except Exception:
        s = None

    if not s:
        s = os.environ.get("AUTH_SECRET", "")

    # fallback (works but you should set a real secret)
    if not s:
        s = "OSOUL_DEFAULT_DEV_SECRET_CHANGE_ME"
    return str(s)


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64u_decode(s: str) -> bytes:
    s = (s or "").strip()
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))


def _sign(payload: str) -> str:
    key = _auth_secret().encode("utf-8")
    sig = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).digest()
    return _b64u(sig)


def _make_auth_token(username: str, days: int = 30) -> str:
    """
    Token format: v3.<exp_ts>.<username>.<sig>
    """
    exp = int(time.time() + int(days) * 86400)
    u = _norm(username)
    payload = f"v3.{exp}.{u}"
    sig = _sign(payload)
    return f"{payload}.{sig}"



def _verify_auth_token(token: str):
    """Verify signed auth token.

    Returns (username, exp_ts) if valid else None.
    Token format: v3.<exp>.<username>.<sig>
    """
    try:
        token = _norm(token)
        if not token:
            return None
        parts = token.split(".")
        if len(parts) != 4:
            return None
        ver, exp_s, username, sig = parts
        if ver != "v3":
            return None
        exp = int(exp_s)
        if exp <= int(time.time()):
            return None
        payload = f"{ver}.{exp}.{username}"
        good = _sign(payload)
        if not hmac.compare_digest(good, sig):
            return None
        u = _norm(username)
        if not u:
            return None
        return u, exp
    except Exception:
        return None



def _user_exists_in_db(username: str) -> bool:
    try:
        return bool(db_user_exists(username))
    except Exception:
        try:
            # fallback using table query
            df = fetch_table("users")
            if df is None or df.empty:
                return False
            return _norm(username) in set(df["username"].astype(str))
        except Exception:
            return False


# ============================================================
# 5) Session bootstrap from cookie
# ============================================================

def _bootstrap_auth_from_cookie():
    """
    Called once per page load to restore session from cookies when Remember me is enabled.
    Never crashes the app if cookies are broken/unavailable.
    """
    if st.session_state.get("_bootstrapped_auth", False):
        return
    st.session_state["_bootstrapped_auth"] = True

    cm = _get_cookie_manager()
    if not cm:
        return

    s = st.session_state
    if s.get("logged_in"):
        return

    cookie_user = _norm(_get_cookie_user(cm))
    cookie_token = None

    # try new token cookie first
    try:
        try:
            cookie_token = _norm(cm.get(cookie="osoul_auth_v2"))  # type: ignore
        except TypeError:
            cookie_token = _norm(cm.get("osoul_auth_v2"))  # type: ignore
    except Exception:
        cookie_token = None

    # fallback legacy cookie
    if not cookie_token:
        try:
            try:
                cookie_token = _norm(cm.get(cookie="osoul_auth"))  # type: ignore
            except TypeError:
                cookie_token = _norm(cm.get("osoul_auth"))  # type: ignore
        except Exception:
            cookie_token = None

    if cookie_token:
        ver = _verify_auth_token(cookie_token)
        if ver and _user_exists_in_db(ver[0]):
            u, exp = ver
            s["logged_in"] = True
            s["username"] = u
            s["auth_exp"] = int(exp)
            return

    if cookie_user:
        exists = _user_exists_in_db(cookie_user)
        if exists:
            s["logged_in"] = True
            s["username"] = cookie_user
            s["auth_exp"] = int(time.time()) + 4*3600
            return

    # if we have cookies but cannot validate, clear them (avoid loop)
    tries = int(s.get("_cookie_bootstrap_tries", 0))
    s["_cookie_bootstrap_tries"] = tries + 1
    if (cookie_token is None and cookie_user is None) and tries < 2:
        return
    _delete_cookie(cm, "osoul_user")
    _delete_cookie(cm, "osoul_auth")
    _delete_cookie(cm, "osoul_auth_v2")


# ============================================================
# 6) Public Auth API for UI
# ============================================================

def logout_user():
    st.session_state["logged_in"] = False
    st.session_state["username"] = None
    st.session_state.pop("auth_exp", None)
    st.session_state.pop("last_seen", None)

    cm = _get_cookie_manager()
    if cm:
        _delete_cookie(cm, "osoul_user")
        _delete_cookie(cm, "osoul_auth")
        _delete_cookie(cm, "osoul_auth_v2")

    st.success("✅ تم تسجيل الخروج")


def login_user(username: str, password: str, remember_me: bool = False, **kwargs):
    # Backward-compatible: callers may pass remember=<bool> instead of remember_me
    if 'remember' in kwargs and kwargs['remember'] is not None:
        remember_me = bool(kwargs['remember'])
    username = _norm(username)
    password = _norm(password)

    ok_u, msg_u = _validate_username(username)
    if not ok_u:
        return False, msg_u

    ok_p, msg_p = _validate_password(password, mode="login")
    if not ok_p:
        return False, msg_p

    try:
        ok = db_verify_user(username, password)
    except Exception:
        ok = False

    if not ok:
        return False, "❌ بيانات الدخول غير صحيحة"

    st.session_state["logged_in"] = True
    st.session_state["username"] = username

    cm = _get_cookie_manager()
    if cm:
        # Always set user cookie (session-level or persistent)
        # If remember_me -> persistent 30 days with signed token
        if remember_me:
            token = _make_auth_token(username, days=30)
            st.session_state["auth_exp"] = int(time.time()) + 30*86400
            _set_cookie(cm, "osoul_user", username, days=30)
            _set_cookie(cm, "osoul_auth_v2", token, days=30)
        else:
            # Session cookie (expires quickly, but still survives refresh)
            # Some browsers treat cookies without expires as session cookies.
            # We'll keep short expiry for stability.
            token = _make_auth_token(username, days=1)
            st.session_state["auth_exp"] = int(time.time()) + 1*86400
            _set_cookie(cm, "osoul_user", username, days=1)
            _set_cookie(cm, "osoul_auth_v2", token, days=1)

    return True, "✅ تم تسجيل الدخول بنجاح"


def register_user(username: str, password: str):
    username = _norm(username)
    password = _norm(password)

    ok_u, msg_u = _validate_username(username)
    if not ok_u:
        return False, msg_u

    ok_p, msg_p = _validate_password(password, mode="login")
    if not ok_p:
        return False, msg_p

    if _user_exists_in_db(username):
        return False, "❌ اسم المستخدم موجود مسبقاً"

    try:
        db_create_user(username, password)
        return True, "✅ تم إنشاء الحساب بنجاح"
    except Exception:
        return False, "❌ حدث خطأ أثناء إنشاء الحساب"


def require_login():
    """Ensure authentication before continuing.

    Returns True if authenticated, otherwise renders login/register UI and returns False.
    """
    _bootstrap_auth_from_cookie()

    from datetime import datetime, timedelta

    # ✅ session idle timeout
    if st.session_state.get("logged_in"):
        # ✅ hard token expiry (even if session is active)
        exp = st.session_state.get("auth_exp")
        if exp and int(time.time()) > int(exp):
            logout_user()
            st.warning("انتهت صلاحية الجلسة. الرجاء تسجيل الدخول مرة أخرى.")

        now = datetime.utcnow()
        last = st.session_state.get("last_seen")
        idle_minutes = int(getattr(config, "SESSION_IDLE_MINUTES", 120) or 120)
        if last and isinstance(last, datetime) and (now - last) > timedelta(minutes=idle_minutes):
            logout_user()
            st.warning("انتهت الجلسة بسبب عدم النشاط. الرجاء تسجيل الدخول مرة أخرى.")
        else:
            st.session_state["last_seen"] = now
            return True

    # ===== Landing / Auth UI =====
    # Prefer full logo if available; fallback to APP_ICON
    def _b64_image(path: str):
        try:
            if not path:
                return None
            if not os.path.isabs(path):
                path = os.path.join(os.path.dirname(__file__), path)
            if not os.path.exists(path):
                return None
            with open(path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except Exception:
            return None

    icon_html = None
    try:
        b64_logo = _b64_image(LOGO_FULL_PATH)
        if b64_logo:
            icon_html = (
                f"<img src='data:image/png;base64,{b64_logo}' "
                "style='width:42px;height:42px;vertical-align:middle;border-radius:12px;'/>"
            )
    except Exception:
        icon_html = None

    if not icon_html:
        try:
            if isinstance(APP_ICON, str) and (APP_ICON.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) or "/" in APP_ICON):
                b64 = _b64_image(APP_ICON)
                icon_html = (
                    f"<img src='data:image/png;base64,{b64}' style='width:34px;height:34px;vertical-align:middle;border-radius:10px;'/>"
                    if b64 else "📈"
                )
            else:
                icon_html = str(APP_ICON)
        except Exception:
            icon_html = "📈"

    st.markdown(
        textwrap.dedent(
            f"""
            <div class="landing-hero">
              <div class="landing-title">{icon_html} {APP_NAME}</div>
              <div class="landing-sub">منصة عربية لتحليل المحافظ، إدارة المخاطر، والباكتيست — بواجهة احترافية وواضحة.</div>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True,
    )

    tab1, tab2 = st.tabs(["تسجيل الدخول", "إنشاء حساب"])

    with tab1:
        st.subheader("تسجيل الدخول")
        with st.form("login_form", clear_on_submit=False):
            u = st.text_input("اسم المستخدم", key="login_username")
            p = st.text_input("كلمة المرور", type="password", key="login_password")
            if getattr(config, "ALLOW_LEGACY_PIN", True):
                st.caption("إذا كانت كلمة مرورك القديمة PIN رقمي (6 أرقام أو أكثر)، اكتبها كما هي وسيتم قبولها.")

            remember = st.checkbox("تذكرني", value=True, key="remember_me")
            submitted = st.form_submit_button("دخول", use_container_width=True)

        if submitted:
            ok, msg = login_user(u, p, remember_me=remember)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    with tab2:
        st.subheader("إنشاء حساب جديد")
        with st.form("register_form", clear_on_submit=False):
            u2 = st.text_input("اسم المستخدم", key="reg_username")
            p2 = st.text_input("كلمة المرور", type="password", key="reg_password")

            if getattr(config, "ALLOW_LEGACY_PIN", True):
                st.caption("للإصدار القديم: يمكنك استخدام PIN رقمي (6 أرقام+). أو استخدم كلمة مرور قوية (8 أحرف+ حروف/أرقام).")
            else:
                st.caption("يفضل كلمة مرور قوية (8 أحرف+ حروف/أرقام).")

            submitted2 = st.form_submit_button("إنشاء الحساب", use_container_width=True)

        if submitted2:
            ok, msg = register_user(u2, p2)
            if ok:
                st.success(msg + " يمكنك الآن تسجيل الدخول.")
            else:
                st.error(msg)

    return False

# ============================================================
# 8) Backward-compatible alias
# ============================================================

def login_system():
    """Alias for older code paths expecting login_system()."""
    return require_login()
