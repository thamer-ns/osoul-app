# coding: utf-8
"""Compatibility shim for typoed legacy module name.

Some vendored copies shipped the exceptions module as ``excptions.py``.
This file preserves imports that expect ``twelvedata.exceptions``.
"""

from .excptions import (
    TwelveDataError,
    BadRequestError,
    InternalServerError,
    InvalidApiKeyError,
)

__all__ = (
    "TwelveDataError",
    "BadRequestError",
    "InternalServerError",
    "InvalidApiKeyError",
)
