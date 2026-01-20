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
from financial_analysis import get_fundamental_ratios, update_financial_statements, get_stored_financials, get_thesis, save_thesis
from market_data import get_static_info, get_tasi_data
from database import execute_query, fetch_table
from config import BACKUP_DIR, APP_NAME
from data_source import TADAWUL_DB

def safe_fmt(val, suffix=""):
    if val is None: return "غير متاح"
    try:
        num = float(val)
        if num == 0 and suffix == "": return "0.00"
        return f"{num:.2f}{suffix}"
    except: return "غير متاح"

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

def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    
    if 'custom_colors' not in st.session_state:
        from config import DEFAULT_COLORS
        st.session_state.custom_colors = DEFAULT_COLORS.copy()
    
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
                sec_sum = open_df.groupby('sector').agg({'symbol':'count','total_cost':'sum','market_value':'sum'}).reset_index()
                total_mv = sec_sum['market_value'].sum()
                sec_sum['current_weight'] = (sec_sum['market_value']/total_mv*100).fillna(0)
                targets = fetch_table("SectorTargets")
                if not targets.empty:
                    sec_sum = pd.merge(sec_sum, targets, on='sector', how='left').fillna(0)
                else: sec_sum['target_percentage'] = 0.0
                sec_sum['remaining'] = (total_mv * sec_sum['target_percentage']/100) - sec_sum['market_value']
                render_table(sec_sum, [('sector', 'القطاع'), ('current_weight', 'الوزن %'), ('target_percentage', 'الهدف %'), ('remaining', 'المتبقي')])
                st.markdown("---")

            cols_op = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'شراء'), ('current_price', 'حالي'), ('market_value', 'القيمة'), ('gain', 'الربح'), ('gain_pct', '%')]
            render_table(apply_sorting(open_df, cols_op, f"{page_key}_o"), cols_op)
            
            st.markdown("---")
            with st.expander("🔻 تسجيل بيع / إغلاق صفقة"):
                sell_options = open_df['symbol'].unique().tolist()
                with st.form(f"sell_form_{page_key}"):
                    c1, c2, c3 = st.columns(3)
                    sel = c1.selectbox("اختر السهم", sell_options)
                    ep = c2.number_input("سعر البيع", min_value=0.01)
                    ed = c3.date_input("تاريخ البيع", date.today())
                    if st.form_submit_button("✅ تأكيد البيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=?, exit_date=? WHERE symbol=? AND strategy=? AND status='Open'", (ep, str(ed), sel, target_strat))
                        st.success("تم البيع"); st.cache_data.clear(); st.rerun()
        else: st.info("المحفظة فارغة")

    with t2:
        if page_key == 'invest':
            sec_p, stock_p = get_comprehensive_performance(df_strat, fin['returns'])
            if not sec_p.empty: render_table(sec_p, [('sector', 'القطاع'), ('net_profit', 'الربح الصافي'), ('roi_pct', 'العائد %')])
        if not open_df.empty:
            dd = calculate_historical_drawdown(open_df)
            if not dd.empty: st.metric("أقصى تراجع", f"{dd['drawdown'].min():.2f}%")

    with t3:
        if not closed_df.empty:
            cols_cl = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح'), ('exit_date', 'تاريخ البيع')]
            render_table(closed_df, cols_cl)
        else: st.info("لا توجد صفقات مغلقة")

