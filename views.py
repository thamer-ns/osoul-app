import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from config import DEFAULT_COLORS
from components import render_navbar, render_kpi, render_table, render_ticker_card, safe_fmt
from analytics import calculate_portfolio_metrics, update_prices, generate_equity_curve, calculate_historical_drawdown
from database import execute_query, fetch_table, clear_all_data
from market_data import get_static_info, get_tasi_data, get_chart_history
from data_source import get_company_details
from charts import render_technical_chart
from backtester import run_backtest # استيراد المختبر

# استيرادات التحليل المالي والكلاسيكي
try: from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui
except: get_fundamental_ratios = lambda s: {'Score':0}; render_financial_dashboard_ui = lambda s: None
try: from classical_analysis import render_classical_analysis
except: render_classical_analysis = lambda s: None

def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    C = DEFAULT_COLORS
    arrow, cl = ("🔼", C['success']) if t_change >= 0 else ("🔽", C['danger'])
    
    st.markdown(f"""
    <div style="background:{C['card_bg']}; padding:20px; border-radius:10px; display:flex; justify-content:space-between; align-items:center; border:1px solid {C['border']};">
        <div><div style="color:{C['sub_text']};">المؤشر العام (TASI)</div><div style="font-size:2rem; font-weight:900;">{safe_fmt(t_price)}</div></div>
        <div style="background:{cl}15; color:{cl}; padding:8px 20px; border-radius:6px; font-weight:bold; direction:ltr;">{arrow} {t_change:.2f}%</div>
    </div>""", unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    with c1: render_kpi("الكاش المتوفر", safe_fmt(fin['cash']), "blue")
    with c2: render_kpi("صافي الاستثمار", safe_fmt(fin['total_deposited'] - fin['total_withdrawn']))
    with c3: render_kpi("القيمة السوقية", safe_fmt(fin['market_val_open']))
    tpl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("الأرباح الكلية", safe_fmt(tpl), tpl)
    
    st.markdown("---")
    st.subheader("📈 نمو المحفظة")
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested'), use_container_width=True)

def view_portfolio(fin, page_key):
    ts = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    all_d = fin['all_trades']
    
    df = pd.DataFrame()
    if not all_d.empty:
        df = all_d[all_d['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    if df.empty: st.info("المحفظة فارغة"); return

    COLS = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'شراء'), ('current_price', 'سوق'), ('gain', 'الربح'), ('gain_pct', '%')]
    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()

    t1, t2 = st.tabs(["الأسهم الحالية", "الأرشيف"])
    with t1:
        if not open_df.empty:
            render_table(open_df, COLS)
            with st.expander("🔻 بيع سهم"):
                with st.form("sell"):
                    c1,c2 = st.columns(2)
                    s = c1.selectbox("السهم", open_df['symbol'].unique())
                    p = c2.number_input("السعر")
                    d = st.date_input("التاريخ", date.today())
                    if st.form_submit_button("بيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, ts))
                        st.success("تم"); st.cache_data.clear(); st.rerun()
    with t2:
        render_table(closed_df, COLS)

def view_backtester_ui(fin):
    st.header("🧪 المختبر")
    c1, c2, c3 = st.columns(3)
    
    # === هنا كان الخطأ، تم الإصلاح ===
    # التحقق مما إذا كانت all_trades فارغة لتجنب KeyError
    trades_df = fin.get('all_trades', pd.DataFrame())
    if not trades_df.empty and 'symbol' in trades_df.columns:
        available_syms = list(set(trades_df['symbol'].unique().tolist() + ["1120"]))
    else:
        available_syms = ["1120", "2222"] # قائمة افتراضية
        
    with c1: st.markdown("**السهم:**"); sym = st.selectbox("bs", available_syms, label_visibility="collapsed")
    with c2: st.markdown("**الاستراتيجية:**"); strat = st.selectbox("bst", ["Trend Follower (جون ميرفي)", "Sniper (هجين)"], label_visibility="collapsed")
    with c3: st.markdown("**رأس المال:**"); cap = st.number_input("bc", 100000, label_visibility="collapsed")
    
    if st.button("🚀 تشغيل"):
        df = get_chart_history(sym, "2y")
        if df is not None:
            res = run_backtest(df, strat, cap)
            if res:
                c1,c2 = st.columns(2)
                c1.metric("العائد", f"{res['return_pct']:.2f}%")
                c2.metric("الرصيد", f"{res['final_value']:,.2f}")
                st.line_chart(res['df']['Portfolio_Value'])
                st.dataframe(res['trades_log'])

def view_add_trade():
    st.header("➕ إضافة صفقة")
    with st.form("add"):
        c1, c2 = st.columns(2)
        s = c1.text_input("الرمز")
        t = c2.selectbox("المحفظة", ["استثمار", "مضاربة", "صكوك"])
        c3, c4 = st.columns(2)
        q = c3.number_input("الكمية", 1.0)
        p = c4.number_input("السعر")
        d = st.date_input("التاريخ", date.today())
        if st.form_submit_button("حفظ"):
            n, sec = get_static_info(s)
            at = "Sukuk" if t=="صكوك" else "Stock"
            execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Open',%s)", (s, n, sec, at, str(d), q, p, t, p))
            st.success("تم"); st.cache_data.clear()

def view_cash_log():
    st.header("💵 السيولة"); fin = calculate_portfolio_metrics()
    t1,t2,t3 = st.tabs(["إيداع", "سحب", "توزيع"])
    with t1: 
        with st.form("d"):
            a=st.number_input("مبلغ"); d=st.date_input("تاريخ"); n=st.text_input("ملاحظة")
            if st.form_submit_button("حفظ"): execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s,%s,%s)", (str(d),a,n)); st.rerun()
        render_table(fin['deposits'], [('date','تاريخ'),('amount','مبلغ')])
    with t2:
        with st.form("w"):
            a=st.number_input("مبلغ"); d=st.date_input("تاريخ"); n=st.text_input("ملاحظة")
            if st.form_submit_button("حفظ"): execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s,%s,%s)", (str(d),a,n)); st.rerun()
        render_table(fin['withdrawals'], [('date','تاريخ'),('amount','مبلغ')])
    with t3: render_table(fin['returns'], [('date','تاريخ'),('symbol','رمز'),('amount','مبلغ')])

