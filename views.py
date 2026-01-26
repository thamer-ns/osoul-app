import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

from config import DEFAULT_COLORS
from components import render_kpi, render_custom_table, render_ticker_card, safe_fmt
from analytics import calculate_portfolio_metrics, update_prices, generate_equity_curve
from database import execute_query, fetch_table
from market_data import get_static_info, get_tasi_data, get_chart_history, fetch_batch_data
from charts import render_technical_chart
from backtester import run_backtest
from financial_analysis import render_financial_dashboard_ui, get_fundamental_ratios, get_thesis, save_thesis
from classical_analysis import render_classical_analysis

# --- القائمة العلوية (المستعادة 100%) ---
def render_navbar():
    c1, c2, c3, c4, c5, c6, c7, c8, c9, c10 = st.columns(10)
    
    # الأزرار الرئيسية
    with c1: 
        if st.button("🏠 الرئيسية", use_container_width=True): st.session_state.page = 'home'; st.rerun()
    with c2: 
        if st.button("⚡ مضاربة", use_container_width=True): st.session_state.page = 'spec'; st.rerun()
    with c3: 
        if st.button("💎 استثمار", use_container_width=True): st.session_state.page = 'invest'; st.rerun()
    with c4: 
        if st.button("💓 نبض", use_container_width=True): st.session_state.page = 'pulse'; st.rerun()
    with c5: 
        if st.button("📜 صكوك", use_container_width=True): st.session_state.page = 'sukuk'; st.rerun()
    with c6: 
        if st.button("🔍 تحليل", use_container_width=True): st.session_state.page = 'analysis'; st.rerun()
    with c7: 
        if st.button("🧪 المختبر", use_container_width=True): st.session_state.page = 'backtest'; st.rerun()
    with c8: 
        if st.button("📂 سجلات", use_container_width=True): st.session_state.page = 'cash'; st.rerun()
    with c9: 
        if st.button("🔄 تحديث", use_container_width=True): st.session_state.page = 'update'; st.rerun()
    
    # قائمة المستخدم (Pop-over) كما طلبت
    with c10:
        with st.popover("👤 القائمة"):
            st.write(f"مرحباً، {st.session_state.get('username', 'زائر')}")
            if st.button("➕ إضافة صفقة", use_container_width=True): st.session_state.page = 'add'; st.rerun()
            if st.button("🛠️ أدوات", use_container_width=True): st.session_state.page = 'tools'; st.rerun()
            if st.button("⚙️ الإعدادات", use_container_width=True): st.session_state.page = 'settings'; st.rerun()
            st.markdown("---")
            if st.button("🚪 خروج", use_container_width=True): 
                try: from security import logout; logout()
                except: st.session_state.clear(); st.rerun()
    st.markdown("---")

