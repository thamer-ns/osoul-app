"""Remove the legacy unsalted SHA-256 password fallback at runtime."""
from __future__ import annotations


def install_database_security_hardening() -> None:
    try:
        import bcrypt
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("bcrypt مطلوب لتشغيل نظام الحسابات بأمان") from exc

    import database

    def hash_password(password: str) -> str:
        if not isinstance(password, str) or not password:
            raise ValueError("كلمة المرور فارغة")
        return bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(rounds=12),
        ).decode("utf-8")

    def check_password(password: str, password_hash: str) -> bool:
        stored = str(password_hash or "")
        if not stored.startswith(("$2a$", "$2b$", "$2y$")):
            return False
        try:
            return bool(
                bcrypt.checkpw(
                    str(password).encode("utf-8"),
                    stored.encode("utf-8"),
                )
            )
        except Exception:
            return False

    database._hash_password = hash_password
    database._check_password = check_password
