import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time

from config import DEFAULT_COLORS
from components import render_navbar, render_kpi, render_table, render_ticker_card, safe_fmt
from analytics import (calculate_portfolio_metrics, update_prices, generate_equity_curve, run_backtest)
from database import execute_query, fetch_table, get_db
from market_data import get_static_info, get_tasi_data, get_chart_history
from data_source import get_company_details
from charts import view_advanced_chart

try: from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui
except ImportError: 
    get_fundamental_ratios = lambda s: {'Score': 0}
    render_financial_dashboard_ui = lambda s: None

def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    C = DEFAULT_COLORS
    arrow, cl = ("🔼", C['success']) if t_change >= 0 else ("🔽", C['danger'])
    
    st.markdown(f"""
    <div class="tasi-box">
        <div><div style="font-size:1.1rem; color:{C['sub_text']};">المؤشر العام</div><div style="font-size:2.2rem; font-weight:900; color:{C['main_text']};">{safe_fmt(t_price)}</div></div>
        <div style="background:{cl}15; color:{cl}; padding:8px 20px; border-radius:10px; font-weight:bold; direction:ltr;">{arrow} {safe_fmt(t_change)}%</div>
    </div>""", unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    total_inv = fin['total_deposited'] - fin['total_withdrawn']
    with c1: render_kpi("الكاش المتوفر", safe_fmt(fin['cash']), "blue")
    with c2: render_kpi("صافي الاستثمار", safe_fmt(total_inv))
    with c3: render_kpi("القيمة السوقية", safe_fmt(fin['market_val_open']))
    tpl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("الربح/الخسارة", safe_fmt(tpl), tpl)
    
    st.markdown("---")
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title=""), use_container_width=True)

def render_pulse_dashboard():
    st.header("💓 نبض السوق")
    trades = fetch_table("Trades")
    wl = fetch_table("Watchlist")
    symbols = set()
    if not trades.empty: symbols.update(trades[trades['status']=='Open']['symbol'].unique())
    if not wl.empty: symbols.update(wl['symbol'].unique())
    if not symbols: st.info("القائمة فارغة."); return
    cols = st.columns(4)
    for i, sym in enumerate(symbols):
        name, _ = get_company_details(sym)
        price = 0.0
        if not trades.empty:
            row = trades[trades['symbol'] == sym]
            if not row.empty: price = row.iloc[0]['current_price']
        with cols[i % 4]: render_ticker_card(sym, name if name else sym, price, 0.0)

