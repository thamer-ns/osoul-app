"""Confirmed first-party cookie authentication for Streamlit.

The browser cookie is written by ``extra_streamlit_components.CookieManager``
(the component intended for this job), not by JavaScript running in an isolated
iframe.  A fresh browser session waits for the cookie component's first snapshot
before deciding that the user is logged out, preventing a refresh from flashing
or permanently selecting the login screen.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Any, Optional

import streamlit as st

import security

COOKIE_NAME = "osoul_auth_v7"
LEGACY_COOKIE_NAMES = ("osoul_auth_v6", "osoul_auth_v5", "osoul_auth_v4")
TOKEN_VERSION = "v7"
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
    """Return one signing key that survives app sleep and process replacement."""
    configured = _setting("AUTH_SECRET")
    if len(configured) >= 32:
        return configured
    if configured:
        _LOGGER.warning("Configured AUTH_SECRET is shorter than 32 characters")

    seed = _setting("OSOUL_AUTH_SECRET_SEED") or _setting("DATABASE_URL")
    if seed:
        return hashlib.sha256(f"osoul-auth-v7\0{seed}".encode("utf-8")).hexdigest()

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


def _context_snapshot() -> dict[str, str]:
    """Return cookies attached to the initial WebSocket request when available."""
    try:
        cookies = st.context.cookies
        return {str(key): str(value) for key, value in cookies.items()}
    except Exception:
        return {}


def _cookie_manager():
    """Create exactly one cookie component in this script run."""
    if security.stx is None:
        return None
    try:
        return security.stx.CookieManager(key="osoul_auth_manager_v7")
    except Exception:
        _LOGGER.exception("Cookie manager initialization failed")
        return None


def _manager_snapshot(manager) -> Optional[dict[str, str]]:
    if manager is None:
        return None
    cookies = getattr(manager, "cookies", None)
    if not isinstance(cookies, dict):
        return None
    return {str(key): str(value) for key, value in cookies.items()}


def _component_snapshot(manager) -> Optional[dict[str, str]]:
    """Wait one frontend cycle before treating an empty cookie result as final."""
    snapshot = _manager_snapshot(manager)
    marker = "_auth_cookie_component_seen_v7"
    if not st.session_state.get(marker):
        st.session_state[marker] = True
        if not snapshot:
            return None
    return snapshot if snapshot is not None else {}


def _set_cookie(manager, token: str, days: int) -> bool:
    if manager is None or not _norm(token):
        return False
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=int(days))
    operation = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
    try:
        manager.set(
            cookie=COOKIE_NAME,
            val=token,
            key=f"osoul_auth_set_v7_{operation}",
            path="/",
            expires_at=expires,
            max_age=int(days) * 86400,
            secure=True,
            same_site="lax",
        )
        return True
    except TypeError:
        try:
            manager.set(
                cookie=COOKIE_NAME,
                val=token,
                key=f"osoul_auth_set_v7_{operation}",
                expires_at=expires,
            )
            return True
        except Exception:
            _LOGGER.exception("Cookie write failed")
            return False
    except Exception:
        _LOGGER.exception("Cookie write failed")
        return False


def _expire_cookie(manager, name: str) -> None:
    if manager is None:
        return
    expires = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
    operation = hashlib.sha256(name.encode("utf-8")).hexdigest()[:10]
    try:
        manager.set(
            cookie=name,
            val="",
            key=f"osoul_auth_delete_{operation}",
            path="/",
            expires_at=expires,
            max_age=0,
            secure=True,
            same_site="lax",
        )
    except TypeError:
        try:
            manager.set(
                cookie=name,
                val="",
                key=f"osoul_auth_delete_{operation}",
                expires_at=expires,
            )
        except Exception:
            _LOGGER.debug("Legacy cookie deletion failed", exc_info=True)
    except Exception:
        _LOGGER.debug("Cookie deletion failed", exc_info=True)


def _verify_legacy_cookie(name: str, token: str) -> Optional[tuple[str, int]]:
    try:
        if name == "osoul_auth_v6":
            import persistent_auth_v3

            return persistent_auth_v3.verify_token(token)
        if name == "osoul_auth_v5":
            import persistent_auth

            return persistent_auth.verify_token(token)
        if name == "osoul_auth_v4":
            return security._verify_token(token)
    except Exception:
        return None
    return None


def _restore_from_snapshot(
    snapshot: dict[str, str],
    manager=None,
) -> bool:
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

    if legacy_name and manager is not None:
        remaining_days = max(
            1,
            min(30, int((int(expires) - int(time.time()) + 86399) // 86400)),
        )
        _set_cookie(manager, make_token(username, remaining_days), remaining_days)
        for name in LEGACY_COOKIE_NAMES:
            _expire_cookie(manager, name)
    return True


def restore_cookie_session(manager=None) -> Optional[bool]:
    """Restore a session, returning ``None`` while the component warms up."""
    if st.session_state.get("_auth_cookie_checked_v7"):
        return bool(st.session_state.get("logged_in"))

    context = _context_snapshot()
    if _restore_from_snapshot(context, manager):
        st.session_state["_auth_cookie_checked_v7"] = True
        return True

    snapshot = _component_snapshot(manager)
    if snapshot is None:
        return None

    st.session_state["_auth_cookie_checked_v7"] = True
    return _restore_from_snapshot(snapshot, manager)


def login_user(
    username: str,
    password: str,
    remember_me: bool = False,
    **kwargs: Any,
):
    manager = kwargs.pop("manager", None)
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

    days = 30 if remember_me else 1
    expires = int(time.time()) + days * 86400
    token = make_token(username, days)
    if manager is None:
        manager = _cookie_manager()
    persisted = _set_cookie(manager, token, days)
    if not persisted:
        return False, "تعذر تثبيت جلسة المتصفح. حدّث الصفحة ثم أعد المحاولة."

    st.session_state["_login_attempts"] = 0
    st.session_state.pop("_login_locked_until", None)
    st.session_state.update(
        logged_in=True,
        username=username,
        auth_exp=expires,
        last_seen=time.time(),
        auth_restored_from_cookie=False,
        _auth_cookie_checked_v7=True,
        _auth_cookie_persisted_v7=True,
    )
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
        "_auth_cookie_checked_v7",
        "_auth_cookie_persisted_v7",
        "user_id",
        "portfolio_id",
    ):
        st.session_state.pop(key, None)
    st.session_state["_auth_cookie_delete_pending_v7"] = True


def _flush_pending_logout(manager) -> bool:
    if not st.session_state.pop("_auth_cookie_delete_pending_v7", False):
        return False
    for name in (COOKIE_NAME, *LEGACY_COOKIE_NAMES):
        _expire_cookie(manager, name)
    st.session_state["_auth_cookie_checked_v7"] = True
    return True


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


def _render_login(manager) -> bool:
    auth_slot = st.empty()
    login_succeeded = False

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
                    manager=manager,
                )
                if valid:
                    login_succeeded = True
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

    if login_succeeded:
        auth_slot.empty()
        return True
    return False


def require_login() -> bool:
    try:
        _stable_auth_secret()
    except RuntimeError as exc:
        st.error("إعداد الأمان غير مكتمل.")
        st.caption(str(exc))
        return False

    if _active_session_is_valid():
        return True

    manager = _cookie_manager()
    if manager is None:
        st.error("تعذر تشغيل مدير جلسة المتصفح.")
        st.caption("أعد تشغيل التطبيق بعد التحقق من مكتبة extra-streamlit-components.")
        return False

    if _flush_pending_logout(manager):
        return _render_login(manager)

    restored = restore_cookie_session(manager)
    if restored is None:
        st.markdown(
            '<div class="os-auth-loading">جاري استعادة الجلسة الآمنة…</div>',
            unsafe_allow_html=True,
        )
        return False
    if restored and _active_session_is_valid():
        return True
    return _render_login(manager)


def login_system() -> bool:
    return require_login()


def install_persistent_auth() -> None:
    security.TOKEN_COOKIE = COOKIE_NAME
    security.login_user = login_user
    security.logout_user = logout_user
    security.require_login = require_login
    security.login_system = login_system
