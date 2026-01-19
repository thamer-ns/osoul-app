import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
# الاستيراد من components ضروري جداً
from components import render_navbar, render_kpi, render_table 
from analytics import (calculate_portfolio_metrics, update_prices, create_smart_backup, 
                       get_comprehensive_performance, get_rebalancing_advice, 
                       get_dividends_calendar, generate_equity_curve, calculate_historical_drawdown)
from charts import render_technical_chart
from financial_analysis import get_fundamental_ratios
from market_data import get_static_info, get_tasi_data
from database import execute_query, fetch_table
from config import BACKUP_DIR, APP_NAME

# ... (دوال العرض: view_dashboard, view_portfolio, view_sukuk_portfolio, view_liquidity كما هي) ...
# سأضع لك دالة التوجيه router فقط للتأكد، وباقي الدوال اتركها كما نسختها سابقاً

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
    C = st.session_state.custom_colors
    arrow = "🔼" if t_change >= 0 else "🔽"
    color = "#10B981" if t_change >= 0 else "#EF4444"
    st.markdown(f"""<div class="tasi-box"><div><div style="font-size:1rem; color:#6B7280;">المؤشر العام (TASI)</div><div style="font-size:2.2rem; font-weight:900; color:#1F2937;">{t_price:,.2f}</div></div><div><div style="background:{color}15; color:{color}; padding:8px 20px; border-radius:10px; font-size:1.2rem; font-weight:bold; direction:ltr;">{arrow} {t_change:+.2f}%</div></div></div>""", unsafe_allow_html=True)
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

def view_portfolio(fin, page_key):
    target_strat = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"محفظة {target_strat}")
    all_data = fin['all_trades']
    if all_data.empty: st.info("لا توجد بيانات"); return
    df_strat = all_data[(all_data['strategy'] == target_strat) & (all_data['asset_type'] != 'Sukuk')].copy()
    if df_strat.empty: st.warning(f"محفظة {target_strat} فارغة"); return
    
    open_df = df_strat[df_strat['status']=='Open'].copy()
    closed_df = df_strat[df_strat['status']=='Close'].copy()
    
    t1, t2, t3 = st.tabs([f"القائمة ({len(open_df)})", "التحليل", f"المغلقة ({len(closed_df)})"])
    with t1:
        if not open_df.empty:
            cols_op = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('status', 'الحالة'), ('quantity', 'الكمية'), ('entry_price', 'شراء'), ('current_price', 'سعر'), ('market_value', 'قيمة'), ('gain', 'ربح'), ('gain_pct', '%'), ('date', 'تاريخ')]
            render_table(apply_sorting(open_df, cols_op, f"{page_key}_o"), cols_op)
        else: st.info("فارغة")
    with t2:
        sec_p, stock_p = get_comprehensive_performance(df_strat, fin['returns'])
        if not sec_p.empty:
            cols_sp = [('sector', 'القطاع'), ('gain', 'رأسمالي'), ('total_dividends', 'توزيعات'), ('net_profit', 'صافي'), ('roi_pct', 'عائد %')]
            render_table(sec_p.sort_values('net_profit', ascending=False), cols_sp)
    with t3:
        if not closed_df.empty:
            cols_cl = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح'), ('gain_pct', '%'), ('exit_date', 'بيع')]
            render_table(apply_sorting(closed_df, cols_cl, f"{page_key}_c"), cols_cl)
        else: st.info("لا يوجد")

def view_sukuk_portfolio(fin):
    st.header("📜 محفظة الصكوك")
    all_data = fin['all_trades']
    if all_data.empty: st.info("لا توجد بيانات"); return
    sukuk_df = all_data[all_data['asset_type'] == 'Sukuk'].copy()
    if sukuk_df.empty: st.warning("لم تقم بإضافة أي صكوك بعد."); return
    total_cost = sukuk_df['total_cost'].sum()
    current_val = sukuk_df['market_value'].sum()
    gain = sukuk_df['gain'].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("إجمالي الصكوك", f"{total_cost:,.2f}")
    c2.metric("القيمة الحالية", f"{current_val:,.2f}")
    c3.metric("الربح الرأسمالي", f"{gain:,.2f}", delta_color="normal")
    st.markdown("### قائمة الصكوك")
    cols = [('company_name', 'اسم الصك'), ('symbol', 'الرمز'), ('quantity', 'العدد'), ('entry_price', 'سعر الشراء'), ('current_price', 'السعر الحالي'), ('market_value', 'القيمة السوقية'), ('gain_pct', 'النمو %')]
    render_table(sukuk_df, cols)