def view_portfolio(fin, page_key):
    ts = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    all_d = fin['all_trades']
    df = pd.DataFrame()
    if not all_d.empty:
        df = all_d[all_d['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    if not df.empty:
        total_market = df[df['status']=='Open']['market_value'].sum()
        df['weight'] = df.apply(lambda x: (x['market_value'] / total_market * 100) if x['status']=='Open' and total_market > 0 else 0, axis=1)
        df['daily_change'] = df.apply(lambda x: ((x['current_price'] - x['prev_close']) / x['prev_close'] * 100) if pd.notna(x['prev_close']) and x['prev_close'] > 0 else 0, axis=1)

    COLS_FULL = [
        ('company_name', 'اسم الشركة'), ('sector', 'القطاع'), ('status', 'الحالة'),
        ('symbol', 'رمز الشركة'), ('date', 'تاريخ الشراء'), ('exit_date', 'تاريخ البيع'),
        ('quantity', 'الكمية'), ('entry_price', 'سعر الشراء'), ('total_cost', 'التكلفة'),
        ('year_high', 'اعلى سنوي'), ('current_price', 'السعر الحالي'), ('year_low', 'ادنى سنوي'),
        ('market_value', 'سعر السوق'), ('gain', 'الربح والخسارة'), ('gain_pct', 'نسبة الربح والخسارة'),
        ('weight', 'وزن السهم'), ('daily_change', 'نسبة التغير اليومي'), ('prev_close', 'اغلاق الامس')
    ]

    if not df.empty:
        op = df[df['status']=='Open'].copy()
        market_val = op['quantity'].mul(op['current_price']).sum() if not op.empty else 0
        total_cost = op['quantity'].mul(op['entry_price']).sum() if not op.empty else 0
        unrealized = market_val - total_cost
        cl = df[df['status']=='Close'].copy()
        realized_profit = ((cl['exit_price'] - cl['entry_price']) * cl['quantity']).sum() if not cl.empty else 0

        c1, c2, c3, c4 = st.columns(4)
        with c1: render_kpi("القيمة السوقية", safe_fmt(market_val), "blue")
        with c2: render_kpi("التكلفة", safe_fmt(total_cost))
        with c3: render_kpi("الربح العائم", safe_fmt(unrealized), unrealized)
        with c4: render_kpi("الربح المحقق", safe_fmt(realized_profit), realized_profit)
        st.markdown("---")

    if df.empty: st.info("المحفظة فارغة"); return

    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()

    t1, t2, t3 = st.tabs(["الأسهم الحالية", "تحليل الأداء", "الأرشيف"])
    with t1:
        if not open_df.empty:
            # ترتيب تلقائي بالأحدث
            open_df = open_df.sort_values(by="date", ascending=False)
            render_table(open_df, COLS_FULL)
            
            with st.expander("🔻 بيع سهم"):
                with st.form("sell"):
                    c1,c2 = st.columns(2)
                    st.markdown("**اختر السهم:**"); s = c1.selectbox("s", open_df['symbol'].unique(), label_visibility="collapsed")
                    st.markdown("**سعر البيع:**"); p = c2.number_input("p", min_value=0.0, label_visibility="collapsed")
                    st.markdown("**التاريخ:**"); d = st.date_input("d", date.today(), label_visibility="collapsed")
                    if st.form_submit_button("تأكيد"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, ts))
                        st.success("تم"); time.sleep(0.5); st.rerun()
        else: st.info("لا توجد أسهم حالية")
    
    with t2:
        if not open_df.empty and page_key == 'invest':
            fig = px.pie(open_df, values='market_value', names='sector', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            
    with t3:
        if not closed_df.empty: 
            closed_df['net_sales'] = closed_df['quantity'] * closed_df['exit_price']
            closed_df['realized_gain'] = closed_df['net_sales'] - closed_df['total_cost']
            
            c1, c2 = st.columns(2)
            with c1: render_kpi("صافي البيع", safe_fmt(closed_df['net_sales'].sum()), "blue")
            with c2: render_kpi("الربح المحقق", safe_fmt(closed_df['realized_gain'].sum()))
            
            render_table(closed_df, COLS_FULL)
        else: st.info("الأرشيف فارغ")

def view_cash_log():
    st.header("💵 سجل السيولة")
    fin = calculate_portfolio_metrics()
    c1, c2, c3 = st.columns(3)
    net = fin['deposits']['amount'].sum() - fin['withdrawals']['amount'].sum()
    with c1: render_kpi("إجمالي الإيداعات", safe_fmt(fin['deposits']['amount'].sum()), "success")
    with c2: render_kpi("إجمالي السحوبات", safe_fmt(fin['withdrawals']['amount'].sum()), "danger")
    with c3: render_kpi("صافي التمويل", safe_fmt(net), "blue")
    st.markdown("---")

    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "العوائد"])
    cols = [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظات')]
    with t1: render_table(fin['deposits'].sort_values('date', ascending=False), cols)
    with t2: render_table(fin['withdrawals'].sort_values('date', ascending=False), cols)
    with t3: render_table(fin['returns'].sort_values('date', ascending=False), [('date','التاريخ'), ('symbol','الرمز'), ('amount','المبلغ'), ('note','النوع')])

def view_add_operations():
    # صفحة الإضافة الموحدة (الميزة الجديدة)
    st.header("➕ تسجيل العمليات")
    tab1, tab2 = st.tabs(["📈 صفقة أسهم", "💰 حركة مالية (كاش)"])
    
    with tab1:
        with st.form("add_trade"):
            c1, c2 = st.columns(2)
            st.markdown("**الرمز:**"); sym = c1.text_input("t_s", label_visibility="collapsed")
            st.markdown("**المحفظة:**"); strat = c2.selectbox("t_st", ["استثمار", "مضاربة", "صكوك"], label_visibility="collapsed")
            c3, c4, c5 = st.columns(3)
            st.markdown("**الكمية:**"); qty = c3.number_input("t_q", min_value=1.0, label_visibility="collapsed")
            st.markdown("**السعر:**"); price = c4.number_input("t_p", min_value=0.0, step=0.01, label_visibility="collapsed")
            st.markdown("**التاريخ:**"); dt = c5.date_input("t_d", date.today(), label_visibility="collapsed")
            if st.form_submit_button("حفظ الصفقة"):
                if sym and qty > 0:
                    cn, sec = get_company_details(sym)
                    at = "Sukuk" if strat == "صكوك" else "Stock"
                    execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Open', %s)", (sym, cn, sec, at, str(dt), qty, price, strat, price))
                    st.success("تم الحفظ"); st.cache_data.clear()
                else: st.error("بيانات ناقصة")

    with tab2:
        with st.form("add_cash"):
            c1, c2 = st.columns(2)
            st.markdown("**نوع العملية:**"); op_type = c1.selectbox("op_t", ["إيداع نقدي", "سحب نقدي", "توزيعات"], label_visibility="collapsed")
            st.markdown("**المبلغ:**"); amount = c2.number_input("op_a", min_value=0.0, step=100.0, label_visibility="collapsed")
            c3, c4 = st.columns(2)
            st.markdown("**التاريخ:**"); op_date = c3.date_input("op_d", date.today(), label_visibility="collapsed")
            st.markdown("**ملاحظة/رمز:**"); note = c4.text_input("op_n", label_visibility="collapsed")
            if st.form_submit_button("حفظ العملية"):
                if amount > 0:
                    if op_type == "إيداع نقدي": execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s, %s, %s)", (str(op_date), amount, note))
                    elif op_type == "سحب نقدي": execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s, %s, %s)", (str(op_date), amount, note))
                    else: 
                        cn, _ = get_company_details(note)
                        execute_query("INSERT INTO ReturnsGrants (date, symbol, company_name, amount, note) VALUES (%s, %s, %s, %s, %s)", (str(op_date), note, cn, amount, "توزيعات"))
                    st.success("تم التسجيل"); st.rerun()