def view_analysis(fin):
    st.header("🔬 التحليل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    c1,c2=st.columns([1,2]); ns=c1.text_input("بحث"); sym=c2.selectbox("اختر", [ns]+syms if ns else syms) if syms or ns else None
    if sym:
        n, s = get_static_info(sym); st.markdown(f"### {n} ({sym})")
        t1,t2,t3,t4,t5 = st.tabs(["مؤشرات", "قوائم", "أطروحة", "فني", "كلاسيكي"])
        with t1: d=get_fundamental_ratios(sym); st.metric("التقييم", f"{d['Score']}/10")
        with t2: render_financial_dashboard_ui(sym)
        with t3: st.info("الأطروحة")
        with t4: render_technical_chart(sym)
        with t5: render_classical_analysis(sym)

def view_sukuk_portfolio(fin):
    st.header("📜 الصكوك")
    df = fin['all_trades']
    if 'asset_type' in df.columns:
        sk = df[df['asset_type']=='Sukuk']
        if not sk.empty: render_table(sk, [('company_name','اسم'),('symbol','رمز'),('quantity','كمية'),('entry_price','سعر')])
        else: st.warning("لا يوجد")

def view_tools(): st.header("🛠️ أدوات"); st.info(f"الزكاة: {calculate_portfolio_metrics()['market_val_open']*0.025775:,.2f}")
def view_settings(): st.header("⚙️ إعدادات"); st.info("الاستيراد والحذف")

def router():
    render_navbar()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    if pg == 'home': view_dashboard(fin)
    elif pg == 'pulse': st.info("نبض السوق")
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'sukuk': view_sukuk_portfolio(fin)
    elif pg == 'cash': view_cash_log()
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'backtest': view_backtester_ui(fin)
    elif pg == 'tools': view_tools()
    elif pg == 'settings': view_settings()
    elif pg == 'add': view_add_trade()
    elif pg == 'update':
        with st.spinner("تحديث..."): update_prices()
        st.session_state.page = 'home'; st.rerun()
