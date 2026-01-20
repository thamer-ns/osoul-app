import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

# === الاستيرادات ===
from components import render_navbar, render_kpi, render_table
from analytics import (calculate_portfolio_metrics, update_prices, create_smart_backup, 
                       get_comprehensive_performance, get_rebalancing_advice, 
                       get_dividends_calendar, generate_equity_curve, calculate_historical_drawdown)
from charts import render_technical_chart
# تم تحديث الاستيراد هنا ليشمل الدالة الجديدة
from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui, format_large_number
from market_data import get_static_info, get_tasi_data
from database import execute_query, fetch_table
from config import BACKUP_DIR, APP_NAME
from data_source import TADAWUL_DB

# === دوال المساعدة ===
def apply_sorting(df, cols_definition, key_suffix):
    if df.empty: return df
    with st.expander("🔍 أدوات الفرز", expanded=False):
        label_to_col = {label: col for col, label in cols_definition}
        sort_options = list(label_to_col.keys())
        c1, c2 = st.columns([2, 1])
        with c1: selected = st.selectbox("فرز حسب:", sort_options, index=0, key=f"sc_{key_suffix}")
        with c2: order = st.radio("الترتيب:", ["تنازلي", "تصاعدي"], horizontal=True, key=f"so_{key_suffix}")
    target = label_to_col[selected]
    asc = (order == "تصاعدي")
    try: return df.sort_values(by=target, ascending=asc)
    except: return df

def safe_fmt(val, suffix=""):
    if val is None: return "غير متاح"
    try:
        num = float(val)
        if num == 0 and suffix == "": return "0.00"
        return f"{num:.2f}{suffix}"
    except (ValueError, TypeError): return "غير متاح"

