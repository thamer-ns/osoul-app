import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

# === الاستيرادات ===
from components import render_navbar, render_kpi, render_table
from analytics import (calculate_portfolio_metrics, update_prices, create_smart_backup, 
                       get_comprehensive_performance, get_dividends_calendar, 
                       generate_equity_curve, calculate_historical_drawdown)
from charts import render_technical_chart
from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui
from market_data import get_static_info, get_tasi_data
from database import execute_query, fetch_table, get_db
from config import APP_NAME
from data_source import TADAWUL_DB

# === دوال مساعدة ===

def safe_fmt(val, suffix=""):
    """تنسيق آمن للأرقام"""
    if val is None: return "غير متاح"
    try:
        num = float(val)
        if num == 0 and suffix == "": return "0.00"
        return f"{num:.2f}{suffix}"
    except: return "غير متاح"

def apply_sorting(df, cols_definition, key_suffix):
    """تطبيق الفرز على الجداول"""
    if df.empty: return df
    with st.expander("🔍 أدوات الفرز والتصفية", expanded=False):
        label_to_col = {label: col for col, label in cols_definition}
        sort_options = list(label_to_col.keys())
        c1, c2 = st.columns([2, 1])
        with c1: selected = st.selectbox("فرز حسب:", sort_options, key=f"sc_{key_suffix}")
        with c2: order = st.radio("الترتيب:", ["تنازلي", "تصاعدي"], horizontal=True, key=f"so_{key_suffix}")
    target = label_to_col[selected]
    asc = (order == "تصاعدي")
    try: return df.sort_values(by=target, ascending=asc)
    except: return df

# === الصفحات (Views) ===

