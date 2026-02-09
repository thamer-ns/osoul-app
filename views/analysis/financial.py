#views/analysis/financial.py
import streamlit as st
import pandas as pd
from datetime import date

from views.shared import (
    FinancialParser,
    save_financial_record,
    sync_auto_yahoo,
    get_financial_statements,
    get_advanced_fundamental_ratios,
    _sym_key,
    _render_table_like_trades,
)


def _to_num(x, default=0.0):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def _kv_card(title: str, rows: list):
    """Card helper (عرض فقط). rows: list[(k,v)]"""
    html = [f"<div class='os-card'><div class='os-card-title'>{title}</div>"]
    for k, v in rows:
        html.append(f"<div class='os-kv'><div class='os-k'>{k}</div><div class='os-v'>{v}</div></div>")
    html.append("</div>")
    st.markdown("\n".join(html), unsafe_allow_html=True)


def render_data_import_ui_content(symbol):
    st.info("يدعم النظام: ملفات PDF من تداول، ملفات Excel/CSV، أو النسخ واللصق المباشر.")
    parser = FinancialParser()
    sk = _sym_key(symbol)

    uploaded_file = st.file_uploader(
        "رفع ملف قوائم مالية (PDF, Excel, CSV)",
        type=["pdf", "xlsx", "xls", "csv"],
        key=f"fin_upload_{sk}",
    )
    pasted_text = st.text_area(
        "أو الصق البيانات هنا مباشرة:",
        key=f"fin_paste_{sk}",
        height=140,
    )

    if st.button("🚀 معالجة واستخراج البيانات", key=f"fin_parse_{sk}"):
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

        if results:
            st.success(f"تم استخراج {len(results)} سجلات بنجاح!")
            final_symbol = symbol

            if detected_symbol and detected_symbol != symbol:
                st.warning(f"⚠️ الملف لشركة {detected_symbol}، وأنت في صفحة {symbol}.")
                if st.checkbox(f"استخدام {detected_symbol}؟", value=True, key=f"use_detect_{sk}"):
                    final_symbol = detected_symbol

            if not final_symbol:
                final_symbol = st.text_input(
                    "⚠️ الرجاء إدخال رمز السهم (مثال: 1120.SR):",
                    key=f"fin_manual_sym_{sk}",
                )

            if final_symbol:
                st.write("### 🧐 مراجعة البيانات المستخرجة:")
                preview_df = pd.DataFrame([{"Date": r["date"], **r["data"]} for r in results])
                _render_table_like_trades(preview_df, max_rows=200)

                if st.button("💾 تأكيد وحفظ في قاعدة البيانات", key=f"fin_save_{_sym_key(final_symbol)}"):
                    count = 0
                    for r in results:
                        if save_financial_record(
                            final_symbol, r["date"], r["data"], period_type="Annual", source="File/Paste"
                        ):
                            count += 1
                    st.success(f"تم حفظ {count} سجلات لشركة {final_symbol}.")
                    st.rerun()
            else:
                st.error("يجب تحديد رمز السهم للحفظ.")
        else:
            st.error("لم يتم العثور على بيانات مالية صالحة.")


