#views/analysis/technical.py
import streamlit as st
import pandas as pd

from market_data import get_chart_history
from views.shared import _sym_key, _render_technical_chart_flex


def _safe_to_df(x):
    if x is None:
        return None
    if isinstance(x, pd.DataFrame):
        return x
    try:
        return pd.DataFrame(x)
    except Exception:
        return None


def _price_snapshot(symbol: str, period: str = "1y", interval: str = "1d"):
    """
    Snapshot بسيط للعرض:
    - آخر إغلاق + تغير
    - أعلى/أدنى خلال الفترة
    - آخر حجم تداول
    """
    try:
        df = _safe_to_df(get_chart_history(symbol, period=period, interval=interval))
        if df is None or df.empty:
            return {}

        cols = {str(c).lower(): c for c in df.columns}
        close = cols.get("close") or ("Close" if "Close" in df.columns else None)
        high = cols.get("high") or ("High" if "High" in df.columns else None)
        low = cols.get("low") or ("Low" if "Low" in df.columns else None)
        vol = cols.get("volume") or ("Volume" if "Volume" in df.columns else None)

        def _num(s):
            return pd.to_numeric(s, errors="coerce")

        out = {}
        if close:
            ser = _num(df[close]).dropna()
            if not ser.empty:
                out["last"] = float(ser.iloc[-1])
                if len(ser) >= 2 and float(ser.iloc[-2]) != 0:
                    out["chg_pct"] = (float(ser.iloc[-1]) / float(ser.iloc[-2]) - 1) * 100.0

        if high:
            ser = _num(df[high]).dropna()
            if not ser.empty:
                out["high"] = float(ser.max())

        if low:
            ser = _num(df[low]).dropna()
            if not ser.empty:
                out["low"] = float(ser.min())

        if vol:
            ser = _num(df[vol]).dropna()
            if not ser.empty:
                out["vol"] = float(ser.iloc[-1])

        return out
    except Exception:
        return {}


def render_technical_tab(sym: str):
    symk = _sym_key(sym)

    st.markdown("### 📈 التحليل الفني")
    st.caption("تحسين العرض فقط: نفس الشارت ونفس المنطق—مع ملخص سريع وإعدادات أوضح.")

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

    # بناءً على طلبك: إزالة "الشارت الاحترافي" نهائيًا لأنه لا يعمل بالشكل الصحيح.
    # سيتم عرض وضع واحد ثابت (Fallback) فقط.
    c_mode.markdown("**وضع الشارت:** قديم (ثابت)")

    # Snapshot (KPIs)
    snap = _price_snapshot(sym, period=period_opts[p_label], interval=interval_opts[i_label])
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("السعر", f"{snap.get('last', 0):,.2f}" if snap.get("last") else "—")
    with k2:
        ch = snap.get("chg_pct", None)
        st.metric("التغير", f"{ch:+.2f}%" if isinstance(ch, (int, float)) else "—")
    with k3:
        st.metric("أعلى", f"{snap.get('high', 0):,.2f}" if snap.get("high") else "—")
    with k4:
        st.metric("أدنى", f"{snap.get('low', 0):,.2f}" if snap.get("low") else "—")

    with st.expander("⚙️ ملاحظات الاستخدام"):
        st.write("- اسحب داخل الشارت للتحريك (Pan).")
        st.write("- استخدم Scroll للتكبير/التصغير.")
        st.write("- لو واجهت مشكلة بيانات جرّب فترة أكبر أو وضع Fallback.")

    # Chart
    try:
        _render_technical_chart_flex(sym, period=period_opts[p_label], interval=interval_opts[i_label])
    except Exception as e:
        st.error("❌ حصل خطأ أثناء عرض الشارت.")
        st.code(str(e))
        st.info("سيتم عرض وضع Fallback تلقائيًا.")
        try:
            _render_technical_chart_flex(sym, period=period_opts[p_label], interval=interval_opts[i_label])
        except Exception as e2:
            st.error("❌ حتى وضع Fallback فشل.")
            st.code(str(e2))