def view_analysis(fin):
    st.header("🔍 مركز التحليل المالي المتكامل")
    from classical_analysis import render_classical_analysis
    
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    symbols = []
    if not trades.empty: symbols.extend(trades['symbol'].unique().tolist())
    if not wl.empty: symbols.extend(wl['symbol'].unique().tolist())
    symbols = list(set(symbols))
    
    c_search, c_sel = st.columns([1, 2])
    with c_search: new_search = st.text_input("بحث عن رمز جديد (مثال: 1120)")
    if new_search and new_search not in symbols: symbols.insert(0, new_search)
    
    with c_sel: symbol = st.selectbox("اختر الشركة للتحليل", symbols) if symbols else None

    if symbol:
        n, s = get_static_info(symbol)
        st.markdown(f"### {n} ({symbol}) - {s}")
        
        tab_dash, tab_fin, tab_thesis, tab_tech, tab_class = st.tabs(["📊 النظرة الشاملة", "📑 القوائم المالية", "📝 الأطروحة", "📈 فني", "🏛️ كلاسيكي"])

        with tab_dash:
            with st.spinner("جلب البيانات..."): data = get_fundamental_ratios(symbol)
            if data and data['Current_Price'] > 0:
                c1, c2 = st.columns([1, 3])
                with c1: st.metric("التقييم الآلي", f"{data['Score']}/10", data['Rating'])
                with c2: st.caption("يتم حساب التقييم بناءً على مكررات الربحية والقيمة العادلة والنمو.")
                st.markdown("---")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("P/E", safe_fmt(data['P/E']))
                k2.metric("P/B", safe_fmt(data['P/B']))
                k3.metric("ROE", safe_fmt(data['ROE'], "%"))
                k4.metric("Margin", safe_fmt(data['Profit_Margin'], "%"))
                
                fv = data['Fair_Value']
                curr = data['Current_Price']
                delta = ((curr - fv) / fv * 100) if fv and fv > 0 else 0
                st.metric("القيمة العادلة", safe_fmt(fv), f"{delta:.1f}%" if fv else None, delta_color="inverse")
            else: st.error("بيانات السهم غير متاحة حالياً.")

        with tab_fin:
            c_act, c_link = st.columns([1, 3])
            with c_act:
                if st.button("🔄 تحديث القوائم"):
                    with st.spinner("جاري التحديث..."):
                        if update_financial_statements(symbol): st.success("تم")
                        else: st.error("فشل")
            with c_link:
                st.markdown(f"""<div style="display:flex; gap:10px;">
                    <a href="https://www.saudiexchange.sa/wps/portal/tadawul/home" target="_blank" style="padding:5px 15px; background:#009540; color:white; border-radius:5px;">تداول</a>
                    <a href="https://sa.tradingview.com/chart/?symbol=TADAWUL%3A{symbol}" target="_blank" style="padding:5px 15px; background:#131722; color:white; border-radius:5px;">TradingView</a>
                    <a href="https://www.google.com/finance/quote/{symbol}:TADAWUL" target="_blank" style="padding:5px 15px; background:#4285F4; color:white; border-radius:5px;">Google</a>
                </div>""", unsafe_allow_html=True)

            df_fin = get_stored_financials(symbol)
            if not df_fin.empty:
                df_display = df_fin.copy()
                df_display['date'] = pd.to_datetime(df_display['date']).dt.year
                df_display = df_display.set_index('date').sort_index()
                fig = px.bar(df_display, x=df_display.index, y=['revenue', 'net_income'], barmode='group', title="الإيرادات وصافي الربح")
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(df_display.T, use_container_width=True)
            else: st.info("اضغط تحديث لجلب القوائم.")

        with tab_thesis:
            current = get_thesis(symbol)
            def_text = current['thesis_text'] if current else ""
            def_target = current['target_price'] if current else 0.0
            def_rec = current['recommendation'] if current else "Hold"
            
            with st.form("thesis_form"):
                r_col, t_col = st.columns(2)
                new_rec = r_col.selectbox("قرارك", ["Buy", "Sell", "Hold", "Watch"], index=["Buy", "Sell", "Hold", "Watch"].index(def_rec) if def_rec in ["Buy", "Sell", "Hold", "Watch"] else 2)
                new_target = t_col.number_input("المستهدف", value=def_target)
                new_text = st.text_area("الأطروحة ومبررات الاستثمار", value=def_text, height=200)
                if st.form_submit_button("حفظ الأطروحة"):
                    save_thesis(symbol, new_text, new_target, new_rec)
                    st.success("تم الحفظ")

        with tab_tech: render_technical_chart(symbol, "2y", "1d")
        with tab_class: render_classical_analysis(symbol)

