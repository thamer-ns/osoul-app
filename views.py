import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import date
from config import DEFAULT_COLORS
from components import render_kpi, render_custom_table, render_ticker_card, safe_fmt
from analytics import calculate_portfolio_metrics, update_prices, generate_equity_curve, create_smart_backup
from database import execute_query, fetch_table
from market_data import get_static_info, get_tasi_data, get_chart_history, fetch_batch_data
from data_source import get_company_details
from security import validate_trade_inputs

# ========================================================
# 🛡️ استيراد الوحدات مع الحماية (Fail-Safe Imports)
# ========================================================

# 1. الرسوم البيانية
try:
    from charts import render_technical_chart
except ImportError:
    def render_technical_chart(symbol): st.warning("⚠️ ملف charts.py مفقود أو به خطأ.")

# 2. المختبر (Backtester)
try:
    from backtester import run_backtest
except ImportError:
    run_backtest = None 

# 3. التحليل المالي
try:
    from financial_analysis import (
        get_thesis, save_thesis, 
        FinancialParser, save_financial_record, 
        get_stored_financials_df, get_advanced_fundamental_ratios,
        sync_auto_yahoo
    )
except ImportError:
    def get_thesis(s): return {}
    def save_thesis(s, t, tg, r): pass
    def get_stored_financials_df(s, p): return pd.DataFrame()
    def get_advanced_fundamental_ratios(s): return {}
    class FinancialParser: pass
    def save_financial_record(*args): pass
    def sync_auto_yahoo(s): return False, "Module Missing"

# 4. التحليل الكلاسيكي
try:
    from classical_analysis import render_classical_analysis
except ImportError:
    def render_classical_analysis(s): st.warning("⚠️ ملف classical_analysis.py مفقود.")

# 5. محرك الذكاء الاصطناعي (AI Engine)
try:
    from ai_engine import generate_ai_report, calculate_portfolio_risk_score, run_stress_test, generate_rebalancing_suggestions
except ImportError:
    def generate_ai_report(s): return {} 
    def calculate_portfolio_risk_score(df, c): return 50
    def run_stress_test(v, df): return {"scenarios": [], "insight": ""}
    def generate_rebalancing_suggestions(df, c): return []

# ========================================================
# 1. شريط التنقل (Navigation)
# ========================================================
def render_navbar():
    buttons = [
        ('🏠 الرئيسية','home'), ('⚡ مضاربة','spec'), ('💎 استثمار','invest'),
        ('💓 نبض','pulse'), ('📜 صكوك','sukuk'), ('🔍 تحليل','analysis'),
        ('🧪 المختبر','backtest'), ('💰 السيولة','cash'), ('🔄 تحديث','update')
    ]
    
    st.markdown("""<style>div.stButton > button {width: 100%; border-radius: 8px;}</style>""", unsafe_allow_html=True)
    
    cols = st.columns(len(buttons) + 1)
    for i, (label, key) in enumerate(buttons):
        with cols[i]:
            is_active = st.session_state.page == key
            if st.button(label, key=f"nav_{key}", type="primary" if is_active else "secondary"):
                st.session_state.page = key
                st.rerun()
                
    with cols[-1]:
        with st.popover("👤 القائمة"):
            st.write(f"مرحباً, {st.session_state.get('username', 'Guest')}")
            if st.button("➕ إضافة صفقة", key="nav_add"): st.session_state.page='add'; st.rerun()
            if st.button("⚙️ إعدادات", key="nav_set"): st.session_state.page='settings'; st.rerun()
            st.divider()
            if st.button("🚪 خروج", key="nav_logout"):
                try: from security import logout; logout()
                except: st.session_state.clear(); st.rerun()

