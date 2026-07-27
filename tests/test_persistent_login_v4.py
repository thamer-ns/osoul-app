from __future__ import annotations

import inspect
from types import SimpleNamespace

import persistent_auth_v4 as base
import persistent_auth_v5 as auth
import security


class FakeSecrets(dict):
    pass


class FakeManager:
    def __init__(self, cookies=None, on_set=None):
        self.cookies = dict(cookies or {})
        self.calls = []
        self.on_set = on_set

    def set(self, **kwargs):
        if self.on_set is not None:
            self.on_set(kwargs)
        self.calls.append(kwargs)
        self.cookies[str(kwargs["cookie"])] = str(kwargs["val"])


def _fake_streamlit(*, cookies=None, state=None):
    return SimpleNamespace(
        session_state=dict(state or {}),
        secrets=FakeSecrets({"AUTH_SECRET": "k" * 64}),
        context=SimpleNamespace(
            cookies=dict(cookies or {}),
            url="https://app.example",
        ),
    )


def _allow_login(monkeypatch):
    monkeypatch.setattr(security, "_login_lock_remaining", lambda: 0)
    monkeypatch.setattr(security, "_validate_username", lambda username: (True, ""))
    monkeypatch.setattr(
        security,
        "_validate_password",
        lambda password, mode="login": (True, ""),
    )
    monkeypatch.setattr(security, "db_verify_user", lambda username, password: True)


def test_python_session_is_committed_before_cookie_component_can_rerun(monkeypatch):
    fake_st = _fake_streamlit()
    monkeypatch.setattr(base, "st", fake_st)
    _allow_login(monkeypatch)

    def assert_session_already_active(_kwargs):
        assert fake_st.session_state["logged_in"] is True
        assert fake_st.session_state["username"] == "thamer"
        assert fake_st.session_state["_auth_cookie_checked_v7"] is True

    manager = FakeManager(on_set=assert_session_already_active)
    valid, _ = auth.login_user(
        "thamer",
        "valid-password",
        remember_me=True,
        manager=manager,
    )

    assert valid is True
    assert fake_st.session_state["_auth_cookie_persisted_v7"] is True
    assert manager.calls[0]["cookie"] == base.COOKIE_NAME
    assert manager.calls[0]["path"] == "/"
    assert manager.calls[0]["secure"] is True
    assert manager.calls[0]["same_site"] == "lax"
    assert manager.calls[0]["max_age"] == 30 * 86400


def test_refresh_restores_v7_cookie_from_initial_request(monkeypatch):
    fake_st = _fake_streamlit()
    monkeypatch.setattr(base, "st", fake_st)
    monkeypatch.setattr(security, "db_user_exists", lambda username: username == "thamer")

    token = base.make_token("thamer", 30)
    fake_st.context.cookies[base.COOKIE_NAME] = token

    assert base.restore_cookie_session(FakeManager()) is True
    assert fake_st.session_state["logged_in"] is True
    assert fake_st.session_state["username"] == "thamer"
    assert fake_st.session_state["auth_restored_from_cookie"] is True


def test_empty_cookie_component_gets_one_warmup_cycle(monkeypatch):
    fake_st = _fake_streamlit()
    monkeypatch.setattr(base, "st", fake_st)
    manager = FakeManager()

    assert base._component_snapshot(manager) is None
    assert fake_st.session_state["_auth_cookie_component_seen_v7"] is True
    assert base._component_snapshot(manager) == {}


def test_login_screen_is_removed_without_persistent_success_banner():
    source = inspect.getsource(base._render_login)
    assert "auth_slot.empty()" in source
    assert "success_message" not in source
    assert "location.reload" not in inspect.getsource(base)
    assert "document.cookie" not in inspect.getsource(base)


def test_failed_cookie_write_rolls_back_provisional_session(monkeypatch):
    fake_st = _fake_streamlit()
    monkeypatch.setattr(base, "st", fake_st)
    _allow_login(monkeypatch)
    monkeypatch.setattr(base, "_set_cookie", lambda manager, token, days: False)

    valid, _ = auth.login_user(
        "thamer",
        "valid-password",
        remember_me=True,
        manager=FakeManager(),
    )

    assert valid is False
    assert "logged_in" not in fake_st.session_state
    assert "username" not in fake_st.session_state