def render_financial_dashboard_ui(symbol):
    """
    ✅ تحسين واجهة عرض التبويب المالي بدون تغيير المنطق:
    - ترتيب أوضح
    - Cards/KPIs بدلاً من تكدس نصوص
    - تشخيص اكتمال البيانات حتى تتأكد ما فيه شيء “مبرمج” ولا يظهر
    """
    tab_dashboard, tab_data_mgmt = st.tabs(["📊 لوحة التحليل المالي", "⚙️ إدارة البيانات"])

    # =====================================================
    # Dashboard
    # =====================================================
    with tab_dashboard:
        df_annual = get_financial_statements(symbol, "Annual")
        df_quarter = get_financial_statements(symbol, "Quarterly")

        st.markdown("### 💰 لوحة التحليل المالي")
        ptype = st.radio(
            "نطاق التحليل:",
            ["Annual", "Quarterly"],
            horizontal=True,
            label_visibility="collapsed",
            key=f"fin_ptype_{_sym_key(symbol)}",
        )
        df = df_annual if ptype == "Annual" else df_quarter

        # ---- Diagnostics card
        _kv_card(
            "🧪 فحص البيانات",
            [
                ("الفترة", ptype),
                ("عدد السجلات", str(int(len(df)) if isinstance(df, pd.DataFrame) else 0)),
                ("حالة البيانات", "متوفرة ✅" if (isinstance(df, pd.DataFrame) and not df.empty) else "غير متوفرة ⚠️"),
            ],
        )

        dashboard_has_data = isinstance(df, pd.DataFrame) and (not df.empty)

        if not dashboard_has_data:
            st.warning("⚠️ لا توجد بيانات مالية محفوظة لهذا السهم.")
            st.info("👈 انتقل لتبويب 'إدارة البيانات' لرفع ملف أو جلب المعلومات.")
        else:

            # ---- Metrics
            metrics = {}
            try:
                metrics = get_advanced_fundamental_ratios(symbol) or {}
            except Exception:
                metrics = {}

            fscore = metrics.get("Piotroski_Score", 0)
            health = metrics.get("Financial_Health", "-")
            fv = metrics.get("Fair_Value_Graham", 0)
            opinions = metrics.get("Opinions", "-")

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("المتانة (F-Score)", f"{_to_num(fscore, 0):.0f}/9", str(health))
            with c2:
                st.metric("قيمة جراهام", f"{_to_num(fv, 0):,.2f}" if _to_num(fv, 0) > 0 else "N/A")
            with c3:
                st.metric("الرأي", "جاهز" if opinions and str(opinions).strip() != "-" else "—")
            with c4:
                st.metric("عدد الأعمدة", str(len(df.columns)))

            st.markdown(
                f"""
                <div class="os-card" style="margin-top:10px;">
                  <div class="os-card-title">📝 ملاحظات مالية</div>
                  <div class="os-muted">{opinions}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown("---")

            # ---- Charts selector
            st.markdown("### 📊 الرسوم البيانية")
            cols_to_plot = []
            try:
                plot_df = df.copy()
                if "date" in plot_df.columns:
                    try:
                        plot_df["Year"] = pd.to_datetime(plot_df["date"], errors="coerce").dt.strftime("%Y-%m")
                    except Exception:
                        plot_df["Year"] = plot_df["date"].astype(str)
                else:
                    plot_df["Year"] = [str(i) for i in range(len(plot_df))]

                candidates = [
                    ("revenue", "الإيرادات"),
                    ("net_income", "صافي الربح"),
                    ("operating_cash_flow", "التدفق النقدي التشغيلي"),
                    ("total_assets", "إجمالي الأصول"),
                    ("total_liabilities", "إجمالي المطلوبات"),
                    ("total_equity", "حقوق الملكية"),
                ]

                available = [(c, lbl) for c, lbl in candidates if c in plot_df.columns]
                default = [c for c, _ in available[:3]]
                pick = st.multiselect(
                    "اختر المؤشرات لعرضها",
                    options=[c for c, _ in available],
                    default=default,
                    key=f"fin_plot_pick_{_sym_key(symbol)}",
                )
                cols_to_plot = pick
                if cols_to_plot:
                    import plotly.express as px

                    fig = px.bar(
                        plot_df.sort_values("date") if "date" in plot_df.columns else plot_df,
                        x="Year",
                        y=cols_to_plot,
                        barmode="group",
                        title="الأداء المالي التاريخي",
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("اختر مؤشرًا واحدًا على الأقل لعرض الرسم.")
            except Exception:
                st.warning("تعذر رسم البيانات الآن (تحقق من وجود عمود التاريخ/القيم).")

            st.markdown("---")
            with st.expander("📋 عرض الجدول التفصيلي"):
                _render_table_like_trades(df, max_rows=600)

    # =====================================================
    # Data management
    # =====================================================
    with tab_data_mgmt:
        st.markdown("### ⚙️ إدارة البيانات")
        st.caption("هنا تستطيع تحديث البيانات تلقائيًا أو استيرادها أو إدخالها يدويًا بدون فقد أي ميزة.")

        t1, t2, t3 = st.tabs(["⚡ تحديث آلي (Yahoo)", "📂 استيراد ملف/نص", "✍️ إدخال يدوي شامل"])

        with t1:
            st.markdown(
                """
                <div class="os-card">
                  <div class="os-card-title">⚡ مزامنة تلقائية</div>
                  <div class="os-muted">سيتم جلب البيانات من Yahoo Finance مباشرة (حسب توفر الرمز والاتصال).</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("بدء المزامنة الآلية", key=f"sync_yahoo_{_sym_key(symbol)}", type="primary"):
                with st.spinner("جاري الاتصال..."):
                    ok, msg = sync_auto_yahoo(symbol)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        with t2:
            render_data_import_ui_content(symbol)

        with t3:
            st.markdown("##### تسجيل البيانات المالية يدوياً")
            st.caption("أدخل البيانات اللازمة للتحليل المالي. (نفس حقولك—بدون حذف).")

            with st.form(f"manual_fin_entry_{_sym_key(symbol)}"):
                col_meta1, col_meta2 = st.columns(2)
                f_date = col_meta1.date_input("تاريخ القوائم", date.today(), key=f"fin_date_{_sym_key(symbol)}")
                f_type = col_meta2.selectbox("الفترة", ["Annual", "Quarterly"], key=f"fin_type_{_sym_key(symbol)}")

                st.divider()
                st.markdown("**1. قائمة الدخل (Income Statement)**")
                c_inc1, c_inc2 = st.columns(2)
                rev = c_inc1.number_input("إجمالي الإيرادات", min_value=0.0, format="%.2f", key=f"fin_rev_{_sym_key(symbol)}")
                net_inc = c_inc2.number_input("صافي الربح", format="%.2f", key=f"fin_net_{_sym_key(symbol)}")

                st.divider()
                st.markdown("**2. قائمة التدفقات النقدية**")
                ocf = st.number_input("التدفق النقدي التشغيلي", help="Operating Cash Flow", format="%.2f", key=f"fin_ocf_{_sym_key(symbol)}")

                st.divider()
                st.markdown("**3. المركز المالي (Balance Sheet)**")
                c_bs1, c_bs2 = st.columns(2)
                tot_assets = c_bs1.number_input("إجمالي الأصول", min_value=0.0, format="%.2f", key=f"fin_assets_{_sym_key(symbol)}")
                tot_liab = c_bs2.number_input("إجمالي المطلوبات", min_value=0.0, format="%.2f", key=f"fin_liab_{_sym_key(symbol)}")

                c_bs3, c_bs4 = st.columns(2)
                cur_assets = c_bs3.number_input("الأصول المتداولة", min_value=0.0, format="%.2f", key=f"fin_cur_assets_{_sym_key(symbol)}")
                cur_liab = c_bs4.number_input("المطلوبات المتداولة", min_value=0.0, format="%.2f", key=f"fin_cur_liab_{_sym_key(symbol)}")

                c_bs5, c_bs6 = st.columns(2)
                tot_equity = c_bs5.number_input("إجمالي حقوق الملكية", format="%.2f", key=f"fin_equity_{_sym_key(symbol)}")
                lt_debt = c_bs6.number_input("الديون طويلة الأجل", min_value=0.0, format="%.2f", key=f"fin_ltdebt_{_sym_key(symbol)}")

                st.divider()
                if st.form_submit_button("💾 حفظ البيانات", type="primary"):
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
                    if save_financial_record(symbol, str(f_date), data, f_type, "Manual_Full"):
                        st.success("تم الحفظ بنجاح!")
                        st.rerun()
                    else:
                        st.error("فشل الحفظ. تأكد من البيانات.")
