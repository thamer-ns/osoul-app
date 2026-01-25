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

# ==========================================
# 1. شريط التنقل (تم إصلاح الأزرار)
# ==========================================
def render_navbar_custom():
    render_navbar() # استدعاء الهيدر الأساسي
    
    # القائمة الرئيسية - تم إصلاح عدد الأعمدة وإضافة المختبر
    c_nav = st.container()
    with c_nav:
        cols = st.columns(8) # زدنا العدد إلى 8 لاستيعاب المختبر
        labels = ['الرئيسية', 'مضاربة', 'استثمار', 'السيولة', 'التحليل', 'المختبر', 'إضافة', 'الإعدادات']
        keys = ['home', 'spec', 'invest', 'cash', 'analysis', 'backtest', 'add', 'settings']
        
        for i, (col, label, key) in enumerate(zip(cols, labels, keys)):
            is_active = (st.session_state.page == key)
            btn_type = "primary" if is_active else "secondary"
            if col.button(label, key=f"nav_btn_{key}", type=btn_type, use_container_width=True):
                st.session_state.page = key
                st.rerun()
    st.markdown("---")

# ==========================================
# 2. لوحة القيادة
# ==========================================
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
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title="نمو المحفظة"), use_container_width=True)

# ==========================================
# 3. نبض السوق
# ==========================================
def render_pulse_dashboard():
    st.header("💓 نبض السوق")
    if st.button("تحديث الأسعار الآن 🔄"):
        with st.spinner("جاري الاتصال بالسوق..."):
            update_prices()
            st.success("تم التحديث")
            time.sleep(1)
            st.rerun()
            
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
        change = 0.0
        if not trades.empty:
            row = trades[trades['symbol'] == sym]
            if not row.empty: 
                price = row.iloc[0]['current_price']
                prev = row.iloc[0]['prev_close']
                if prev > 0: change = ((price - prev)/prev)*100
        
        with cols[i % 4]: render_ticker_card(sym, name if name else sym, price, change)

# ==========================================
# 4. المحفظة (مضاربة / استثمار)
# ==========================================
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
        ('current_price', 'السعر الحالي'), ('market_value', 'سعر السوق'), 
        ('gain', 'الربح والخسارة'), ('gain_pct', 'النسبة %'),
        ('weight', 'الوزن %'), ('daily_change', 'التغير اليومي %')
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

    if df.empty: st.info(f"محفظة {ts} فارغة حالياً."); return

    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()

    t1, t2, t3 = st.tabs(["الأسهم الحالية", "تحليل الأداء", "الأرشيف"])
    with t1:
        if not open_df.empty:
            open_df = open_df.sort_values(by="date", ascending=False)
            render_table(open_df, COLS_FULL)
        else: st.info("لا توجد أسهم مفتوحة")
    
    with t2:
        if not open_df.empty and page_key == 'invest':
            fig = px.pie(open_df, values='market_value', names='sector', hole=0.4, title="توزيع القطاعات")
            st.plotly_chart(fig, use_container_width=True)
            
    with t3:
        if not closed_df.empty: 
            closed_df['net_sales'] = closed_df['quantity'] * closed_df['exit_price']
            closed_df['realized_gain'] = closed_df['net_sales'] - closed_df['total_cost']
            c1, c2 = st.columns(2)
            with c1: render_kpi("صافي المبيعات", safe_fmt(closed_df['net_sales'].sum()), "blue")
            with c2: render_kpi("إجمالي الربح المحقق", safe_fmt(closed_df['realized_gain'].sum()))
            render_table(closed_df, COLS_FULL)
        else: st.info("سجل الصفقات المغلقة فارغ")

