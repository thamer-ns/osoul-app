"""Strong password storage with one-time legacy hash migration."""
from __future__ import annotations

import hashlib
import hmac
import re


def install_database_security_hardening() -> None:
    try:
        import bcrypt
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("bcrypt مطلوب لتشغيل نظام الحسابات بأمان") from exc

    import database

    if getattr(database, "_bcrypt_hardening_installed", False):
        return

    def hash_password(password: str) -> str:
        if not isinstance(password, str) or not password:
            raise ValueError("كلمة المرور فارغة")
        return bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(rounds=12),
        ).decode("utf-8")

    def check_bcrypt(password: str, password_hash: str) -> bool:
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

    def verify_user_and_migrate(username: str, password: str) -> bool:
        database.ensure_users_table()
        connection, kind = database.get_connection()
        try:
            cursor = connection.cursor()
            columns = database._users_columns()
            password_column = (
                "password_hash"
                if "password_hash" in columns
                else "password"
                if "password" in columns
                else "password_hash"
            )
            placeholder = "%s" if kind == "postgres" else "?"
            cursor.execute(
                f"SELECT {password_column} FROM users "
                f"WHERE username={placeholder} LIMIT 1",
                (str(username),),
            )
            row = cursor.fetchone()
            if not row:
                return False
            stored = str(row[0] if isinstance(row, (tuple, list)) else row or "")
            if check_bcrypt(password, stored):
                return True

            is_legacy_sha = bool(re.fullmatch(r"[0-9a-fA-F]{64}", stored))
            if not is_legacy_sha:
                return False
            candidate = hashlib.sha256(str(password).encode("utf-8")).hexdigest()
            if not hmac.compare_digest(candidate.lower(), stored.lower()):
                return False

            upgraded = hash_password(str(password))
            cursor.execute(
                f"UPDATE users SET {password_column}={placeholder} "
                f"WHERE username={placeholder} AND {password_column}={placeholder}",
                (upgraded, str(username), stored),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return False
            connection.commit()
            return True
        except Exception:
            try:
                connection.rollback()
            except Exception:
                import logging
                logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)
            return False
        finally:
            database.put_connection(connection, kind)

    database._hash_password = hash_password
    database._check_password = check_bcrypt
    database.db_verify_user = verify_user_and_migrate
    database._bcrypt_hardening_installed = True
