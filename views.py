import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

from config import DEFAULT_COLORS
from components import render_kpi, render_custom_table, render_ticker_card, safe_fmt
from analytics import calculate_portfolio_metrics, update_prices, generate_equity_curve
from database import execute_query, fetch_table, get_db, clear_all_data
from market_data import get_static_info, get_tasi_data, get_chart_history, fetch_batch_data
from charts import render_technical_chart
from backtester import run_backtest
from financial_analysis import render_financial_dashboard_ui, get_fundamental_ratios, get_thesis, save_thesis
from classical_analysis import render_classical_analysis

def render_navbar():
    c1, c2, c3, c4, c5, c6, c7, c8, c9, c10 = st.columns(10)
    buttons = [
        ('🏠 الرئيسية', 'home'), ('⚡ مضاربة', 'spec'), ('💎 استثمار', 'invest'),
        ('💓 نبض', 'pulse'), ('📜 صكوك', 'sukuk'), ('🔍 تحليل', 'analysis'),
        ('🧪 المختبر', 'backtest'), ('💰 السيولة', 'cash'), ('🔄 تحديث', 'update')
    ]
    for i, (lbl, key) in enumerate(buttons):
        with [c1,c2,c3,c4,c5,c6,c7,c8,c9][i]:
            if st.button(lbl, use_container_width=True): st.session_state.page = key; st.rerun()
    with c10:
        with st.popover("👤 القائمة"):
            st.write(f"مرحباً {st.session_state.get('username','User')}")
            if st.button("➕ إضافة", use_container_width=True): st.session_state.page='add'; st.rerun()
            if st.button("⚙️ إعدادات", use_container_width=True): st.session_state.page='settings'; st.rerun()
            if st.button("خروج", use_container_width=True): st.session_state.clear(); st.rerun()
    st.markdown("---")

