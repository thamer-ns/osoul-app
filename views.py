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

from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui, get_thesis, save_thesis

from market_data import get_static_info, get_tasi_data

from database import execute_query, fetch_table, get_db, clean_database_duplicates, clear_all_data

from config import APP_NAME

from data_source import TADAWUL_DB



# === دوال مساعدة ===

def safe_fmt(val, suffix=""):

    if val is None: return "غير متاح"

    try:

        num = float(val)

        if num == 0 and suffix == "": return "0.00"

        return f"{num:.2f}{suffix}"

    except: return "غير متاح"



def apply_sorting(df, cols_definition, key_suffix):

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



# === الصفحات ===

def view_dashboard(fin):

    try: t_price, t_change = get_tasi_data()

    except: t_price, t_change = 0, 0

    arrow = "🔼" if t_change >= 0 else "🔽"

    color = "#006644" if t_change >= 0 else "#DE350B"

    

    st.markdown(f"""

    <div style="background:white; padding:20px; border-radius:8px; border:1px solid #DFE1E6; margin-bottom:20px; display:flex; justify-content:space-between; align-items:center; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">

        <div>

            <div style="font-size:0.9rem; color:#5E6C84; font-weight:bold;">المؤشر العام (TASI)</div>

            <div style="font-size:2rem; font-weight:900; color:#172B4D;">{t_price:,.2f}</div>

        </div>

        <div style="background:{color}15; color:{color}; padding:8px 20px; border-radius:6px; font-size:1.2rem; font-weight:bold; direction:ltr;">

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

    color_pl = 'success' if total_pl >= 0 else 'danger'

    with c4: render_kpi("صافي الربح الكلي", f"{total_pl:,.2f}", color_pl)

    

    st.markdown("---")

    st.markdown("### 📈 نمو المحفظة")

    curve_data = generate_equity_curve(fin['all_trades'])

    if not curve_data.empty and 'date' in curve_data.columns:

        fig = px.line(curve_data, x='date', y='cumulative_invested')

        fig.update_layout(yaxis_title="القيمة (ريال)", xaxis_title="التاريخ", font=dict(family="Cairo"), paper_bgcolor="white", plot_bgcolor="white")

        st.plotly_chart(fig, use_container_width=True)

    else: st.info("📉 لا توجد بيانات كافية لرسم منحنى النمو.")



def view_portfolio(fin, page_key):

    target_strat = "مضاربة" if page_key == 'spec' else "استثمار"

    st.header(f"💼 محفظة {target_strat}")

    all_data = fin['all_trades']

    

    df_strat = pd.DataFrame()

    if not all_data.empty and 'strategy' in all_data.columns:

        all_data['strategy'] = all_data['strategy'].astype(str).str.strip()

        df_strat = all_data[(all_data['strategy'] == target_strat) & (all_data['asset_type'] != 'Sukuk')].copy()

    

    if df_strat.empty: 

        st.warning(f"المحفظة فارغة. (تأكد أن الصفقات مسجلة تحت مسمى '{target_strat}')")

    

    if 'status' not in df_strat.columns: df_strat['status'] = 'Open'



    open_df = df_strat[df_strat['status']=='Open'].copy()

    closed_df = df_strat[df_strat['status']=='Close'].copy()

    

    if not open_df.empty:

        open_df['total_cost'] = open_df['quantity'] * open_df['entry_price']

        open_df['market_value'] = open_df['quantity'] * open_df['current_price']

        open_df['gain'] = open_df['market_value'] - open_df['total_cost']

        open_df['gain_pct'] = open_df.apply(lambda row: (row['gain']/row['total_cost']*100) if row['total_cost']>0 else 0, axis=1)



    t1, t2, t3 = st.tabs([f"القائمة ({len(open_df)})", "تحليل الأداء", f"الأرشيف ({len(closed_df)})"])

    

    with t1:

        # === قسم توزيع القطاعات (الاستثمار فقط) ===

        if page_key == 'invest':

            st.markdown("#### 🎯 التوزيع القطاعي والأهداف")

            

            # تجهيز البيانات

            sec_sum = pd.DataFrame(columns=['sector', 'market_value', 'current_weight'])

            if not open_df.empty:

                sec_sum = open_df.groupby('sector').agg({'market_value':'sum'}).reset_index()

                total_mv = sec_sum['market_value'].sum()

                if total_mv > 0: sec_sum['current_weight'] = (sec_sum['market_value']/total_mv*100)

            

            saved_targets = fetch_table("SectorTargets")

            all_secs = set(sec_sum['sector'].tolist())

            if not saved_targets.empty: all_secs.update(saved_targets['sector'].tolist())

            

            df_edit = pd.DataFrame({'sector': list(all_secs)})

            df_edit = pd.merge(df_edit, sec_sum, on='sector', how='left').fillna(0)

            if not saved_targets.empty:

                df_edit = pd.merge(df_edit, saved_targets, on='sector', how='left')

                df_edit['target_percentage'] = df_edit['target_percentage'].fillna(0.0)

            else: df_edit['target_percentage'] = 0.0



            # 1. العرض باستخدام الجدول الجميل (للقراءة فقط)

            render_table(df_edit, [('sector', 'القطاع'), ('current_weight', 'الوزن الحالي %'), ('target_percentage', 'الهدف %')])

            

            # 2. زر التعديل (يظهر الجدول القابل للتعديل عند الضغط عليه)

            with st.expander("✏️ تعديل الأهداف (النسب)"):

                edited_targets = st.data_editor(

                    df_edit,

                    column_config={

                        "sector": st.column_config.TextColumn("القطاع", disabled=True),

                        "target_percentage": st.column_config.NumberColumn("الهدف %", format="%d%%", step=1, min_value=0, max_value=100)

                    },

                    hide_index=True, use_container_width=True

                )

                if st.button("حفظ التغييرات"):

                    execute_query("DELETE FROM SectorTargets")

                    for _, row in edited_targets.iterrows():

                        if row['target_percentage'] > 0:

                            execute_query("INSERT INTO SectorTargets (sector, target_percentage) VALUES (?,?)", (row['sector'], row['target_percentage']))

                    st.success("تم الحفظ!")

                    st.rerun()

            st.markdown("---")



        if not open_df.empty:

            # === ترتيب الأعمدة بالضبط كما طلبت ===

            cols_op = [

                ('company_name', 'اسم الشركة'),

                ('sector', 'القطاع'),

                ('status', 'الحالة'),

                ('symbol', 'رمز الشركة'),

                ('date', 'تاريخ الشراء'),

                ('exit_date', 'تاريخ البيع'),

                ('quantity', 'الكمية'),

                ('entry_price', 'سعر الشراء'),

                ('total_cost', 'التكلفة'),

                ('year_high', 'اعلى سنوي'),

                ('current_price', 'السعر الحالي'),

                ('year_low', 'ادنى سنوي'),

                ('market_value', 'سعر السوق'), # أو القيمة السوقية

                ('gain', 'الربح والخسارة'),

                ('gain_pct', 'نسبة الربح والخسارة'),

                ('weight', 'وزن السهم'),

                ('daily_change', 'نسبة التغير اليومي'),

                ('prev_close', 'اغلاق الامس')

            ]

            render_table(apply_sorting(open_df, cols_op, page_key), cols_op)

            

            st.markdown("---")

            with st.expander("🔴 تسجيل بيع"):

                with st.form(f"sell_{page_key}"):

                    c1, c2, c3 = st.columns(3)

                    sel = c1.selectbox("السهم", open_df['symbol'].unique())

                    ep = c2.number_input("سعر البيع", min_value=0.01)

                    ed = c3.date_input("التاريخ", date.today())

                    if st.form_submit_button("تأكيد البيع"):

                        execute_query("UPDATE Trades SET status='Close', exit_price=?, exit_date=? WHERE symbol=? AND strategy=? AND status='Open'", (ep, str(ed), sel, target_strat))

                        st.success("تم البيع"); st.cache_data.clear(); st.rerun()

        else: st.info("لا توجد صفقات مفتوحة.")



    with t2:

        if not open_df.empty:

            dd = calculate_historical_drawdown(open_df)

            if not dd.empty:

                st.markdown("##### 📉 أقصى تراجع")

                fig = px.area(dd, x='date', y='drawdown', color_discrete_sequence=['#DE350B'])

                st.plotly_chart(fig, use_container_width=True)



    with t3:

        if not closed_df.empty:

            render_table(closed_df, [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح'), ('gain_pct', '%'), ('exit_date', 'تاريخ البيع')])

        else: st.info("سجل فارغ.")



def view_sukuk_portfolio(fin):

    st.header("📜 محفظة الصكوك")

    all_data = fin['all_trades']

    sukuk_df = pd.DataFrame()

    if not all_data.empty:

        sukuk_df = all_data[all_data['asset_type'] == 'Sukuk'].copy()

    

    if sukuk_df.empty: st.warning("لم تقم بإضافة أي صكوك بعد."); return

    

    open_sukuk = sukuk_df[sukuk_df['status'] == 'Open'].copy()

    total_cost = open_sukuk['total_cost'].sum()

    gain = open_sukuk['gain'].sum()

    

    c1, c2 = st.columns(2)

    c1.metric("إجمالي الصكوك", f"{total_cost:,.2f}")

    c2.metric("الربح الرأسمالي", f"{gain:,.2f}")

    

    cols = [('company_name', 'اسم الصك'), ('symbol', 'الرمز'), ('quantity', 'العدد'), ('entry_price', 'سعر الشراء'), ('current_price', 'السعر الحالي'), ('market_value', 'القيمة السوقية'), ('gain_pct', 'النمو %')]

    render_table(open_sukuk, cols)



# === استعادة قسم التحليل (Fixing Missing Analysis) ===

def view_analysis(fin):

    st.header("🔬 مركز التحليل الشامل")

    from classical_analysis import render_classical_analysis

    trades = fin['all_trades']

    wl = fetch_table("Watchlist")

    

    symbols = []

    if not trades.empty: symbols.extend(trades['symbol'].unique().tolist())

    if not wl.empty: symbols.extend(wl['symbol'].unique().tolist())

    symbols = list(set(symbols))

    

    c_search, c_sel = st.columns([1, 2])

    with c_search: new_search = st.text_input("بحث عن رمز (مثال: 1120)")

    if new_search and new_search not in symbols: symbols.insert(0, new_search)

    with c_sel: symbol = st.selectbox("اختر الشركة للتحليل", symbols) if symbols else None

    

    if symbol:

        n, s = get_static_info(symbol)

        st.markdown(f"### {n} ({symbol})")

        t1, t2, t3, t4, t5 = st.tabs(["📊 المؤشرات", "📑 القوائم المالية", "📝 الأطروحة", "📈 فني", "🏛️ كلاسيكي"])

        

        with t1:

            with st.spinner("جاري التحليل..."):

                d = get_fundamental_ratios(symbol)

                if d and d['Current_Price']:

                    c_sc, c_det = st.columns([1, 3])

                    with c_sc:

                         color = "#006644" if d['Score'] >= 7 else "#DE350B"

                         st.markdown(f"<div style='text-align:center; padding:15px; border:2px solid {color}; border-radius:15px;'><div style='font-size:3rem; font-weight:bold; color:{color};'>{d['Score']}/10</div><div style='font-weight:bold;'>{d['Rating']}</div></div>", unsafe_allow_html=True)

                    with c_det:

                        st.markdown("**أبرز الملاحظات:**")

                        for op in d['Opinions']: st.write(f"• {op}")

                    st.markdown("---")

                    k1, k2, k3, k4 = st.columns(4)

                    k1.metric("P/E", safe_fmt(d['P/E']))

                    k2.metric("P/B", safe_fmt(d['P/B']))

                    k3.metric("ROE", safe_fmt(d['ROE'], "%"))

                    k4.metric("Fair Value", safe_fmt(d['Fair_Value']))

        with t2: render_financial_dashboard_ui(symbol)

        with t3:

            current = get_thesis(symbol)

            def_text = current['thesis_text'] if current else ""

            def_target = current['target_price'] if current else 0.0

            with st.form("thesis_form"):

                target = st.number_input("السعر المستهدف", value=def_target)

                text = st.text_area("أطروحة الاستثمار", value=def_text)

                if st.form_submit_button("حفظ"):

                    save_thesis(symbol, text, target, "Hold")

                    st.success("تم الحفظ")

        with t4: render_technical_chart(symbol, "2y", "1d")

        with t5: render_classical_analysis(symbol)



def view_add_trade():

    st.header("➕ إضافة عملية جديدة")

    with st.container():

        with st.form("add_trade_form"):

            c1, c2 = st.columns(2)

            sym = c1.text_input("رمز السهم")

            strat = c2.selectbox("المحفظة", ["استثمار", "مضاربة", "صكوك"])

            c3, c4, c5 = st.columns(3)

            qty = c3.number_input("الكمية", min_value=1.0)

            price = c4.number_input("السعر", min_value=0.0)

            date_ex = c5.date_input("التاريخ", date.today())

            

            if st.form_submit_button("💾 حفظ", type="primary"):

                n, s = get_static_info(sym)

                atype = "Sukuk" if strat == "صكوك" else "Stock"

                execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (?,?,?,?,?,?,?,?,'Open',?)", (sym, n, s, atype, str(date_ex), qty, price, strat, price))

                st.success("تم"); st.cache_data.clear()



def view_cash_log():

    st.header("💵 سجل السيولة")

    fin = calculate_portfolio_metrics()

    

    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "التوزيعات"])

    

    with t1:

        total_d = fin['deposits']['amount'].sum() if not fin['deposits'].empty else 0

        st.metric("إجمالي الإيداعات", f"{total_d:,.2f}", delta="مجموع كلي")

        

        with st.expander("➕ إيداع جديد"):

             with st.form("dep"):

                 amt = st.number_input("المبلغ"); dt = st.date_input("التاريخ"); nt = st.text_input("ملاحظة")

                 if st.form_submit_button("حفظ"): execute_query("INSERT INTO Deposits (date, amount, note) VALUES (?,?,?)", (str(dt), amt, nt)); st.success("تم"); st.rerun()

        render_table(fin['deposits'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])

        

    with t2:

        total_w = fin['withdrawals']['amount'].sum() if not fin['withdrawals'].empty else 0

        st.metric("إجمالي السحوبات", f"{total_w:,.2f}", delta="-", delta_color="inverse")

        

        with st.expander("➖ سحب جديد"):

             with st.form("wit"):

                 amt = st.number_input("المبلغ"); dt = st.date_input("التاريخ"); nt = st.text_input("ملاحظة")

                 if st.form_submit_button("حفظ"): execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (?,?,?)", (str(dt), amt, nt)); st.success("تم"); st.rerun()

        render_table(fin['withdrawals'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])

        

    with t3:

        total_r = fin['returns']['amount'].sum() if not fin['returns'].empty else 0

        st.metric("إجمالي التوزيعات", f"{total_r:,.2f}", delta="+", delta_color="normal")

        

        with st.expander("💰 تسجيل توزيع"):

             with st.form("ret"):

                 sym = st.text_input("الرمز"); amt = st.number_input("المبلغ"); dt = st.date_input("التاريخ")

                 if st.form_submit_button("حفظ"): execute_query("INSERT INTO ReturnsGrants (date, symbol, amount) VALUES (?,?,?)", (str(dt), sym, amt)); st.success("تم"); st.rerun()

        render_table(fin['returns'], [('date','التاريخ'), ('symbol','الرمز'), ('amount','المبلغ')])



def view_tools():

    st.header("🛠️ الأدوات")

    fin = calculate_portfolio_metrics()

    st.info("زكاة تقديرية (2.5775%): " + str(fin['market_val_open'] * 0.025775))



def view_settings():

    st.header("⚙️ الإعدادات العامة")

    

    st.markdown("### 📤 النسخ الاحتياطي")

    if st.button("📦 إنشاء نسخة احتياطية (Excel)"):

        if create_smart_backup(): st.success("✅ تم الحفظ في مجلد backups")

        else: st.error("فشل النسخ")

    

    st.markdown("---")

    st.markdown("### 📥 إدارة البيانات")

    if st.button("🗑️ حذف جميع البيانات (Format)", type="primary"):

        clear_all_data()

        st.warning("تم مسح البيانات!"); st.cache_data.clear(); st.rerun()



    st.warning("استعادة البيانات (سيتم دمج الأعمدة الصحيحة فقط)")

    f = st.file_uploader("ملف Excel", type=['xlsx'])

    if f and st.button("🚀 استيراد"):

        try:

            xls = pd.ExcelFile(f)

            with get_db() as conn:

                tables = ['Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants', 'Watchlist', 'SectorTargets', 'InvestmentThesis', 'FinancialStatements']

                for t in tables:

                    if t in xls.sheet_names:

                        df = pd.read_excel(xls, t)

                        if not df.empty:

                            if 'id' in df.columns: df = df.drop(columns=['id'])

                            cursor = conn.execute(f"PRAGMA table_info({t})")

                            db_cols = [row['name'] for row in cursor.fetchall()]

                            valid_df = df[[c for c in df.columns if c in db_cols]]

                            if 'strategy' in db_cols and 'strategy' not in valid_df.columns:

                                valid_df['strategy'] = 'استثمار'

                            valid_df.to_sql(t, conn, if_exists='append', index=False)

            st.success("تم الاستيراد!")

            st.cache_data.clear()

        except Exception as e: st.error(f"خطأ: {e}")



def router():

    render_navbar()

    if 'page' not in st.session_state: st.session_state.page = 'home'

    pg = st.session_state.page

    fin = calculate_portfolio_metrics()

    if pg == 'home': view_dashboard(fin)

    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)

    elif pg == 'sukuk': view_sukuk_portfolio(fin)

    elif pg == 'cash': view_cash_log()

    elif pg == 'analysis': view_analysis(fin)

    elif pg == 'tools': view_tools()

    elif pg == 'add': view_add_trade()

    elif pg == 'settings': view_settings()

    elif pg == 'update':

        with st.spinner("تحديث..."): update_prices()

        st.session_state.page = 'home'; st.rerun()
