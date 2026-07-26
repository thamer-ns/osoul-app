"""Authentication and input validation for Osoli."""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import html
import os
import re
import secrets
import textwrap
import time
from typing import Optional

import streamlit as st

from config import APP_ICON, APP_NAME, LOGO_FULL_PATH
from database import db_create_user, db_user_exists, db_verify_user

try:
    import extra_streamlit_components as stx  # type: ignore
except Exception:  # pragma: no cover
    stx = None

TOKEN_COOKIE = "osoul_auth_v4"
MAX_LOGIN_ATTEMPTS = int(os.getenv("OSOUL_MAX_LOGIN_ATTEMPTS", "5"))
LOCK_SECONDS = int(os.getenv("OSOUL_LOGIN_LOCK_SECONDS", "900"))


def validate_trade_inputs(quantity, price):
    try:
        quantity_value = float(quantity)
        price_value = float(price)
    except Exception:
        return False, "الرجاء إدخال أرقام صحيحة"
    if not 0 < quantity_value <= 1_000_000_000:
        return False, "الكمية يجب أن تكون أكبر من صفر وضمن حد منطقي"
    if not 0 < price_value <= 1_000_000_000:
        return False, "السعر يجب أن يكون أكبر من صفر وضمن حد منطقي"
    return True, ""


def _norm(value: object) -> str:
    return str(value or "").strip()


def _validate_username(username: str):
    username = _norm(username)
    if not 3 <= len(username) <= 30:
        return False, "اسم المستخدم يجب أن يكون بين 3 و30 حرفًا"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", username):
        return False, "اسم المستخدم يقبل الأحرف الإنجليزية والأرقام و ._- فقط"
    return True, ""


def _validate_password(password: str, mode: str = "login"):
    password = str(password or "")
    if not password:
        return False, "أدخل كلمة المرور"
    if len(password) > 200:
        return False, "كلمة المرور طويلة جدًا"
    if mode == "login":
        return True, ""
    minimum = int(os.getenv("OSOUL_MIN_PASSWORD_LEN", "10"))
    if len(password) < minimum:
        return False, f"كلمة المرور يجب ألا تقل عن {minimum} أحرف"
    categories = sum(
        [
            bool(re.search(r"[A-Za-z]", password)),
            bool(re.search(r"\d", password)),
            bool(re.search(r"[^A-Za-z0-9]", password)),
        ]
    )
    if categories < 2:
        return False, "استخدم مزيجًا من الحروف والأرقام والرموز"
    if password.lower() in {
        "password",
        "password123",
        "1234567890",
        "qwerty123",
    }:
        return False, "اختر كلمة مرور غير شائعة"
    return True, ""


