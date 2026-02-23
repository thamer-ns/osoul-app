# views/signals.py
import streamlit as st
import pandas as pd

from database import fetch_table
from views.shared import _generate_ai_report_flex, _extract_ai, _fmt_price
from quality_engine import quality_score, quality_label
from market_data import get_chart_history, get_ticker_symbol
from data_normalizer import normalize_ohlcv


def _floating_notification(message: str, tone: str = "success"):
    color = {"success": "#16c784", "warning": "#f59e0b", "danger": "#ea3943"}.get(tone, "#16c784")
    st.markdown(
        f"""
        <div style="
          position:fixed;
          bottom:20px;
          left:20px;
          background: rgba(21,26,35,0.95);
          border-left:5px solid {color};
          padding:12px 14px;
          border-radius:12px;
          box-shadow:0 10px 30px rgba(0,0,0,0.45);
          z-index:9999;
          animation: slideUp 0.45s ease-out;
          max-width: 360px;
          color: #e6edf3;
          ">
          {message}
        </div>
        <style>
        @keyframes slideUp {{
          from {{ transform: translateY(16px); opacity:0; }}
          to   {{ transform: translateY(0); opacity:1; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _play_sound():
    # Lightweight: browser will play if allowed
    st.markdown(
        """
        <audio autoplay>
          <source src="https://actions.google.com/sounds/v1/cartoon/clang_and_wobble.ogg" type="audio/ogg">
        </audio>
        """,
        unsafe_allow_html=True,
    )


def _signal_card(symbol: str, timeframe: str, ex: dict, q_score: float = 0.0):
    rec = str(ex.get("recommendation") or "—")
    rec_l = rec.lower()
    pill = "hold"
    if "buy" in rec_l or "شراء" in rec_l:
        pill = "buy"
    elif "sell" in rec_l or "بيع" in rec_l:
        pill = "sell"

    conf = int(ex.get("confidence") or 0)
    entry_zone = (ex.get("entry") or {}).get("entry_zone")
    stop = (ex.get("risk") or {}).get("stop")
    rr = (ex.get("risk") or {}).get("rr")
    targets = ex.get("targets") or []
    t1 = None
    if isinstance(targets, list) and targets:
        t1 = targets[0].get("price") if isinstance(targets[0], dict) else targets[0]

    st.markdown(
        f"""
        <div class="os-signal-card">
          <div class="os-signal-head">
            <div class="os-signal-title">{symbol} — {timeframe}</div>
            <span class="os-pill {pill}">{rec}</span>
          </div>
          <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:10px;">
            <div class="os-card" style="padding:12px; margin:0;">
              <div class="kpi-title">الثقة</div>
              <div class="kpi-value" style="font-size:1.25rem;">{conf}%</div>
            </div>
            <div class="os-card" style="padding:12px; margin:0;">
              <div class="kpi-title">الدخول</div>
              <div class="kpi-value" style="font-size:1.25rem;">{_fmt_price(entry_zone)}</div>
            </div>
            <div class="os-card" style="padding:12px; margin:0;">
              <div class="kpi-title">وقف الخسارة</div>
              <div class="kpi-value" style="font-size:1.25rem;">{_fmt_price(stop)}</div>
            </div>
          </div>
          <div style="margin-top:10px; display:flex; gap:10px; flex-wrap:wrap;">
            <span class="os-pill hold">🎯 هدف 1: {_fmt_price(t1)}</span>
            <span class="os-pill hold">⚖️ R:R: {float(rr or 0):.2f}</span>
            <span class="os-pill hold">⭐ جودة: {q_score:.1f} ({quality_label(q_score)})</span>
          </div>
          <div style="margin-top:10px; color: var(--muted); font-weight:700;">
            {st.session_state.get("signal_hint","")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def view_signals(fin: dict):
    st.markdown("## ⚡ الإشارات (v2)")
    st.caption("بطاقات إشارات احترافية مع خطة دخول/مخاطر + جودة البيانات.")

    # Build symbol universe
    symbols = set()
    try:
        if isinstance(fin, dict) and "all_trades" in fin and isinstance(fin["all_trades"], pd.DataFrame):
            df = fin["all_trades"]
            if not df.empty and "symbol" in df.columns:
                symbols.update([get_ticker_symbol(s) for s in df["symbol"].astype(str).tolist() if str(s).strip()])
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at views/signals.py:119')

    try:
        wl = fetch_table("watchlist")
        if wl is not None and not wl.empty and "symbol" in wl.columns:
            symbols.update([get_ticker_symbol(s) for s in wl["symbol"].astype(str).tolist() if str(s).strip()])
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at views/signals.py:126')

    symbols = sorted(symbols)
    if not symbols:
        st.info("لا توجد رموز في المحفظة/قائمة المراقبة. أضف صفقة أو أضف رمز لقائمة المراقبة.")
        return

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        selected = st.multiselect("اختر الأسهم", symbols, default=symbols[: min(5, len(symbols))])
    with c2:
        timeframe = st.selectbox("الفاصل", ["15m", "1h", "4h", "1d"], index=3)
    with c3:
        sound = st.toggle("🔊 صوت", value=False)

    colA, colB = st.columns([1, 1])
    with colA:
        show_notify = st.toggle("تنبيه عائم", value=True)
    with colB:
        show_details = st.toggle("تفاصيل إضافية", value=False)

    if st.button("🚀 توليد الإشارات", use_container_width=True):
        for sym in selected:
            with st.spinner(f"جارٍ تحليل {sym}..."):
                rep = _generate_ai_report_flex(sym, timeframe)
                ex = _extract_ai(rep)

            # quality score from history (light)
            q_score = 0.0
            try:
                hist = get_chart_history(sym, years=2, interval="1d")
                hist = normalize_ohlcv(hist)
                q_score = quality_score(hist)
            except Exception:
                q_score = 0.0

            if not ex.get("ok"):
                st.error(f"{sym}: تعذر توليد التقرير")
                continue

            _signal_card(sym, timeframe, ex, q_score=q_score)

            rec = str(ex.get("recommendation") or "").lower()
            if show_notify:
                if "buy" in rec or "شراء" in rec:
                    _floating_notification(f"تم توليد إشارة شراء لـ {sym} 🚀", "success")
                elif "sell" in rec or "بيع" in rec:
                    _floating_notification(f"تنبيه بيع/تقليل لـ {sym}", "warning")
            if sound and (("buy" in rec) or ("sell" in rec) or ("شراء" in rec) or ("بيع" in rec)):
                _play_sound()

            if show_details:
                st.expander("تفاصيل التقرير").json(ex.get("raw") or {})

