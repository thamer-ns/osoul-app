#views/analysis/technical.py
import streamlit as st
from views.shared import _sym_key, _render_tv_like_chart, _render_technical_chart_flex

def render_technical_tab(sym: str):
    symk = _sym_key(sym)

    period_opts = {
        "6 أشهر": "6mo",
        "سنة": "1y",
        "سنتين": "2y",
        "5 سنوات": "5y",
        "10 سنوات": "10y",
        "الحد الأقصى": "max",
    }
    interval_opts = {
        "يومي 1D": "1d",
        "أسبوعي 1W": "1wk",
        "شهري 1M": "1mo",
        "ساعة 1H": "1h",
        "30 دقيقة": "30m",
        "15 دقيقة": "15m",
    }

    c_p, c_i, c_mode = st.columns([1.2, 1.2, 1.6])
    p_label = c_p.selectbox("الفترة (Period)", list(period_opts.keys()), index=2, key=f"tech_p_{symk}")
    i_label = c_i.selectbox("الفاصل (Interval)", list(interval_opts.keys()), index=0, key=f"tech_i_{symk}")

    mode = c_mode.radio(
        "وضع الشارت",
        ["احترافي", "قديم (Fallback)"],
        horizontal=True,
        key=f"tech_mode_{symk}"
    )

    if mode == "احترافي":
        _render_tv_like_chart(sym, period_opts[p_label], interval_opts[i_label])
    else:
        _render_technical_chart_flex(sym, period=period_opts[p_label], interval=interval_opts[i_label])