def _auth_secret() -> str:
    value = ""
    try:
        value = str(st.secrets.get("AUTH_SECRET", "") or "")
    except Exception:
        value = ""
    value = value or os.getenv("AUTH_SECRET", "")
    if len(value) >= 32:
        return value
    allow_dev = os.getenv("OSOUL_ALLOW_EPHEMERAL_AUTH_SECRET", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if allow_dev:
        if "_ephemeral_auth_secret" not in st.session_state:
            st.session_state["_ephemeral_auth_secret"] = secrets.token_urlsafe(48)
        return str(st.session_state["_ephemeral_auth_secret"])
    raise RuntimeError("AUTH_SECRET غير مضبوط أو أقصر من 32 حرفًا")


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _sign(payload: str) -> str:
    digest = hmac.new(
        _auth_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64_encode(digest)


def _make_token(username: str, days: int) -> str:
    issued = int(time.time())
    expires = issued + max(1, int(days)) * 86400
    encoded_username = _b64_encode(_norm(username).encode("utf-8"))
    nonce = secrets.token_urlsafe(12)
    payload = f"v4.{issued}.{expires}.{encoded_username}.{nonce}"
    return f"{payload}.{_sign(payload)}"


def _verify_token(token: str):
    try:
        parts = _norm(token).split(".")
        if len(parts) != 6 or parts[0] != "v4":
            return None
        version, issued_text, expires_text, encoded_username, nonce, signature = parts
        payload = ".".join(
            [version, issued_text, expires_text, encoded_username, nonce]
        )
        if not hmac.compare_digest(_sign(payload), signature):
            return None
        issued = int(issued_text)
        expires = int(expires_text)
        now = int(time.time())
        if issued > now + 300 or expires <= now or expires - issued > 31 * 86400:
            return None
        username = _b64_decode(encoded_username).decode("utf-8")
        valid_username, _ = _validate_username(username)
        if not valid_username or not db_user_exists(username):
            return None
        return username, expires
    except Exception:
        return None


def _cookie_manager():
    if stx is None:
        return None
    try:
        if "_osoul_cookie_manager" not in st.session_state:
            st.session_state["_osoul_cookie_manager"] = stx.CookieManager(
                key="osoul_cookie_manager_v4"
            )
        return st.session_state["_osoul_cookie_manager"]
    except Exception:
        return None


def _cookie_get(manager, key: str) -> Optional[str]:
    if manager is None:
        return None
    try:
        try:
            return manager.get(cookie=key)
        except TypeError:
            return manager.get(key)
    except Exception:
        return None


def _cookie_set(manager, key: str, value: str, days: int) -> bool:
    if manager is None:
        return False
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=days)
    widget_key = f"cookie_set_{key}_{int(time.time() * 1000)}"
    try:
        try:
            manager.set(
                cookie=key,
                val=value,
                expires_at=expires,
                key=widget_key,
            )
        except TypeError:
            manager.set(key, value, expires, key=widget_key)
        return True
    except Exception:
        return False


def _cookie_delete(manager, key: str) -> None:
    if manager is None:
        return
    expires = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    widget_key = f"cookie_delete_{key}_{int(time.time() * 1000)}"
    try:
        try:
            manager.set(
                cookie=key,
                val="",
                expires_at=expires,
                key=widget_key,
            )
        except TypeError:
            manager.set(key, "", expires, key=widget_key)
    except Exception:
        pass


def _bootstrap_cookie_session() -> None:
    if st.session_state.get("_auth_cookie_checked"):
        return
    st.session_state["_auth_cookie_checked"] = True
    manager = _cookie_manager()
    token = _cookie_get(manager, TOKEN_COOKIE)
    verified = _verify_token(token or "") if token else None
    if not verified:
        if token:
            _cookie_delete(manager, TOKEN_COOKIE)
        return
    username, expires = verified
    st.session_state.update(
        logged_in=True,
        username=username,
        auth_exp=expires,
        last_seen=time.time(),
    )


def _login_lock_remaining() -> int:
    locked_until = int(st.session_state.get("_login_locked_until", 0) or 0)
    return max(0, locked_until - int(time.time()))


def _record_failed_login() -> None:
    attempts = int(st.session_state.get("_login_attempts", 0) or 0) + 1
    st.session_state["_login_attempts"] = attempts
    if attempts >= MAX_LOGIN_ATTEMPTS:
        st.session_state["_login_locked_until"] = int(time.time()) + LOCK_SECONDS
        st.session_state["_login_attempts"] = 0


def login_user(
    username: str,
    password: str,
    remember_me: bool = False,
    **kwargs,
):
    if kwargs.get("remember") is not None:
        remember_me = bool(kwargs["remember"])
    remaining = _login_lock_remaining()
    if remaining:
        return False, f"محاولات كثيرة. أعد المحاولة بعد {remaining // 60 + 1} دقيقة"
    username = _norm(username)
    valid, message = _validate_username(username)
    if not valid:
        return False, message
    valid, message = _validate_password(password, "login")
    if not valid:
        return False, message
    try:
        verified = bool(db_verify_user(username, str(password)))
    except Exception:
        verified = False
    if not verified:
        _record_failed_login()
        return False, "بيانات الدخول غير صحيحة"
    st.session_state["_login_attempts"] = 0
    st.session_state.pop("_login_locked_until", None)
    days = 30 if remember_me else 1
    expires = int(time.time()) + days * 86400
    st.session_state.update(
        logged_in=True,
        username=username,
        auth_exp=expires,
        last_seen=time.time(),
    )
    _cookie_set(
        _cookie_manager(),
        TOKEN_COOKIE,
        _make_token(username, days),
        days,
    )
    return True, "تم تسجيل الدخول بنجاح"


def register_user(username: str, password: str):
    username = _norm(username)
    valid, message = _validate_username(username)
    if not valid:
        return False, message
    valid, message = _validate_password(password, "register")
    if not valid:
        return False, message
    try:
        if db_user_exists(username):
            return False, "اسم المستخدم موجود مسبقًا"
        if not db_create_user(username, str(password)):
            return False, "تعذر إنشاء الحساب"
        return True, "تم إنشاء الحساب بنجاح"
    except Exception:
        return False, "تعذر إنشاء الحساب"


def logout_user():
    _cookie_delete(_cookie_manager(), TOKEN_COOKIE)
    for key in (
        "logged_in",
        "username",
        "auth_exp",
        "last_seen",
        "user_id",
        "portfolio_id",
    ):
        st.session_state.pop(key, None)


def _render_brand() -> None:
    logo = html.escape(str(APP_ICON))
    try:
        if LOGO_FULL_PATH and os.path.exists(LOGO_FULL_PATH):
            with open(LOGO_FULL_PATH, "rb") as handle:
                encoded = base64.b64encode(handle.read()).decode("ascii")
            logo = (
                "<img src='data:image/png;base64,"
                + encoded
                + "' style='width:44px;height:44px;border-radius:12px'/>"
            )
    except Exception:
        pass
    st.markdown(
        textwrap.dedent(
            f"""
            <div class="landing-hero">
              <div class="landing-title">{logo} {html.escape(str(APP_NAME))}</div>
              <div class="landing-sub">منصة عربية لإدارة المحافظ والتحليل الفني والمالي وإدارة المخاطر.</div>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True,
    )


def require_login():
    try:
        _auth_secret()
    except RuntimeError as exc:
        st.error("إعداد الأمان غير مكتمل. أضف AUTH_SECRET جديدًا في Secrets.")
        st.caption(str(exc))
        return False
    _bootstrap_cookie_session()
    if st.session_state.get("logged_in"):
        now = int(time.time())
        expires = int(st.session_state.get("auth_exp", 0) or 0)
        idle_minutes = int(os.getenv("OSOUL_SESSION_IDLE_MINUTES", "120"))
        last_seen = float(st.session_state.get("last_seen", now) or now)
        if expires <= now or now - last_seen > idle_minutes * 60:
            logout_user()
            st.warning("انتهت الجلسة. سجل الدخول مرة أخرى.")
        else:
            st.session_state["last_seen"] = float(now)
            return True

    _render_brand()
    login_tab, register_tab = st.tabs(["تسجيل الدخول", "إنشاء حساب"])
    with login_tab:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("اسم المستخدم")
            password = st.text_input("كلمة المرور", type="password")
            remember = st.checkbox("تذكرني لمدة 30 يومًا", value=False)
            submitted = st.form_submit_button("دخول", use_container_width=True)
        if submitted:
            valid, message = login_user(
                username,
                password,
                remember_me=remember,
            )
            if valid:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

    with register_tab:
        with st.form("register_form", clear_on_submit=False):
            username = st.text_input(
                "اسم المستخدم",
                key="register_username",
            )
            password = st.text_input(
                "كلمة المرور القوية",
                type="password",
                key="register_password",
            )
            confirmation = st.text_input(
                "تأكيد كلمة المرور",
                type="password",
                key="register_confirmation",
            )
            submitted = st.form_submit_button(
                "إنشاء الحساب",
                use_container_width=True,
            )
        if submitted:
            if password != confirmation:
                st.error("كلمتا المرور غير متطابقتين")
            else:
                valid, message = register_user(username, password)
                if valid:
                    st.success(message)
                else:
                    st.error(message)
    return False


def login_system():
    return require_login()