def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    
    arrow = "🔼" if t_change >= 0 else "🔽"
    color = "#10B981" if t_change >= 0 else "#EF4444"
    
    # كارد المؤشر العام
    st.markdown(f"""
    <div style="background:white; padding:20px; border-radius:12px; border:1px solid #E5E7EB; margin-bottom:20px; display:flex; justify-content:space-between; align-items:center; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
        <div>
            <div style="font-size:0.9rem; color:#6B7280; font-weight:bold;">المؤشر العام (TASI)</div>
            <div style="font-size:2rem; font-weight:900; color:#1F2937;">{t_price:,.2f}</div>
        </div>
        <div style="background:{color}15; color:{color}; padding:8px 20px; border-radius:10px; font-size:1.2rem; font-weight:bold; direction:ltr;">
            {arrow} {t_change:+.2f}%
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 📊 الملخص المالي")
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi("الكاش المتوفر", f"{fin['cash']:,.2f}", "blue")
    with c2: render_kpi("رأس المال المستثمر", f"{(fin['total_deposited']-fin['total_withdrawn']):,.2f}")
    with c3: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}")
    
    total_pl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("صافي الربح الكلي", f"{total_pl:,.2f}", total_pl)
    
    st.markdown("---")
    
    st.markdown("### 📈 نمو المحفظة")
    curve_data = generate_equity_curve(fin['all_trades'])
    if not curve_data.empty and 'date' in curve_data.columns:
        fig = px.line(curve_data, x='date', y='cumulative_invested')
        fig.update_layout(yaxis_title="القيمة (ريال)", xaxis_title="التاريخ", font=dict(family="Cairo"), paper_bgcolor="white", plot_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("📉 لا توجد بيانات كافية لرسم منحنى النمو.")

def view_portfolio(fin, page_key):
    target_strat = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {target_strat}")
    
    all_data = fin['all_trades']
    if all_data.empty: st.info("لا توجد بيانات"); return
    
    df_strat = all_data[(all_data['strategy'] == target_strat) & (all_data['asset_type'] != 'Sukuk')].copy()
    if df_strat.empty: st.warning("المحفظة فارغة. اذهب لصفحة 'إضافة' للبدء."); return
    
    open_df = df_strat[df_strat['status']=='Open'].copy()
    closed_df = df_strat[df_strat['status']=='Close'].copy()
    
    if not open_df.empty:
        open_df['total_cost'] = open_df['quantity'] * open_df['entry_price']
        open_df['market_value'] = open_df['quantity'] * open_df['current_price']
        open_df['gain'] = open_df['market_value'] - open_df['total_cost']
        open_df['gain_pct'] = open_df.apply(lambda row: (row['gain']/row['total_cost']*100) if row['total_cost']>0 else 0, axis=1)

    t1, t2, t3 = st.tabs([f"الأسهم القائمة ({len(open_df)})", "تحليل الأداء", f"الأرشيف ({len(closed_df)})"])
    
    with t1:
        if not open_df.empty:
            if page_key == 'invest':
                st.markdown("#### 🧩 التوزيع القطاعي")
                sec_sum = open_df.groupby('sector').agg({'market_value':'sum'}).reset_index()
                total_mv = sec_sum['market_value'].sum()
                sec_sum['weight'] = (sec_sum['market_value']/total_mv*100)
                
                cols_sec = [('sector', 'القطاع'), ('market_value', 'القيمة'), ('weight', 'الوزن %')]
                render_table(sec_sum, cols_sec)
                st.markdown("---")

            cols_op = [
                ('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), 
                ('entry_price', 'التكلفة'), ('current_price', 'السعر'), ('daily_change', 'يومي %'),
                ('market_value', 'القيمة'), ('gain', 'الربح'), ('gain_pct', '%')
            ]
            render_table(apply_sorting(open_df, cols_op, page_key), cols_op)
            
            st.markdown("---")
            with st.expander("🔴 إنهاء صفقة (بيع)", expanded=False):
                with st.form(f"sell_form_{page_key}"):
                    c1, c2, c3 = st.columns(3)
                    selected_symbol = c1.selectbox("اختر السهم", open_df['symbol'].unique())
                    exit_price = c2.number_input("سعر البيع", min_value=0.01)
                    exit_date = c3.date_input("تاريخ البيع", date.today())
                    if st.form_submit_button("تأكيد البيع"):
                        execute_query(
                            "UPDATE Trades SET status='Close', exit_price=?, exit_date=? WHERE symbol=? AND strategy=? AND status='Open'", 
                            (exit_price, str(exit_date), selected_symbol, target_strat)
                        )
                        st.success("تم البيع بنجاح!"); st.cache_data.clear(); st.rerun()
        else:
            st.info("🎉 لا توجد صفقات مفتوحة.")

    with t2:
        if not open_df.empty:
            dd = calculate_historical_drawdown(open_df)
            if not dd.empty:
                st.markdown("##### 📉 أقصى تراجع تاريخي (Drawdown)")
                fig = px.area(dd, x='date', y='drawdown', color_discrete_sequence=['#EF4444'])
                st.plotly_chart(fig, use_container_width=True)

    with t3:
        if not closed_df.empty:
            cols_cl = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح المحقق'), ('gain_pct', '%'), ('exit_date', 'تاريخ البيع')]
            render_table(closed_df, cols_cl)
        else: st.info("سجل الصفقات المغلقة فارغ.")

def view_analysis(fin):
    st.header("🔬 مركز التحليل الشامل")
    from classical_analysis import render_classical_analysis
    
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    symbols = list(set(trades['symbol'].tolist() + wl['symbol'].tolist()))
    
    c_search, c_sel = st.columns([1, 2])
    with c_search: new_search = st.text_input("بحث عن رمز (مثال: 1120)")
    if new_search and new_search not in symbols: symbols.insert(0, new_search)
    
    with c_sel:
        symbol = st.selectbox("اختر الشركة للتحليل", symbols) if symbols else None
    
    if symbol:
        n, s = get_static_info(symbol)
        st.markdown(f"### {n} ({symbol})")
        
        t1, t2, t3, t4 = st.tabs(["📊 المؤشرات الأساسية", "📑 القوائم المالية", "📈 التحليل الفني", "🏛️ التحليل الكلاسيكي"])
        
        with t1:
            with st.spinner("جاري التحليل..."):
                d = get_fundamental_ratios(symbol)
                if d and d['Current_Price']:
                    c_sc, c_det = st.columns([1, 3])
                    with c_sc:
                         color = "#10B981" if d['Score'] >= 7 else "#EF4444"
                         st.markdown(f"""
                         <div style="text-align:center; padding:15px; border:2px solid {color}; border-radius:15px;">
                            <div style="font-size:3rem; font-weight:bold; color:{color};">{d['Score']}/10</div>
                            <div style="font-weight:bold;">{d['Rating']}</div>
                         </div>
                         """, unsafe_allow_html=True)
                    with c_det:
                        st.markdown("**أبرز الملاحظات:**")
                        for op in d['Opinions']: st.write(f"• {op}")
                    
                    st.markdown("---")
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("مكرر الأرباح (P/E)", safe_fmt(d['P/E']))
                    k2.metric("مضاعف الدفترية (P/B)", safe_fmt(d['P/B']))
                    k3.metric("العائد (ROE)", safe_fmt(d['ROE'], "%"))
                    k4.metric("القيمة العادلة", safe_fmt(d['Fair_Value']))

        with t2:
            render_financial_dashboard_ui(symbol)
            
        with t3:
            render_technical_chart(symbol, "2y", "1d")
            
        with t4:
            render_classical_analysis(symbol)

def view_add_trade():
    st.header("➕ إضافة عملية جديدة")
    with st.container():
        with st.form("add_trade_form"):
            c1, c2 = st.columns(2)
            sym = c1.text_input("رمز السهم (مثال: 1120)")
            strat = c2.selectbox("نوع المحفظة", ["استثمار", "مضاربة", "صكوك"])
            
            c3, c4, c5 = st.columns(3)
            qty = c3.number_input("الكمية", min_value=1.0)
            price = c4.number_input("سعر التنفيذ", min_value=0.0)
            date_ex = c5.date_input("تاريخ التنفيذ", date.today())
            
            asset_type = "Sukuk" if strat == "صكوك" else "Stock"
            
            if st.form_submit_button("💾 حفظ البيانات", type="primary"):
                if sym and qty > 0 and price > 0:
                    n, s = get_static_info(sym)
                    if asset_type == "Sukuk": s = "أدوات الدين"
                    execute_query(
                        """INSERT INTO Trades 
                           (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Open', ?)""",
                        (sym, n, s, asset_type, str(date_ex), qty, price, strat, price)
                    )
                    st.success("✅ تمت الإضافة بنجاح")
                    st.cache_data.clear()
                else:
                    st.error("الرجاء التأكد من إدخال الرمز والكمية والسعر")

def view_cash_log():
    st.header("💵 سجل السيولة")
    fin = calculate_portfolio_metrics()
    
    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "سجل التوزيعات"])
    
    with t1:
        with st.expander("➕ تسجيل إيداع جديد"):
             with st.form("dep_f"):
                 amt = st.number_input("المبلغ")
                 dt = st.date_input("التاريخ")
                 nt = st.text_input("ملاحظة")
                 if st.form_submit_button("حفظ"):
                     execute_query("INSERT INTO Deposits (date, amount, note) VALUES (?,?,?)", (str(dt), amt, nt))
                     st.success("تم"); st.cache_data.clear(); st.rerun()
        render_table(fin['deposits'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
        
    with t2:
        with st.expander("➖ تسجيل سحب جديد"):
             with st.form("wit_f"):
                 amt = st.number_input("المبلغ")
                 dt = st.date_input("التاريخ")
                 nt = st.text_input("ملاحظة")
                 if st.form_submit_button("حفظ"):
                     execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (?,?,?)", (str(dt), amt, nt))
                     st.success("تم"); st.cache_data.clear(); st.rerun()
        render_table(fin['withdrawals'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
        
    with t3:
        with st.expander("💰 تسجيل توزيعات نقدية"):
             with st.form("ret_f"):
                 sym = st.text_input("الرمز")
                 amt = st.number_input("المبلغ")
                 dt = st.date_input("التاريخ")
                 if st.form_submit_button("حفظ"):
                     execute_query("INSERT INTO ReturnsGrants (date, symbol, amount) VALUES (?,?,?)", (str(dt), sym, amt))
                     st.success("تم"); st.cache_data.clear(); st.rerun()
        render_table(fin['returns'], [('date','التاريخ'), ('symbol','الرمز'), ('amount','المبلغ')])

def view_settings():
    st.header("⚙️ الإعدادات العامة")
    
    tab_sec, tab_data = st.tabs(["توزيع القطاعات", "إدارة البيانات"])
    
    # 1. توزيع القطاعات
    with tab_sec:
        all_sectors = sorted(list(set(d['sector'] for d in TADAWUL_DB.values())))
        df_all = pd.DataFrame({'sector': all_sectors})
        saved = fetch_table("SectorTargets")
        
        if not saved.empty:
            df = pd.merge(df_all, saved, on='sector', how='left').fillna(0)
        else:
            df = df_all
            df['target_percentage'] = 0.0
            
        st.info("قم بتعديل النسب المئوية المستهدفة للقطاعات:")
        
        with st.container():
            edited = st.data_editor(
                df, 
                column_config={
                    "sector": st.column_config.TextColumn("القطاع", disabled=True),
                    "target_percentage": st.column_config.NumberColumn(
                        "النسبة المستهدفة %", min_value=0, max_value=100, step=1, format="%d%%"
                    )
                },
                hide_index=True,
                use_container_width=True,
                key="sec_editor"
            )
            
        if st.button("💾 حفظ التوزيع", type="primary"):
            execute_query("DELETE FROM SectorTargets")
            for _, row in edited.iterrows():
                if row['target_percentage'] > 0:
                    execute_query("INSERT INTO SectorTargets (sector, target_percentage) VALUES (?,?)", (row['sector'], row['target_percentage']))
            st.success("تم الحفظ بنجاح")

    # 2. إدارة البيانات (الاستيراد والتصدير)
    with tab_data:
        st.markdown("### 📤 النسخ الاحتياطي")
        if st.button("📦 إنشاء ملف نسخة احتياطية (Excel)"):
            if create_smart_backup():
                st.success("✅ تم حفظ النسخة بنجاح في مجلد 'backups'")
            else:
                st.error("حدث خطأ أثناء النسخ")
            
        st.markdown("---")
        
        st.markdown("### 📥 استيراد بيانات (Restore)")
        st.warning("تحذير: هذه العملية ستقوم بدمج البيانات من الملف إلى البرنامج.")
        
        uploaded_file = st.file_uploader("اختر ملف النسخة الاحتياطية (Excel)", type=['xlsx'])
        
        if uploaded_file is not None:
            if st.button("🚀 تأكيد الاستيراد"):
                try:
                    with st.spinner("جاري قراءة الملف واستعادة البيانات..."):
                        xls = pd.ExcelFile(uploaded_file)
                        
                        # قائمة الجداول التي نريد استعادتها
                        tables_to_restore = ['Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants', 'Watchlist', 'SectorTargets', 'InvestmentThesis']
                        
                        restored_count = 0
                        with get_db() as conn:
                            for table_name in tables_to_restore:
                                if table_name in xls.sheet_names:
                                    df = pd.read_excel(xls, table_name)
                                    if not df.empty:
                                        # حذف عمود الـ id لتجنب مشاكل التكرار مع قاعدة البيانات
                                        if 'id' in df.columns:
                                            df = df.drop(columns=['id'])
                                        
                                        # استخدام to_sql للإدخال السريع
                                        df.to_sql(table_name, conn, if_exists='append', index=False)
                                        restored_count += 1
                        
                        if restored_count > 0:
                            st.success(f"تمت استعادة البيانات بنجاح من {restored_count} جدول!")
                            st.cache_data.clear()
                        else:
                            st.warning("لم يتم العثور على جداول صالحة في الملف.")
                            
                except Exception as e:
                    st.error(f"حدث خطأ أثناء الاستيراد: {str(e)}")

# === الموجه الرئيسي ===

def router():
    render_navbar()
    
    if 'page' not in st.session_state: st.session_state.page = 'home'
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    
    if pg == 'home': view_dashboard(fin)
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'sukuk': view_portfolio(fin, 'invest') # (مؤقت)
    elif pg == 'cash': view_cash_log()
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'add': view_add_trade()
    elif pg == 'settings': view_settings()
    elif pg == 'update':
        with st.spinner("جاري تحديث الأسعار..."):
            update_prices()
        st.session_state.page = 'home'; st.rerun()
