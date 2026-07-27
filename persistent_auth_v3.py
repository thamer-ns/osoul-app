"""Stable first-party authentication without login rerun races.

The previous flow wrote a cookie and immediately forced a full browser reload.
On Streamlit Community Cloud that reload could win the race and start a fresh
session before the browser had committed the cookie.  This module instead:

* opens the application in the already-authenticated Streamlit session;
* writes one signed first-party cookie without any automatic reload or rerun;
* restores that token from ``st.context.cookies`` on a later real refresh;
* keeps legacy v5/v4 cookies readable during migration;
* defers cookie deletion to the first logged-out render so callbacks do not
  attempt to render custom components.
"""
from __future__ import annotations

import base64
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

COOKIE_NAME = "osoul_auth_v6"
LEGACY_COOKIE_NAMES = ("osoul_auth_v5", "osoul_auth_v4")
TOKEN_VERSION = "v6"
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
    configured = _setting("AUTH_SECRET")
    if len(configured) >= 32:
        return configured
    if configured:
        _LOGGER.warning("Configured AUTH_SECRET is shorter than 32 characters")

    seed = _setting("OSOUL_AUTH_SECRET_SEED") or _setting("DATABASE_URL")
    if seed:
        material = f"osoul-auth-v6\0{seed}".encode("utf-8")
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


def _request_cookies() -> dict[str, str]:
    try:
        cookies = st.context.cookies
        return {str(key): str(value) for key, value in cookies.items()}
    except Exception:
        return {}


def _is_https() -> bool:
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
    if _is_https():
        parts.append("Secure")
    return "; ".join(parts)


def _emit_cookie_assignments(assignments: list[str]) -> None:
    """Write cookies without triggering a Streamlit rerun or browser reload."""
    encoded = json.dumps(assignments)
    components.html(
        f"""
        <script>
        const assignments = {encoded};
        for (const assignment of assignments) {{
          try {{ document.cookie = assignment; }} catch (error) {{}}
          try {{
            if (window.parent && window.parent !== window) {{
              window.parent.document.cookie = assignment;
            }}
          }} catch (error) {{}}
        }}
        </script>
        """,
        height=0,
        width=0,
    )


def _queue_login_cookie(token: str, days: int) -> None:
    st.session_state["_auth_cookie_pending_v6"] = {
        "token": _norm(token),
        "days": max(1, min(_MAX_TOKEN_DAYS, int(days))),
    }


def _flush_login_cookie() -> None:
    pending = st.session_state.pop("_auth_cookie_pending_v6", None)
    if not isinstance(pending, dict):
        return
    token = _norm(pending.get("token"))
    days = int(pending.get("days", 1) or 1)
    if not token:
        return
    assignments = [
        _cookie_assignment(COOKIE_NAME, token, days * 86400),
        *[
            _cookie_assignment(name, "", 0)
            for name in LEGACY_COOKIE_NAMES
        ],
    ]
    _emit_cookie_assignments(assignments)


def _flush_logout_cookie() -> bool:
    if not st.session_state.pop("_auth_cookie_delete_pending_v6", False):
        return False
    assignments = [
        _cookie_assignment(COOKIE_NAME, "", 0),
        *[
            _cookie_assignment(name, "", 0)
            for name in LEGACY_COOKIE_NAMES
        ],
    ]
    _emit_cookie_assignments(assignments)
    return True


def _verify_legacy_cookie(name: str, token: str) -> Optional[tuple[str, int]]:
    try:
        if name == "osoul_auth_v5":
            import persistent_auth

            return persistent_auth.verify_token(token)
        if name == "osoul_auth_v4":
            return security._verify_token(token)
    except Exception:
        return None
    return None