def view_liquidity():
    fin = calculate_portfolio_metrics()
    c1, c2, c3 = st.columns(3)
    with c1: render_kpi("إيداعات", f"{fin['total_deposited']:,.2f}", "blue")
    with c2: render_kpi("سحوبات", f"{fin['total_withdrawn']:,.2f}", -1)
    with c3: render_kpi("عوائد", f"{fin['total_returns']:,.2f}", "success")
    st.markdown("---")
    t1, t2, t3 = st.tabs(["إيداع", "سحب", "عوائد"])
    with t1: render_table(apply_sorting(fin['deposits'], [('date','تاريخ'),('amount','مبلغ'),('note','ملاحظة')], "ld"), [('date','تاريخ'),('amount','مبلغ'),('note','ملاحظة')])
    with t2: render_table(apply_sorting(fin['withdrawals'], [('date','تاريخ'),('amount','مبلغ'),('note','ملاحظة')], "lw"), [('date','تاريخ'),('amount','مبلغ'),('note','ملاحظة')])
    with t3: render_table(apply_sorting(fin['returns'], [('date','تاريخ'),('amount','مبلغ'),('symbol','رمز')], "lr"), [('date','تاريخ'),('amount','مبلغ'),('symbol','رمز')])

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

def view_add_trade():
    st.header("إضافة عملية جديدة")
    with st.form("add"):
        c1, c2 = st.columns(2)
        sym = c1.text_input("الرمز (مثال: 1120)")
        asset = c2.selectbox("نوع الأصل", ["Stock", "Sukuk", "REIT"], index=0)
        c3, c4, c5 = st.columns(3)
        qty = c3.number_input("الكمية", 1.0)
        price = c4.number_input("سعر الشراء", 0.01)
        strat = c5.selectbox("المحفظة", ["استثمار", "مضاربة"])
        d = st.date_input("تاريخ الشراء", date.today())
        if st.form_submit_button("حفظ العملية"):
            if sym and qty:
                n, s = get_static_info(sym)
                if asset == "Sukuk": s = "الصكوك والسندات"
                execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (?,?,?,?,?,?,?,?,?,?)", (sym, n, s, asset, str(d), qty, price, strat, 'Open', price))
                st.success("تمت الإضافة بنجاح"); st.cache_data.clear()

def view_settings():
    st.header("إعدادات")
    st.markdown("### الأهداف")
    targets = fetch_table("SectorTargets")
    if targets.empty:
        df = pd.DataFrame([{'القطاع': 'بنوك', 'الهدف': 0.0}])
    else:
        df = targets.rename(columns={'sector': 'القطاع', 'target_percentage': 'الهدف'})[['القطاع', 'الهدف']]
    ed = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    if st.button("حفظ الأهداف"):
        execute_query("DELETE FROM SectorTargets")
        for _, row in ed.iterrows():
            if row['القطاع'] and row['الهدف']:
                execute_query("INSERT INTO SectorTargets (sector, target_percentage) VALUES (?,?)", (row['القطاع'], row['الهدف']))
        st.success("تم الحفظ")
    st.markdown("---")
    with st.expander("إدارة البيانات"):
        if st.button("نسخ احتياطي"): create_smart_backup(); st.success("تم النسخ")

def view_analysis(fin):
    st.header("🔍 التحليل الشامل (مالي وفني)")
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
        st.markdown("---")
        st.subheader(f"📊 البطاقة المالية: {symbol}")
        with st.spinner("جاري جلب البيانات..."): ratios = get_fundamental_ratios(symbol)
        if ratios:
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("P/E", f"{ratios['P/E']:.2f}" if ratios['P/E'] else "-")
            k2.metric("P/B", f"{ratios['P/B']:.2f}" if ratios['P/B'] else "-")
            k3.metric("ROE", f"{ratios['ROE']:.1f}%" if ratios['ROE'] else "-")
            k4.metric("EPS", f"{ratios['EPS']:.2f}" if ratios['EPS'] else "-")
            fv = ratios['Fair_Value']
            curr = ratios['Current_Price']
            delta_val = ((curr - fv) / fv * 100) if fv > 0 and curr > 0 else 0
            k5.metric("Graham FV", f"{fv:.2f}", delta=f"{delta_val:.1f}%", delta_color="inverse" if curr < fv else "normal")
        st.markdown("---")
        render_technical_chart(symbol, period, interval)

# === دالة التوجيه (Router) ===
def router():
    # هنا يتم رسم القائمة العلوية
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
