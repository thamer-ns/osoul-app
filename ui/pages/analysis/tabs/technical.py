# ui/pages/analysis/tabs/technical.py
import streamlit as st
import pandas as pd
import traceback

from market_data import get_chart_history
from ui.common import sym_key as _sym_key

try:
    from charts import render_technical_chart
except Exception:
    render_technical_chart = None


def render_tab(symbol: str, fin: dict, company_name: str = "", sector: str = ""):
    symk = _sym_key(symbol)

    period_opts = {
        "6 أشهر": "6mo",
        "سنة": "1y",
        "سنتين": "2y",
        "5 سنوات": "5y",
        "10 سنوات": "10y",
        "الحد الأقصى": "max",
    }

    c1, c2 = st.columns([1.2, 2.0])
    p_label = c1.selectbox("الفترة (Period)", list(period_opts.keys()), index=2, key=f"tech_p_{symk}")
    mode = c2.radio("وضع العرض", ["احترافي (DataFrame)", "قديم (charts.py)"], horizontal=True, key=f"tech_mode_{symk}")

    period = period_opts[p_label]

    if mode == "قديم (charts.py)":
        if not render_technical_chart:
            st.warning("charts.py غير متوفر لعرض الشارت القديم.")
            return
        try:
            render_technical_chart(symbol, period=period, interval="1d")
        except TypeError:
            render_technical_chart(symbol, period=period)
        except Exception as e:
            st.error(f"فشل عرض الشارت القديم: {e}")
            st.code(traceback.format_exc(), language="text")
        return

    # احترافي: نعرض DataFrame + إحصائيات بسيطة (بدون تكرار)
    with st.spinner("جاري جلب بيانات الشارت..."):
        df = get_chart_history(symbol, period)

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

    st.caption("عرض بيانات الشارت (آخر 200 صف)")
    st.dataframe(df.tail(200), use_container_width=True)
