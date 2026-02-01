# ui/pages/analysis/technical_tab.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ui.common import sym_key as _sym_key
from market_data import get_chart_history

# fallback charts
try:
    from charts import render_technical_chart
except Exception:
    def render_technical_chart(symbol, *args, **kwargs):
        st.warning("⚠️ ملف charts.py مفقود أو به خطأ.")


def _get_chart_history_flex(symbol: str, period: str, interval: str):
    try:
        return get_chart_history(symbol, period=period, interval=interval)
    except TypeError:
        try:
            return get_chart_history(symbol, period)
        except TypeError:
            return get_chart_history(symbol)


def _build_tv_like_plot(df: pd.DataFrame, title: str = "") -> go.Figure:
    d = df.copy()

    if "date" in d.columns:
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d = d.dropna(subset=["date"]).sort_values("date")
        x = d["date"]
    else:
        try:
            d.index = pd.to_datetime(d.index, errors="coerce")
        except Exception:
            pass
        d = d[~pd.isna(d.index)]
        d = d.sort_index()
        x = d.index

    colmap = {str(c).lower(): c for c in d.columns}
    Open = colmap.get("open") if "open" in colmap else ("Open" if "Open" in d.columns else None)
    High = colmap.get("high") if "high" in colmap else ("High" if "High" in d.columns else None)
    Low  = colmap.get("low") if "low" in colmap else ("Low" if "Low" in d.columns else None)
    Close= colmap.get("close") if "close" in colmap else ("Close" if "Close" in d.columns else None)
    Vol  = colmap.get("volume") if "volume" in colmap else ("Volume" if "Volume" in d.columns else None)

    if not all([Open, High, Low, Close]):
        raise ValueError("بيانات الشارت لا تحتوي أعمدة OHLC بشكل صحيح.")

    for c in [Open, High, Low, Close]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if Vol and Vol in d.columns:
        d[Vol] = pd.to_numeric(d[Vol], errors="coerce").fillna(0)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25]
    )

    fig.add_trace(
        go.Candlestick(
            x=x,
            open=d[Open], high=d[High], low=d[Low], close=d[Close],
            name="OHLC",
        ),
        row=1, col=1
    )

    if Vol and Vol in d.columns:
        fig.add_trace(
            go.Bar(x=x, y=d[Vol], name="Volume"),
            row=2, col=1
        )

    fig.update_layout(
        title=title,
        height=720,
        margin=dict(l=10, r=10, t=50, b=10),
        xaxis=dict(
            rangeslider=dict(visible=True),
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            showline=True,
        ),
        xaxis2=dict(
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
        ),
        yaxis=dict(
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            fixedrange=False
        ),
        yaxis2=dict(
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            fixedrange=False
        ),
        hovermode="x unified",
        dragmode="pan",
        showlegend=False,
    )

    fig.update_xaxes(
        rangeselector=dict(
            buttons=list([
                dict(count=7, label="7D", step="day", stepmode="backward"),
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=3, label="3M", step="month", stepmode="backward"),
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="1Y", step="year", stepmode="backward"),
                dict(step="all", label="All"),
            ])
        )
    )

    return fig


def _render_tv_like_chart(symbol: str, period: str, interval: str):
    with st.spinner("جاري جلب بيانات الشارت..."):
        df = _get_chart_history_flex(symbol, period, interval)

    if df is None:
        st.error("❌ لم يتم جلب بيانات الشارت.")
        return

    if not isinstance(df, pd.DataFrame):
        try:
            df = pd.DataFrame(df)
        except Exception:
            st.error("❌ البيانات غير قابلة للتحويل إلى DataFrame.")
            return

    if df.empty:
        st.warning("⚠️ البيانات فارغة (جرّب فترة أكبر).")
        return

    if "date" not in df.columns:
        try:
            if isinstance(df.index, pd.DatetimeIndex):
                df = df.reset_index().rename(columns={"index": "date"})
        except Exception:
            pass

    try:
        fig = _build_tv_like_plot(df, title=f"{symbol} | {period} | {interval}")
        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "scrollZoom": True,
                "displaylogo": False,
                "displayModeBar": True,
                "modeBarButtonsToAdd": ["drawline", "drawopenpath", "drawrect", "drawcircle", "eraseshape"],
            },
        )
        st.caption("💡 تلميح: اسحب للتحريك (Pan)، و Scroll للتكبير/التصغير، و Range Slider للتنقل.")
    except Exception as e:
        st.error(f"❌ فشل بناء الشارت الاحترافي: {e}")
        st.info("سأعرض الشارت القديم كخطة بديلة.")
        try:
            render_technical_chart(symbol, period=period, interval=interval)
        except TypeError:
            render_technical_chart(symbol, period)


def render_technical_tab(symbol: str):
    symk = _sym_key(symbol)

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
        _render_tv_like_chart(symbol, period_opts[p_label], interval_opts[i_label])
    else:
        try:
            render_technical_chart(symbol, period=period_opts[p_label], interval=interval_opts[i_label])
        except TypeError:
            render_technical_chart(symbol, period_opts[p_label])
