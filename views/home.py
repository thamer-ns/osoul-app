"""Main page composition."""
from __future__ import annotations


def view_home(finance) -> None:
    from views.dashboard import view_dashboard
    from views.owned_stocks import render_owned_stocks

    view_dashboard(finance)
    render_owned_stocks(finance)
