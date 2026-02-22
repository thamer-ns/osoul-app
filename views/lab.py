from __future__ import annotations

#views/lab.py
import streamlit as st
from feature_flags import get_flag
import pandas as pd
import traceback

from data_source import get_company_details
from views.shared import (
    run_backtest, bt_import_error, _select_strategy_ui, _normalize_symbol,
    _get_chart_history_flex, _to_float, safe_fmt
)
from market_data import get_chart_history  # كما في ملفك

# Optional: buried features
try:
    from backtester import get_strategy_notes, get_lab_runs
except Exception:
    get_strategy_notes = None
    get_lab_runs = None

def view_backtester_ui(fin):
    st.header("🧪 المختبر")

    st.subheader("🧠 تحليل متعدد الفواصل (AI)")
    colA, colB = st.columns([2, 1])
    with colA:
        ai_symbol = st.text_input("الرمز للتحليل (يدعم: 1120 / AAPL / BTC-USD)", value="1120", key="lab_ai_symbol")
    with colB:
        horizon_days = st.number_input("أفق التقييم (للمعايرة) بالأيام", min_value=5, max_value=60, value=20, step=5, key="lab_cal_h")

    tfs_all = ["15M", "30M", "1H", "4H", "1D", "1W", "1M"]
    timeframes = st.multiselect("الفواصل", tfs_all, default=tfs_all, key="lab_ai_tfs")

    with st.expander("🎛️ معايرة thresholds (اختياري)"):
        st.caption("تعتمد على سجلات النظام ai_signals/ai_outcomes (سريعة وخفيفة).")
        cal_tf = st.selectbox("الفاصل المراد معايرته", options=tfs_all, index=4, key="lab_cal_tf")
        if st.button("⚙️ تشغيل المعايرة الآن", key="lab_run_cal"):
            try:
                from ai_engine_core.calibration import calibrate_thresholds, get_current_thresholds
                res = calibrate_thresholds(cal_tf, horizon_days=int(horizon_days))
                st.success("تمت المعايرة ✅" if res.get("used") else "لم تتم المعايرة (بيانات غير كافية)")
                st.json(res)
                st.info({"current_thresholds": get_current_thresholds(cal_tf)})
            except Exception as e:
                st.error(f"تعذر تشغيل المعايرة: {e}")

    if st.button("تشغيل التحليل متعدد الفواصل", key="lab_run_ai"):
        from views.shared import generate_ai_report
        sym_norm = _normalize_symbol(ai_symbol)
        results = []
        with st.spinner("جاري التحليل..."):
            for tf in timeframes:
                try:
                    rep = generate_ai_report(sym_norm, timeframe=tf)
                    results.append((tf, rep))
                except Exception as e:
                    results.append((tf, {"error": str(e)}))

        rows = []
        for tf, rep in results:
            if not isinstance(rep, dict) or "error" in rep:
                rows.append({"TF": tf, "Recommendation": "—", "Score": None, "Confidence": None, "Note": rep.get("error") if isinstance(rep, dict) else "error"})
                continue
            rows.append({
                "TF": tf,
                "Recommendation": rep.get("recommendation"),
                "Score": rep.get("total_score"),
                "Confidence": rep.get("confidence"),
                "Source": (rep.get("engine_meta") or {}).get("data_lineage", {}).get("source"),
                "Coverage": (rep.get("engine_meta") or {}).get("data_lineage", {}).get("rows"),
            })
        df_sum = pd.DataFrame(rows)
        # توحيد ترتيب الأعمدة وتنسيق القيم لعرض متناسق مع جداول التطبيق
        desired = ["TF", "Recommendation", "Score", "Confidence", "Source", "Coverage", "Note"]
        cols = [c for c in desired if c in df_sum.columns]
        if cols:
            df_sum = df_sum[cols]
        df_sum = df_sum.fillna("—")
        try:
            html_table = df_sum.to_html(index=False, classes=["finance-table"], escape=False)
            st.markdown(html_table, unsafe_allow_html=True)
        except Exception:
            st.dataframe(df_sum, use_container_width=True, hide_index=True)

        for tf, rep in results:
            with st.expander(f"تفاصيل {tf}", expanded=False):
                if not isinstance(rep, dict):
                    st.write(rep)
                    continue
                if "error" in rep:
                    st.error(rep["error"])
                    continue
                st.write({
                    "recommendation": rep.get("recommendation"),
                    "total_score": rep.get("total_score"),
                    "confidence": rep.get("confidence"),
                    "thresholds_used": (rep.get("engine_meta") or {}).get("thresholds_used"),
                    "why_wrong": (rep.get("engine_meta") or {}).get("why_wrong"),
                    "data_lineage": (rep.get("engine_meta") or {}).get("data_lineage"),
                })
                ev = rep.get("signal_events") or []
                if ev:
                    st.markdown("**Timeline (أحدث الشارات):**")
                    st.json(ev)

    st.divider()


    if not run_backtest:
        st.warning("Backtester غير متوفر حالياً.")
        if bt_import_error:
            st.code(bt_import_error)
        st.info("✅ الحل: تأكد أن backtester.py يحتوي list_strategies و run_backtest بشكل صحيح.")
        return

    st.markdown("#### ⚙️ إعدادات الاختبار")
    cA, cB, cC = st.columns([1.2, 1.2, 1.6])
    s = cA.text_input("رمز السهم", "1120", key="lab_symbol", help="اكتب 1120 أو 1120.SR")
    cap = cB.number_input("رأس المال", min_value=1000.0, value=100000.0, step=1000.0, key="lab_cap")
    period = cC.selectbox("الفترة التاريخية", ["6mo", "1y", "2y", "5y", "10y", "max"], index=3, key="lab_period")

    strat = _select_strategy_ui(key_prefix="lab")
    st.caption("💡 إذا الاستراتيجية تعتمد على مؤشرات طويلة، اختر فترة أكبر (مثل 5y أو 10y).")


    # -----------------------------------------------------
    # 📒 ملاحظات الاستراتيجيات + سجل التجارب (اختياري)
    # -----------------------------------------------------
    if get_flag("enable_strategy_notes", False):
        with st.expander("📒 ملاحظات الاستراتيجية (تجريبي)", expanded=False):
            if callable(get_strategy_notes):
                note = get_strategy_notes(strat)
                if note:
                    st.write(note)
                else:
                    st.info("لا توجد ملاحظات محفوظة لهذه الاستراتيجية.")
            else:
                st.info("ميزة الملاحظات غير متوفرة حالياً (backtester.py).")

        with st.expander("📁 سجل التجارب السابقة (lab_runs) — تجريبي", expanded=False):
            if callable(get_lab_runs):
                try:
                    runs = get_lab_runs(limit=50)
                    if runs is None or (isinstance(runs, pd.DataFrame) and runs.empty):
                        st.info("لا يوجد سجلات تجارب بعد.")
                    else:
                        if not isinstance(runs, pd.DataFrame):
                            runs = pd.DataFrame(runs)
                        st.dataframe(runs, width="stretch", hide_index=True)
                except Exception as e:
                    st.error(f"تعذر عرض سجل التجارب: {e}")
            else:
                st.info("ميزة سجل التجارب غير متوفرة حالياً (backtester.py).")

    if st.button("🚀 بدء الاختبار", key="bt_run", type="primary"):
        try:
            s_norm = _normalize_symbol(s)
            st.caption(f"🔎 الرمز: {s_norm} | الفترة: {period} | الاستراتيجية: {strat}")

            with st.spinner("جاري جلب البيانات التاريخية..."):
                try:
                    data = get_chart_history(s_norm, period)
                except TypeError:
                    data = _get_chart_history_flex(s_norm, period, "1d")

            if data is None or (isinstance(data, pd.DataFrame) and data.empty):
                st.error("❌ لم يتم جلب بيانات (DataFrame فارغ)")
                return

            if not isinstance(data, pd.DataFrame):
                data = pd.DataFrame(data)

            if "Close" not in data.columns and "close" not in data.columns:
                st.error("❌ لا يوجد عمود Close في البيانات")
                st.write("الأعمدة:", list(data.columns))
                return

            try:
                info = get_company_details(s_norm)
                if isinstance(info, (list, tuple)) and len(info) >= 2:
                    sec = info[1]
                elif isinstance(info, dict):
                    sec = info.get("sector") or info.get("Sector") or ""
                else:
                    sec = ""
            except Exception:
                sec = ""

            with st.spinner("🧪 جاري تنفيذ الاستراتيجية على البيانات..."):
                res = run_backtest(data, str(strat), float(cap), symbol=s_norm, sector=sec)

            if not res:
                st.warning("⚠️ لم يرجع الاختبار نتيجة.")
                return

            st.session_state["__last_bt_result__"] = res
            st.success(f"✅ اكتمل الاختبار ({res.get('strategy_name_ar', strat)})")

        except Exception as e:
            st.error(f"Backtest Error: {e}")
            st.code(traceback.format_exc())

    res = st.session_state.get("__last_bt_result__")
    if res:
        st.markdown("---")
        st.markdown("#### 📊 النتائج")

        t_sum, t_curve, t_trades, t_raw = st.tabs(["ملخص", "منحنى المحفظة", "الصفقات", "خام"])

        with t_sum:
            kpis = {
                "return_pct": ("العائد %", "percent"),
                "final_value": ("القيمة النهائية", "money"),
                "max_drawdown_pct": ("أقصى سحب %", "percent"),
                "win_rate": ("نسبة النجاح", "percent"),
                "trades_count": ("عدد الصفقات", "number"),
                "sharpe": ("Sharpe", "number"),
            }

            cols = st.columns(4)
            idx = 0
            for key, (label, typ) in kpis.items():
                if key in res:
                    v = res.get(key)
                    if typ == "percent":
                        txt = f"{_to_float(v, 0):.2f}%"
                    elif typ == "money":
                        txt = safe_fmt(_to_float(v, 0))
                    elif typ == "number":
                        try:
                            txt = str(int(_to_float(v, 0)))
                        except Exception:
                            txt = str(v)
                    else:
                        try:
                            txt = f"{_to_float(v, 0):.2f}"
                        except Exception:
                            txt = str(v)

                    with cols[idx % 4]:
                        st.metric(label, txt)
                    idx += 1

            if isinstance(res.get("metrics"), dict) and res["metrics"]:
                st.markdown("---")
                st.markdown("**📌 مؤشرات إضافية**")
                mdf = pd.DataFrame([{"Metric": k, "Value": v} for k, v in res["metrics"].items()])
                st.dataframe(mdf, width="stretch")

        with t_curve:
            df_curve = res.get("df")
            if isinstance(df_curve, pd.DataFrame) and not df_curve.empty:
                col = None
                for cand in ["Portfolio_Value", "portfolio_value", "equity", "Equity", "value"]:
                    if cand in df_curve.columns:
                        col = cand
                        break
                if col:
                    st.line_chart(df_curve[col])
                else:
                    st.info("لا يوجد عمود منحنى واضح داخل df.")
                    st.dataframe(df_curve.head(50), width="stretch")
            else:
                st.info("لا يوجد DataFrame منحنى داخل النتيجة.")

        with t_trades:
            trades_df = res.get("trades") or res.get("trades_df")
            if isinstance(trades_df, pd.DataFrame) and not trades_df.empty:
                st.dataframe(trades_df, width="stretch")
            else:
                st.info("لا توجد صفقات مسجلة داخل نتيجة الاختبار (أو الاستراتيجية لا ترجعها).")

        with t_raw:
            st.json({k: v for k, v in res.items() if k != "df"})
