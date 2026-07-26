import security_v2


def test_signed_token_round_trip(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "x" * 64)
    monkeypatch.setattr(security_v2, "db_user_exists", lambda username: username == "thamer")
    token = security_v2._make_token("thamer", 1)
    payload = security_v2._verify_token(token)
    assert payload is not None
    assert payload["sub"] == "thamer"


def test_registration_password_policy():
    ok, _ = security_v2._validate_password("123456", registration=True)
    assert not ok
    ok, _ = security_v2._validate_password("Strong-Pass-2026", registration=True)
    assert ok