# === الصفحات ===
def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    
    if 'custom_colors' not in st.session_state:
        from config import DEFAULT_COLORS
        st.session_state.custom_colors = DEFAULT_COLORS.copy()
    C = st.session_state.custom_colors
    
    arrow = "🔼" if t_change >= 0 else "🔽"
    color = "#10B981" if t_change >= 0 else "#EF4444"
    
    st.markdown(f"""
    <div class="tasi-box">
        <div><div style="font-size:0.9rem;color:#6B7280;font-weight:bold;">المؤشر العام (TASI)</div><div style="font-size:2rem;font-weight:900;color:#1F2937;">{t_price:,.2f}</div></div>
        <div><div style="background:{color}15;color:{color};padding:8px 20px;border-radius:10px;font-size:1.1rem;font-weight:bold;direction:ltr;">{arrow} {t_change:+.2f}%</div></div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### الملخص المالي")
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi("الكاش المتوفر", f"{fin['cash']:,.2f}")
    with c2: render_kpi("رأس المال", f"{(fin['total_deposited']-fin['total_withdrawn']):,.2f}")
    with c3: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}", "blue")
    with c4: render_kpi("صافي الربح", f"{(fin['unrealized_pl']+fin['realized_pl']+fin['total_returns']):,.2f}", (fin['unrealized_pl']+fin['realized_pl']))
    st.markdown("---")
    st.markdown("### 📈 منحنى النمو")
    curve = generate_equity_curve(fin['all_trades'])
    if not curve.empty:
        fig = px.line(curve, x='date', y='cumulative_invested', title='نمو حجم الاستثمار')
        fig.update_layout(font=dict(family="Cairo"), yaxis_title="القيمة", xaxis_title="التاريخ")
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("لا توجد بيانات كافية لرسم المنحنى.")

def view_portfolio(fin, page_key):
    target_strat = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"محفظة {target_strat}")
    all_data = fin['all_trades']
    
    if all_data.empty: st.info("لا توجد بيانات"); return
    df_strat = all_data[(all_data['strategy'] == target_strat) & (all_data['asset_type'] != 'Sukuk')].copy()
    if df_strat.empty: st.warning(f"محفظة {target_strat} فارغة. اذهب لصفحة 'إضافة' للبدء."); return
    
    open_df = df_strat[df_strat['status']=='Open'].copy()
    closed_df = df_strat[df_strat['status']=='Close'].copy()
    
    if not open_df.empty:
        open_df['total_cost'] = open_df['quantity'] * open_df['entry_price']
        open_df['market_value'] = open_df['quantity'] * open_df['current_price']
        open_df['gain'] = open_df['market_value'] - open_df['total_cost']
        open_df['gain_pct'] = open_df.apply(lambda row: (row['gain'] / row['total_cost'] * 100) if row['total_cost'] > 0 else 0, axis=1)

    t1, t2, t3 = st.tabs([f"القائمة ({len(open_df)})", "تحليل الأداء", f"المغلقة ({len(closed_df)})"])
    
    with t1:
        if not open_df.empty:
            if page_key == 'invest':
                st.markdown("#### توزيع القطاعات")
                sec_sum = open_df.groupby('sector').agg({'symbol':'count','total_cost':'sum','market_value':'sum'}).reset_index()
                total_mv = sec_sum['market_value'].sum()
                sec_sum['current_weight'] = (sec_sum['market_value']/total_mv*100).fillna(0)
                
                targets = fetch_table("SectorTargets")
                if not targets.empty:
                    sec_sum = pd.merge(sec_sum, targets, on='sector', how='left')
                    sec_sum['target_percentage'] = sec_sum['target_percentage'].fillna(0.0)
                else: sec_sum['target_percentage'] = 0.0
                sec_sum['remaining'] = (total_mv * sec_sum['target_percentage']/100) - sec_sum['market_value']
                cols_sec = [('sector', 'القطاع'), ('symbol', 'عدد'), ('total_cost', 'التكلفة'), ('current_weight', 'الوزن %'), ('target_percentage', 'الهدف %'), ('remaining', 'المتبقي')]
                render_table(apply_sorting(sec_sum, cols_sec, f"{page_key}_s"), cols_sec)
                st.markdown("---")

            st.markdown("#### تفاصيل الأسهم")
            cols_op = [
                ('company_name', 'الشركة'), 
                ('symbol', 'الرمز'), 
                ('quantity', 'الكمية'), 
                ('entry_price', 'سعر الشراء'),    
                ('total_cost', 'إجمالي التكلفة'), 
                ('current_price', 'السعر الحالي'), 
                ('daily_change', 'يومي %'), 
                ('market_value', 'القيمة السوقية'), 
                ('gain', 'الربح/الخسارة'), 
                ('gain_pct', '% النمو')
            ]
            render_table(apply_sorting(open_df, cols_op, f"{page_key}_o"), cols_op)
            
            st.markdown("---")
            with st.expander("🔻 تسجيل بيع / إغلاق صفقة", expanded=True):
                sell_options = open_df['symbol'].unique().tolist()
                with st.form(f"sell_form_{page_key}"):
                    c1, c2, c3 = st.columns(3)
                    selected_symbol = c1.selectbox("اختر السهم للبيع", sell_options)
                    exit_price = c2.number_input("سعر البيع", min_value=0.01)
                    exit_date = c3.date_input("تاريخ البيع", date.today())
                    
                    if st.form_submit_button("✅ تأكيد البيع"):
                        try:
                            execute_query(
                                "UPDATE Trades SET status='Close', exit_price=?, exit_date=? WHERE symbol=? AND strategy=? AND status='Open'", 
                                (exit_price, str(exit_date), selected_symbol, target_strat)
                            )
                            st.success(f"تم بيع {selected_symbol} بنجاح!")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"حدث خطأ: {e}")
        else: st.info("المحفظة فارغة حالياً")

    with t2:
        if page_key == 'invest':
            sec_p, stock_p = get_comprehensive_performance(df_strat, fin['returns'])
            if not sec_p.empty:
                st.markdown("### الأداء حسب القطاع")
                cols_sp = [('sector', 'القطاع'), ('gain', 'رأسمالي'), ('total_dividends', 'توزيعات'), ('net_profit', 'صافي'), ('roi_pct', 'عائد %')]
                render_table(sec_p.sort_values('net_profit', ascending=False), cols_sp)
        
        if not open_df.empty:
            st.markdown("### تحليل المخاطر")
            dd = calculate_historical_drawdown(open_df)
            if not dd.empty: st.metric("أقصى تراجع", f"{dd['drawdown'].min():.2f}%")

    with t3:
        if not closed_df.empty:
            cols_cl = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح المحقق'), ('gain_pct', '%'), ('exit_date', 'تاريخ البيع')]
            render_table(apply_sorting(closed_df, cols_cl, f"{page_key}_c"), cols_cl)
        else: st.info("لا توجد صفقات مغلقة")

def view_sukuk_portfolio(fin):
    st.header("📜 محفظة الصكوك")
    all_data = fin['all_trades']
    
    if all_data.empty: st.info("لا توجد بيانات"); return
    sukuk_df = all_data[all_data['asset_type'] == 'Sukuk'].copy()
    
    if sukuk_df.empty: st.warning("لم تقم بإضافة أي صكوك بعد."); return
    
    open_sukuk = sukuk_df[sukuk_df['status'] == 'Open'].copy()
    total_cost = open_sukuk['total_cost'].sum()
    current_val = open_sukuk['market_value'].sum()
    gain = open_sukuk['gain'].sum()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("إجمالي الصكوك", f"{total_cost:,.2f}")
    c2.metric("القيمة الحالية", f"{current_val:,.2f}")
    c3.metric("الربح الرأسمالي", f"{gain:,.2f}", delta_color="normal")
    
    st.markdown("### الصكوك القائمة")
    cols = [('company_name', 'اسم الصك'), ('symbol', 'الرمز'), ('quantity', 'العدد'), ('entry_price', 'سعر الشراء'), ('current_price', 'السعر الحالي'), ('market_value', 'القيمة السوقية'), ('gain_pct', 'النمو %')]
    render_table(open_sukuk, cols)
    
    if not open_sukuk.empty:
        st.markdown("---")
        with st.expander("🔻 بيع / استرداد صك", expanded=True):
            sell_opts = open_sukuk['symbol'].unique().tolist()
            with st.form("sell_sukuk_form"):
                c1, c2, c3 = st.columns(3)
                sel_sukuk = c1.selectbox("اختر الصك", sell_opts)
                exit_p = c2.number_input("سعر البيع/الاسترداد", min_value=0.01)
                exit_d = c3.date_input("تاريخ العملية", date.today())
                if st.form_submit_button("✅ تأكيد العملية"):
                    execute_query("UPDATE Trades SET status='Close', exit_price=?, exit_date=? WHERE symbol=? AND asset_type='Sukuk' AND status='Open'", (exit_p, str(exit_d), sel_sukuk))
                    st.success(f"تم بيع {sel_sukuk} بنجاح"); st.cache_data.clear(); st.rerun()

def view_liquidity():
    fin = calculate_portfolio_metrics()
    c1, c2, c3 = st.columns(3)
    with c1: render_kpi("إيداعات", f"{fin['total_deposited']:,.2f}", "blue")
    with c2: render_kpi("سحوبات", f"{fin['total_withdrawn']:,.2f}", -1)
    with c3: render_kpi("عوائد", f"{fin['total_returns']:,.2f}", "success")
    st.markdown("---")
    cal = get_dividends_calendar(fin['returns'])
    if not cal.empty:
        st.markdown("### سجل التوزيعات")
        render_table(cal, [('year_month', 'الشهر'), ('amount', 'القيمة'), ('symbol', 'الشركات')])
    st.markdown("---")
    t1, t2, t3 = st.tabs(["إيداع", "سحب", "عوائد"])
    with t1: render_table(apply_sorting(fin['deposits'], [('date','تاريخ'),('amount','مبلغ'),('note','ملاحظة')], "ld"), [('date','تاريخ'),('amount','مبلغ'),('note','ملاحظة')])
    with t2: render_table(apply_sorting(fin['withdrawals'], [('date','تاريخ'),('amount','مبلغ'),('note','ملاحظة')], "lw"), [('date','تاريخ'),('amount','مبلغ'),('note','ملاحظة')])
    with t3: render_table(apply_sorting(fin['returns'], [('date','تاريخ'),('amount','مبلغ'),('symbol','رمز')], "lr"), [('date','تاريخ'),('amount','مبلغ'),('symbol','رمز')])

def view_add_trade():
    st.header("مركز العمليات")
    tab1, tab2, tab3 = st.tabs(["➕ صفقة جديدة", "💰 تسجيل عائد/توزيع", "🏦 إدارة السيولة"])
    with tab1:
        with st.form("buy_form"):
            c1, c2 = st.columns(2)
            sym = c1.text_input("رمز الورقة المالية (مثال: 1120)")
            asset_map = {"سهم": "Stock", "صك": "Sukuk", "ريت": "REIT"}
            asset_label = c2.selectbox("نوع الأصل", list(asset_map.keys()), index=0)
            asset_val = asset_map[asset_label]
            c3, c4, c5 = st.columns(3)
            qty = c3.number_input("الكمية", 1.0)
            price = c4.number_input("سعر الشراء", 0.01)
            strat = c5.selectbox("المحفظة", ["استثمار", "مضاربة", "صكوك"])
            d = st.date_input("تاريخ الشراء", date.today())
            if st.form_submit_button("💾 حفظ الصفقة"):
                if sym and qty:
                    n, s = get_static_info(sym)
                    if asset_val == "Sukuk": 
                        s = "الصكوك والسندات"
                        if n == f"سهم {sym}": n = f"صك {sym}"
                    if strat == "صكوك" and asset_val != "Sukuk": asset_val = "Sukuk"
                    execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (?,?,?,?,?,?,?,?,?,?)", (sym, n, s, asset_val, str(d), qty, price, strat, 'Open', price))
                    st.success("تمت إضافة الصفقة"); st.cache_data.clear()
    with tab2:
        st.info("تسجيل التوزيعات النقدية")
        trades = fetch_table("Trades")
        open_assets = []
        if not trades.empty: open_assets = trades[trades['status'] == 'Open']['symbol'].unique().tolist()
        if open_assets:
            with st.form("dividend_form"):
                c1, c2 = st.columns(2)
                selected_asset = c1.selectbox("اختر الأصل", open_assets)
                amount = c2.number_input("قيمة التوزيعات (ريال)", min_value=0.01)
                div_date = st.date_input("تاريخ الاستحقاق", date.today())
                if st.form_submit_button("💰 تسجيل العائد"):
                    comp_name, _ = get_static_info(selected_asset)
                    execute_query("INSERT INTO ReturnsGrants (date, symbol, company_name, amount) VALUES (?,?,?,?)", (str(div_date), selected_asset, comp_name, amount))
                    st.success(f"تم تسجيل {amount} ريال"); st.cache_data.clear()
        else: st.warning("لا توجد أصول مفتوحة.")
    with tab3:
        col_dep, col_wit = st.columns(2)
        with col_dep:
            st.markdown("#### 📥 إيداع نقدي")
            with st.form("deposit_form"):
                amt_d = st.number_input("المبلغ", min_value=0.01, key="d_amt")
                date_d = st.date_input("التاريخ", date.today(), key="d_date")
                note_d = st.text_input("ملاحظة", key="d_note")
                if st.form_submit_button("تأكيد الإيداع"):
                    execute_query("INSERT INTO Deposits (date, amount, note) VALUES (?,?,?)", (str(date_d), amt_d, note_d))
                    st.success("تم الإيداع"); st.cache_data.clear()
        with col_wit:
            st.markdown("#### 📤 سحب نقدي")
            with st.form("withdraw_form"):
                amt_w = st.number_input("المبلغ", min_value=0.01, key="w_amt")
                date_w = st.date_input("التاريخ", date.today(), key="w_date")
                note_w = st.text_input("ملاحظة", key="w_note")
                if st.form_submit_button("تأكيد السحب"):
                    execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (?,?,?)", (str(date_w), amt_w, note_w))
                    st.success("تم السحب"); st.cache_data.clear()

def view_tools():
    st.header("أدوات")
    t1, t2 = st.tabs(["الزكاة", "التقارير"])
    fin = calculate_portfolio_metrics()
    with t1:
        st.info("زكاة تقديرية (2.5775%)")
        base = fin['market_val_open'] + fin['cash']
        st.metric("الزكاة المستحقة", f"{(base*0.025775):,.2f}", help=f"الوعاء: {base:,.2f}")
    with t2:
        html = f"""<html><head><style>body{{font-family:Arial;direction:rtl;}}table{{width:100%;border-collapse:collapse;}}th,td{{border:1px solid #ddd;padding:8px;}}</style></head><body><h1>تقرير {APP_NAME}</h1><p>تاريخ: {date.today()}</p><h2>الملخص</h2><p>قيمة سوقية: {fin['market_val_open']}</p><p>كاش: {fin['cash']}</p></body></html>"""
        st.download_button("تحميل تقرير", html, file_name="report.html", mime="text/html")

def view_settings():
    st.header("إعدادات وتوزيع القطاعات")
    st.info("💡 قم بتعديل النسب المستهدفة في الجدول أدناه مباشرة ثم اضغط حفظ.")
    all_sectors = sorted(list(set(d['sector'] for d in TADAWUL_DB.values())))
    df_all_sectors = pd.DataFrame({'sector': all_sectors})
    saved_targets = fetch_table("SectorTargets")
    if not saved_targets.empty:
        df_merged = pd.merge(df_all_sectors, saved_targets, on='sector', how='left').fillna(0)
    else:
        df_merged = df_all_sectors
        df_merged['target_percentage'] = 0.0
    st.markdown("### 🎯 توزيع الأهداف")
    edited_df = st.data_editor(
        df_merged,
        column_config={
            "sector": st.column_config.TextColumn("القطاع", disabled=True, width="medium"),
            "target_percentage": st.column_config.NumberColumn("النسبة المستهدفة %", min_value=0, max_value=100, step=1, format="%.0f%%", width="small")
        }, hide_index=True, use_container_width=True, num_rows="fixed")
    if st.button("حفظ التغييرات"):
        total_pct = edited_df['target_percentage'].sum()
        if total_pct > 100: st.warning(f"⚠️ مجموع النسب {total_pct}% أكبر من 100%!")
        execute_query("DELETE FROM SectorTargets")
        for _, row in edited_df.iterrows():
            if row['target_percentage'] > 0:
                execute_query("INSERT INTO SectorTargets (sector, target_percentage) VALUES (?,?)", (row['sector'], row['target_percentage']))
        st.success(f"تم الحفظ بنجاح (المجموع: {total_pct}%)")
    st.markdown("---")
    with st.expander("إدارة البيانات"):
        if st.button("نسخ احتياطي فوري"): create_smart_backup(); st.success("تم النسخ")

# =========================================================
# تحديث الدالة الرئيسية للتحليل (View Analysis)
# =========================================================
def view_analysis(fin):
    st.header("🔍 مركز التحليل")
    from classical_analysis import render_classical_analysis
    
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    symbols = []
    if not trades.empty: symbols.extend(trades['symbol'].unique().tolist())
    if not wl.empty: symbols.extend(wl['symbol'].unique().tolist())
    symbols = list(set(symbols))
    if not symbols: st.info("أضف أسهم للمحفظة أولاً"); return
    
    c1, c2, c3 = st.columns([1, 1, 2])
    symbol = c1.selectbox("اختر الشركة", symbols)
    period = c2.selectbox("الفترة", ["1y", "2y", "5y", "max"], index=1)
    interval = c3.selectbox("الفاصل الزمني", ["1d", "1wk", "1mo"], index=0)

    if symbol:
        st.markdown(f"### تحليل سهم: {symbol}")
        # --- التحديث: إضافة تبويب القوائم المالية ---
        tab_fund, tab_financials, tab_tech, tab_class = st.tabs([
            "💰 المؤشرات والتقييم", 
            "📑 القوائم المالية (جديد)", 
            "📈 التحليل الفني", 
            "🏛️ التحليل الكلاسيكي"
        ])
        
        # 1. المؤشرات (الكود الأصلي)
        with tab_fund:
            with st.spinner("جاري فحص القوائم المالية وحساب المؤشرات..."):
                data = get_fundamental_ratios(symbol)
            
            if data and data['Current_Price'] > 0:
                c_score, c_opinion = st.columns([1, 2])
                with c_score:
                    score_color = "#0e6ba8"
                    if data['Score'] < 4: score_color = "#EF4444"
                    elif data['Score'] > 7: score_color = "#10B981"
                    
                    st.markdown(f"""
                    <div style="text-align:center; padding:10px; border:2px solid #E5E7EB; border-radius:10px;">
                        <h4 style="margin:0; color:#6B7280;">التقييم العام</h4>
                        <h1 style="margin:0; font-size:3rem; color:{score_color};">{data['Score']}/10</h1>
                        <h3 style="margin:0;">{data['Rating']}</h3>
                    </div>""", unsafe_allow_html=True)
                
                with c_opinion:
                    st.info("💡 **رأي المحلل الآلي:**")
                    if data['Opinions']:
                        for op in data['Opinions']: st.markdown(f"- {op}")
                    else: st.markdown("- لا توجد بيانات كافية لتوليد رأي دقيق.")
                
                st.markdown("---")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("مكرر الربحية (P/E)", safe_fmt(data['P/E']))
                k2.metric("القيمة الدفترية (P/B)", safe_fmt(data['P/B']))
                k3.metric("العائد (ROE)", safe_fmt(data['ROE'], "%"))
                k4.metric("هامش الربح", safe_fmt(data['Profit_Margin'], "%"))
                
                k5, k6, k7, k8 = st.columns(4)
                k5.metric("التوزيعات", safe_fmt(data['Dividend_Yield'], "%"))
                k6.metric("المديونية", safe_fmt(data['Debt_to_Equity']))
                k7.metric("الربح (EPS)", safe_fmt(data['EPS']))
                
                fv = data['Fair_Value']
                curr = data['Current_Price']
                if fv and fv > 0 and curr > 0:
                    delta = ((curr - fv) / fv * 100)
                    color = "inverse" if fv > 0 and curr < fv else "normal"
                    k8.metric("القيمة العادلة", f"{fv:.2f}", delta=f"{delta:.1f}% عن السعر", delta_color=color)
                else:
                    k8.metric("القيمة العادلة", "غير متاحة", "نقص بيانات")
            else:
                st.error(f"تعذر جلب البيانات المالية للسهم {symbol}. يرجى المحاولة لاحقاً.")

        # 2. القوائم المالية (القسم الجديد)
        with tab_financials:
            render_financial_dashboard_ui(symbol)

        # 3. التحليل الفني
        with tab_tech:
            render_technical_chart(symbol, period, interval)
            
        # 4. التحليل الكلاسيكي
        with tab_class:
            render_classical_analysis(symbol)

def router():
    render_navbar()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    if pg == 'home': view_dashboard(fin)
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'sukuk': view_sukuk_portfolio(fin)
    elif pg == 'cash': view_liquidity()
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'tools': view_tools()
    elif pg == 'add': view_add_trade()
    elif pg == 'settings': view_settings()
    elif pg == 'update':
        with st.spinner("جاري التحديث..."): update_prices()
        st.session_state.page = 'home'; st.rerun()
