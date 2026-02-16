#excptions.py
# coding: utf-8
"""Compatibility module.

The vendored SDK historically shipped `excptions.py` (typo) while internal
imports use `exceptions.py`. Keep both paths working.
"""

from .excptions import (  # noqa: F401
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
__all__ = (
    "TwelveDataError",
    "BadRequestError",
    "InternalServerError",
    "InvalidApiKeyError",
)


class TwelveDataError(RuntimeError):
    pass


class BadRequestError(TwelveDataError):
    pass


class InternalServerError(TwelveDataError):
    pass


class InvalidApiKeyError(TwelveDataError):
    pass
