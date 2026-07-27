from __future__ import annotations

from types import SimpleNamespace

import security


class FakeCookieManager:
    def __init__(self, cookies=None):
        self.cookies = dict(cookies or {})
        self.set_calls = []
        self.deleted = []

    def set(self, *args, **kwargs):
        self.set_calls.append((args, kwargs))


def _fake_streamlit(initial=None):
    return SimpleNamespace(session_state=dict(initial or {}))


def test_refresh_waits_for_cookie_component_then_restores_session(monkeypatch):
    cookie_value = f"{security.TOKEN_COOKIE}-fixture"
    manager = FakeCookieManager({security.TOKEN_COOKIE: cookie_value})
    fake_st = _fake_streamlit({"_auth_cookie_manager_warmup": True})

    monkeypatch.setattr(security, "st", fake_st)
    monkeypatch.setattr(security, "_cookie_manager", lambda: manager)
    monkeypatch.setattr(
        security,
        "_verify_token",
        lambda value: ("thamer", 9_999_999_999) if value == cookie_value else None,
    )

    # Constructor run: do not permanently record an empty/early cookie result.
    assert security._bootstrap_cookie_session() is False
    assert "_auth_cookie_checked" not in fake_st.session_state

    # Browser-component rerun: the signed cookie restores the login.
    assert security._bootstrap_cookie_session() is True
    assert fake_st.session_state["logged_in"] is True
    assert fake_st.session_state["username"] == "thamer"
    assert fake_st.session_state["auth_restored_from_cookie"] is True


def test_absent_cookie_is_final_only_after_component_is_ready(monkeypatch):
    manager = FakeCookieManager({})
    fake_st = _fake_streamlit({"_auth_cookie_manager_warmup": True})
    monkeypatch.setattr(security, "st", fake_st)
    monkeypatch.setattr(security, "_cookie_manager", lambda: manager)

    assert security._bootstrap_cookie_session() is False
    assert "_auth_cookie_checked" not in fake_st.session_state

    assert security._bootstrap_cookie_session() is False
    assert fake_st.session_state["_auth_cookie_checked"] is True
    assert not fake_st.session_state.get("logged_in", False)


def test_logout_clears_cookie_bootstrap_state(monkeypatch):
    fake_st = _fake_streamlit(
        {
            "logged_in": True,
            "username": "thamer",
            "_auth_cookie_checked": True,
            "_auth_cookie_manager_warmup": True,
            "auth_restored_from_cookie": True,
        }
    )
    monkeypatch.setattr(security, "st", fake_st)
    monkeypatch.setattr(security, "_cookie_manager", lambda: None)

    security.logout_user()

    assert "logged_in" not in fake_st.session_state
    assert "_auth_cookie_checked" not in fake_st.session_state
    assert "_auth_cookie_manager_warmup" not in fake_st.session_state
    assert "auth_restored_from_cookie" not in fake_st.session_state
