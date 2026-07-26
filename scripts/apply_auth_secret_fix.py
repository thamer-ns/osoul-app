"""Apply the runtime AUTH_SECRET fallback and its regression tests."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECURITY = ROOT / "security.py"
TEST_FILE = ROOT / "tests" / "test_auth_secret_runtime.py"


def main() -> None:
    text = SECURITY.read_text(encoding="utf-8")

    text = text.replace(
        "import html\nimport os\n",
        "import html\nimport logging\nimport os\n",
        1,
    )
    text = text.replace(
        "import time\nfrom typing import Optional\n",
        "import time\nfrom pathlib import Path\nfrom typing import Optional\n",
        1,
    )

    old = '''def _auth_secret() -> str:
    value = ""
    try:
        value = str(st.secrets.get("AUTH_SECRET", "") or "")
    except Exception:
        value = ""
    value = value or os.getenv("AUTH_SECRET", "")
    if len(value) >= 32:
        return value
    allow_dev = os.getenv("OSOUL_ALLOW_EPHEMERAL_AUTH_SECRET", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if allow_dev:
        if "_ephemeral_auth_secret" not in st.session_state:
            st.session_state["_ephemeral_auth_secret"] = secrets.token_urlsafe(48)
        return str(st.session_state["_ephemeral_auth_secret"])
    raise RuntimeError("AUTH_SECRET غير مضبوط أو أقصر من 32 حرفًا")
'''

    new = '''_RUNTIME_AUTH_SECRET: Optional[str] = None


def _configured_auth_secret() -> str:
    """Read a persistent secret from Streamlit Secrets or the environment."""
    value = ""
    try:
        value = str(st.secrets.get("AUTH_SECRET", "") or "").strip()
    except Exception:
        value = ""
    return value or str(os.getenv("AUTH_SECRET", "") or "").strip()


def _runtime_auth_secret_path() -> Path:
    configured = str(os.getenv("OSOUL_AUTH_SECRET_FILE", "") or "").strip()
    if configured:
        return Path(configured).expanduser()
    state_home = str(os.getenv("XDG_STATE_HOME", "") or "").strip()
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return base / "osoul" / "auth_secret"


def _read_runtime_auth_secret(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    except OSError:
        logging.getLogger(__name__).warning(
            "Could not read the runtime auth secret file",
            exc_info=True,
        )
        return ""
    if len(value) < 32:
        logging.getLogger(__name__).warning(
            "Ignoring an invalid runtime auth secret file at %s",
            path,
        )
        return ""
    try:
        os.chmod(path, 0o600)
    except OSError:
        logging.getLogger(__name__).debug(
            "Could not tighten runtime auth secret permissions",
            exc_info=True,
        )
    return value


def _load_or_create_runtime_auth_secret() -> str:
    """Return one server-wide random secret without committing it to Git."""
    global _RUNTIME_AUTH_SECRET
    if _RUNTIME_AUTH_SECRET and len(_RUNTIME_AUTH_SECRET) >= 32:
        return _RUNTIME_AUTH_SECRET

    path = _runtime_auth_secret_path()
    existing = _read_runtime_auth_secret(path)
    if existing:
        _RUNTIME_AUTH_SECRET = existing
        return existing

    generated = secrets.token_urlsafe(64)
    try:
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            logging.getLogger(__name__).debug(
                "Could not tighten runtime auth state directory permissions",
                exc_info=True,
            )
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(generated)
        _RUNTIME_AUTH_SECRET = generated
        logging.getLogger(__name__).warning(
            "AUTH_SECRET is not configured; generated a private runtime secret. "
            "Persistent login cookies will reset if the hosting filesystem is replaced."
        )
        return generated
    except FileExistsError:
        existing = _read_runtime_auth_secret(path)
        if existing:
            _RUNTIME_AUTH_SECRET = existing
            return existing
    except OSError:
        logging.getLogger(__name__).warning(
            "Could not persist the generated runtime auth secret; using a process-wide secret",
            exc_info=True,
        )

    _RUNTIME_AUTH_SECRET = generated
    return generated


def _auth_secret() -> str:
    value = _configured_auth_secret()
    if len(value) >= 32:
        return value
    if value:
        logging.getLogger(__name__).warning(
            "Configured AUTH_SECRET is shorter than 32 characters and was ignored"
        )
    return _load_or_create_runtime_auth_secret()
'''

    if old not in text:
        if new in text:
            print("security.py already repaired")
        else:
            raise RuntimeError("Expected _auth_secret block was not found")
    else:
        text = text.replace(old, new, 1)
        SECURITY.write_text(text, encoding="utf-8")

    TEST_FILE.write_text(
        '''from __future__ import annotations

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
''',
        encoding="utf-8",
    )
    print("AUTH_SECRET runtime fallback applied")


if __name__ == "__main__":
    main()