def view_dashboard(fin):
    # === إصلاح مؤشر تاسي (التصميم القديم الجميل) ===
    try: tp, tc = get_tasi_data()
    except: tp, tc = 0, 0
    
    # تحديد السهم واللون بناء على التغير الحقيقي
    arrow = "🔼" if tc >= 0 else "🔽"
    
    # استخدام كلاس .tasi-box الذي أعدناه في styles.py
    st.markdown(f"""
    <div class="tasi-box">
        <div>
            <div style="font-size:1.1rem; opacity:0.9;">المؤشر العام (TASI)</div>
            <div style="font-size:2.5rem; font-weight:900;">{safe_fmt(tp)}</div>
        </div>
        <div style="background:rgba(255,255,255,0.2); padding:10px 25px; border-radius:12px; font-weight:bold; font-size:1.4rem;">
            {arrow} {tc:.2f}%
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi("الكاش المتوفر", safe_fmt(fin['cash']), "blue")
    with c2: render_kpi("رأس المال المستثمر", safe_fmt(fin['total_deposited']-fin['total_withdrawn']))
    with c3: render_kpi("القيمة السوقية", safe_fmt(fin['market_val_open']))
    tpl = fin['unrealized_pl'] + fin['realized_pl']
    with c4: render_kpi("الربح/الخسارة", safe_fmt(tpl), 'success' if tpl>=0 else 'danger')
    
    st.markdown("---")
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title="نمو المحفظة"), use_container_width=True)

def view_analysis(fin):
    st.header("🔍 مركز التحليل الشامل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c1,c2=st.columns([1,2]); ns=c1.text_input("بحث عن رمز"); sym=c2.selectbox("اختر من القائمة", [ns]+syms if ns else syms) if syms or ns else None
    
    if sym:
        n, s = get_static_info(sym)
        st.markdown(f"### {n} ({sym})")
        
        # === ترتيب التبويبات كما طلبت (مؤشرات، فني، قوائم، كلاسيكي، أطروحة) ===
        t1,t2,t3,t4,t5 = st.tabs(["📊 المؤشرات الأساسية", "📈 التحليل الفني", "📑 القوائم المالية", "🏛️ التحليل الكلاسيكي", "📝 الأطروحة"])
        
        with t1: 
            d=get_fundamental_ratios(sym)
            c_sc, c_dt = st.columns([1,3])
            col_sc = "green" if d['Score']>=7 else "red"
            c_sc.markdown(f"<div style='text-align:center; border:2px solid {col_sc}; border-radius:10px; padding:10px;'><h1 style='color:{col_sc}; margin:0;'>{d['Score']}/10</h1><b>{d['Rating']}</b></div>", unsafe_allow_html=True)
            c_dt.write(d.get('Opinions', []))
            st.markdown("---")
            k1,k2,k3,k4=st.columns(4)
            k1.metric("P/E", safe_fmt(d.get('P/E')))
            k2.metric("P/B", safe_fmt(d.get('P/B')))
            k3.metric("ROE", safe_fmt(d.get('ROE'), '%'))
            k4.metric("Fair Value", safe_fmt(d.get('Fair_Value')))
            
        with t2: render_technical_chart(sym)
        with t3: render_financial_dashboard_ui(sym)
        with t4: render_classical_analysis(sym)
        with t5:
            th = get_thesis(sym)
            with st.form("th"):
                tx = st.text_area("النص", value=th['thesis_text'] if th else "")
                tg = st.number_input("الهدف", value=th['target_price'] if th else 0.0)
                if st.form_submit_button("حفظ"): save_thesis(sym, tx, tg, "Hold"); st.success("تم")

# === باقي الصفحات (تعمل كما هي) ===
def view_portfolio(fin, key):
    ts = "مضاربة" if key=='spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    df = fin['all_trades']
    if df.empty: st.info("فارغة"); return
    sub = df[df['strategy'].astype(str).str.contains(ts, na=False)]
    op = sub[sub['status']=='Open']; cl = sub[sub['status']=='Close']
    
    t1,t2 = st.tabs(["الصفقات القائمة", "الأرشيف"])
    with t1:
        if not op.empty:
            cols = [('company_name','الشركة','text'),('symbol','الرمز','text'),('status','الحالة','badge'),('quantity','الكمية','money'),('entry_price','شراء','money'),('current_price','سوق','money'),('gain','الربح','colorful'),('gain_pct','%','percent')]
            render_custom_table(op, cols)
            with st.expander("بيع"):
                with st.form(f"s_{key}"):
                    s=st.selectbox("سهم", op['symbol'].unique()); p=st.number_input("سعر"); d=st.date_input("تاريخ")
                    if st.form_submit_button("تأكيد"): execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'",(p,str(d),s,ts)); st.rerun()
        else: st.info("لا توجد صفقات")
    with t2:
        if not cl.empty: render_custom_table(cl, [('company_name','الشركة','text'),('symbol','الرمز','text'),('gain','الربح','colorful'),('exit_date','تاريخ','date')])

def view_cash_log():
    st.header("💰 السيولة"); fin = calculate_portfolio_metrics()
    c1,c2,c3 = st.columns(3)
    with c1: render_kpi("الإيداعات", safe_fmt(fin['deposits']['amount'].sum()), "success")
    with c2: render_kpi("السحوبات", safe_fmt(fin['withdrawals']['amount'].sum()), "danger")
    with c3: render_kpi("العوائد", safe_fmt(fin['returns']['amount'].sum()), "blue")
    st.markdown("---")
    t1,t2,t3 = st.tabs(["إيداع", "سحب", "توزيع"])
    cols = [('date','تاريخ','date'),('amount','مبلغ','money'),('note','ملاحظة','text')]
    with t1: render_custom_table(fin['deposits'], cols); 
    with t2: render_custom_table(fin['withdrawals'], cols); 
    with t3: render_custom_table(fin['returns'], cols)

def render_pulse_dashboard():
    st.header("💓 نبض السوق")
    trades = fetch_table("Trades"); wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    if not syms: st.info("فارغة"); return
    data = fetch_batch_data(syms)
    cols = st.columns(4)
    for i, (s, info) in enumerate(data.items()):
        chg = ((info['price']-info['prev_close'])/info['prev_close'])*100 if info['prev_close']>0 else 0
        with cols[i%4]: render_ticker_card(s, "سهم", info['price'], chg)

def view_backtester_ui(fin):
    st.header("🧪 المختبر")
    c1,c2,c3 = st.columns(3)
    sym = c1.selectbox("السهم", ["1120.SR"] + fin['all_trades']['symbol'].unique().tolist())
    strat = c2.selectbox("خطة", ["Trend Follower", "Sniper"])
    cap = c3.number_input("مبلغ", 100000)
    if st.button("بدء"):
        res = run_backtest(get_chart_history(sym, "2y"), strat, cap)
        if res:
            st.metric("العائد", f"{res['return_pct']:.2f}%")
            st.line_chart(res['df']['Portfolio_Value'])
            st.dataframe(res['trades_log'])
        else: st.error("بيانات ناقصة")

def view_sukuk_portfolio(fin): st.header("📜 صكوك"); render_custom_table(fin['all_trades'][fin['all_trades']['asset_type']=='Sukuk'], [('symbol','رمز','text'),('quantity','كمية','money')])
def view_add_trade():
    st.header("➕ إضافة"); 
    with st.form("add"):
        c1,c2=st.columns(2); s=c1.text_input("رمز"); t=c2.selectbox("نوع", ["استثمار","مضاربة","صكوك"])
        c3,c4,c5=st.columns(3); q=c3.number_input("كمية"); p=c4.number_input("سعر"); d=c5.date_input("تاريخ", date.today())
        if st.form_submit_button("حفظ"):
            at = "Sukuk" if t=="صكوك" else "Stock"
            execute_query("INSERT INTO Trades (symbol, asset_type, date, quantity, entry_price, strategy, status) VALUES (%s,%s,%s,%s,%s,%s,'Open')", (s,at,str(d),q,p,t))
            st.success("تم"); st.cache_data.clear()
def view_tools(): st.header("🛠️ أدوات"); st.info("الزكاة")
def view_settings(): st.header("⚙️ إعدادات"); st.info("الاستيراد")

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
    elif pg == 'add': view_add_trade()
    elif pg == 'update':
        with st.spinner("تحديث..."): update_prices()
        st.session_state.page='home'; st.rerun()
