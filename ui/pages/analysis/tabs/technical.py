# ui/pages/analysis/tabs/technical.py
import streamlit as st
import traceback


def _render_technical_chart_flex(symbol: str, period: str = "2y", interval: str = "1d"):
    """
    يحاول تشغيل charts.render_technical_chart بأي توقيع متاح.
    """
    try:
        from charts import render_technical_chart
    except Exception:
        render_technical_chart = None

    if not callable(render_technical_chart):
        st.warning("⚠️ charts.py غير متاح أو render_technical_chart غير موجود.")
        return

    try:
        return render_technical_chart(symbol, period=period, interval=interval)
    except TypeError:
        try:
            return render_technical_chart(symbol, period=period)
        except TypeError:
            try:
                return render_technical_chart(symbol, period)
            except TypeError:
                return render_technical_chart(symbol)


def _call_first_available(mod, names, *args, **kwargs):
    for n in names:
        fn = getattr(mod, n, None)
        if callable(fn):
            fn(*args, **kwargs)
            return True
    return False


def render(fin, sym: str, symk: str):
    st.subheader("📈 التحليل الفني")

    # 1) حاول ui/pages/analysis/technical_tab.py (قديم عندك غالباً)
    try:
        from ui.pages.analysis import technical_tab as legacy_tech
        ok = _call_first_available(
            legacy_tech,
            ["render", "render_technical", "render_technical_tab", "view", "view_technical", "tab"],
            fin, sym, symk
        )
        if ok:
            return
    except Exception:
        pass

    # 2) fallback: شارت charts مباشرة
    try:
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

        c_p, c_i = st.columns([1.2, 1.2])
        p_label = c_p.selectbox("الفترة (Period)", list(period_opts.keys()), index=2, key=f"tech_p_{symk}")
        i_label = c_i.selectbox("الفاصل (Interval)", list(interval_opts.keys()), index=0, key=f"tech_i_{symk}")

        _render_technical_chart_flex(sym, period=period_opts[p_label], interval=interval_opts[i_label])
        return

    except Exception as e:
        st.error("تعذر تشغيل تبويب الفني.")
        st.write(str(e))
        with st.expander("Trace"):
            st.code(traceback.format_exc(), language="text")