def view_analysis(fin):
    st.header("🔬 مركز التحليل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    symbols = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c1, c2 = st.columns([1, 2])
    with c1: 
        st.markdown("**بحث:**")
        ns = st.text_input("s_search", label_visibility="collapsed")
    if ns and ns not in symbols: symbols.insert(0, ns)
    
    with c2:
        st.markdown("**اختر الشركة:**")
        sym = st.selectbox("s_select", symbols, label_visibility="collapsed") if symbols else None
    
    if sym:
        n, s = get_company_details(sym)
        st.markdown(f"### {n} ({sym})")
        t1, t2, t3, t4, t5 = st.tabs(["📊 المؤشرات", "📑 القوائم", "📝 الأطروحة", "📈 الشارت", "🏛️ كلاسيكي"])
        with t1:
            d = get_fundamental_ratios(sym)
            c1,c2 = st.columns([1,3])
            c1.metric("التقييم", f"{d['Score']}/10")
            render_financial_dashboard_ui(sym)
        with t2: st.info("البيانات المالية")
        with t3: st.info("الأطروحة")
        with t4: view_advanced_chart(sym)
        with t5: st.info("التحليل الكلاسيكي")

def view_backtester_ui(fin):
    st.header("🧪 مختبر الاستراتيجيات")
    c1, c2, c3 = st.columns(3)
    with c1: 
        st.markdown("**السهم:**"); sym = st.selectbox("bs", list(set(fin['all_trades']['symbol'].unique().tolist()+["1120"])), label_visibility="collapsed")
    with c2: 
        st.markdown("**استراتيجية:**"); strat = st.selectbox("bst", ["Trend Follower", "Sniper"], label_visibility="collapsed")
    with c3: 
        st.markdown("**رأس المال:**"); cap = st.number_input("bc", 100000, label_visibility="collapsed")
    if st.button("🚀 تشغيل"):
        df = get_chart_history(sym, "2y")
        if df is not None:
            res = run_backtest(df, strat, cap)
            if res:
                c1,c2 = st.columns(2)
                c1.metric("العائد", f"{res['return_pct']:.2f}%")
                c2.metric("الرصيد", f"{res['final_value']:,.2f}")
                st.line_chart(res['df']['Portfolio_Value'])

def view_settings():
    st.header("⚙️ الإعدادات")
    with st.expander("📥 استيراد بيانات (Excel/CSV)"):
        f = st.file_uploader("اختر الملف", accept_multiple_files=False)
        if f and st.button("بدء الاستيراد"): st.info("جاهز")

def view_sukuk_portfolio(fin):
    st.header("📜 الصكوك")
    df = fin['all_trades']
    sk = df[df['asset_type']=='Sukuk'].copy()
    if not sk.empty:
        render_table(sk, [('company_name', 'اسم الصك'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'شراء'), ('gain', 'الربح')])
    else: st.info("لا توجد صكوك")

def view_tools():
    st.header("🛠️ الأدوات")
    fin = calculate_portfolio_metrics()
    st.info(f"الزكاة التقديرية: {safe_fmt(fin['market_val_open']*0.025775)} ريال")

def router():
    render_navbar()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    
    if pg == 'home': view_dashboard(fin)
    elif pg == 'pulse': render_pulse_dashboard()
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'sukuk': view_sukuk_portfolio(fin)
    elif pg == 'cash': view_cash_log()
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'backtest': view_backtester_ui(fin)
    elif pg == 'tools': view_tools()
    elif pg == 'settings': view_settings()
    elif pg == 'add': view_add_operations()
    elif pg == 'update': 
        with st.spinner("تحديث..."): update_prices()
        st.session_state.page='home'; st.rerun()
