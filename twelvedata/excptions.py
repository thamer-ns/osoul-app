# coding: utf-8
"""Backward-compatible alias.

This project vendors parts of the Twelve Data Python SDK.
Upstream code imports `twelvedata.exceptions`, but an older vendored copy used a
misspelled file name: `excptions.py`.

Keep this module so any legacy imports keep working.
"""

from .exceptions import *  # noqa: F401,F403