# ==========================================
# 5. سجل السيولة (تم إصلاح خطأ KeyError)
# ==========================================
def view_cash_log():
    st.header("💵 سجل السيولة")
    fin = calculate_portfolio_metrics()
    
    # حماية من البيانات الفارغة
    dep_sum = fin['deposits']['amount'].sum() if not fin['deposits'].empty else 0
    wit_sum = fin['withdrawals']['amount'].sum() if not fin['withdrawals'].empty else 0
    net = dep_sum - wit_sum
    
    c1, c2, c3 = st.columns(3)
    with c1: render_kpi("إجمالي الإيداعات", safe_fmt(dep_sum), "success")
    with c2: render_kpi("إجمالي السحوبات", safe_fmt(wit_sum), "danger")
    with c3: render_kpi("صافي التمويل", safe_fmt(net), "blue")
    st.markdown("---")

    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "العوائد"])
    cols = [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظات')]
    
    with t1: 
        if not fin['deposits'].empty: render_table(fin['deposits'].sort_values('date', ascending=False), cols)
        else: st.info("لا توجد إيداعات")
    with t2: 
        if not fin['withdrawals'].empty: render_table(fin['withdrawals'].sort_values('date', ascending=False), cols)
        else: st.info("لا توجد سحوبات")
    with t3: 
        if not fin['returns'].empty: render_table(fin['returns'].sort_values('date', ascending=False), [('date','التاريخ'), ('symbol','الرمز'), ('amount','المبلغ'), ('note','النوع')])
        else: st.info("لا توجد عوائد مسجلة")

# ==========================================
# 6. مركز العمليات
# ==========================================
def view_add_operations():
    st.header("➕ مركز العمليات")
    tab1, tab2 = st.tabs(["💼 عمليات الأسهم", "💰 العمليات المالية"])
    
    with tab1:
        with st.form("stock_op"):
            c_type, c_strat = st.columns(2)
            op_kind = c_type.selectbox("نوع العملية", ["شراء", "بيع"], label_visibility="collapsed")
            strat = c_strat.selectbox("المحفظة", ["استثمار", "مضاربة", "صكوك"], label_visibility="collapsed")
            
            trades = fetch_table("Trades")
            open_symbols = []
            if not trades.empty:
                mask = (trades['status'] == 'Open') & (trades['strategy'] == strat)
                open_symbols = trades[mask]['symbol'].unique().tolist()

            c_sym, c_qty = st.columns(2)
            selected_sym = None
            if op_kind == "بيع":
                if open_symbols:
                    selected_sym = c_sym.selectbox("اختر السهم", open_symbols, label_visibility="collapsed")
                else:
                    c_sym.warning("لا توجد أسهم متاحة للبيع")
            else:
                selected_sym = c_sym.text_input("رمز السهم", placeholder="مثال: 1120", label_visibility="collapsed")

            qty = c_qty.number_input("الكمية", min_value=1.0, step=1.0, label_visibility="collapsed")
            c_price, c_date = st.columns(2)
            price = c_price.number_input("السعر", min_value=0.0, step=0.01, label_visibility="collapsed")
            op_date = c_date.date_input("التاريخ", date.today(), label_visibility="collapsed")

            if st.form_submit_button("تنفيذ"):
                if not selected_sym or qty <= 0 or price <= 0:
                    st.error("بيانات غير مكتملة")
                else:
                    if op_kind == "شراء":
                        cn, sec = get_company_details(selected_sym)
                        at = "Sukuk" if strat == "صكوك" else "Stock"
                        execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Open', %s)", (selected_sym, cn, sec, at, str(op_date), qty, price, strat, price))
                        st.success(f"تم شراء {selected_sym}")
                    elif op_kind == "بيع":
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (price, str(op_date), selected_sym, strat))
                        st.success(f"تم بيع {selected_sym}")
                    st.cache_data.clear()

    with tab2:
        with st.form("cash_op"):
            c1, c2 = st.columns(2)
            op_type = c1.selectbox("النوع", ["إيداع نقدي", "سحب نقدي", "توزيعات"], label_visibility="collapsed")
            amount = c2.number_input("المبلغ", min_value=0.0, step=100.0, label_visibility="collapsed")
            c3, c4 = st.columns(2)
            op_date = c3.date_input("التاريخ", date.today(), label_visibility="collapsed")
            note = c4.text_input("ملاحظات", label_visibility="collapsed")
            if st.form_submit_button("تسجيل"):
                if amount > 0:
                    if op_type == "إيداع نقدي": execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s, %s, %s)", (str(op_date), amount, note))
                    elif op_type == "سحب نقدي": execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s, %s, %s)", (str(op_date), amount, note))
                    else: 
                        cn, _ = get_company_details(note) 
                        execute_query("INSERT INTO ReturnsGrants (date, symbol, company_name, amount, note) VALUES (%s, %s, %s, %s, %s)", (str(op_date), note, cn, amount, "توزيعات"))
                    st.success("تم التسجيل")
                    st.rerun()