def view_add_trade():
    st.header("مركز العمليات")
    t1, t2, t3 = st.tabs(["➕ صفقة جديدة", "💰 تسجيل عائد", "🏦 مالية"])
    with t1:
        with st.form("buy_form"):
            c1, c2 = st.columns(2)
            sym = c1.text_input("الرمز (مثال: 1120)")
            atype = c2.selectbox("نوع الأصل", ["Stock", "Sukuk", "REIT"])
            c3, c4, c5 = st.columns(3)
            qty = c3.number_input("الكمية", 1.0)
            price = c4.number_input("السعر", 0.01)
            strat = c5.selectbox("المحفظة", ["استثمار", "مضاربة"])
            d = st.date_input("التاريخ", date.today())
            if st.form_submit_button("حفظ"):
                n, s = get_static_info(sym)
                execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (?,?,?,?,?,?,?,?,?,?)", (sym, n, s, atype, str(d), qty, price, strat, 'Open', price))
                st.success("تم"); st.cache_data.clear()
    with t2:
        with st.form("div_form"):
            trades = fetch_table("Trades")
            syms = trades[trades['status']=='Open']['symbol'].unique().tolist() if not trades.empty else []
            s = st.selectbox("الأصل", syms)
            amt = st.number_input("المبلغ")
            d = st.date_input("التاريخ")
            if st.form_submit_button("تسجيل"):
                n, _ = get_static_info(s)
                execute_query("INSERT INTO ReturnsGrants (date, symbol, company_name, amount) VALUES (?,?,?,?)", (str(d), s, n, amt))
                st.success("تم")
    with t3:
        c1, c2 = st.columns(2)
        with c1: 
            with st.form("dep_form"):
                amt = st.number_input("إيداع")
                if st.form_submit_button("تأكيد الإيداع"):
                    execute_query("INSERT INTO Deposits (date, amount) VALUES (?,?)", (str(date.today()), amt))
                    st.success("تم")
        with c2:
            with st.form("wit_form"):
                amt = st.number_input("سحب")
                if st.form_submit_button("تأكيد السحب"):
                    execute_query("INSERT INTO Withdrawals (date, amount) VALUES (?,?)", (str(date.today()), amt))
                    st.success("تم")

# ... (نفس محتوى views.py السابق، فقط استبدل دالة view_settings بالتالي) ...

def view_settings():
    st.header("⚙️ الإعدادات وتوزيع المحفظة")
    
    # 1. قسم الأوزان (Sector Weights)
    st.markdown("### 🎯 الأهداف القطاعية")
    st.markdown("""
    <div style="font-size:0.9rem; color:#6B7280; margin-bottom:10px;">
    تحكم في التوزيع المستهدف لمحفظتك. سيقوم البرنامج بتنبيهك إذا تجاوزت الوزن المحدد.
    </div>
    """, unsafe_allow_html=True)
    
    all_sectors = sorted(list(set(d['sector'] for d in TADAWUL_DB.values())))
    df_all = pd.DataFrame({'sector': all_sectors})
    saved = fetch_table("SectorTargets")
    
    if not saved.empty:
        df = pd.merge(df_all, saved, on='sector', how='left').fillna(0)
    else:
        df = df_all
        df['target_percentage'] = 0.0
    
    # تحسين عرض المحرر ليشبه الجدول الموحد
    with st.container():
        edited = st.data_editor(
            df, 
            column_config={
                "sector": st.column_config.TextColumn("القطاع", disabled=True),
                "target_percentage": st.column_config.NumberColumn(
                    "النسبة المستهدفة %", 
                    min_value=0, max_value=100, step=1, 
                    format="%d%%",
                    help="أدخل النسبة المئوية المستهدفة لهذا القطاع"
                )
            },
            hide_index=True,
            use_container_width=True,
            key="sec_editor" # مفتاح فريد
        )
        
    # أزرار التحكم
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("💾 حفظ التوزيع", type="primary"):
            execute_query("DELETE FROM SectorTargets")
            total = 0
            for _, row in edited.iterrows():
                if row['target_percentage'] > 0:
                    execute_query("INSERT INTO SectorTargets (sector, target_percentage) VALUES (?,?)", (row['sector'], row['target_percentage']))
                    total += row['target_percentage']
            
            if total > 100:
                st.warning(f"⚠️ تنبيه: مجموع النسب {total}% أكبر من 100%!")
            else:
                st.success(f"تم الحفظ بنجاح (المجموع: {total}%)")
    
    st.markdown("---")
    
    # 2. قسم النسخ الاحتياطي (Data Backup)
    st.markdown("### 🛡️ أمان البيانات")
    c_back, c_info = st.columns([1, 3])
    with c_back:
        if st.button("📦 إنشاء نسخة احتياطية"):
            if create_smart_backup():
                st.success("✅ تم حفظ النسخة في مجلد backups")
            else:
                st.error("فشل النسخ")
    with c_info:
        st.info("يُنصح بعمل نسخة احتياطية بعد إضافة صفقات جديدة. تجد الملفات في مجلد 'backups' داخل المشروع.")

def router():
    render_navbar()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    
    if pg == 'home': view_dashboard(fin)
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'sukuk': view_portfolio(fin, 'invest') # Placeholder
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'add': view_add_trade()
    elif pg == 'settings': view_settings()
    elif pg == 'cash': view_dashboard(fin) # Shortcut
    elif pg == 'tools': 
        st.info("الزكاة: " + str(fin['market_val_open'] * 0.025775))
    elif pg == 'update': 
        update_prices(); st.session_state.page='home'; st.rerun()
