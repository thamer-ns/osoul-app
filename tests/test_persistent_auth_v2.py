from __future__ import annotations

import inspect
from types import SimpleNamespace

import persistent_auth
import security


class FakeSecrets(dict):
    pass


def _fake_streamlit(*, cookies=None, secrets=None, state=None, url="https://app.example"):
    return SimpleNamespace(
        session_state=dict(state or {}),
        secrets=FakeSecrets(secrets or {}),
        context=SimpleNamespace(cookies=dict(cookies or {}), url=url),
    )


def test_initial_request_cookie_restores_without_async_manager(monkeypatch):
    fake_st = _fake_streamlit(secrets={"AUTH_SECRET": "a" * 64})
    monkeypatch.setattr(persistent_auth, "st", fake_st)
    monkeypatch.setattr(security, "db_user_exists", lambda username: username == "thamer")

    token = persistent_auth.make_token("thamer", 30)
    fake_st.context.cookies[persistent_auth.COOKIE_NAME] = token
    monkeypatch.setattr(
        persistent_auth,
        "_fallback_cookie_snapshot",
        lambda: (_ for _ in ()).throw(
            AssertionError("the async cookie manager must not run when st.context is available")
        ),
    )

    assert persistent_auth.restore_cookie_session() is True
    assert fake_st.session_state["logged_in"] is True
    assert fake_st.session_state["username"] == "thamer"
    assert fake_st.session_state["auth_restored_from_cookie"] is True


def test_missing_auth_secret_derives_stable_key_from_database_url(monkeypatch):
    fake_st = _fake_streamlit(
        secrets={"DATABASE_URL": "postgresql://user:password@host/database"}
    )
    monkeypatch.setattr(persistent_auth, "st", fake_st)
    monkeypatch.setattr(
        security,
        "_load_or_create_runtime_auth_secret",
        lambda: (_ for _ in ()).throw(
            AssertionError("stable deployment seed should avoid a runtime-only key")
        ),
    )

    first = persistent_auth._stable_auth_secret()
    second = persistent_auth._stable_auth_secret()
    assert first == second
    assert len(first) == 64
    assert "password" not in first


def test_successful_login_writes_cookie_without_immediate_rerun(monkeypatch):
    fake_st = _fake_streamlit(secrets={"AUTH_SECRET": "b" * 64})
    monkeypatch.setattr(persistent_auth, "st", fake_st)
    monkeypatch.setattr(security, "_login_lock_remaining", lambda: 0)
    monkeypatch.setattr(security, "_validate_username", lambda username: (True, ""))
    monkeypatch.setattr(
        security,
        "_validate_password",
        lambda password, mode="login": (True, ""),
    )
    monkeypatch.setattr(security, "db_verify_user", lambda username, password: True)
    written = []
    monkeypatch.setattr(
        persistent_auth,
        "_write_login_cookie",
        lambda token, days: written.append((token, days)),
    )

    valid, _ = persistent_auth.login_user("thamer", "valid-password", remember_me=True)

    assert valid is True
    assert written and written[0][1] == 30
    assert fake_st.session_state["logged_in"] is True
    assert fake_st.session_state["_auth_cookie_write_pending"] is True
    assert "st.rerun" not in inspect.getsource(persistent_auth.login_user)


def test_cookie_writer_forces_full_reload_only_after_browser_assignment():
    source = inspect.getsource(persistent_auth._render_cookie_script)
    assignment_position = source.index("document.cookie")
    reload_position = source.index("window.parent.location.reload")
    assert assignment_position < reload_position
    assert "450" in source


def test_logout_clears_v5_bootstrap_state(monkeypatch):
    fake_st = _fake_streamlit(
        secrets={"AUTH_SECRET": "c" * 64},
        state={
            "logged_in": True,
            "username": "thamer",
            "_auth_cookie_checked_v5": True,
            "_auth_cookie_write_pending": True,
        },
    )
    monkeypatch.setattr(persistent_auth, "st", fake_st)
    monkeypatch.setattr(persistent_auth, "_delete_login_cookies", lambda: None)

    persistent_auth.logout_user()

    assert "logged_in" not in fake_st.session_state
    assert "username" not in fake_st.session_state
    assert "_auth_cookie_checked_v5" not in fake_st.session_state
    assert "_auth_cookie_write_pending" not in fake_st.session_state
