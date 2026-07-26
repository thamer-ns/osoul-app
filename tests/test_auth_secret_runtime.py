from __future__ import annotations

import stat

import security


def test_runtime_auth_secret_is_stable_and_private(tmp_path, monkeypatch):
    secret_path = tmp_path / "state" / "auth_secret"
    monkeypatch.setenv("OSOUL_AUTH_SECRET_FILE", str(secret_path))
    monkeypatch.setattr(security, "_configured_auth_secret", lambda: "")
    monkeypatch.setattr(security, "_RUNTIME_AUTH_SECRET", None)

    first = security._auth_secret()
    second = security._auth_secret()

    assert first == second
    assert len(first) >= 64
    assert secret_path.read_text(encoding="utf-8") == first
    assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600

    monkeypatch.setattr(security, "_RUNTIME_AUTH_SECRET", None)
    assert security._auth_secret() == first


def test_configured_auth_secret_takes_precedence(tmp_path, monkeypatch):
    secret_path = tmp_path / "state" / "auth_secret"
    configured = "A" * 64
    monkeypatch.setenv("OSOUL_AUTH_SECRET_FILE", str(secret_path))
    monkeypatch.setattr(security, "_configured_auth_secret", lambda: configured)
    monkeypatch.setattr(security, "_RUNTIME_AUTH_SECRET", None)

    assert security._auth_secret() == configured
    assert not secret_path.exists()
