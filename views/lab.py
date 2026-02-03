#views/lab.py
import streamlit as st
import pandas as pd
import traceback

from data_source import get_company_details
from views.shared import (
    run_backtest, bt_import_error, _select_strategy_ui, _normalize_symbol,
    _get_chart_history_flex, _to_float, safe_fmt
)
from market_data import get_chart_history  # كما في ملفك

def view_backtester_ui(fin):
    st.header("🧪 المختبر")

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
                st.dataframe(mdf, use_container_width=True)

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
                    st.dataframe(df_curve.head(50), use_container_width=True)
            else:
                st.info("لا يوجد DataFrame منحنى داخل النتيجة.")

        with t_trades:
            trades_df = res.get("trades") or res.get("trades_df")
            if isinstance(trades_df, pd.DataFrame) and not trades_df.empty:
                st.dataframe(trades_df, use_container_width=True)
            else:
                st.info("لا توجد صفقات مسجلة داخل نتيجة الاختبار (أو الاستراتيجية لا ترجعها).")

        with t_raw:
            st.json({k: v for k, v in res.items() if k != "df"})
