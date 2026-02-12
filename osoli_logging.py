# osoli_logging.py
"""Centralized logging utilities for Osoli.

- Avoids silent failures (except: pass) by logging exceptions.
- Works both inside and outside Streamlit.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

_LOGGER_NAME = "osoli"
# ============================================================
# Redaction (avoid leaking secrets in logs/UI)
# ============================================================

_REDACT_PATTERNS = [
    # postgres URLs with password: postgresql://user:pass@host/db -> postgresql://user:***@host/db
    (re.compile(r'(?i)(postgres(?:ql)?://[^\s:/@]+:)([^@\s]+)(@)'), r'\1***\3'),
    # common key=value secrets
    (re.compile(r'(?i)(AUTH_SECRET\s*[:=]\s*)([^\s\n\r]+)'), r'\1***'),
    (re.compile(r'(?i)(TWELVEDATA_API_KEY\s*[:=]\s*)([^\s\n\r]+)'), r'\1***'),
    (re.compile(r'(?i)(DATABASE_URL\s*[:=]\s*)([^\s\n\r]+)'), r'\1***'),
]

def redact_text(text: str) -> str:
    """Best-effort redaction for secrets in text."""
    s = str(text or "")
    for pat, rep in _REDACT_PATTERNS:
        s = pat.sub(rep, s)
    return s


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact_text(record.msg)
            if record.args:
                if isinstance(record.args, tuple):
                    record.args = tuple(redact_text(a) for a in record.args)
                else:
                    record.args = redact_text(record.args)
        except Exception:
            pass
        return True

def get_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    # Basic configuration (stdout)
    level_name = (os.getenv("OSOLI_LOG_LEVEL") or "INFO").upper().strip()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    handler = logging.StreamHandler()
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    handler.addFilter(RedactionFilter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_exception(exc: BaseException, context: str = "", *, level: str = "ERROR") -> None:
    """Log an exception with optional context.

    level: ERROR | WARNING | INFO | DEBUG
    """
    logger = get_logger()
    lvl = getattr(logging, (level or "ERROR").upper().strip(), logging.ERROR)
    if context:
        logger.log(lvl, context, exc_info=exc)
    else:
        logger.log(lvl, "Unhandled exception", exc_info=exc)


def streamlit_alert(message: str, details: Optional[str] = None, *, kind: str = "warning") -> None:
    """Best-effort Streamlit alert. No-op if Streamlit isn't available."""
    try:
        import streamlit as st  # type: ignore
        fn = getattr(st, kind, None) or st.warning
        if details:
            fn(message)
            with st.expander("التفاصيل", expanded=False):
                st.code(redact_text(details))
        else:
            fn(message)
    except Exception:
        # Outside Streamlit or alert failed -> just log.
        get_logger().warning("%s%s", message, f" | {details}" if details else "")