# --- 1. الرئيسية ---
def view_dashboard(fin):
    try: tp, tc = get_tasi_data()
    except: tp, tc = 0, 0
    ar = "🔼" if tc >= 0 else "🔽"
    
    # صندوق تاسي الأزرق
    st.markdown(f"""
    <div class="tasi-box">
        <div>
            <div style="opacity:0.9;">المؤشر العام (TASI)</div>
            <div style="font-size:2.2rem; font-weight:900;">{safe_fmt(tp)}</div>
        </div>
        <div style="background:rgba(255,255,255,0.2); padding:5px 15px; border-radius:10px; font-weight:bold; direction:ltr;">
            {ar} {tc:.2f}%
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
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title="النمو"), use_container_width=True)

# --- 2. السجلات المالية (السيولة) - تم إرجاع الإضافات ---
def view_cash_log():
    st.header("💰 السجلات المالية")
    fin = calculate_portfolio_metrics()
    
    # الأيقونات العلوية
    c1, c2, c3 = st.columns(3)
    with c1: render_kpi("إجمالي الإيداعات", safe_fmt(fin['deposits']['amount'].sum()), "success")
    with c2: render_kpi("إجمالي السحوبات", safe_fmt(fin['withdrawals']['amount'].sum()), "danger")
    with c3: render_kpi("إجمالي العوائد", safe_fmt(fin['returns']['amount'].sum()), "blue")
    
    st.markdown("---")
    t1, t2, t3 = st.tabs(["📥 الإيداعات", "📤 السحوبات", "🎁 العوائد"])
    
    # الأعمدة
    cols = [('date','التاريخ','date'), ('amount','المبلغ','money'), ('note','ملاحظات','text')]
    
    with t1:
        # هنا أعدت لك زر الإضافة كما كان
        with st.expander("➕ تسجيل إيداع جديد"):
            with st.form("add_dep"):
                a = st.number_input("المبلغ", min_value=0.0)
                d = st.date_input("التاريخ", date.today())
                n = st.text_input("ملاحظة")
                if st.form_submit_button("حفظ الإيداع"):
                    execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s,%s,%s)",(str(d),a,n))
                    st.success("تم"); st.rerun()
        render_custom_table(fin['deposits'], cols)
        
    with t2:
        with st.expander("➖ تسجيل سحب جديد"):
            with st.form("add_wit"):
                a = st.number_input("المبلغ", min_value=0.0)
                d = st.date_input("التاريخ", date.today())
                n = st.text_input("ملاحظة")
                if st.form_submit_button("حفظ السحب"):
                    execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s,%s,%s)",(str(d),a,n))
                    st.success("تم"); st.rerun()
        render_custom_table(fin['withdrawals'], cols)
        
    with t3:
        with st.expander("💵 تسجيل عائد/توزيع"):
            with st.form("add_ret"):
                s = st.text_input("الرمز")
                a = st.number_input("المبلغ", min_value=0.0)
                d = st.date_input("التاريخ", date.today())
                if st.form_submit_button("حفظ العائد"):
                    execute_query("INSERT INTO ReturnsGrants (date, symbol, amount) VALUES (%s,%s,%s)",(str(d),s,a))
                    st.success("تم"); st.rerun()
        render_custom_table(fin['returns'], cols)

# --- 3. المحفظة ---
def view_portfolio(fin, key):
    ts = "مضاربة" if key=='spec' else "استثمار"
    st.header(f"💼 محفظة {ts}"); df = fin['all_trades']
    if df.empty: st.info("فارغة"); return
    sub = df[df['strategy'].astype(str).str.contains(ts, na=False)]
    op = sub[sub['status']=='Open']; cl = sub[sub['status']=='Close']
    
    t1,t2 = st.tabs(["الصفقات القائمة", "الأرشيف"])
    with t1:
        if not op.empty:
            cols = [('company_name','الشركة','text'),('symbol','الرمز','text'),('quantity','الكمية','money'),('entry_price','ت.شراء','money'),('current_price','سوق','money'),('gain','الربح','colorful'),('gain_pct','%','percent')]
            render_custom_table(op, cols)
            with st.expander("🔴 تسجيل بيع"):
                with st.form(f"s_{key}"):
                    s=st.selectbox("سهم", op['symbol'].unique()); p=st.number_input("سعر"); d=st.date_input("تاريخ")
                    if st.form_submit_button("تأكيد"): execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'",(p,str(d),s,ts)); st.rerun()
        else: st.info("لا توجد أسهم")
    with t2:
        if not cl.empty: render_custom_table(cl, [('company_name','الشركة','text'),('symbol','الرمز','text'),('gain','الربح','colorful'),('exit_date','تاريخ','date')])

# --- باقي الصفحات ---
def view_analysis(fin):
    st.header("🔬 التحليل")
    trades = fin['all_trades']
    from database import fetch_table
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    c1,c2=st.columns([1,2]); ns=c1.text_input("بحث"); sym=c2.selectbox("اختر", [ns]+syms if ns else syms) if syms or ns else None
    
    if sym:
        n, s = get_static_info(sym); st.markdown(f"### {n} ({sym})")
        t1,t2,t3,t4,t5 = st.tabs(["مؤشرات", "فني", "قوائم", "كلاسيكي", "أطروحة"])
        with t1: 
            d=get_fundamental_ratios(sym); st.metric("التقييم", f"{d['Score']}/10", d['Rating']); st.write(d.get('Opinions'))
        with t2: render_technical_chart(sym)
        with t3: render_financial_dashboard_ui(sym)
        with t4: render_classical_analysis(sym)
        with t5: 
            th=get_thesis(sym); st.text_area("نص", value=th['thesis_text'] if th else "")

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

def view_sukuk_portfolio(fin): st.header("📜 صكوك"); render_custom_table(fin['all_trades'][fin['all_trades']['asset_type']=='Sukuk'], [('symbol','رمز','text'),('quantity','كمية','money')])
def view_add_trade():
    st.header("➕ إضافة صفقة"); 
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
