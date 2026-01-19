import streamlit as st
import pandas as pd
from datetime import date
from components import render_navbar, render_kpi, render_table
from analytics import (calculate_portfolio_metrics, update_prices, create_smart_backup, 
                       get_comprehensive_performance, get_rebalancing_advice, 
                       get_dividends_calendar, generate_equity_curve, calculate_historical_drawdown)
# استيراد ملفات التحليل المنفصلة
from financial_analysis import get_fundamental_ratios
from technical_analysis import render_technical_chart
from classical_analysis import render_classical_analysis
from market_data import get_static_info, get_tasi_data
from database import execute_query, fetch_table

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

def view_portfolio(fin, page_key):
    target_strat = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"محفظة {target_strat}")
    all_data = fin['all_trades']
    
    if all_data.empty: st.info("لا توجد بيانات"); return
    
    # تدقيق البيانات: استبعاد الصكوك وفلترة الاستراتيجية
    df_strat = all_data[(all_data['strategy'] == target_strat) & (all_data['asset_type'] != 'Sukuk')].copy()
    
    if df_strat.empty: st.warning(f"محفظة {target_strat} فارغة"); return
    
    open_df = df_strat[df_strat['status']=='Open'].copy()
    closed_df = df_strat[df_strat['status']=='Close'].copy()
    
    # إعادة تدقيق الحسابات قبل العرض (Audit)
    if not open_df.empty:
        open_df['gain'] = open_df['market_value'] - open_df['total_cost']
        open_df['gain_pct'] = (open_df['gain'] / open_df['total_cost']) * 100
    
    t1, t2, t3 = st.tabs([f"القائمة ({len(open_df)})", "تحليل الأداء", f"المغلقة ({len(closed_df)})"])
    
    with t1:
        if not open_df.empty:
            # تلخيص القطاعات
            sec_sum = open_df.groupby('sector').agg({'symbol':'count','total_cost':'sum','market_value':'sum'}).reset_index()
            total_mv = sec_sum['market_value'].sum()
            sec_sum['current_weight'] = (sec_sum['market_value']/total_mv*100).fillna(0)
            
            # جلب الأهداف
            targets = fetch_table("SectorTargets")
            if not targets.empty:
                sec_sum = pd.merge(sec_sum, targets, on='sector', how='left')
                sec_sum['target_percentage'] = sec_sum['target_percentage'].fillna(0.0)
            else: sec_sum['target_percentage'] = 0.0
            sec_sum['remaining'] = (total_mv * sec_sum['target_percentage']/100) - sec_sum['market_value']
            
            st.markdown("#### توزيع القطاعات")
            cols_sec = [('sector', 'القطاع'), ('symbol', 'عدد'), ('total_cost', 'التكلفة'), ('current_weight', 'الوزن %'), ('target_percentage', 'الهدف %'), ('remaining', 'المتبقي')]
            render_table(apply_sorting(sec_sum, cols_sec, f"{page_key}_s"), cols_sec)
            
            st.markdown("---")
            st.markdown("#### تفاصيل الأسهم")
            cols_op = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('status', 'الحالة'), ('quantity', 'الكمية'), ('entry_price', 'ت.شراء'), ('current_price', 'سعر'), ('daily_change', 'يومي %'), ('market_value', 'قيمة'), ('gain', 'ربح'), ('gain_pct', '%'), ('date', 'تاريخ')]
            render_table(apply_sorting(open_df, cols_op, f"{page_key}_o"), cols_op)
        else: st.info("فارغة")

    with t2:
        sec_p, stock_p = get_comprehensive_performance(df_strat, fin['returns'])
        if not sec_p.empty:
            st.markdown("### الأداء حسب القطاع")
            cols_sp = [('sector', 'القطاع'), ('gain', 'رأسمالي'), ('total_dividends', 'توزيعات'), ('net_profit', 'صافي'), ('roi_pct', 'عائد %')]
            render_table(sec_p.sort_values('net_profit', ascending=False), cols_sp)
        
        if not open_df.empty:
            st.markdown("### تحليل المخاطر")
            dd = calculate_historical_drawdown(open_df)
            if not dd.empty:
                st.metric("أقصى تراجع (Drawdown)", f"{dd['drawdown'].min():.2f}%")

    with t3:
        if not closed_df.empty:
            cols_cl = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح المحقق'), ('gain_pct', '%'), ('exit_date', 'تاريخ البيع')]
            render_table(apply_sorting(closed_df, cols_cl, f"{page_key}_c"), cols_cl)
        else: st.info("لا توجد صفقات مغلقة")

