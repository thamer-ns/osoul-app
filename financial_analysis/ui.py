# financial_analysis/ui.py
import streamlit as st
import pandas as pd
import plotly.express as px

from market_data import get_ticker_symbol
from .store import get_stored_financials_df, save_financial_record
from .metrics import get_advanced_fundamental_ratios
from .sync import sync_auto_yahoo
from .parsers import FinancialParser


# ==============================================================
# 🖥️ (Optional) Standalone UI (not required by views.py)
# ==============================================================
def render_financial_dashboard_ui(symbol):
    tab_dashboard, tab_data_mgmt = st.tabs(["📊 لوحة التحليل المالي", "⚙️ استيراد البيانات"])

    with tab_dashboard:
        ptype = st.radio(
            "نطاق التحليل:",
            ["Annual", "Quarterly"],
            horizontal=True,
            label_visibility="collapsed",
            key=f"fin_ptype_inline_{symbol}",
        )
        df = get_stored_financials_df(symbol, ptype)

        if df.empty:
            st.warning("⚠️ لا توجد بيانات. استخدم تبويب الاستيراد أو التحديث الآلي.")
        else:
            metrics = get_advanced_fundamental_ratios(symbol)
            c1, c2, c3 = st.columns(3)
            c1.metric("F-Score", f"{metrics['Piotroski_Score']}/9", metrics["Financial_Health"])
            c2.metric(
                "Graham Value",
                f"{metrics.get('Fair_Value_Graham', 0):,.2f}" if metrics.get("Fair_Value_Graham") else "N/A",
            )
            c3.write(metrics.get("Opinions", ""))

            try:
                plot_df = df.copy()
                if "date" in plot_df.columns:
                    plot_df["Year"] = plot_df["date"].dt.strftime("%Y-%m")
                cols = [c for c in ["revenue", "net_income", "operating_cash_flow"] if c in plot_df.columns]
                if cols:
                    fig = px.bar(plot_df.sort_values("date"), x="Year", y=cols, barmode="group")
                    st.plotly_chart(fig, width="stretch")
            except Exception:
                pass

            with st.expander("البيانات التفصيلية"):
                st.dataframe(df, width="stretch")

            with st.expander("📌 مؤشرات متقدمة (DuPont / Altman / Valuation / SGR)"):
                try:
                    adv = {
                        "ROE": metrics.get("ROE", 0),
                        "ROA": metrics.get("ROA", 0),
                        "DuPont PM": metrics.get("DuPont_Profit_Margin", 0),
                        "DuPont AT": metrics.get("DuPont_Asset_Turnover", 0),
                        "DuPont EM": metrics.get("DuPont_Equity_Multiplier", 0),
                        "Altman Z": metrics.get("Altman_Z", 0),
                        "SGR": metrics.get("SGR", 0),
                        "CR": metrics.get("Current_Ratio", 0),
                        "OCF/NI": metrics.get("OCF_to_NetIncome", 0),
                        "PE": metrics.get("PE_Trailing", 0),
                        "PEG": metrics.get("PEG", 0),
                        "P/B": metrics.get("PB", 0),
                    }
                    st.json(adv)
                except Exception:
                    pass

    with tab_data_mgmt:
        st.info("يدعم: PDF تداول / Excel/CSV / Copy-Paste من المتصفح (TradingView/أرقام/Investing/Google Finance)")
        parser = FinancialParser()

        c_up, c_pst = st.columns(2)
        with c_up:
            uploaded_file = st.file_uploader("رفع ملف (PDF, Excel, CSV)", type=["pdf", "xlsx", "xls", "csv"], key=f"fin_up_{symbol}")
        with c_pst:
            pasted_text = st.text_area("أو الصق النص هنا", height=120, key=f"fin_paste_{symbol}")

        cbtn1, cbtn2 = st.columns(2)
        with cbtn1:
            if st.button("⚡ تحديث آلي (Yahoo + بدائل)", key=f"fin_sync_{symbol}"):
                ok, msg = sync_auto_yahoo(symbol)
                (st.success(msg) if ok else st.error(msg))

        with cbtn2:
            if st.button("🚀 معالجة البيانات", key=f"fin_parse_{symbol}"):
                with st.spinner("جاري التحليل..."):
                    results, detected_symbol, err = parser.process_file_or_text(uploaded_file, pasted_text)

                if err:
                    st.error(err)
                    return
                if not results:
                    st.warning("لم نتمكن من استخراج بيانات مفيدة. جرّب لصق جدول بشكل أوضح.")
                    return

                st.success(f"تم استخراج {len(results)} سجلات!")

                target_symbol = detected_symbol or get_ticker_symbol(symbol)
                if detected_symbol and detected_symbol != get_ticker_symbol(symbol):
                    st.warning(f"⚠️ يبدو أن الملف لشركة {detected_symbol}، وأنت في {symbol}.")
                    if st.checkbox("استخدم الرمز المكتشف؟", value=True, key=f"fin_use_detect_{symbol}"):
                        target_symbol = detected_symbol

                preview_df = pd.DataFrame([{"Date": r["date"], **(r["data"] or {})} for r in results])
                st.dataframe(preview_df, width="stretch")

                if st.button("💾 حفظ البيانات", key=f"fin_save_{symbol}"):
                    saved = 0
                    for r in results:
                        if save_financial_record(target_symbol, r["date"], r["data"], "Annual", "File/Paste"):
                            saved += 1
                    st.success(f"تم حفظ {saved} سجل/سجلات")
                    st.rerun()
