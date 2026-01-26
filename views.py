import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

from config import DEFAULT_COLORS
from components import render_kpi, render_table, render_ticker_card, safe_fmt
from analytics import calculate_portfolio_metrics, update_prices, generate_equity_curve
from database import execute_query, fetch_table, clear_all_data
from market_data import get_static_info, get_tasi_data, get_chart_history, fetch_batch_data
from charts import render_technical_chart
from backtester import run_backtest
from financial_analysis import render_financial_dashboard_ui, get_fundamental_ratios, get_thesis, save_thesis
from classical_analysis import render_classical_analysis

# --- القائمة العلوية (تمت استعادة القائمة الكاملة) ---
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
        # القائمة المنسدلة بكل العناصر المطلوبة
        with st.popover("👤 القائمة"):
            st.write(f"أهلاً, {st.session_state.get('username','User')}")
            if st.button("➕ إضافة صفقة", use_container_width=True): st.session_state.page='add'; st.rerun()
            if st.button("🛠️ أدوات", use_container_width=True): st.session_state.page='tools'; st.rerun()
            if st.button("⚙️ إعدادات", use_container_width=True): st.session_state.page='settings'; st.rerun()
            st.markdown("---")
            if st.button("خروج", use_container_width=True): 
                try: from security import logout; logout()
                except: st.session_state.clear(); st.rerun()
    st.markdown("---")

# --- الصفحات ---

def view_dashboard(fin):
    try: tp, tc = get_tasi_data()
    except: tp, tc = 0, 0
    col = "#006644" if tc >= 0 else "#DE350B"
    
    st.markdown(f"""
        <div style="background:white; padding:20px; border-radius:10px; border:1px solid #ddd; display:flex; justify-content:space-between; align-items:center;">
            <div>
                <div style="color:#666;">المؤشر العام (TASI)</div>
                <div style="font-size:2rem; font-weight:bold;">{tp:,.2f}</div>
            </div>
            <div style="color:{col}; font-weight:bold; font-size:1.2rem; direction:ltr;">{tc:+.2f}%</div>
        </div><br>
    """, unsafe_allow_html=True)
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi("الكاش المتوفر", safe_fmt(fin['cash']), "blue")
    with c2: render_kpi("الاستثمار", safe_fmt(fin['total_deposited']-fin['total_withdrawn']))
    with c3: render_kpi("القيمة السوقية", safe_fmt(fin['market_val_open']))
    tpl = fin['unrealized_pl'] + fin['realized_pl']
    with c4: render_kpi("صافي الربح", safe_fmt(tpl), 'success' if tpl>=0 else 'danger')
    
    st.markdown("---")
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title="نمو المحفظة"), use_container_width=True)