def view_add_trade():
    st.header("إضافة عملية جديدة")
    with st.form("add"):
        c1, c2 = st.columns(2)
        sym = c1.text_input("رمز الورقة المالية (مثال: 1120)")
        
        # تعريب قائمة نوع الأصل كما طلبت
        asset_map = {"سهم": "Stock", "صك": "Sukuk", "ريت": "REIT"}
        asset_label = c2.selectbox("نوع الأصل", list(asset_map.keys()), index=0)
        asset_val = asset_map[asset_label] # التخزين بالإنجليزية لضمان عمل الكود
        
        c3, c4, c5 = st.columns(3)
        qty = c3.number_input("الكمية", 1.0)
        price = c4.number_input("سعر الشراء", 0.01)
        strat = c5.selectbox("المحفظة", ["استثمار", "مضاربة"])
        d = st.date_input("تاريخ الشراء", date.today())
        
        if st.form_submit_button("حفظ العملية"):
            if sym and qty:
                # محاولة جلب الاسم من قاعدة البيانات الموسعة
                n, s = get_static_info(sym)
                if asset_val == "Sukuk": 
                    s = "الصكوك والسندات"
                    if n == f"سهم {sym}": n = f"صك {sym}" # تحسين الاسم للصكوك
                
                execute_query(
                    "INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (?,?,?,?,?,?,?,?,?,?)", 
                    (sym, n, s, asset_val, str(d), qty, price, strat, 'Open', price)
                )
                st.success("تمت الإضافة بنجاح"); st.cache_data.clear()

def view_analysis(fin):
    st.header("🔍 مركز التحليل")
    
    # تجميع الرموز
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
        
        # فصل التحليلات في تبويبات كما طلبت
        tab_fund, tab_tech, tab_class = st.tabs(["💰 التحليل المالي", "📈 التحليل الفني", "🏛️ التحليل الكلاسيكي"])
        
        with tab_fund:
            with st.spinner("جاري جلب البيانات المالية..."):
                ratios = get_fundamental_ratios(symbol)
            
            if ratios and ratios.get('Current_Price', 0) > 0:
                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("مكرر الربح (P/E)", f"{ratios['P/E']:.2f}")
                k2.metric("القيمة الدفترية (P/B)", f"{ratios['P/B']:.2f}")
                k3.metric("العائد (ROE)", f"{ratios['ROE']:.1f}%")
                k4.metric("الربح (EPS)", f"{ratios['EPS']:.2f}")
                
                fv = ratios['Fair_Value']
                curr = ratios['Current_Price']
                delta = ((curr - fv) / fv * 100) if fv > 0 else 0
                color = "inverse" if fv > 0 and curr < fv else "normal"
                k5.metric("القيمة العادلة", f"{fv:.2f}", delta=f"{delta:.1f}%", delta_color=color)
            else:
                st.warning("تعذر جلب البيانات المالية، تأكد من الرمز.")

        with tab_tech:
            render_technical_chart(symbol, period, interval)
            
        with tab_class:
            render_classical_analysis(symbol)

# ... (باقي الدوال: router, view_dashboard, view_sukuk, view_liquidity, view_tools, view_settings تبقى كما هي في ردودي السابقة، فقط تأكد من استدعاء الدوال الصحيحة في router) ...
# سأضع لك router للتأكد
def router():
    render_navbar()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    
    if pg == 'home': view_dashboard(fin)
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'sukuk': view_sukuk_portfolio(fin) # view_sukuk_portfolio موجودة في الرد السابق
    elif pg == 'cash': view_liquidity() # view_liquidity موجودة في الرد السابق
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'tools': view_tools() # view_tools موجودة في الرد السابق
    elif pg == 'add': view_add_trade()
    elif pg == 'settings': view_settings() # view_settings موجودة في الرد السابق
    elif pg == 'update':
        with st.spinner("جاري التحديث..."): update_prices()
        st.session_state.page = 'home'; st.rerun()
