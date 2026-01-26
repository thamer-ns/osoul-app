import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time

from config import DEFAULT_COLORS
from components import render_navbar, render_kpi, render_table, render_ticker_card, safe_fmt
from analytics import (calculate_portfolio_metrics, update_prices, generate_equity_curve, run_backtest)
from database import execute_query, fetch_table
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
    st.markdown(f"""<div class="tasi-box"><div><div style="font-size:1.1rem; opacity:0.8;">تاسي</div><div style="font-size:2.2rem; font-weight:900;">{safe_fmt(t_price)}</div></div><div style="background:rgba(255,255,255,0.2); padding:10px 20px; border-radius:12px; font-weight:bold;">{arrow} {t_change:.2f}%</div></div>""", unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    with c1: render_kpi("الكاش المتوفر", safe_fmt(fin['cash']), "blue")
    with c2: render_kpi("صافي الاستثمار", safe_fmt(fin['total_deposited'] - fin['total_withdrawn']))
    with c3: render_kpi("القيمة السوقية", safe_fmt(fin['market_val_open']))
    tpl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("الأرباح الكلية", safe_fmt(tpl), tpl)
    
    st.markdown("---")
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title="نمو المحفظة"), use_container_width=True)

def render_pulse_dashboard():
    st.header("💓 نبض السوق")
    trades = fetch_table("Trades"); wl = fetch_table("Watchlist")
    syms = list(set(trades[trades['status']=='Open']['symbol'].tolist() + wl['symbol'].tolist())) if not trades.empty else []
    if not syms: st.info("القائمة فارغة"); return
    cols = st.columns(4)
    for i, s in enumerate(syms):
        n, _ = get_company_details(s)
        row = trades[trades['symbol']==s]
        p = row.iloc[0]['current_price'] if not row.empty else 0.0
        with cols[i%4]: render_ticker_card(s, n, p, 0.0)