# ==========================================
# 7. التحليل
# ==========================================
def view_analysis(fin):
    st.header("🔬 مركز التحليل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    symbols = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c1, c2 = st.columns([1, 2])
    with c1: 
        ns = st.text_input("بحث عن سهم", label_visibility="collapsed")
    if ns and ns not in symbols: symbols.insert(0, ns)
    
    with c2:
        sym = st.selectbox("اختر الشركة", symbols, label_visibility="collapsed") if symbols else None
    
    if sym:
        n, s = get_company_details(sym)
        st.markdown(f"### {n} ({sym})")
        t1, t2, t3 = st.tabs(["📊 المؤشرات الفنية", "📑 القوائم المالية", "📈 الشارت"])
        with t1:
            d = get_fundamental_ratios(sym)
            st.metric("التقييم العام", f"{d.get('Score', 0)}/10")
            render_financial_dashboard_ui(sym)
        with t2: st.info("سيتم ربط القوائم المالية قريباً")
        with t3: view_advanced_chart(sym)

# ==========================================
# 8. المختبر (تم إضافته كما طلبت)
# ==========================================
def view_backtester_ui(fin):
    st.header("🧪 مختبر الاستراتيجيات")
    st.info("قم باختبار استراتيجيات التداول على بيانات تاريخية للتأكد من فعاليتها.")
    
    with st.form("backtest_form"):
        c1, c2, c3 = st.columns(3)
        sym = c1.text_input("رمز السهم (مثال: 1120)", value="1120")
        strat = c2.selectbox("الاستراتيجية", ["Trend Follower", "Sniper"])
        cap = c3.number_input("رأس المال الافتراضي", value=100000)
        
        if st.form_submit_button("🚀 بدء المحاكاة"):
            with st.spinner("جاري تحليل البيانات التاريخية..."):
                df = get_chart_history(sym, "2y")
                if df is not None and not df.empty:
                    res = run_backtest(df, strat, cap)
                    if res:
                        st.markdown("---")
                        c_res1, c_res2 = st.columns(2)
                        ret_color = "blue" if res['return_pct'] > 0 else "red"
                        c_res1.metric("صافي العائد %", f"{res['return_pct']:.2f}%", delta_color="normal")
                        c_res2.metric("الرصيد النهائي", f"{res['final_value']:,.2f}")
                        
                        st.markdown("#### 📈 نمو المحفظة الافتراضي")
                        st.line_chart(res['df']['Portfolio_Value'])
                        
                        st.markdown("#### 📝 سجل العمليات")
                        st.dataframe(res['df'][res['df']['Signal'] != 0][['Close', 'Signal', 'Portfolio_Value']], use_container_width=True)
                    else: st.error("فشل في تطبيق الاستراتيجية.")
                else: st.error("لا توجد بيانات لهذا السهم.")

# ==========================================
# 9. الإعدادات
# ==========================================
def view_settings():
    st.header("⚙️ الإعدادات")
    with st.expander("📥 استيراد بيانات (Excel/CSV)"):
        f = st.file_uploader("اختر الملف", accept_multiple_files=False)
        if f: st.info("خاصية الاستيراد جاهزة للتفعيل.")

# ==========================================
# الموجه الرئيسي
# ==========================================
def router():
    render_navbar_custom()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    
    if pg == 'home': view_dashboard(fin)
    elif pg == 'pulse': render_pulse_dashboard()
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'cash': view_cash_log()
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'backtest': view_backtester_ui(fin)
    elif pg == 'settings': view_settings()
    elif pg == 'add': view_add_operations()
