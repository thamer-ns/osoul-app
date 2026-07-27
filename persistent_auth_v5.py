"""Race-safe login ordering on top of the confirmed v7 cookie flow."""
from __future__ import annotations

import time
from typing import Any

import persistent_auth_v4 as base
import security

COOKIE_NAME = base.COOKIE_NAME
LEGACY_COOKIE_NAMES = base.LEGACY_COOKIE_NAMES
make_token = base.make_token
verify_token = base.verify_token
restore_cookie_session = base.restore_cookie_session
logout_user = base.logout_user
require_login = base.require_login
login_system = base.login_system


def _clear_provisional_session() -> None:
    for key in (
        "logged_in",
        "username",
        "auth_exp",
        "last_seen",
        "auth_restored_from_cookie",
        "_auth_cookie_checked_v7",
        "_auth_cookie_persisted_v7",
    ):
        base.st.session_state.pop(key, None)


def login_user(
    username: str,
    password: str,
    remember_me: bool = False,
    **kwargs: Any,
):
    """Persist Python session state before the cookie component can rerun."""
    manager = kwargs.pop("manager", None)
    if kwargs.get("remember") is not None:
        remember_me = bool(kwargs["remember"])

    remaining = security._login_lock_remaining()
    if remaining:
        return False, f"محاولات كثيرة. أعد المحاولة بعد {remaining // 60 + 1} دقيقة"

    username = base._norm(username)
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
    token = base.make_token(username, days)
    if manager is None:
        manager = base._cookie_manager()

    security_state = {
        "logged_in": True,
        "username": username,
        "auth_exp": expires,
        "last_seen": time.time(),
        "auth_restored_from_cookie": False,
        "_auth_cookie_checked_v7": True,
        "_auth_cookie_persisted_v7": False,
    }
    base.st.session_state.update(**security_state)

    if not base._set_cookie(manager, token, days):
        _clear_provisional_session()
        return False, "تعذر تثبيت جلسة المتصفح. حدّث الصفحة ثم أعد المحاولة."

    base.st.session_state["_login_attempts"] = 0
    base.st.session_state.pop("_login_locked_until", None)
    base.st.session_state["_auth_cookie_persisted_v7"] = True
    return True, "تم تسجيل الدخول بنجاح"


def install_persistent_auth() -> None:
    """Install the ordered login function into both auth modules and security."""
    base.login_user = login_user
    security.TOKEN_COOKIE = COOKIE_NAME
    security.login_user = login_user
    security.logout_user = base.logout_user
    security.require_login = base.require_login
    security.login_system = base.login_system
