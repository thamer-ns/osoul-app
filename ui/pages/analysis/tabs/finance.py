# ui/pages/analysis/tabs/finance.py
import streamlit as st
import pandas as pd
from datetime import date

from financial_analysis import (
    FinancialParser,
    save_financial_record,
    get_financial_statements,
    get_advanced_fundamental_ratios,
    sync_auto_yahoo,
)

from ui.common import sym_key as _sym_key


def _render_table(df: pd.DataFrame, max_rows: int = 600):
    if df is None or (not isinstance(df, pd.DataFrame)) or df.empty:
        st.info("📭 لا توجد بيانات لعرضها")
        return
    if len(df) > max_rows:
        df = df.head(max_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_import_ui(symbol: str):
    st.info("يدعم النظام: ملفات PDF من تداول، ملفات Excel/CSV، أو النسخ واللصق المباشر.")
    parser = FinancialParser()

    uploaded_file = st.file_uploader("رفع ملف قوائم مالية (PDF, Excel, CSV)", type=["pdf", "xlsx", "xls", "csv"])
    pasted_text = st.text_area("أو الصق البيانات هنا مباشرة:")

    if st.button("🚀 معالجة واستخراج البيانات", key=f"fin_parse_{_sym_key(symbol)}"):
        results, detected_symbol, err = [], None, None
        with st.spinner("جاري تحليل النصوص واستخراج الأرقام..."):
            if uploaded_file:
                results, detected_symbol, err = parser.process_file_or_text(uploaded_file=uploaded_file)
            elif pasted_text:
                results, detected_symbol, err = parser.process_file_or_text(text_input=pasted_text)
            else:
                st.warning("الرجاء اختيار ملف أو لصق نص.")
                return

        if err:
            st.error(err)
            return

        if not results:
            st.error("لم يتم العثور على بيانات مالية صالحة.")
            return

        st.success(f"تم استخراج {len(results)} سجلات بنجاح!")
        final_symbol = symbol

        if detected_symbol and detected_symbol != symbol:
            st.warning(f"⚠️ الملف لشركة {detected_symbol}، وأنت في صفحة {symbol}.")
            if st.checkbox(f"استخدام {detected_symbol}؟", value=True, key=f"use_detect_{_sym_key(symbol)}"):
                final_symbol = detected_symbol

        st.write("### 🧐 مراجعة البيانات المستخرجة:")
        preview_df = pd.DataFrame([{"Date": r["date"], **r["data"]} for r in results])
        _render_table(preview_df, max_rows=200)

        if st.button("💾 تأكيد وحفظ في قاعدة البيانات", key=f"fin_save_{_sym_key(final_symbol)}"):
            count = 0
            for r in results:
                ok = save_financial_record(final_symbol, r["date"], r["data"], period_type="Annual", source="File/Paste")
                if ok:
                    count += 1
            st.success(f"تم حفظ {count} سجلات لشركة {final_symbol}.")
            st.rerun()


def render_tab(symbol: str, fin: dict, company_name: str = "", sector: str = ""):
    tab_dashboard, tab_data = st.tabs(["📊 لوحة التحليل المالي", "⚙️ إدارة البيانات"])

    with tab_dashboard:
        ptype = st.radio("نطاق التحليل:", ["Annual", "Quarterly"], horizontal=True, key=f"fin_ptype_{_sym_key(symbol)}")
        df = get_financial_statements(symbol, ptype)

        if df is None or df.empty:
            st.warning("⚠️ لا توجد بيانات مالية محفوظة لهذا السهم.")
            st.info("👈 انتقل لتبويب 'إدارة البيانات' لرفع ملف أو جلب المعلومات.")
        else:
            metrics = get_advanced_fundamental_ratios(symbol) or {}
            c1, c2, c3 = st.columns(3)
            c1.metric("المتانة (F-Score)", f"{metrics.get('Piotroski_Score', 0)}/9", metrics.get("Financial_Health", "-"))
            fv = metrics.get("Fair_Value_Graham", 0)
            c2.metric("قيمة جراهام", f"{fv:,.2f}" if fv and fv > 0 else "N/A")
            c3.write(f"**ملاحظات:** {metrics.get('Opinions', '-')}")
            st.divider()
            _render_table(df)

    with tab_data:
        t1, t2, t3 = st.tabs(["⚡ تحديث آلي (Yahoo)", "📂 استيراد ملف/نص", "✍️ إدخال يدوي شامل"])

        with t1:
            st.caption("جلب البيانات من Yahoo Finance مباشرة")
            if st.button("بدء المزامنة الآلية", key=f"sync_yahoo_{_sym_key(symbol)}"):
                with st.spinner("جاري الاتصال..."):
                    ok, msg = sync_auto_yahoo(symbol)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        with t2:
            _render_import_ui(symbol)

        with t3:
            st.caption("أدخل البيانات اللازمة للتحليل المالي.")
            with st.form(f"manual_fin_entry_{_sym_key(symbol)}"):
                col_meta1, col_meta2 = st.columns(2)
                f_date = col_meta1.date_input("تاريخ القوائم", date.today(), key=f"fin_date_{_sym_key(symbol)}")
                f_type = col_meta2.selectbox("الفترة", ["Annual", "Quarterly"], key=f"fin_type_{_sym_key(symbol)}")

                st.divider()
                c1, c2 = st.columns(2)
                rev = c1.number_input("إجمالي الإيرادات", min_value=0.0, format="%.2f")
                net_inc = c2.number_input("صافي الربح", format="%.2f")

                ocf = st.number_input("التدفق النقدي التشغيلي", format="%.2f")

                st.divider()
                b1, b2 = st.columns(2)
                tot_assets = b1.number_input("إجمالي الأصول", min_value=0.0, format="%.2f")
                tot_liab = b2.number_input("إجمالي المطلوبات", min_value=0.0, format="%.2f")

                b3, b4 = st.columns(2)
                cur_assets = b3.number_input("الأصول المتداولة", min_value=0.0, format="%.2f")
                cur_liab = b4.number_input("المطلوبات المتداولة", min_value=0.0, format="%.2f")

                b5, b6 = st.columns(2)
                tot_equity = b5.number_input("إجمالي حقوق الملكية", format="%.2f")
                lt_debt = b6.number_input("الديون طويلة الأجل", min_value=0.0, format="%.2f")

                if st.form_submit_button("💾 حفظ البيانات"):
                    data = {
                        "revenue": rev,
                        "net_income": net_inc,
                        "operating_cash_flow": ocf,
                        "total_assets": tot_assets,
                        "total_liabilities": tot_liab,
                        "current_assets": cur_assets,
                        "current_liabilities": cur_liab,
                        "total_equity": tot_equity,
                        "long_term_debt": lt_debt,
                    }
                    ok = save_financial_record(symbol, str(f_date), data, f_type, "Manual_Full")
                    if ok:
                        st.success("تم الحفظ بنجاح!")
                        st.rerun()
                    else:
                        st.error("فشل الحفظ. تأكد من البيانات.")
