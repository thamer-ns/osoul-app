# views/analysis/technical.py
# -*- coding: utf-8 -*-

"""واجهة التحليل الفني.

مهم:
- لا يتم حذف أي شيء من الواجهة الحالية.
- تمت إضافة قسم "مؤشرات متقدمة" فقط كإضافة.
- هذه المؤشرات (عند توفرها) يتم استخدام نفس نتائجها داخل المستشار (AI)
  عبر ai_engine_core/packs.py.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st

from market_data import get_chart_history
from views.shared import _sym_key, _render_technical_chart_flex

# ==============================
# مؤشرات متقدمة (Advanced Indicators)
# ==============================
# هذا الاستيراد اختياري حتى لا ينكسر التطبيق إذا لم تكن الحزمة موجودة.
_ADV_AVAILABLE = True
try:
    from technical_indicators.advanced import compute_advanced_technical_pack
except Exception:
    compute_advanced_technical_pack = None
    _ADV_AVAILABLE = False


def _as_list(x: Any):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _render_indicator_block(title: str, res: Dict[str, Any]):
    """Render a standardized indicator result."""
    st.markdown(f"### {title}")

    conf = res.get("confidence")
    if conf is not None:
        try:
            st.caption(f"درجة الثقة: **{int(conf)}%**")
        except Exception:
            st.caption(f"درجة الثقة: **{conf}**")

    errors = _as_list(res.get("errors"))
    if errors:
        st.warning("⚠️ ملاحظات/أخطاء أثناء الحساب:\n- " + "\n- ".join([str(e) for e in errors]))

    evidence = _as_list(res.get("evidence"))
    if evidence:
        st.info("**الأدلة:**\n\n- " + "\n- ".join([str(e) for e in evidence]))

    signals = _as_list(res.get("signals"))
    if signals:
        try:
            st.markdown("**الإشارات:**")
            df_sig = pd.DataFrame(signals)
            st.dataframe(df_sig, use_container_width=True)
        except Exception:
            st.write(signals)

    features = res.get("features", {})
    if isinstance(features, dict) and features:
        with st.expander("عرض الخصائص (Features)"):
            try:
                df_feat = pd.DataFrame(
                    [{"feature": k, "value": v} for k, v in features.items()]
                )
                st.dataframe(df_feat, use_container_width=True)
            except Exception:
                st.json(features)


def _render_advanced_section(df: pd.DataFrame, symbol: str, interval: str):
    if not _ADV_AVAILABLE or compute_advanced_technical_pack is None:
        st.warning("حزمة المؤشرات المتقدمة غير متوفرة داخل هذا الإصدار.")
        st.caption("تأكد من وجود: technical_indicators/advanced.py")
        return

    if df is None or df.empty:
        st.warning("لا توجد بيانات سعرية كافية لحساب المؤشرات المتقدمة.")
        return

    with st.spinner("جاري حساب المؤشرات المتقدمة..."):
        pack = compute_advanced_technical_pack(df, symbol=symbol, timeframe=interval)

    # عرض ملخص سريع
    st.caption("هذه النتائج تُستخدم كذلك داخل **المستشار (AI)** ضمن حزمة التحليل الفني (Technical Pack).")

    # العناصر
    rls = pack.get("rls_forecast", {})
    wrsi = pack.get("chaos_wrsi", {})
    vp = pack.get("volume_profile_clusters", {})
    tl = pack.get("trendline_breakout", {})

    # --- RLS
    _render_indicator_block("RLS Forecast (التنبؤ/الارتداد للمتوسط)", rls)

    # --- Chaos WRSI
    _render_indicator_block("Chaos Weighted RSI (زخم ديناميكي)", wrsi)

    # --- Volume Profile Clusters
    _render_indicator_block("Clusters Volume Profile (تحليل الحجم حسب شرائح سعرية)", vp)

    # --- Trendline Breakout
    _render_indicator_block("Trendline Breakout Navigator (ترندلاين + اختراق/إعادة اختبار)", tl)


def view_technical(symbol: str, interval: str = "1d"):
    st.subheader("📈 التحليل الفني")

    # جلب بيانات الرسم/السعر
    df = None
    try:
        df = get_chart_history(symbol, period="1y", interval=interval)
    except Exception as e:
        st.error(f"تعذر جلب البيانات السعرية للرسم: {e}")

    # تبويبات داخل التحليل الفني (بدون حذف)
    tab1, tab2 = st.tabs(["ملخص فني", "مؤشرات متقدمة"])

    with tab1:
        # ====== الموجود سابقاً: الرسم + وصف بسيط ======
        st.markdown("### الرسم الفني (مرن)")

        # مفتاح تخزين الرسم داخل session state
        # NOTE: views.shared._sym_key() تقبل وسيطًا واحدًا فقط.
        key = f"{_sym_key(symbol)}_tech_chart"
        try:
            _render_technical_chart_flex(symbol, df, key=key)
        except Exception as e:
            st.warning(f"تعذر عرض الرسم المرن: {e}")
            if df is not None and not df.empty:
                st.dataframe(df.tail(10), use_container_width=True)

        st.caption("ملاحظة: هذا القسم هو الموجود سابقاً — لم يتم حذفه أو تغييره إلا بقدر تنظيم العرض داخل تبويب.")

    with tab2:
        _render_advanced_section(df, symbol=symbol, interval=interval)


def render_technical_tab(symbol: str, interval: str = "1d"):
    """Compatibility entry point.

    Some parts of the app expect `render_technical_tab` to exist.
    We keep this thin wrapper to preserve imports and avoid breaking
    the existing routing logic.
    """
    return view_technical(symbol, interval=interval)