def restore_cookie_session() -> bool:
    if st.session_state.get("_auth_cookie_checked_v6"):
        return bool(st.session_state.get("logged_in"))

    st.session_state["_auth_cookie_checked_v6"] = True
    snapshot = _request_cookies()
    token = _norm(snapshot.get(COOKIE_NAME))
    verified = verify_token(token) if token else None

    legacy_name = ""
    if not verified:
        for name in LEGACY_COOKIE_NAMES:
            legacy_token = _norm(snapshot.get(name))
            if not legacy_token:
                continue
            verified = _verify_legacy_cookie(name, legacy_token)
            if verified:
                legacy_name = name
                break

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
    if legacy_name:
        remaining_days = max(
            1,
            min(
                30,
                int((int(expires) - int(time.time()) + 86399) // 86400),
            ),
        )
        _queue_login_cookie(make_token(username, remaining_days), remaining_days)
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
        auth_restored_from_cookie=False,
    )
    _queue_login_cookie(token, days)
    return True, "تم تسجيل الدخول بنجاح"


def logout_user() -> None:
    for key in (
        "logged_in",
        "username",
        "auth_exp",
        "last_seen",
        "auth_restored_from_cookie",
        "_auth_cookie_checked",
        "_auth_cookie_checked_v5",
        "_auth_cookie_checked_v6",
        "_auth_cookie_manager_warmup",
        "_auth_cookie_write_pending",
        "_auth_cookie_pending_v6",
        "user_id",
        "portfolio_id",
    ):
        st.session_state.pop(key, None)
    st.session_state["_auth_cookie_delete_pending_v6"] = True


def _active_session_is_valid() -> bool:
    if not st.session_state.get("logged_in"):
        return False
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
        return False
    st.session_state["last_seen"] = float(now)
    return True


def require_login() -> bool:
    try:
        _stable_auth_secret()
    except RuntimeError as exc:
        st.error("إعداد الأمان غير مكتمل.")
        st.caption(str(exc))
        return False

    deleted = _flush_logout_cookie()
    if not deleted:
        restore_cookie_session()

    if _active_session_is_valid():
        _flush_login_cookie()
        return True

    auth_slot = st.empty()
    login_succeeded = False
    success_message = ""

    with auth_slot.container():
        security._render_brand()
        login_tab, register_tab = st.tabs(["تسجيل الدخول", "إنشاء حساب"])

        with login_tab:
            with st.form("login_form", clear_on_submit=False):
                username = st.text_input("اسم المستخدم")
                password = st.text_input("كلمة المرور", type="password")
                remember = st.checkbox(
                    "ابقني مسجلًا لمدة 30 يومًا",
                    value=True,
                )
                submitted = st.form_submit_button(
                    "دخول",
                    use_container_width=True,
                )
            if submitted:
                valid, message = login_user(
                    username,
                    password,
                    remember_me=remember,
                )
                if valid:
                    login_succeeded = True
                    success_message = message
                else:
                    st.error(message)

        with register_tab:
            with st.form("register_form", clear_on_submit=False):
                new_username = st.text_input(
                    "اسم المستخدم",
                    key="register_username",
                )
                new_password = st.text_input(
                    "كلمة المرور القوية",
                    type="password",
                    key="register_password",
                )
                confirmation = st.text_input(
                    "تأكيد كلمة المرور",
                    type="password",
                    key="register_confirmation",
                )
                register_submitted = st.form_submit_button(
                    "إنشاء الحساب",
                    use_container_width=True,
                )
            if register_submitted:
                if new_password != confirmation:
                    st.error("كلمتا المرور غير متطابقتين")
                else:
                    valid, message = security.register_user(
                        new_username,
                        new_password,
                    )
                    if valid:
                        st.success(message)
                    else:
                        st.error(message)

    if not login_succeeded:
        return False

    auth_slot.empty()
    _flush_login_cookie()
    st.success(success_message)
    return True


def login_system() -> bool:
    return require_login()


def install_persistent_auth() -> None:
    security.TOKEN_COOKIE = COOKIE_NAME
    security.login_user = login_user
    security.logout_user = logout_user
    security.require_login = require_login
    security.login_system = login_system
