import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from components import render_navbar, render_kpi, render_table
from analytics import (calculate_portfolio_metrics, update_prices, create_smart_backup, 
                       get_comprehensive_performance, get_dividends_calendar, 
                       generate_equity_curve, calculate_historical_drawdown)
from charts import render_technical_chart
from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui
from market_data import get_static_info, get_tasi_data
from database import execute_query, fetch_table
from config import APP_NAME
from data_source import TADAWUL_DB

def safe_fmt(val, suffix=""):
    try:
        if val is None: return "غير متاح"
        num = float(val)
        return f"{num:.2f}{suffix}"
    except: return "غير متاح"

def apply_sorting(df, cols_def, key):
    if df.empty: return df
    with st.expander("🔍 فرز"):
        l2c = {l: c for c, l in cols_def}
        sel = st.selectbox("حسب:", list(l2c.keys()), key=f"s_{key}")
        asc = st.radio("الترتيب:", ["تنازلي", "تصاعدي"], horizontal=True, key=f"o_{key}") == "تصاعدي"
    return df.sort_values(by=l2c[sel], ascending=asc)

def view_dashboard(fin):
    try: t_p, t_c = get_tasi_data()
    except: t_p, t_c = 0, 0
    
    if 'custom_colors' not in st.session_state:
        from config import DEFAULT_COLORS
        st.session_state.custom_colors = DEFAULT_COLORS.copy()
    
    color = "#10B981" if t_c >= 0 else "#EF4444"
    
    # عرض المؤشر العام
    st.markdown(f"<div style='background:white;padding:15px;border-radius:10px;box-shadow:0 2px 5px rgba(0,0,0,0.05);display:flex;justify-content:space-between;align-items:center;'><div><div style='color:gray'>المؤشر العام</div><div style='font-size:1.8rem;font-weight:bold'>{t_p:,.2f}</div></div><div style='color:{color};font-weight:bold;direction:ltr'>{t_c:+.2f}%</div></div>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # عرض الملخص المالي
    c1, c2, c3 = st.columns(3)
    c1.metric("القيمة السوقية", f"{fin['market_val_open']:,.2f}")
    c2.metric("الكاش", f"{fin['cash']:,.2f}")
    c3.metric("الربح الكلي", f"{(fin['unrealized_pl']+fin['realized_pl']+fin['total_returns']):,.2f}")
    
    # --- إصلاح الخطأ هنا ---
    # نقوم بتوليد البيانات أولاً
    curve_data = generate_equity_curve(fin['all_trades'])
    
    # نفحص هل البيانات موجودة وفيها أعمدة؟
    if not curve_data.empty and 'date' in curve_data.columns:
        fig = px.line(curve_data, x='date', y='cumulative_invested', title="نمو المحفظة")
        st.plotly_chart(fig, use_container_width=True)
    else:
        # إذا كانت فارغة نعرض رسالة بدلاً من الانهيار
        st.info("📉 لا توجد بيانات كافية لرسم منحنى النمو. (قم بإضافة صفقات أولاً)")

def view_portfolio(fin, key):
    strat = "مضاربة" if key == 'spec' else "استثمار"
    st.header(f"محفظة {strat}")
    df = fin['all_trades']
    if df.empty: st.info("لا توجد بيانات"); return
    df = df[(df['strategy']==strat) & (df['asset_type']!='Sukuk')]
    
    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()
    
    t1, t2 = st.tabs(["المفتوحة", "المغلقة"])
    with t1:
        if not open_df.empty:
            cols = [('symbol','الرمز'), ('company_name','الشركة'), ('quantity','الكمية'), ('entry_price','التكلفة'), ('current_price','السعر'), ('gain','الربح'), ('gain_pct','%')]
            render_table(apply_sorting(open_df, cols, key), cols)
            with st.expander("تسجيل بيع"):
                with st.form(f"sell_{key}"):
                    sym = st.selectbox("السهم", open_df['symbol'].unique())
                    pr = st.number_input("سعر البيع")
                    dt = st.date_input("التاريخ", date.today())
                    if st.form_submit_button("بيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=?, exit_date=? WHERE symbol=? AND status='Open'", (pr, str(dt), sym))
                        st.success("تم البيع"); st.cache_data.clear(); st.rerun()
        else: st.info("المحفظة فارغة")
    with t2:
        if not closed_df.empty:
            cols = [('symbol','الرمز'), ('gain','الربح'), ('exit_date','التاريخ')]
            render_table(closed_df, cols)

def view_analysis(fin):
    st.header("مركز التحليل")
    from classical_analysis import render_classical_analysis
    syms = list(set(fin['all_trades']['symbol'].tolist() + fetch_table("Watchlist")['symbol'].tolist()))
    if not syms: st.warning("أضف أسهماً للمحفظة أولاً"); return
    
    c1, c2, c3 = st.columns([1,1,2])
    sym = c1.selectbox("السهم", syms)
    per = c2.selectbox("المدى", ["1y","2y","5y"])
    
    if sym:
        t1, t2, t3, t4 = st.tabs(["المؤشرات", "القوائم المالية", "الفني", "الكلاسيكي"])
        with t1:
            d = get_fundamental_ratios(sym)
            if d['Current_Price']:
                c_sc, c_op = st.columns([1,2])
                c_sc.markdown(f"<h1 style='text-align:center;color:#0e6ba8'>{d['Score']}/10</h1>", unsafe_allow_html=True)
                for op in d['Opinions']: c_op.write(f"- {op}")
                st.markdown("---")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("P/E", safe_fmt(d['P/E']))
                k2.metric("P/B", safe_fmt(d['P/B']))
                k3.metric("العائد", safe_fmt(d['ROE'], "%"))
                k4.metric("العادلة", safe_fmt(d['Fair_Value']))
        with t2: render_financial_dashboard_ui(sym)
        with t3: render_technical_chart(sym, per, "1d")
        with t4: render_classical_analysis(sym)

def view_add_trade():
    st.header("إضافة عملية")
    with st.form("add"):
        c1,c2 = st.columns(2)
        sym = c1.text_input("الرمز (مثال 1120)")
        qty = c2.number_input("الكمية", 1.0)
        pr = st.number_input("السعر", 0.0)
        strat = st.selectbox("المحفظة", ["استثمار", "مضاربة", "صكوك"])
        type_ = "Sukuk" if strat == "صكوك" else "Stock"
        dt = st.date_input("التاريخ", date.today())
        if st.form_submit_button("حفظ"):
            n, s = get_static_info(sym)
            execute_query("INSERT INTO Trades (symbol,company_name,sector,asset_type,date,quantity,entry_price,strategy,status,current_price) VALUES (?,?,?,?,?,?,?,?,'Open',?)", (sym,n,s,type_,str(dt),qty,pr,strat,pr))
            st.success("تم"); st.cache_data.clear()

def view_settings():
    st.header("الإعدادات")
    if st.button("نسخ احتياطي"): create_smart_backup(); st.success("تم")

def router():
    render_navbar()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    if pg == 'home': view_dashboard(fin)
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'add': view_add_trade()
    elif pg == 'settings': view_settings()