def view_portfolio(fin, key):
    ts = "مضاربة" if key=='spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    df = fin['all_trades']
    
    if df.empty: st.info("المحفظة فارغة"); return
    sub = df[df['strategy'].astype(str).str.contains(ts, na=False)]
    
    open_df = sub[sub['status']=='Open']
    closed_df = sub[sub['status']=='Close']
    
    t1,t2 = st.tabs([f"الأسهم الحالية ({len(open_df)})", "الأرشيف"])
    
    with t1:
        if not open_df.empty:
            # الجدول بالتصميم الذي تحبه (أعمدة محددة)
            cols = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'الشراء'), ('current_price', 'الحالي'), ('market_value', 'القيمة'), ('gain', 'الربح'), ('gain_pct', '%')]
            render_table(open_df, cols)
            
            with st.expander("🔴 تسجيل بيع"):
                with st.form(f"s_{key}"):
                    c1,c2 = st.columns(2)
                    s = c1.selectbox("اختر السهم", open_df['symbol'].unique())
                    p = c2.number_input("سعر البيع")
                    d = st.date_input("تاريخ البيع", date.today())
                    if st.form_submit_button("تأكيد البيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'",(p,str(d),s,ts))
                        st.success("تم"); st.rerun()
        else: st.info("لا توجد أسهم حالية")
        
    with t2:
        if not closed_df.empty:
            render_table(closed_df, [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح'), ('exit_date', 'تاريخ البيع')])

def view_analysis(fin):
    st.header("🔬 مركز التحليل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    # مربع البحث في الأعلى
    c1, c2 = st.columns([1, 2])
    ns = c1.text_input("بحث عن رمز")
    if ns and ns not in syms: syms.insert(0, ns)
    sym = c2.selectbox("أو اختر من القائمة", syms) if syms else None
    
    if sym:
        n, s = get_static_info(sym)
        st.markdown(f"### {n} ({sym})")
        # التبويبات الكاملة
        t1,t2,t3,t4,t5 = st.tabs(["📊 المؤشرات", "📈 الفني", "📑 القوائم", "🏛️ الكلاسيكي", "📝 الأطروحة"])
        
        with t1: 
            d=get_fundamental_ratios(sym)
            c_sc, c_dt = st.columns([1,3])
            c_sc.metric("التقييم", f"{d['Score']}/10", d['Rating'])
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
                if st.form_submit_button("حفظ"): save_thesis(sym, tx, 0, "Hold"); st.success("تم")

def view_backtester_ui(fin):
    st.header("🧪 مختبر الاستراتيجيات")
    c1,c2,c3 = st.columns(3)
    
    # تجهيز القائمة
    all_syms = ["1120.SR", "2010.SR"]
    if not fin['all_trades'].empty: 
        all_syms += fin['all_trades']['symbol'].unique().tolist()
        
    with c1: sym = st.selectbox("السهم", list(set(all_syms)))
    with c2: strat = st.selectbox("الاستراتيجية", ["Trend Follower (جون ميرفي)", "Sniper (هجين)"])
    with c3: cap = st.number_input("رأس المال", 100000)
    
    if st.button("🚀 بدء الاختبار", type="primary"):
        with st.spinner("جاري التحليل..."):
            df = get_chart_history(sym, "2y")
            res = run_backtest(df, strat, cap)
            if res:
                k1, k2 = st.columns(2)
                k1.metric("العائد", f"{res['return_pct']:.2f}%")
                k2.metric("الرصيد النهائي", f"{res['final_value']:,.2f}")
                st.line_chart(res['df']['Portfolio_Value'])
                with st.expander("تفاصيل الصفقات"): st.dataframe(res['trades_log'], use_container_width=True)
            else: st.error("فشل التحليل (بيانات غير كافية)")

def view_cash_log():
    st.header("💰 السيولة")
    fin = calculate_portfolio_metrics()
    
    # الأيقونات الثلاثة
    c1, c2, c3 = st.columns(3)
    with c1: render_kpi("إجمالي الإيداعات", safe_fmt(fin['deposits']['amount'].sum()), "success")
    with c2: render_kpi("إجمالي السحوبات", safe_fmt(fin['withdrawals']['amount'].sum()), "danger")
    with c3: render_kpi("إجمالي العوائد", safe_fmt(fin['returns']['amount'].sum()), "blue")
    
    st.markdown("---")
    t1,t2,t3 = st.tabs(["إيداع", "سحب", "توزيع"])
    with t1: render_table(fin['deposits'], [('date','تاريخ'),('amount','مبلغ'),('note','ملاحظة')])
    with t2: render_table(fin['withdrawals'], [('date','تاريخ'),('amount','مبلغ'),('note','ملاحظة')])
    with t3: render_table(fin['returns'], [('date','تاريخ'),('symbol','رمز'),('amount','مبلغ')])

# بقية الصفحات تعمل بشكل قياسي
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

def view_sukuk_portfolio(fin): st.header("📜 صكوك"); render_table(fin['all_trades'][fin['all_trades']['asset_type']=='Sukuk'], [('symbol','رمز'),('quantity','كمية')])
def view_add_trade():
    st.header("➕ إضافة"); 
    with st.form("add"):
        c1,c2=st.columns(2); s=c1.text_input("رمز"); t=c2.selectbox("نوع", ["استثمار","مضاربة","صكوك"])
        c3,c4,c5=st.columns(3); q=c3.number_input("كمية"); p=c4.number_input("سعر"); d=c5.date_input("تاريخ")
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