# ========================================================
# 2. لوحة القيادة (Dashboard)
# ========================================================
def view_dashboard(fin):
    try: tp, tc = get_tasi_data()
    except: tp, tc = 0, 0
    ar = "🔼" if tc >= 0 else "🔽"
    clr = "#4caf50" if tc >= 0 else "#f44336"

    df = fin['all_trades']
    total_assets = fin['market_val_open'] + fin['cash']
    cash_pct = (fin['cash'] / total_assets * 100) if total_assets else 0
    
    c_tasi, c_risk = st.columns([3, 1])
    with c_tasi:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); padding: 20px; border-radius: 15px; color: white; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div>
                <div style="font-size: 0.9rem; opacity: 0.8;">المؤشر العام (TASI)</div>
                <div style="font-size: 2.2rem; font-weight: bold;">{safe_fmt(tp)}</div>
            </div>
            <div style="background: rgba(255,255,255,0.2); padding: 5px 15px; border-radius: 20px; font-weight: bold; font-size: 1.2rem;">
                {ar} {tc:.2f}%
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with c_risk:
        risk_score = calculate_portfolio_risk_score(df, cash_pct)
        r_col = "success" if risk_score < 40 else "warning" if risk_score < 70 else "danger"
        render_kpi("مستوى المخاطرة", f"{risk_score}/100", r_col, "🛡️")

    st.divider()

    c1, c2, c3, c4 = st.columns(4)
    total_pl = fin['unrealized_pl'] + fin['realized_pl']
    with c1: render_kpi(f"الكاش المتوفر ({cash_pct:.1f}%)", safe_fmt(fin['cash']), "blue", "💵")
    with c2: render_kpi("صافي الإيداعات", safe_fmt(fin['total_deposited'] - fin['total_withdrawn']), "neutral", "🏦")
    with c3: render_kpi("قيمة الأصول الحالية", safe_fmt(fin['market_val_open']), "neutral", "📊")
    with c4: render_kpi("الربح الكلي (المحقق+الورقي)", safe_fmt(total_pl), 'success' if total_pl>=0 else 'danger', "💰")

    if not df.empty:
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.subheader("توزيع الأصول")
            try:
                open_trades = df[df['status'] == 'Open']
                invest_val = open_trades[open_trades['strategy'].astype(str).str.contains('استثمار', na=False)]['market_value'].sum()
                spec_val = open_trades[open_trades['strategy'].astype(str).str.contains('مضاربة', na=False)]['market_value'].sum()
                sukuk_val = open_trades[open_trades['asset_type'] == 'Sukuk']['market_value'].sum()
                
                alloc_data = {'Asset': ['استثمار', 'مضاربة', 'صكوك', 'كاش'], 
                              'Value': [invest_val, spec_val, sukuk_val, fin['cash']]}
                fig = px.pie(alloc_data, values='Value', names='Asset', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.update_layout(height=300, margin=dict(t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
            except: st.info("جاري تجميع البيانات...")

        with col_chart2:
            st.subheader("نمو المحفظة")
            curve = generate_equity_curve(df)
            if not curve.empty:
                fig2 = px.line(curve, x='date', y='cumulative_invested', title='')
                fig2.update_traces(line_color='#2ecc71', line_width=3)
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("لا توجد بيانات تاريخية كافية للرسم.")
    else:
        st.info("ابدأ بإضافة صفقات لتظهر التحليلات هنا.")

# ========================================================
# 3. عرض المحفظة (Portfolio View)
# ========================================================
def view_portfolio(fin, key):
    ts = "مضاربة" if key == 'spec' else "استثمار"
    st.header(f"💼 محفظة ال{ts}")
    
    df = fin['all_trades']
    if df.empty:
        st.info("لا توجد صفقات.")
        return

    sub = df[df['strategy'].astype(str).str.contains(ts, na=False)].copy()
    op = sub[sub['status'] == 'Open'].copy()
    cl = sub[sub['status'] == 'Close'].copy()

    tab1, tab2 = st.tabs(["📌 الصفقات القائمة", "🗄️ الأرشيف المغلق"])

    with tab1:
        if not op.empty:
            tot_cost = op['total_cost'].sum()
            tot_val = op['market_value'].sum()
            tot_gain = op['gain'].sum()
            k1, k2, k3 = st.columns(3)
            with k1: render_kpi("التكلفة", safe_fmt(tot_cost), "neutral")
            with k2: render_kpi("القيمة السوقية", safe_fmt(tot_val), "blue")
            with k3: render_kpi("الربح/الخسارة", safe_fmt(tot_gain), "success" if tot_gain>=0 else "danger")
            
            st.divider()
            
            live_data = fetch_batch_data(op['symbol'].unique().tolist())
            op['prev_close'] = op['symbol'].apply(lambda x: live_data.get(x, {}).get('prev_close', 0))
            op['day_change'] = op.apply(lambda r: ((r['current_price'] - r['prev_close']) / r['prev_close'] * 100) if r['prev_close'] > 0 else 0, axis=1)
            op['status_ar'] = "مفتوحة"

            cols = [
                ('company_name', 'الشركة', 'text'), 
                ('symbol', 'الرمز', 'text'),
                ('quantity', 'الكمية', 'money'), 
                ('entry_price', 'متوسط التكلفة', 'money'),
                ('current_price', 'السعر الحالي', 'money'),
                ('day_change', 'التغير اليومي', 'percent'),
                ('gain', 'الربح/الخسارة', 'colorful'),
                ('gain_pct', 'النسبة %', 'percent')
            ]
            render_custom_table(op, cols)

            c_act1, c_act2 = st.columns(2)
            with c_act1:
                with st.expander("🔴 إغلاق صفقة (بيع)"):
                    opts = {f"{r['company_name']} ({r['quantity']})": r['id'] for _, r in op.iterrows()}
                    sel = st.selectbox("اختر الصفقة", list(opts.keys()), key=f"sel_sell_{key}")
                    if sel:
                        tid = opts[sel]
                        with st.form(f"sell_{tid}"):
                            p = st.number_input("سعر البيع", min_value=0.0)
                            d = st.date_input("تاريخ البيع", date.today())
                            if st.form_submit_button("تنفيذ البيع"):
                                execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s", (p, str(d), tid))
                                st.success("تم البيع!"); st.cache_data.clear(); st.rerun()
            
            with c_act2:
                with st.expander("✏️ تعديل صفقة"):
                    opts_e = {f"{r['company_name']} - {r['date']}": r['id'] for _, r in op.iterrows()}
                    sel_e = st.selectbox("اختر للتعديل", list(opts_e.keys()), key=f"sel_edit_{key}")
                    if sel_e:
                        tid = opts_e[sel_e]
                        curr = op[op['id'] == tid].iloc[0]
                        with st.form(f"edit_{tid}"):
                            nq = st.number_input("الكمية", value=float(curr['quantity']))
                            np = st.number_input("سعر الشراء", value=float(curr['entry_price']))
                            nd = st.date_input("التاريخ", pd.to_datetime(curr['date']))
                            if st.form_submit_button("حفظ التعديل"):
                                execute_query("UPDATE Trades SET quantity=%s, entry_price=%s, date=%s WHERE id=%s", (nq, np, str(nd), tid))
                                st.success("تم التعديل!"); st.cache_data.clear(); st.rerun()
        else:
            st.info("لا توجد صفقات مفتوحة في هذه المحفظة.")

    with tab2:
        if not cl.empty:
            render_custom_table(cl, [('company_name','الشركة','text'), ('gain','الربح المحقق','colorful'), ('exit_date','تاريخ الخروج','date')])
        else:
            st.info("الأرشيف فارغ.")

# ========================================================
# 4. محفظة الصكوك
# ========================================================
def view_sukuk_portfolio(fin):
    st.header("📜 الصكوك والعوائد الثابتة")
    df = fin['all_trades']
    sukuk = df[df['asset_type'] == 'Sukuk'].copy() if not df.empty else pd.DataFrame()
    
    if sukuk.empty:
        st.warning("لم تقم بإضافة أي صكوك بعد.")
        if st.button("➕ إضافة صك جديد"): st.session_state.page='add'; st.rerun()
        return

    op = sukuk[sukuk['status'] == 'Open']
    if not op.empty:
        total_inv = op['total_cost'].sum()
        st.metric("إجمالي الاستثمار في الصكوك", safe_fmt(total_inv))
        
        cols = [('company_name', 'اسم الصك', 'text'), ('quantity', 'العدد', 'text'), 
                ('entry_price', 'قيمة الصك', 'money'), ('total_cost', 'الإجمالي', 'money'), ('date', 'تاريخ الشراء', 'date')]
        render_custom_table(op, cols)
        
        with st.expander("استرداد / بيع صك"):
            opts = {f"{r['company_name']}": r['id'] for _, r in op.iterrows()}
            s = st.selectbox("اختر الصك", list(opts.keys()))
            if s:
                tid = opts[s]
                with st.form(f"sukuk_{tid}"):
                    val = st.number_input("المبلغ المسترد كاملاً")
                    dt = st.date_input("تاريخ الاسترداد")
                    if st.form_submit_button("تأكيد"):
                        qty = float(op[op['id']==tid].iloc[0]['quantity'])
                        ep = val / qty if qty else 0
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s", (ep, str(dt), tid))
                        st.success("تم"); st.cache_data.clear(); st.rerun()
    else:
        st.info("جميع الصكوك مغلقة.")

# ========================================================
# 5. سجل السيولة (Cash Log)
# ========================================================
def view_cash_log():
    st.header("💰 سجل العمليات المالية")
    fin = calculate_portfolio_metrics()
    
    t1, t2, t3 = st.tabs(["📥 الإيداعات", "📤 السحوبات", "🎁 التوزيعات"])
    
    with t1:
        with st.form("new_dep"):
            a = st.number_input("المبلغ", min_value=0.0)
            d = st.date_input("التاريخ", date.today())
            n = st.text_input("ملاحظة")
            if st.form_submit_button("تسجيل إيداع"):
                execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                st.success("تم"); st.cache_data.clear(); st.rerun()
        if not fin['deposits'].empty: render_custom_table(fin['deposits'], [('date','التاريخ','date'),('amount','المبلغ','money'),('note','ملاحظة','text')])

    with t2:
        with st.form("new_wit"):
            a = st.number_input("المبلغ", min_value=0.0)
            d = st.date_input("التاريخ", date.today())
            n = st.text_input("ملاحظة")
            if st.form_submit_button("تسجيل سحب"):
                execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                st.success("تم"); st.cache_data.clear(); st.rerun()
        if not fin['withdrawals'].empty: render_custom_table(fin['withdrawals'], [('date','التاريخ','date'),('amount','المبلغ','money'),('note','ملاحظة','text')])

    with t3:
        with st.form("new_ret"):
            s = st.text_input("رمز السهم")
            a = st.number_input("مبلغ التوزيع", min_value=0.0)
            d = st.date_input("التاريخ", date.today())
            if st.form_submit_button("تسجيل توزيعات"):
                execute_query("INSERT INTO ReturnsGrants (date, symbol, amount) VALUES (%s,%s,%s)", (str(d), s, a))
                st.success("تم"); st.cache_data.clear(); st.rerun()
        if not fin['returns'].empty: render_custom_table(fin['returns'], [('date','التاريخ','date'),('symbol','السهم','text'),('amount','المبلغ','money')])

# ========================================================
# 6. التحليل الشامل (Analysis)
# ========================================================

def render_data_import_ui_content(symbol):
    st.info("يدعم النظام: ملفات PDF من تداول، ملفات Excel/CSV، أو النسخ واللصق المباشر.")
    
    parser = FinancialParser()
    
    uploaded_file = st.file_uploader("رفع ملف قوائم مالية (PDF, Excel, CSV)", type=['pdf', 'xlsx', 'xls', 'csv'])
    pasted_text = st.text_area("أو الصق البيانات هنا مباشرة:")
    
    if st.button("🚀 معالجة واستخراج البيانات"):
        results = []
        detected_symbol = None
        
        with st.spinner("جاري تحليل النصوص واستخراج الأرقام..."):
            if uploaded_file:
                results, detected_symbol = parser.process_file_or_text(uploaded_file=uploaded_file)
            elif pasted_text:
                results, detected_symbol = parser.process_file_or_text(text_input=pasted_text)
                
        if isinstance(results, tuple): 
             results, detected_symbol, err_msg = results
             if err_msg:
                 st.error(err_msg)
                 return

        if results:
            st.success(f"تم استخراج {len(results)} سجلات بنجاح!")
            final_symbol = symbol
            
            if detected_symbol and detected_symbol != symbol:
                st.warning(f"⚠️ الملف لشركة {detected_symbol}، وأنت في صفحة {symbol}.")
                if st.checkbox(f"استخدام {detected_symbol}؟", value=True): final_symbol = detected_symbol
            
            if not final_symbol:
                final_symbol = st.text_input("⚠️ الرجاء إدخال رمز السهم (مثال: 1120.SR):")
            
            if final_symbol:
                st.write("### 🧐 مراجعة البيانات المستخرجة:")
                preview_df = pd.DataFrame([{'Date': r['date'], **r['data']} for r in results])
                st.dataframe(preview_df)
                
                if st.button("💾 تأكيد وحفظ في قاعدة البيانات"):
                    count = 0
                    for r in results:
                        if save_financial_record(final_symbol, r['date'], r['data'], source='File/Paste'):
                            count += 1
                    st.success(f"تم حفظ {count} سجلات لشركة {final_symbol}.")
                    st.rerun()
            else:
                st.error("يجب تحديد رمز السهم للحفظ.")
        else:
            st.error("لم يتم العثور على بيانات مالية صالحة.")

def render_financial_dashboard_ui(symbol):
    tab_dashboard, tab_data_mgmt = st.tabs(["📊 لوحة التحليل المالي", "⚙️ إدارة البيانات"])
    
    with tab_dashboard:
        ptype = st.radio("نطاق التحليل:", ["Annual", "Quarterly"], horizontal=True, label_visibility="collapsed")
        df = get_stored_financials_df(symbol, ptype)
        
        if df.empty:
            st.warning("⚠️ لا توجد بيانات مالية محفوظة لهذا السهم.")
            st.info("👈 انتقل لتبويب 'إدارة البيانات' لرفع ملف أو جلب المعلومات.")
        else:
            metrics = get_advanced_fundamental_ratios(symbol)
            c1, c2, c3 = st.columns(3)
            c1.metric("المتانة (F-Score)", f"{metrics['Piotroski_Score']}/9", metrics['Financial_Health'])
            fv = metrics.get('Fair_Value_Graham', 0)
            c2.metric("قيمة جراهام", f"{fv:,.2f}" if fv > 0 else "N/A")
            c3.write(f"**ملاحظات:** {metrics.get('Opinions', '-')}")
            st.markdown("---")
            
            try:
                plot_df = df.copy()
                plot_df['Year'] = plot_df['date'].dt.strftime('%Y-%m')
                cols_to_plot = [c for c in ['revenue', 'net_income', 'operating_cash_flow'] if c in plot_df.columns and plot_df[c].sum() != 0]
                if cols_to_plot:
                    fig = px.bar(plot_df.sort_values('date'), x='Year', y=cols_to_plot, barmode='group', title="الأداء المالي التاريخي")
                    st.plotly_chart(fig, use_container_width=True)
            except: pass

            with st.expander("عرض الجدول التفصيلي"):
                st.dataframe(df, use_container_width=True)
            
    with tab_data_mgmt:
        st.markdown("#### مصادر البيانات")
        t1, t2, t3 = st.tabs(["⚡ تحديث آلي (Yahoo)", "📂 استيراد ملف/نص", "✍️ إدخال يدوي شامل"])
        
        with t1:
            st.caption("جلب البيانات من Yahoo Finance مباشرة")
            if st.button("بدء المزامنة الآلية"):
                with st.spinner("جاري الاتصال..."):
                    ok, msg = sync_auto_yahoo(symbol)
                    if ok: st.success(msg); st.rerun()
                    else: st.error(msg)
        
        with t2:
            render_data_import_ui_content(symbol)
            
        with t3:
            # === [START] النموذج اليدوي الجديد والمفصل ===
            st.markdown("##### تسجيل البيانات المالية يدوياً")
            st.caption("أدخل البيانات اللازمة للتحليل المالي (جراهام، بيوتروسكي، وجودة الأرباح).")
            
            with st.form("manual_fin_entry"):
                col_meta1, col_meta2 = st.columns(2)
                f_date = col_meta1.date_input("تاريخ القوائم", date.today())
                f_type = col_meta2.selectbox("الفترة", ["Annual", "Quarterly"])
                
                st.divider()
                st.markdown("**1. قائمة الدخل (Income Statement)**")
                c_inc1, c_inc2 = st.columns(2)
                rev = c_inc1.number_input("إجمالي الإيرادات (Revenue)", min_value=0.0, format="%.2f")
                net_inc = c_inc2.number_input("صافي الربح (Net Income)", format="%.2f")
                
                st.divider()
                st.markdown("**2. قائمة التدفقات النقدية (Cash Flow)**")
                ocf = st.number_input("التدفق النقدي التشغيلي (Operating Cash Flow)", help="مهم جداً لقياس جودة الأرباح", format="%.2f")
                
                st.divider()
                st.markdown("**3. المركز المالي (Balance Sheet)**")
                c_bs1, c_bs2 = st.columns(2)
                tot_assets = c_bs1.number_input("إجمالي الأصول (Total Assets)", min_value=0.0, format="%.2f")
                tot_liab = c_bs2.number_input("إجمالي المطلوبات (Total Liabilities)", min_value=0.0, format="%.2f")
                
                c_bs3, c_bs4 = st.columns(2)
                cur_assets = c_bs3.number_input("الأصول المتداولة (Current Assets)", min_value=0.0, format="%.2f")
                cur_liab = c_bs4.number_input("المطلوبات المتداولة (Current Liabilities)", min_value=0.0, format="%.2f")
                
                c_bs5, c_bs6 = st.columns(2)
                tot_equity = c_bs5.number_input("إجمالي حقوق الملكية (Equity)", format="%.2f")
                lt_debt = c_bs6.number_input("الديون طويلة الأجل (Long Term Debt)", min_value=0.0, format="%.2f")

                st.divider()
                if st.form_submit_button("💾 حفظ البيانات المالية"):
                    data = {
                        'revenue': rev, 'net_income': net_inc, 'operating_cash_flow': ocf,
                        'total_assets': tot_assets, 'total_liabilities': tot_liab,
                        'current_assets': cur_assets, 'current_liabilities': cur_liab,
                        'total_equity': tot_equity, 'long_term_debt': lt_debt
                    }
                    if save_financial_record(symbol, str(f_date), data, f_type, 'Manual_Full'):
                        st.success("تم الحفظ بنجاح! سيتم تحديث التحليل الآن.")
                        st.rerun()
                    else:
                        st.error("فشل الحفظ. تأكد من إدخال قيم صالحة.")
            # === [END] ===

def view_analysis(fin):
    st.header("🔬 التحليل الشامل والمستشار الذكي")
    
    trades = fin['all_trades']
    total_assets = fin['market_val_open'] + fin['cash']
    cash_pct = (fin['cash'] / total_assets * 100) if total_assets else 0

    if not trades.empty:
        open_pos = trades[trades['status']=='Open']
        st.subheader("🛡️ اختبار التحمل (Stress Test)")
        stress = run_stress_test(fin['market_val_open'], open_pos)
        if stress.get('scenarios'):
            c_ch, c_tx = st.columns([3, 1])
            with c_ch:
                sdf = pd.DataFrame(stress['scenarios'])
                fig = px.bar(sdf, x='scenario', y='impact_pct', color='scenario', 
                             title="تأثير سيناريوهات السوق على المحفظة",
                             color_discrete_map={row['scenario']: row['color'] for _, row in sdf.iterrows()})
                st.plotly_chart(fig, use_container_width=True)
            with c_tx:
                st.info(stress.get('insight', ''))
        st.divider()

    wl = fetch_table("Watchlist")
    my_stocks = trades['symbol'].unique().tolist() if not trades.empty else []
    wl_stocks = wl['symbol'].unique().tolist() if not wl.empty else []
    all_stocks = list(set(my_stocks + wl_stocks))
    
    c_sel1, c_sel2 = st.columns([2, 1])
    search_sym = c_sel2.text_input("بحث عن رمز جديد")
    
    options = [search_sym] + all_stocks if search_sym else all_stocks
    selected_sym = c_sel1.selectbox("اختر الشركة للتحليل:", options) if options else None
    
    if selected_sym:
        nm, sc = get_company_details(selected_sym)
        st.markdown(f"## {nm} ({selected_sym}) - {sc}")
        
        at1, at2, at3, at4, at5 = st.tabs(["🤖 المستشار", "💰 القوائم المالية", "📈 الشارت الفني", "🏛️ كلاسيكي", "📝 ملاحظاتي"])
        
        with at1:
            ai_suggestions = generate_rebalancing_suggestions(trades, cash_pct)
            if ai_suggestions:
                with st.expander(f"📢 تنبيهات المستشار الذكي للمحفظة ({len(ai_suggestions)})", expanded=True):
                    for level, msg in ai_suggestions:
                        if level == 'priority': st.error(msg, icon="🚨")
                        elif level == 'warning': st.warning(msg, icon="⚠️")
                        elif level == 'success': st.success(msg, icon="✅")
                        else: st.info(msg, icon="ℹ️")

            with st.spinner("جاري تحليل البيانات..."):
                report = generate_ai_report(selected_sym)
            
            rec_text = report.get('recommendation', 'غير متوفر')
            rec_color = report.get('color', '#6c757d')
            rec_strat = report.get('strategy', 'لا توجد بيانات كافية للتحليل')
            
            st.markdown(f"""
            <div style="text-align:center; padding: 20px; background-color: #f8f9fa; border-radius: 15px; border: 2px solid {rec_color}; margin-bottom: 20px;">
                <h2 style="color: {rec_color}; margin:0;">{rec_text}</h2>
                <p style="color: #333; margin-top:10px; font-size:1.1rem;">{rec_strat}</p>
            </div>
            """, unsafe_allow_html=True)
            
            col_t, col_f = st.columns(2)
            with col_t:
                st.markdown("##### 📐 الرؤية الفنية")
                for r in report.get('tech_reasons', []): st.write(f"• {r}")
            with col_f:
                st.markdown("##### 📊 الرؤية المالية")
                for r in report.get('fund_reasons', []): st.write(f"• {r}")

        with at2: render_financial_dashboard_ui(selected_sym)
        with at3: render_technical_chart(selected_sym)
        with at4: render_classical_analysis(selected_sym)
        with at5:
            thesis = get_thesis(selected_sym)
            old_txt = thesis['thesis_text'] if thesis else ""
            with st.form("th_form"):
                new_txt = st.text_area("اكتب تحليلك الخاص أو ملاحظاتك هنا:", value=old_txt, height=200)
                if st.form_submit_button("حفظ الملاحظات"):
                    save_thesis(selected_sym, new_txt, 0, "Hold")
                    st.success("تم الحفظ")

# ========================================================
# 7. المختبر (Backtester)
# ========================================================
def view_backtester_ui(fin):
    st.header("🧪 مختبر الاستراتيجيات")
    if not run_backtest:
        st.error("⚠️ وحدة الاختبار غير متوفرة. تأكد من وجود الملف backtester.py")
        return

    all_syms = fin['all_trades']['symbol'].unique().tolist()
    if "1120.SR" not in all_syms: all_syms.append("1120.SR")
    
    c1, c2, c3 = st.columns(3)
    s = c1.selectbox("السهم للاختبار", all_syms)
    strat = c2.selectbox("الاستراتيجية", ["Trend Follower", "Sniper", "RSI Reversal"])
    amount = c3.number_input("رأس المال الافتراضي", 100000, step=5000)
    
    if st.button("🚀 تشغيل المحاكاة"):
        with st.spinner("جاري العودة بالزمن واختبار البيانات..."):
            hist = get_chart_history(s, period="2y")
            res = run_backtest(hist, strat, amount)
            
            if res:
                st.success("اكتمل الاختبار!")
                m1, m2, m3 = st.columns(3)
                ret_col = "success" if res['return_pct'] > 0 else "danger"
                m1.metric("العائد النهائي", f"{res['return_pct']:.2f}%")
                m2.metric("القيمة النهائية", f"{res['final_value']:,.2f}")
                m3.metric("عدد الصفقات", len(res['trades_log']))
                
                st.line_chart(res['df']['Portfolio_Value'])
                with st.expander("سجل الصفقات الافتراضية"):
                    st.dataframe(res['trades_log'])
            else:
                st.error("فشل الاختبار. قد لا تتوفر بيانات تاريخية كافية.")

# ========================================================
# 8. نبض السوق وإضافة صفقة والإعدادات
# ========================================================
# ========================================================
# 8. نبض السوق (Market Pulse) - المطور
# ========================================================
# ========================================================
# 8. نبض السوق (Market Pulse) - التصميم المطور 🌟
# ========================================================
def render_pulse_dashboard():
    st.header("💓 نبض السوق والفرص")
    
    # 1. تحديد القوائم
    market_leaders = ['1120.SR', '2222.SR', '2010.SR', '7010.SR', '1180.SR'] 
    
    wl = fetch_table("Watchlist")
    trades = fetch_table("Trades")
    my_stocks = list(set(wl['symbol'].tolist() + trades['symbol'].tolist()))
    
    all_syms = list(set(market_leaders + my_stocks))
    
    if not all_syms:
        st.info("لا توجد أسهم للمراقبة.")
        return
        
    # جلب البيانات
    with st.spinner("جاري مسح السوق..."):
        data = fetch_batch_data(all_syms)
    
    # تجهيز البيانات
    rows = []
    for sym, info in data.items():
        price = info.get('price', 0)
        prev = info.get('prev_close', 0)
        high_yr = info.get('year_high', 0)
        low_yr = info.get('year_low', 0)
        
        # جلب الاسم العربي
        name, _ = get_company_details(sym)
        
        change_pct = ((price - prev) / prev * 100) if prev > 0 else 0
        
        # موقع السعر من القمة والقاع (0 - 100)
        range_pos = 0
        if high_yr > low_yr:
            range_pos = (price - low_yr) / (high_yr - low_yr) * 100
            
        rows.append({
            'symbol': sym,
            'name': name,
            'price': price,
            'change': change_pct,
            'range_pos': range_pos,
            'year_low': low_yr,
            'year_high': high_yr,
            'is_leader': f"{sym}.SR" in market_leaders or sym in market_leaders
        })
    
    df_pulse = pd.DataFrame(rows)
    if df_pulse.empty: return

    # --- 1. القياديات (مؤشرات السوق) ---
    st.markdown("##### 🏛️ القياديات (اتجاه السوق)")
    leaders = df_pulse[df_pulse['is_leader'] == True]
    cols_l = st.columns(len(leaders))
    for i, row in enumerate(leaders.to_dict('records')):
        with cols_l[i]:
            # عرض مبسط للقياديات
            st.metric(row['name'], f"{row['price']}", f"{row['change']:.2f}%")
    
    st.divider()
    
    # --- 2. الأكثر حركة (السيولة) ---
    c_win, c_lose = st.columns(2)
    
    def render_card(r):
        color = "#059669" if r['change'] >= 0 else "#DC2626"
        bg_color = "#ECFDF5" if r['change'] >= 0 else "#FEF2F2"
        arrow = "🔼" if r['change'] >= 0 else "🔽"
        
        st.markdown(f"""
        <div style="background:white; border:1px solid #E5E7EB; border-radius:12px; padding:12px; margin-bottom:10px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="font-weight:bold; font-size:1rem; color:#1F2937;">{r['name']}</div>
                    <div style="font-size:0.8rem; color:#6B7280; font-family:monospace;">{r['symbol']}</div>
                </div>
                <div style="text-align:left;">
                    <div style="font-weight:bold; font-size:1.1rem; color:#111827;">{r['price']}</div>
                    <div style="font-size:0.85rem; color:{color}; background:{bg_color}; padding:2px 6px; border-radius:6px; font-weight:600;">
                        {r['change']:+.2f}%
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with c_win:
        st.markdown("##### 🚀 الأكثر ارتفاعاً")
        winners = df_pulse.sort_values('change', ascending=False).head(5)
        for _, row in winners.iterrows():
            if row['change'] > 0: render_card(row)
            else: st.caption("لا يوجد")

    with c_lose:
        st.markdown("##### 🩸 الأكثر انخفاضاً")
        losers = df_pulse.sort_values('change', ascending=True).head(5)
        for _, row in losers.iterrows():
            if row['change'] < 0: render_card(row)
            else: st.caption("لا يوجد")
            
    # --- 3. رادار القمم والقيعان (Visual Radar) ---
    st.markdown("---")
    st.markdown("##### 🎯 رادار الأسعار (موقع السعر من أدنى وأعلى سنوي)")
    
    # تصفية الأسهم التي قريبة من القاع (أقل من 20%) أو القمة (أكثر من 80%)
    opportunities = df_pulse[(df_pulse['range_pos'] < 20) | (df_pulse['range_pos'] > 80)].sort_values('range_pos')
    
    if not opportunities.empty:
        for _, row in opportunities.iterrows():
            c1, c2 = st.columns([1, 3])
            with c1:
                st.markdown(f"**{row['name']}**")
                st.caption(f"{row['symbol']}")
            with c2:
                # شريط التقدم المرئي
                val = int(row['range_pos'])
                st.progress(val / 100)
                
                # وصف الحالة
                if val < 20:
                    st.caption(f"🟢 في مناطق قاع (الأدنى: {row['year_low']}) - السعر الحالي: {row['price']}")
                else:
                    st.caption(f"🔴 في مناطق قمة (الأعلى: {row['year_high']}) - السعر الحالي: {row['price']}")
    else:
        st.info("جميع الأسهم تتداول في مناطق متوسطة حالياً.")
def view_settings():
    st.header("⚙️ الإعدادات والنظام")
    
    st.subheader("📦 النسخ الاحتياطي")
    if st.button("تحميل نسخة من بياناتي (Excel)"):
        data, name = create_smart_backup()
        if data:
            st.download_button("📥 تنزيل الملف", data, name, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.success("جاهز للتنزيل")

# ========================================================
# 9. الموجه الرئيسي (Router)
# ========================================================
def router():
    if 'page' not in st.session_state: st.session_state.page = 'home'
    
    render_navbar()
    
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    
    if pg == 'home': view_dashboard(fin)
    elif pg == 'spec': view_portfolio(fin, 'spec')
    elif pg == 'invest': view_portfolio(fin, 'invest')
    elif pg == 'sukuk': view_sukuk_portfolio(fin)
    elif pg == 'cash': view_cash_log()
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'backtest': view_backtester_ui(fin)
    elif pg == 'pulse': render_pulse_dashboard()
    elif pg == 'add': view_add_trade()
    elif pg == 'settings': view_settings()
    elif pg == 'update':
        with st.spinner("جاري تحديث الأسعار من السوق..."):
            update_prices()
        st.success("تم التحديث!")
        st.session_state.page = 'home'
        st.rerun()
