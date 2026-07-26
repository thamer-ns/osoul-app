"""Compatibility wrapper for the Osoli v2 portfolio pages.

The previous implementation contained an indentation error on the default
branch. All callers now use the stable, user-scoped implementation.
"""
from views.portfolio_v2 import render_pulse_dashboard, view_add_trade, view_portfolio

__all__ = ["view_portfolio", "render_pulse_dashboard", "view_add_trade"]
