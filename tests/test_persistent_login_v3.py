from __future__ import annotations

import inspect
from types import SimpleNamespace

import persistent_auth_v3 as auth
import security


class FakeSecrets(dict):
    pass


def _fake_streamlit(*, cookies=None, state=None):
    return SimpleNamespace(
        session_state=dict(state or {}),
        secrets=FakeSecrets({"AUTH_SECRET": "z" * 64}),
        context=SimpleNamespace(
            cookies=dict(cookies or {}),
            url="https://app.example",
        ),
    )


def test_login_opens_session_without_rerun_or_reload(monkeypatch):
    fake_st = _fake_streamlit()
    monkeypatch.setattr(auth, "st", fake_st)
    monkeypatch.setattr(security, "_login_lock_remaining", lambda: 0)
    monkeypatch.setattr(
        security,
        "_validate_username",
        lambda username: (True, ""),
    )
    monkeypatch.setattr(
        security,
        "_validate_password",
        lambda password, mode="login": (True, ""),
    )
    monkeypatch.setattr(
        security,
        "db_verify_user",
        lambda username, password: True,
    )

    valid, _ = auth.login_user(
        "thamer",
        "valid-password",
        remember_me=True,
    )

    assert valid is True
    assert fake_st.session_state["logged_in"] is True
    assert fake_st.session_state["username"] == "thamer"
    pending = fake_st.session_state["_auth_cookie_pending_v6"]
    assert pending["days"] == 30
    assert "st.rerun" not in inspect.getsource(auth.login_user)
    assert "location.reload" not in inspect.getsource(auth)


def test_cookie_writer_has_no_async_manager_and_no_forced_navigation(monkeypatch):
    fake_st = _fake_streamlit(
        state={
            "_auth_cookie_pending_v6": {
                "token": "signed-token",
                "days": 30,
            }
        }
    )
    monkeypatch.setattr(auth, "st", fake_st)
    rendered = []
    monkeypatch.setattr(
        auth.components,
        "html",
        lambda html, **kwargs: rendered.append((html, kwargs)),
    )

    auth._flush_login_cookie()

    assert rendered
    html = rendered[0][0]
    assert auth.COOKIE_NAME in html
    assert "document.cookie" in html
    assert "window.parent.document.cookie" in html
    assert "location.reload" not in html
    assert "CookieManager" not in inspect.getsource(auth._flush_login_cookie)
    assert "_auth_cookie_pending_v6" not in fake_st.session_state


def test_real_refresh_restores_from_initial_request_cookie(monkeypatch):
    fake_st = _fake_streamlit()
    monkeypatch.setattr(auth, "st", fake_st)
    monkeypatch.setattr(
        security,
        "db_user_exists",
        lambda username: username == "thamer",
    )

    token = auth.make_token("thamer", 30)
    fake_st.context.cookies[auth.COOKIE_NAME] = token

    assert auth.restore_cookie_session() is True
    assert fake_st.session_state["logged_in"] is True
    assert fake_st.session_state["username"] == "thamer"
    assert fake_st.session_state["auth_restored_from_cookie"] is True


def test_logout_defers_cookie_component_until_logged_out_render(monkeypatch):
    fake_st = _fake_streamlit(
        state={
            "logged_in": True,
            "username": "thamer",
            "auth_exp": 9_999_999_999,
            "_auth_cookie_checked_v6": True,
        }
    )
    monkeypatch.setattr(auth, "st", fake_st)
    rendered = []
    monkeypatch.setattr(
        auth.components,
        "html",
        lambda html, **kwargs: rendered.append((html, kwargs)),
    )

    auth.logout_user()

    assert rendered == []
    assert "logged_in" not in fake_st.session_state
    assert fake_st.session_state["_auth_cookie_delete_pending_v6"] is True

    assert auth._flush_logout_cookie() is True
    assert rendered
    assert "Max-Age=0" in rendered[0][0]
    assert "_auth_cookie_delete_pending_v6" not in fake_st.session_state
