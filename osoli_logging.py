"""
osoli_logging.py
Logging utilities with automatic redaction for secrets/credentials.

- Keeps existing API: setup_logger(), log_exception()
- Adds: redact_text(), RedactionFilter, get_logger()
"""
from __future__ import annotations

import logging
import os
import re
import traceback
from typing import Optional, Iterable, Pattern

# --- Redaction ---------------------------------------------------------------

_DEFAULT_PATTERNS: list[tuple[Pattern[str], str]] = [
    # postgresql://user:pass@host -> postgresql://user:***@host
    (re.compile(r"(postgres(?:ql)?://[^:\s/]+:)([^@\s]+)(@)", re.IGNORECASE), r"\1***\3"),
    # Anything like password=... or pwd: ...
    (re.compile(r"(?i)(password\s*[=:]\s*)([^\s,;]+)"), r"\1***"),
    (re.compile(r"(?i)(pwd\s*[=:]\s*)([^\s,;]+)"), r"\1***"),
    # Common env keys
    (re.compile(r"(?i)(AUTH_SECRET\s*[=:]\s*)([^\s,;]+)"), r"\1***"),
    (re.compile(r"(?i)(TWELVEDATA_API_KEY\s*[=:]\s*)([^\s,;]+)"), r"\1***"),
    (re.compile(r"(?i)(DATABASE_URL\s*[=:]\s*)([^\s,;]+)"), r"\1***"),
    # JWT-like tokens / long api keys
    (re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_-]{24,}(?![A-Za-z0-9])"), "***"),
]

def redact_text(text: object, extra_patterns: Optional[Iterable[tuple[Pattern[str], str]]] = None) -> str:
    """Redact secrets from arbitrary text."""
    s = "" if text is None else str(text)
    patterns = list(_DEFAULT_PATTERNS)
    if extra_patterns:
        patterns.extend(list(extra_patterns))
    for rx, repl in patterns:
        try:
            s = rx.sub(repl, s)
        except Exception:
            # Never let logging crash the app
            continue
    return s


class RedactionFilter(logging.Filter):
    """Redacts record.msg and rendered message."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            # Render message, redact it, then store back in record.msg
            msg = record.getMessage()
            msg = redact_text(msg)
            record.msg = msg
            record.args = ()
        except Exception:
            pass
        return True


# --- Logger setup ------------------------------------------------------------

_LOGGER_NAME_DEFAULT = "osoul"
_LOGGER: Optional[logging.Logger] = None


def setup_logger(name: str = _LOGGER_NAME_DEFAULT, log_file: Optional[str] = None) -> logging.Logger:
    """Create/retrieve a configured logger (idempotent)."""
    global _LOGGER
    logger = logging.getLogger(name)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

    # Avoid duplicate handlers on reruns
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler()
        fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        handler.addFilter(RedactionFilter())
        logger.addHandler(handler)

    # Optional file handler
    if log_file and not any(getattr(h, "baseFilename", None) == log_file for h in logger.handlers):
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        fh.setFormatter(logging.Formatter(fmt))
        fh.addFilter(RedactionFilter())
        logger.addHandler(fh)

    logger.propagate = False
    _LOGGER = logger
    return logger


def get_logger() -> logging.Logger:
    """Get default logger."""
    global _LOGGER
    if _LOGGER is None:
        _LOGGER = setup_logger(_LOGGER_NAME_DEFAULT)
    return _LOGGER


def log_exception(logger: Optional[logging.Logger], msg: str, exc: BaseException) -> None:
    """Log exception with redaction + traceback."""
    lg = logger or get_logger()
    safe_msg = redact_text(msg)
    safe_exc = redact_text(exc)
    tb = redact_text(traceback.format_exc())
    lg.error(f"{safe_msg}: {safe_exc}\n{tb}")
