# coding: utf-8
"""twelvedata.exceptions

Fix for vendored Twelve Data SDK.

The upstream SDK expects this module to exist. In this repo we previously had a
misspelled file name (`excptions.py`) which breaks imports on case-sensitive
systems and causes runtime failures.

We keep `excptions.py` as a backward-compatible alias.
"""


class TwelveDataError(Exception):
    """Base exception for Twelvedata SDK compatibility."""


class InvalidApiKeyError(TwelveDataError):
    """Raised when API key is missing/invalid (401)."""


class BadRequestError(TwelveDataError):
    """Raised for request validation errors (400)."""


class InternalServerError(TwelveDataError):
    """Raised for server-side errors (5xx)."""
