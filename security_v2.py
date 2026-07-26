"""Hardened authentication for Osoli.

Key changes from the legacy module:
- no unsigned username-cookie fallback;
- no built-in authentication secret;
- strong password policy is applied during registration;
- rate limiting for repeated login failures;
- signed, expiring v4 tokens with constant-time verification.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import streamlit as st

import config
from database import db_create_user, db_user_exists, db_verify_user

try:
    import bcrypt  # noqa: F401
except Exception as exc:  # pragma: no cover
    raise RuntimeError("bcrypt مطلوب لتشغيل المصادقة الآمنة.") from exc

try:
    import extra_streamlit_components as stx

    _HAS_COOKIES = True
except Exception:  # pragma: no cover
    stx = None
    _HAS_COOKIES = False

_COOKIE_NAME = "osoul_auth_v4"
_LOGIN_WINDOW_SECONDS = 300
_MAX_LOGIN_FAILURES = 5


def validate_trade_inputs(quantity: Any, price: Any) -> tuple[bool, str]:
    try:
        q = float(quantity)
        p = float(price)
    except Exception:
        return False, "الرجاء إدخال أرقام صحيحة."
    if not (q > 0 and p > 0):
        return False, "الكمية والسعر يجب أن يكونا أكبر من صفر."
    if q > 1_000_000_000 or p > 1_000_000_000:
        return False, "القيمة المدخلة تتجاوز الحد المنطقي."
    return True, ""


def _username(value: Any) -> str:
    return str(value or "").strip()


def _validate_username(value: Any) -> tuple[bool, str]:
    username = _username(value)
    if not 3 <= len(username) <= 40:
        return False, "اسم المستخدم يجب أن يكون بين 3 و40 حرفًا."
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", username):
        return False, "اسم المستخدم يقبل الأحرف الإنجليزية والأرقام و . _ - فقط."
    return True, ""


def _validate_password(value: Any, *, registration: bool) -> tuple[bool, str]:
    password = str(value or "")
    if not registration:
        return (bool(password), "" if password else "أدخل كلمة المرور.")
    min_len = max(10, int(getattr(config, "MIN_PASSWORD_LEN", 10) or 10))
    if len(password) < min_len:
        return False, f"كلمة المرور يجب ألا تقل عن {min_len} أحرف."
    if len(password) > 200:
        return False, "كلمة المرور طويلة جدًا."
    checks = (
        re.search(r"[A-Z]", password),
        re.search(r"[a-z]", password),
        re.search(r"\d", password),
        re.search(r"[^A-Za-z0-9]", password),
    )
    if sum(bool(x) for x in checks) < 3:
        return False, "استخدم مزيجًا من الأحرف الكبيرة والصغيرة والأرقام والرموز."
    if password.lower() in {"password123", "1234567890", "qwerty12345"}:
        return False, "كلمة المرور شائعة وغير آمنة."
    return True, ""


def _auth_secret() -> Optional[str]:
    secret = ""
    try:
        secret = str(st.secrets.get("AUTH_SECRET", "") or "").strip()
    except Exception:
        pass
    secret = secret or str(os.getenv("AUTH_SECRET", "") or "").strip()
    return secret if len(secret) >= 32 else None


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(value: str) -> bytes:
    value = str(value or "")
    return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def _sign(payload_b64: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64e(digest)


def _make_token(username: str, days: int) -> str:
    secret = _auth_secret()
    if not secret:
        raise RuntimeError("AUTH_SECRET غير مضبوط أو أقصر من 32 حرفًا.")
    payload = {
        "v": 4,
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + max(1, int(days)) * 86400,
    }
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64, secret)}"


def _verify_token(token: str) -> Optional[dict[str, Any]]:
    secret = _auth_secret()
    if not secret or not token or "." not in token:
        return None
    try:
        payload_b64, signature = token.split(".", 1)
        expected = _sign(payload_b64, secret)
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_b64d(payload_b64).decode("utf-8"))
        if payload.get("v") != 4:
            return None
        if int(payload.get("exp") or 0) <= int(time.time()):
            return None
        username = _username(payload.get("sub"))
        if not username or not db_user_exists(username):
            return None
        return payload
    except Exception:
        return None


def _cookie_manager():
    if not _HAS_COOKIES:
        return None
    try:
        if "_osoul_cookie_manager_v4" not in st.session_state:
            st.session_state["_osoul_cookie_manager_v4"] = stx.CookieManager(
                key="osoul_cookie_manager_v4"
            )
        return st.session_state["_osoul_cookie_manager_v4"]
    except Exception:
        return None


def _read_cookie() -> str:
    manager = _cookie_manager()
    if not manager:
        return ""
    try:
        try:
            return str(manager.get(cookie=_COOKIE_NAME) or "")
        except TypeError:
            return str(manager.get(_COOKIE_NAME) or "")
    except Exception:
        return ""


def _set_cookie(token: str, days: int) -> None:
    manager = _cookie_manager()
    if not manager:
        return
    expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=days)
    try:
        try:
            manager.set(
                cookie=_COOKIE_NAME,
                val=token,
                expires_at=expiry,
                key=f"set_auth_v4_{int(time.time() * 1000)}",
            )
        except TypeError:
            manager.set(
                _COOKIE_NAME,
                token,
                expiry,
                key=f"set_auth_v4_{int(time.time() * 1000)}",
            )
    except Exception:
        pass


def _delete_cookie() -> None:
    manager = _cookie_manager()
    if not manager:
        return
    expiry = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)
    try:
        try:
            manager.set(
                cookie=_COOKIE_NAME,
                val="",
                expires_at=expiry,
                key=f"delete_auth_v4_{int(time.time() * 1000)}",
            )
        except TypeError:
            manager.set(
                _COOKIE_NAME,
                "",
                expiry,
                key=f"delete_auth_v4_{int(time.time() * 1000)}",
            )
    except Exception:
        pass


def _failure_state() -> tuple[int, float]:
    failures = int(st.session_state.get("_login_failures_v4", 0) or 0)
    started = float(st.session_state.get("_login_window_v4", 0.0) or 0.0)
    if not started or time.time() - started > _LOGIN_WINDOW_SECONDS:
        failures, started = 0, time.time()
        st.session_state["_login_failures_v4"] = failures
        st.session_state["_login_window_v4"] = started
    return failures, started


def _record_failure() -> None:
    failures, _ = _failure_state()
    st.session_state["_login_failures_v4"] = failures + 1


def _clear_failures() -> None:
    st.session_state.pop("_login_failures_v4", None)
    st.session_state.pop("_login_window_v4", None)


def login_user(username: str, password: str, remember_me: bool = False, **_: Any):
    username = _username(username)
    ok, message = _validate_username(username)
    if not ok:
        return False, message
    ok, message = _validate_password(password, registration=False)
    if not ok:
        return False, message

    failures, started = _failure_state()
    if failures >= _MAX_LOGIN_FAILURES:
        remaining = max(1, int(_LOGIN_WINDOW_SECONDS - (time.time() - started)))
        return False, f"محاولات كثيرة. أعد المحاولة بعد {remaining} ثانية."

    try:
        verified = bool(db_verify_user(username, password))
    except Exception:
        verified = False
    if not verified:
        _record_failure()
        return False, "بيانات الدخول غير صحيحة."

    _clear_failures()
    days = 30 if remember_me else 1
    token = _make_token(username, days)
    st.session_state.update(
        logged_in=True,
        username=username,
        auth_exp=int(time.time()) + days * 86400,
        last_seen=datetime.now(timezone.utc),
    )
    _set_cookie(token, days)
    return True, "تم تسجيل الدخول بنجاح."


def register_user(username: str, password: str):
    username = _username(username)
    ok, message = _validate_username(username)
    if not ok:
        return False, message
    ok, message = _validate_password(password, registration=True)
    if not ok:
        return False, message
    if db_user_exists(username):
        return False, "اسم المستخدم موجود مسبقًا."
    try:
        created = bool(db_create_user(username, password))
    except Exception:
        created = False
    return (
        (True, "تم إنشاء الحساب بنجاح.")
        if created
        else (False, "تعذر إنشاء الحساب. راجع اتصال قاعدة البيانات.")
    )


def logout_user() -> None:
    for key in ("logged_in", "username", "auth_exp", "last_seen"):
        st.session_state.pop(key, None)
    _delete_cookie()


def _bootstrap_session() -> None:
    if st.session_state.get("_auth_bootstrapped_v4"):
        return
    st.session_state["_auth_bootstrapped_v4"] = True
    if st.session_state.get("logged_in"):
        return
    payload = _verify_token(_read_cookie())
    if payload:
        st.session_state.update(
            logged_in=True,
            username=_username(payload["sub"]),
            auth_exp=int(payload["exp"]),
            last_seen=datetime.now(timezone.utc),
        )
    else:
        _delete_cookie()


def require_login() -> bool:
    if not _auth_secret():
        st.error("إعداد الأمان غير مكتمل: أضف AUTH_SECRET عشوائيًا بطول 32 حرفًا على الأقل.")
        st.stop()

    _bootstrap_session()
    now = datetime.now(timezone.utc)
    if st.session_state.get("logged_in"):
        expiry = int(st.session_state.get("auth_exp") or 0)
        last_seen = st.session_state.get("last_seen")
        idle_minutes = max(10, int(getattr(config, "SESSION_IDLE_MINUTES", 120) or 120))
        expired = expiry and int(time.time()) >= expiry
        idle = isinstance(last_seen, datetime) and now - last_seen > timedelta(minutes=idle_minutes)
        if expired or idle:
            logout_user()
            st.warning("انتهت الجلسة. سجّل الدخول من جديد.")
        else:
            st.session_state["last_seen"] = now
            return True

    st.markdown(
        """
        <div class="landing-hero">
          <div class="landing-title">📈 أصولي</div>
          <div class="landing-sub">إدارة المحافظ والتحليل المالي والفني وإدارة المخاطر.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    allow_registration = str(
        os.getenv(
            "ALLOW_REGISTRATION",
            str(getattr(config, "ALLOW_REGISTRATION", False)),
        )
    ).lower() in {"1", "true", "yes", "on"}

    labels = ["تسجيل الدخول"] + (["إنشاء حساب"] if allow_registration else [])
    tabs = st.tabs(labels)

    with tabs[0]:
        with st.form("login_form_v4", clear_on_submit=False):
            username = st.text_input("اسم المستخدم")
            password = st.text_input("كلمة المرور", type="password")
            remember = st.checkbox("تذكرني", value=True)
            submitted = st.form_submit_button("دخول", use_container_width=True)
        if submitted:
            ok, message = login_user(username, password, remember_me=remember)
            if ok:
                st.success(message)
                st.rerun()
            st.error(message)

    if allow_registration:
        with tabs[1]:
            with st.form("register_form_v4", clear_on_submit=False):
                new_username = st.text_input("اسم المستخدم الجديد")
                new_password = st.text_input("كلمة المرور الجديدة", type="password")
                submitted = st.form_submit_button("إنشاء الحساب", use_container_width=True)
            if submitted:
                ok, message = register_user(new_username, new_password)
                (st.success if ok else st.error)(message)
    else:
        st.caption("إنشاء الحسابات الجديدة مغلق افتراضيًا لأسباب أمنية.")

    return False


def login_system() -> bool:
    return require_login()
