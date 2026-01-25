import streamlit as st
import pandas as pd
from config import DEFAULT_COLORS
from components import render_navbar, render_kpi, render_table, render_ticker_card, safe_fmt
from analytics import calculate_portfolio_metrics, generate_equity_curve, run_backtest
from database import execute_query, fetch_table
from market_data import get_static_info, get_tasi_data, get_chart_history
from charts import view_advanced_chart

def view_dashboard(fin):
    try: t_price, t_chg = get_tasi_data()
    except: t_price, t_chg = 0, 0
    C = DEFAULT_COLORS
    st.markdown(f'<div class="tasi-box"><div><div style="font-size:1.1rem; opacity:0.8;">تاسي</div><div style="font-size:2.2rem; font-weight:900;">{safe_fmt(t_price)}</div></div><div style="background:rgba(255,255,255,0.2); padding:10px 20px; border-radius:12px; font-weight:bold;">{t_chg:+.2f}%</div></div>', unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    with c1: render_kpi("الكاش", safe_fmt(fin['cash']), "blue")
    with c2: render_kpi("صافي الاستثمار", safe_fmt(fin['total_deposited'] - fin['total_withdrawn']))
    with c3: render_kpi("قيمة المحفظة", safe_fmt(fin['market_val_open']))
    tpl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("الأرباح الكلية", safe_fmt(tpl), tpl)

def view_portfolio(fin, key):
    ts = "مضاربة" if key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    df = fin['all_trades']
    if df.empty: st.info("لا توجد بيانات"); return
    
    sub_df = df[df['strategy'].astype(str).str.contains(ts, na=False)].copy()
    if sub_df.empty: st.info("المحفظة فارغة"); return

    open_df = sub_df[sub_df['status']=='Open']
    cols = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'الشراء'), ('current_price', 'الحالي'), ('gain', 'الربح'), ('gain_pct', '%')]
    
    t1, t2 = st.tabs(["الأسهم الحالية", "الأرشيف"])
    with t1: render_table(open_df, cols)
    with t2: render_table(sub_df[sub_df['status']=='Close'], cols)

def view_add_operations():
    st.header("➕ مركز العمليات")
    tab1, tab2 = st.tabs(["📈 صفقة أسهم", "💰 حركة مالية"])
    with tab1:
        with st.form("f1"):
            c1,c2 = st.columns(2)
            s = c1.text_input("الرمز (مثال: 1120)")
            strt = c2.selectbox("المحفظة", ["استثمار", "مضاربة", "صكوك"])
            c3,c4 = st.columns(2)
            q = c3.number_input("الكمية", min_value=1.0)
            p = c4.number_input("السعر", min_value=0.01)
            if st.form_submit_button("حفظ الصفقة"):
                name, sector = get_static_info(s)
                execute_query("INSERT INTO Trades (symbol, company_name, sector, quantity, entry_price, strategy) VALUES (%s,%s,%s,%s,%s,%s)", (s, name, sector, q, p, strt))
                st.success("تم الحفظ"); st.rerun()
    with tab2:
        with st.form("f2"):
            c1,c2 = st.columns(2)
            tp = c1.selectbox("النوع", ["إيداع", "سحب", "عائد/توزيعات"])
            amt = c2.number_input("المبلغ")
            note = st.text_input("ملاحظة / الرمز")
            if st.form_submit_button("حفظ الحركة"):
                tbl = "Deposits" if "إيداع" in tp else ("Withdrawals" if "سحب" in tp else "ReturnsGrants")
                execute_query(f"INSERT INTO {tbl} (date, amount, note) VALUES (CURRENT_DATE, %s, %s)", (amt, note))
                st.success("تم الحفظ"); st.rerun()

def router():
    render_navbar()
    fin = calculate_portfolio_metrics()
    pg = st.session_state.get('page', 'home')
    if pg == 'home': view_dashboard(fin)
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'add': view_add_operations()
    elif pg == 'analysis': view_advanced_chart(fin)
    elif pg == 'cash': 
        st.header("💵 سجل السيولة")
        render_table(fin['deposits'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظة')])
    elif pg == 'settings': st.header("⚙️ الإعدادات"); st.info("قسم الاستيراد قيد التطوير")
