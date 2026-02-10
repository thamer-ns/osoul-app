# technical_indicators/__init__.py
# -*- coding: utf-8 -*-

"""
Technical Indicators package.

This module hosts optional, advanced indicators that can be used by:
- views/analysis/technical.py (UI display)
- ai_engine_core/packs.py (AI Engine packs)
"""

from .advanced import compute_advanced_technical_pack  # noqa: F401
