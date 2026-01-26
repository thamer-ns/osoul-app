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
try: from classical_analysis import render_classical_analysis
except: render_classical_analysis = lambda x: st.info("التحليل الكلاسيكي")
try: from financial_analysis import render_financial_dashboard_ui, get_fundamental_ratios
except: 
    render_financial_dashboard_ui = lambda x: st.info("القوائم المالية")
    get_fundamental_ratios = lambda x: {'Score': 0}

def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    C = DEFAULT_COLORS
    arrow, cl = ("🔼", C['success']) if t_change >= 0 else ("🔽", C['danger'])
    st.markdown(f"""<div class="tasi-box"><div><div style="font-size:1.1rem; opacity:0.9;">تاسي</div><div style="font-size:2.5rem; font-weight:900;">{safe_fmt(t_price)}</div></div><div style="background:rgba(255,255,255,0.2); padding:10px 20px; border-radius:12px; font-weight:bold;">{arrow} {t_change:.2f}%</div></div>""", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    with c1: render_kpi("الكاش", safe_fmt(fin['cash']), "blue")
    with c2: render_kpi("صافي الاستثمار", safe_fmt(fin['total_deposited'] - fin['total_withdrawn']))
    with c3: render_kpi("قيمة المحفظة", safe_fmt(fin['market_val_open']))
    tpl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("الأرباح", safe_fmt(tpl), tpl)
    st.markdown("---")
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title=""), use_container_width=True)

def view_portfolio(fin, key):
    ts = "مضاربة" if key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    df = fin['all_trades']
    if df.empty: st.info("لا توجد بيانات"); return
    
    sub_df = df[df['strategy'].astype(str).str.contains(ts, na=False)].copy()
    if sub_df.empty: st.info("المحفظة فارغة"); return

    COLS = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'الشراء'), ('current_price', 'الحالي'), ('market_value', 'القيمة'), ('gain', 'الربح')]
    
    t1, t2 = st.tabs(["الأسهم الحالية", "الأرشيف"])
    with t1:
        render_table(sub_df[sub_df['status']=='Open'], COLS)
    with t2:
        render_table(sub_df[sub_df['status']=='Close'], COLS)

def view_analysis(fin):
    st.header("🔬 مركز التحليل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c1, c2 = st.columns([1, 2])
    with c1: 
        st.markdown("**بحث:**"); ns = st.text_input("s_s", label_visibility="collapsed")
    if ns and ns not in syms: syms.insert(0, ns)
    with c2:
        st.markdown("**اختر الشركة:**"); sym = st.selectbox("s_sl", syms, label_visibility="collapsed") if syms else None
    
    if sym:
        n, s = get_static_info(sym)
        st.markdown(f"### {n} ({sym})")
        t1, t2, t3, t4, t5 = st.tabs(["📊 المؤشرات", "📑 القوائم", "📝 الأطروحة", "📈 الشارت", "🏛️ كلاسيكي"])
        with t1:
            d = get_fundamental_ratios(sym)
            st.metric("التقييم", f"{d.get('Score', 0)}/10")
        with t2: render_financial_dashboard_ui(sym)
        with t3: st.info("الأطروحة الاستثمارية")
        with t4: view_advanced_chart(sym)
        with t5: render_classical_analysis(sym)

def view_backtester_ui(fin):
    st.header("🧪 المختبر")
    c1, c2, c3 = st.columns(3)
    with c1: 
        syms = list(set(fin['all_trades']['symbol'].unique().tolist() + ["1120.SR"]))
        sym = st.selectbox("bs", syms, label_visibility="collapsed")
    with c2: strat = st.selectbox("bst", ["Trend Follower", "Sniper"], label_visibility="collapsed")
    with c3: cap = st.number_input("bc", 100000, label_visibility="collapsed")
    
    if st.button("🚀 تشغيل"):
        df = get_chart_history(sym, "2y")
        if df is not None:
            res = run_backtest(df, strat, cap)
            if res:
                c1, c2 = st.columns(2)
                c1.metric("العائد", f"{res['return_pct']:.2f}%")
                c2.metric("الرصيد", f"{res['final_value']:,.2f}")
                st.line_chart(res['df']['Portfolio_Value'])

def view_sukuk_portfolio(fin):
    st.header("📜 الصكوك")
    df = fin['all_trades']
    if 'asset_type' not in df.columns: st.info("لا توجد بيانات"); return
    sk = df[df['asset_type']=='Sukuk'].copy()
    if not sk.empty:
        render_table(sk, [('company_name', 'الاسم'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('gain', 'الربح')])
    else: st.info("لا توجد صكوك")

def view_cash_log():
    st.header("💵 سجل السيولة")
    fin = calculate_portfolio_metrics()
    t1, t2 = st.tabs(["إيداعات", "سحوبات"])
    with t1: render_table(fin['deposits'], [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظة')])
    with t2: render_table(fin['withdrawals'], [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظة')])

def view_add_operations():
    st.header("➕ إضافة")
    with st.form("add"):
        c1, c2 = st.columns(2)
        ty = c1.selectbox("النوع", ["صفقة أسهم", "إيداع نقدي", "سحب نقدي"], label_visibility="collapsed")
        val = c2.number_input("القيمة/السعر", 0.0, label_visibility="collapsed")
        # ... باقي الحقول ...
        if st.form_submit_button("حفظ"):
            st.success("تم")

def view_settings(): st.header("⚙️ الإعدادات"); st.info("الاستيراد")
def view_tools(): st.header("🛠️ الأدوات"); st.info("الزكاة")

def router():
    render_navbar()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    if pg == 'home': view_dashboard(fin)
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'backtest': view_backtester_ui(fin)
    elif pg == 'sukuk': view_sukuk_portfolio(fin)
    elif pg == 'cash': view_cash_log()
    elif pg == 'add': view_add_operations()
    elif pg == 'settings': view_settings()
    elif pg == 'tools': view_tools()
    elif pg == 'update': 
        with st.spinner("تحديث..."): update_prices()
        st.session_state.page='home'; st.rerun()
