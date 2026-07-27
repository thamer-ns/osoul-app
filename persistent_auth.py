"""Reliable browser-persistent authentication for Streamlit.

The built-in session state disappears on a browser refresh.  This module keeps
one signed token in a first-party cookie, reads it from ``st.context.cookies`` on
the initial request, and uses a two-phase browser write so an immediate
``st.rerun`` cannot cancel cookie persistence.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any, Optional

import streamlit as st
import streamlit.components.v1 as components

import security

COOKIE_NAME = "osoul_auth_v5"
LEGACY_COOKIE_NAME = "osoul_auth_v4"
TOKEN_VERSION = "v5"
_MAX_TOKEN_DAYS = 31
_LOGGER = logging.getLogger(__name__)


def _norm(value: object) -> str:
    return str(value or "").strip()


def _setting(name: str) -> str:
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    if value not in (None, ""):
        return str(value).strip()
    return str(os.getenv(name, "") or "").strip()


def _stable_auth_secret() -> str:
    """Return a stable signing secret across refreshes, sleeps, and redeploys."""
    configured = _setting("AUTH_SECRET")
    if len(configured) >= 32:
        return configured
    if configured:
        _LOGGER.warning("Configured AUTH_SECRET is shorter than 32 characters")

    seed = _setting("OSOUL_AUTH_SECRET_SEED") or _setting("DATABASE_URL")
    if seed:
        _LOGGER.warning(
            "AUTH_SECRET is missing; deriving a deployment-stable signing key. "
            "Configure AUTH_SECRET explicitly for independent key rotation."
        )
        material = f"osoul-auth-v5\0{seed}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    fallback = security._load_or_create_runtime_auth_secret()
    if len(fallback) < 32:
        raise RuntimeError("تعذر إنشاء مفتاح توقيع آمن للجلسة")
    return fallback


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _sign(payload: str) -> str:
    digest = hmac.new(
        _stable_auth_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64_encode(digest)


def make_token(username: str, days: int) -> str:
    issued = int(time.time())
    lifetime = max(1, min(_MAX_TOKEN_DAYS, int(days))) * 86400
    expires = issued + lifetime
    encoded_username = _b64_encode(_norm(username).encode("utf-8"))
    nonce = secrets.token_urlsafe(18)
    payload = f"{TOKEN_VERSION}.{issued}.{expires}.{encoded_username}.{nonce}"
    return f"{payload}.{_sign(payload)}"


def verify_token(token: str) -> Optional[tuple[str, int]]:
    try:
        parts = _norm(token).split(".")
        if len(parts) != 6 or parts[0] != TOKEN_VERSION:
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
        if issued > now + 300:
            return None
        if expires <= now or expires - issued > _MAX_TOKEN_DAYS * 86400:
            return None
        username = _b64_decode(encoded_username).decode("utf-8")
        valid, _ = security._validate_username(username)
        if not valid or not security.db_user_exists(username):
            return None
        return username, expires
    except Exception:
        return None


def _context_cookie_snapshot() -> tuple[Optional[dict[str, str]], bool]:
    """Read cookies carried by the initial browser request.

    The boolean indicates whether the modern Streamlit context API was
    available.  An available empty dictionary is authoritative; it is not the
    same as an asynchronous component that has not loaded yet.
    """
    try:
        context = getattr(st, "context")
        cookies = getattr(context, "cookies")
    except Exception:
        return None, False
    if cookies is None:
        return {}, True
    try:
        snapshot = {str(key): str(value) for key, value in cookies.items()}
    except Exception:
        try:
            snapshot = dict(cookies)
        except Exception:
            return {}, True
    return snapshot, True


def _fallback_cookie_snapshot() -> Optional[dict[str, str]]:
    manager = security._cookie_manager()
    snapshot = security._cookie_snapshot(manager)
    if snapshot is None:
        return None
    return {str(key): str(value) for key, value in snapshot.items()}


def _browser_is_https() -> bool:
    try:
        return str(st.context.url).lower().startswith("https://")
    except Exception:
        return True


def _cookie_assignment(name: str, value: str, max_age: int) -> str:
    parts = [
        f"{name}={value}",
        f"Max-Age={max(0, int(max_age))}",
        "Path=/",
        "SameSite=Lax",
    ]
    if _browser_is_https():
        parts.append("Secure")
    return "; ".join(parts)


def _render_cookie_script(
    assignments: list[str],
    *,
    reload_after_write: bool,
) -> None:
    commands = "\n".join(
        f"document.cookie = {json.dumps(value)};" for value in assignments
    )
    reload_script = (
        "setTimeout(() => window.parent.location.reload(), 450);"
        if reload_after_write
        else ""
    )
    components.html(
        f"""
        <script>
        {commands}
        {reload_script}
        </script>
        """,
        height=0,
        width=0,
    )


def _write_login_cookie(token: str, days: int) -> None:
    """Write through both the package component and a first-party JS fallback."""
    manager = security._cookie_manager()
    security._cookie_set(manager, COOKIE_NAME, token, days)
    security._cookie_delete(manager, LEGACY_COOKIE_NAME)
    assignments = [
        _cookie_assignment(COOKIE_NAME, token, days * 86400),
        _cookie_assignment(LEGACY_COOKIE_NAME, "", 0),
    ]
    _render_cookie_script(assignments, reload_after_write=True)


def _delete_login_cookies() -> None:
    manager = security._cookie_manager()
    for name in (COOKIE_NAME, LEGACY_COOKIE_NAME):
        security._cookie_delete(manager, name)
    assignments = [
        _cookie_assignment(COOKIE_NAME, "", 0),
        _cookie_assignment(LEGACY_COOKIE_NAME, "", 0),
    ]
    try:
        _render_cookie_script(assignments, reload_after_write=False)
    except Exception:
        _LOGGER.debug("Browser cookie deletion fallback failed", exc_info=True)


def restore_cookie_session() -> bool:
    if st.session_state.get("_auth_cookie_checked_v5"):
        return bool(st.session_state.get("logged_in"))

    snapshot, context_available = _context_cookie_snapshot()
    if not context_available:
        snapshot = _fallback_cookie_snapshot()
        if snapshot is None:
            return False

    st.session_state["_auth_cookie_checked_v5"] = True
    token = _norm((snapshot or {}).get(COOKIE_NAME))
    verified = verify_token(token) if token else None

    if not verified:
        legacy_token = _norm((snapshot or {}).get(LEGACY_COOKIE_NAME))
        if legacy_token:
            try:
                verified = security._verify_token(legacy_token)
            except Exception:
                verified = None

    if not verified:
        return False

    username, expires = verified
    st.session_state.update(
        logged_in=True,
        username=username,
        auth_exp=int(expires),
        last_seen=time.time(),
        auth_restored_from_cookie=True,
    )
    return True


def login_user(
    username: str,
    password: str,
    remember_me: bool = False,
    **kwargs: Any,
):
    if kwargs.get("remember") is not None:
        remember_me = bool(kwargs["remember"])
    remaining = security._login_lock_remaining()
    if remaining:
        return False, f"محاولات كثيرة. أعد المحاولة بعد {remaining // 60 + 1} دقيقة"

    username = _norm(username)
    valid, message = security._validate_username(username)
    if not valid:
        return False, message
    valid, message = security._validate_password(password, "login")
    if not valid:
        return False, message

    try:
        verified = bool(security.db_verify_user(username, str(password)))
    except Exception:
        verified = False
    if not verified:
        security._record_failed_login()
        return False, "بيانات الدخول غير صحيحة"

    st.session_state["_login_attempts"] = 0
    st.session_state.pop("_login_locked_until", None)
    days = 30 if remember_me else 1
    expires = int(time.time()) + days * 86400
    token = make_token(username, days)
    st.session_state.update(
        logged_in=True,
        username=username,
        auth_exp=expires,
        last_seen=time.time(),
        _auth_cookie_write_pending=True,
    )
    _write_login_cookie(token, days)
    return True, "تم تسجيل الدخول وتثبيت الجلسة في المتصفح"


def logout_user() -> None:
    _delete_login_cookies()
    for key in (
        "logged_in",
        "username",
        "auth_exp",
        "last_seen",
        "auth_restored_from_cookie",
        "_auth_cookie_checked",
        "_auth_cookie_checked_v5",
        "_auth_cookie_manager_warmup",
        "_auth_cookie_write_pending",
        "user_id",
        "portfolio_id",
    ):
        st.session_state.pop(key, None)


def require_login() -> bool:
    try:
        _stable_auth_secret()
    except RuntimeError as exc:
        st.error("إعداد الأمان غير مكتمل.")
        st.caption(str(exc))
        return False

    restore_cookie_session()
    if st.session_state.get("logged_in"):
        now = int(time.time())
        expires = int(st.session_state.get("auth_exp", 0) or 0)
        idle_minutes = security._int_setting(
            "OSOUL_SESSION_IDLE_MINUTES",
            120,
            5,
            10_080,
        )
        last_seen = float(st.session_state.get("last_seen", now) or now)
        if expires <= now or now - last_seen > idle_minutes * 60:
            logout_user()
            st.warning("انتهت الجلسة. سجل الدخول مرة أخرى.")
        else:
            st.session_state["last_seen"] = float(now)
            st.session_state.pop("_auth_cookie_write_pending", None)
            return True

    security._render_brand()
    login_tab, register_tab = st.tabs(["تسجيل الدخول", "إنشاء حساب"])

    with login_tab:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("اسم المستخدم")
            password = st.text_input("كلمة المرور", type="password")
            remember = st.checkbox("ابقني مسجلًا لمدة 30 يومًا", value=True)
            submitted = st.form_submit_button("دخول", use_container_width=True)
        if submitted:
            valid, message = login_user(
                username,
                password,
                remember_me=remember,
            )
            if valid:
                st.success(message)
                st.info("يتم الآن تثبيت الجلسة ثم إعادة فتح الصفحة تلقائيًا...")
                return False
            st.error(message)

    with register_tab:
        with st.form("register_form", clear_on_submit=False):
            username = st.text_input("اسم المستخدم", key="register_username")
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
                valid, message = security.register_user(username, password)
                if valid:
                    st.success(message)
                else:
                    st.error(message)
    return False


def login_system() -> bool:
    return require_login()


def install_persistent_auth() -> None:
    """Replace the legacy asynchronous bootstrap before page modules import it."""
    security.TOKEN_COOKIE = COOKIE_NAME
    security.login_user = login_user
    security.logout_user = logout_user
    security.require_login = require_login
    security.login_system = login_system