def view_portfolio(fin, page_key):
    ts = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    all_d = fin['all_trades']
    df = pd.DataFrame()
    if not all_d.empty: df = all_d[all_d['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    if df.empty: st.info("المحفظة فارغة"); return

    # الأعمدة الكاملة كما طلبت
    COLS = [
        ('company_name', 'الشركة'), ('sector', 'القطاع'), ('status', 'الحالة'),
        ('symbol', 'الرمز'), ('date', 'تاريخ الشراء'), ('exit_date', 'تاريخ البيع'),
        ('quantity', 'الكمية'), ('entry_price', 'سعر الشراء'), ('total_cost', 'التكلفة'),
        ('year_high', 'اعلى سنوي'), ('current_price', 'السعر الحالي'), ('year_low', 'ادنى سنوي'),
        ('market_value', 'سعر السوق'), ('gain', 'الربح/الخسارة'), ('gain_pct', 'النسبة %'),
        ('weight', 'الوزن'), ('daily_change', 'تغير يومي'), ('prev_close', 'اغلاق سابق')
    ]

    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()

    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi("القيمة السوقية", safe_fmt(open_df['market_value'].sum() if not open_df.empty else 0), "blue")
    with c2: render_kpi("التكلفة", safe_fmt(open_df['total_cost'].sum() if not open_df.empty else 0))
    with c3: render_kpi("الربح العائم", safe_fmt(open_df['gain'].sum() if not open_df.empty else 0))
    with c4: render_kpi("الربح المحقق", safe_fmt(closed_df['gain'].sum() if not closed_df.empty else 0))
    st.markdown("---")

    t1, t2 = st.tabs(["الأسهم الحالية", "الأرشيف"])
    with t1:
        if not open_df.empty:
            render_table(open_df.sort_values('date', ascending=False), COLS)
            with st.expander("🔻 بيع سهم"):
                with st.form("sell"):
                    c1,c2 = st.columns(2)
                    st.markdown("**السهم:**"); s = c1.selectbox("s", open_df['symbol'].unique(), label_visibility="collapsed")
                    st.markdown("**سعر البيع:**"); p = c2.number_input("p", min_value=0.0, label_visibility="collapsed")
                    st.markdown("**التاريخ:**"); d = st.date_input("d", date.today(), label_visibility="collapsed")
                    if st.form_submit_button("تأكيد"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, ts))
                        st.success("تم"); time.sleep(0.5); st.rerun()
        else: st.info("لا توجد أسهم حالية")
    
    with t2:
        if not closed_df.empty:
            closed_df['net_sales'] = closed_df['quantity'] * closed_df['exit_price']
            closed_df['realized_gain'] = closed_df['net_sales'] - closed_df['total_cost']
            render_table(closed_df.sort_values('exit_date', ascending=False), COLS)
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

def view_sukuk_portfolio(fin):
    st.header("📜 الصكوك")
    df = fin['all_trades']
    if 'asset_type' not in df.columns: st.info("لا توجد بيانات"); return
    
    sk = df[df['asset_type']=='Sukuk'].copy()
    if not sk.empty:
        render_table(sk, [('company_name', 'الاسم'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'شراء'), ('gain', 'الربح')])
    else: st.info("لا توجد صكوك")

def view_add_operations():
    st.header("➕ مركز العمليات")
    tab1, tab2 = st.tabs(["📈 تسجيل صفقة", "💰 حركة مالية"])
    with tab1:
        with st.form("tr"):
            c1, c2 = st.columns(2)
            st.markdown("**الرمز:**"); s = c1.text_input("s", label_visibility="collapsed")
            st.markdown("**المحفظة:**"); st_t = c2.selectbox("st", ["استثمار", "مضاربة", "صكوك"], label_visibility="collapsed")
            c3, c4 = st.columns(2)
            st.markdown("**الكمية:**"); q = c3.number_input("q", 1.0, label_visibility="collapsed")
            st.markdown("**السعر:**"); p = c4.number_input("p", 0.0, label_visibility="collapsed")
            st.markdown("**التاريخ:**"); d = st.date_input("d", date.today(), label_visibility="collapsed")
            if st.form_submit_button("حفظ"):
                n, sec = get_company_details(s)
                at = "Sukuk" if st_t == "صكوك" else "Stock"
                execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Open',%s)", (s, n, sec, at, str(d), q, p, st_t, p))
                st.success("تم"); st.cache_data.clear()
    with tab2:
        with st.form("ca"):
            c1, c2 = st.columns(2)
            st.markdown("**النوع:**"); ty = c1.selectbox("t", ["إيداع نقدي", "سحب نقدي", "توزيعات"], label_visibility="collapsed")
            st.markdown("**المبلغ:**"); am = c2.number_input("a", 0.0, label_visibility="collapsed")
            st.markdown("**التاريخ:**"); da = st.date_input("da", date.today(), label_visibility="collapsed")
            st.markdown("**ملاحظة:**"); no = st.text_input("no", label_visibility="collapsed")
            if st.form_submit_button("حفظ"):
                if "إيداع" in ty: execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s,%s,%s)", (str(da), am, no))
                elif "سحب" in ty: execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s,%s,%s)", (str(da), am, no))
                else: execute_query("INSERT INTO ReturnsGrants (date, symbol, amount, note) VALUES (%s,%s,%s,%s)", (str(da), no, am, "توزيعات"))
                st.success("تم"); st.rerun()

def view_analysis(fin):
    view_advanced_chart(fin)

def view_backtester_ui(fin):
    st.header("🧪 المختبر")
    st.info("قيد التطوير")

def view_tools():
    st.header("🛠️ الأدوات")
    fin = calculate_portfolio_metrics()
    st.info(f"الزكاة: {safe_fmt(fin['market_val_open']*0.025775)}")

def view_settings():
    st.header("⚙️ الإعدادات")
    with st.expander("📥 استيراد"):
        f = st.file_uploader("ملف", accept_multiple_files=False)
        if f: st.info("جاهز")

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
