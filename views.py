import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

# الاستيرادات الأساسية
from config import DEFAULT_COLORS
from components import render_kpi, render_table, render_ticker_card, safe_fmt
from analytics import calculate_portfolio_metrics, update_prices, generate_equity_curve
from database import execute_query, fetch_table, get_db, clear_all_data
from market_data import get_static_info, get_tasi_data, get_chart_history, fetch_batch_data
from charts import render_technical_chart
from backtester import run_backtest
from financial_analysis import render_financial_dashboard_ui, get_fundamental_ratios, get_thesis, save_thesis
from classical_analysis import render_classical_analysis

# --- القائمة العلوية ---
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
        with st.popover("👤"):
            if st.button("➕ إضافة", use_container_width=True): st.session_state.page='add'; st.rerun()
            if st.button("⚙️ إعدادات", use_container_width=True): st.session_state.page='settings'; st.rerun()
            if st.button("خروج", use_container_width=True): st.session_state.clear(); st.rerun()
    st.markdown("---")

# --- 1. قسم التحليل (كما طلبت بالضبط) ---
def view_analysis(fin):
    st.header("🔍 مركز التحليل الشامل")
    
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    # مربع البحث والاختيار في الأعلى
    c1, c2 = st.columns([1, 2])
    with c1: ns = st.text_input("بحث عن رمز جديد")
    if ns and ns not in syms: syms.insert(0, ns)
    with c2: sym = st.selectbox("أو اختر من القائمة", syms) if syms else None
    
    if sym:
        n, s = get_static_info(sym)
        st.markdown(f"### {n} ({sym})")
        
        # التبويبات الشاملة
        t1, t2, t3, t4, t5 = st.tabs(["📊 المؤشرات الأساسية", "📈 التحليل الفني", "📑 القوائم المالية", "🏛️ الكلاسيكي", "📝 الأطروحة"])
        
        with t1: # المؤشرات
            d = get_fundamental_ratios(sym)
            c_sc, c_det = st.columns([1, 3])
            
            # مربع التقييم الملون
            col_score = "green" if d['Score'] >= 7 else "orange" if d['Score'] >= 4 else "red"
            c_sc.markdown(f"""
                <div style="text-align:center; padding:15px; border:2px solid {col_score}; border-radius:10px;">
                    <h1 style="color:{col_score}; margin:0;">{d['Score']}/10</h1>
                    <b>{d['Rating']}</b>
                </div>
            """, unsafe_allow_html=True)
            
            with c_det:
                st.write("**الملاحظات:**")
                for op in d.get('Opinions', []): st.write(f"- {op}")
            
            st.markdown("---")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("مكرر الربحية (P/E)", safe_fmt(d.get('P/E')))
            k2.metric("مضاعف الدفترية (P/B)", safe_fmt(d.get('P/B')))
            k3.metric("العائد على الحقوق (ROE)", safe_fmt(d.get('ROE'), '%'))
            k4.metric("القيمة العادلة", safe_fmt(d.get('Fair_Value')))
            
        with t2: # الفني
            render_technical_chart(sym)
            
        with t3: # القوائم المالية (مع اللصق)
            render_financial_dashboard_ui(sym)
            
        with t4: # الكلاسيكي
            render_classical_analysis(sym)
            
        with t5: # الأطروحة
            th = get_thesis(sym)
            with st.form("thesis_form"):
                st.write("أطروحتك الاستثمارية:")
                txt = st.text_area("النص", value=th['thesis_text'] if th else "", height=150)
                c_t1, c_t2 = st.columns(2)
                tgt = c_t1.number_input("الهدف السعري", value=th['target_price'] if th else 0.0)
                rec = c_t2.selectbox("التوصية", ["شراء", "احتفاظ", "بيع"], index=0)
                if st.form_submit_button("حفظ الأطروحة"): 
                    save_thesis(sym, txt, tgt, rec)
                    st.success("تم الحفظ")

# --- 2. قسم المختبر (يعمل بالكامل) ---
def view_backtester_ui(fin):
    st.header("🧪 مختبر الاستراتيجيات")
    
    # واجهة الإدخال
    with st.container():
        c1, c2, c3 = st.columns(3)
        # تجهيز القائمة
        all_syms = ["1120.SR", "2010.SR"]
        if not fin['all_trades'].empty: 
            all_syms += fin['all_trades']['symbol'].unique().tolist()
        
        with c1: sym = st.selectbox("السهم للاختبار", list(set(all_syms)))
        with c2: strat = st.selectbox("الاستراتيجية", ["Trend Follower (جون ميرفي)", "Sniper (هجين)"])
        with c3: cap = st.number_input("رأس المال الافتراضي", 100000, step=1000)
        
        if st.button("🚀 بدء المحاكاة", type="primary", use_container_width=True):
            with st.spinner("جاري استرجاع البيانات التاريخية وتحليلها..."):
                df = get_chart_history(sym, "2y")
                res = run_backtest(df, strat, cap)
                
                if res:
                    st.markdown("---")
                    # عرض النتائج
                    k1, k2, k3 = st.columns(3)
                    ret_col = "normal" if res['return_pct'] > 0 else "inverse"
                    k1.metric("العائد الكلي", f"{res['return_pct']:.2f}%")
                    k2.metric("الرصيد النهائي", f"{res['final_value']:,.2f}")
                    k3.metric("عدد الصفقات", len(res['trades_log']))
                    
                    st.line_chart(res['df']['Portfolio_Value'])
                    
                    with st.expander("سجل الصفقات التفصيلي", expanded=True):
                        st.dataframe(res['trades_log'], use_container_width=True)
                else:
                    st.error("بيانات السهم غير كافية لإجراء اختبار دقيق (نحتاج 6 أشهر على الأقل).")

# --- 3. قسم السيولة (بالتصميم القديم والأيقونات) ---
def view_cash_log():
    st.header("💰 السيولة")
    fin = calculate_portfolio_metrics()
    
    # الأيقونات العلوية الثلاثة
    c1, c2, c3 = st.columns(3)
    with c1: render_kpi("إجمالي الإيداعات", safe_fmt(fin['deposits']['amount'].sum()), "success")
    with c2: render_kpi("إجمالي السحوبات", safe_fmt(fin['withdrawals']['amount'].sum()), "danger")
    with c3: render_kpi("إجمالي العوائد", safe_fmt(fin['returns']['amount'].sum()), "blue")
    
    st.markdown("---")
    
    # جداول السجلات
    t1, t2, t3 = st.tabs(["📥 سجل الإيداعات", "📤 سجل السحوبات", "💵 سجل العوائد"])
    
    with t1:
        with st.expander("➕ تسجيل إيداع جديد"):
            with st.form("dep"):
                a = st.number_input("المبلغ"); d = st.date_input("التاريخ"); n = st.text_input("ملاحظة/المصدر")
                if st.form_submit_button("حفظ"): execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s,%s,%s)",(str(d),a,n)); st.rerun()
        render_table(fin['deposits'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظة')])
        
    with t2:
        with st.expander("➖ تسجيل سحب جديد"):
            with st.form("wit"):
                a = st.number_input("المبلغ"); d = st.date_input("التاريخ"); n = st.text_input("ملاحظة/السبب")
                if st.form_submit_button("حفظ"): execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s,%s,%s)",(str(d),a,n)); st.rerun()
        render_table(fin['withdrawals'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظة')])
        
    with t3:
        with st.expander("💵 تسجيل توزيعات أرباح"):
            with st.form("ret"):
                s = st.text_input("رمز السهم"); a = st.number_input("المبلغ"); d = st.date_input("التاريخ")
                if st.form_submit_button("حفظ"): execute_query("INSERT INTO ReturnsGrants (date, symbol, amount) VALUES (%s,%s,%s)",(str(d),s,a)); st.rerun()
        render_table(fin['returns'], [('date','التاريخ'), ('symbol','الرمز'), ('amount','المبلغ')])

# --- باقي الصفحات (تعمل كما هي) ---
def view_dashboard(fin):
    try: tp, tc = get_tasi_data()
    except: tp, tc = 0, 0
    col = "#006644" if tc >= 0 else "#DE350B"
    st.markdown(f"<div class='tasi-box'><div><b>تاسي</b><h2>{tp:,.2f}</h2></div><div style='color:{col}'><b>{tc:+.2f}%</b></div></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi("الكاش", safe_fmt(fin['cash']), "blue")
    with c2: render_kpi("الاستثمار", safe_fmt(fin['total_deposited']-fin['total_withdrawn']))
    with c3: render_kpi("القيمة السوقية", safe_fmt(fin['market_val_open']))
    tpl = fin['unrealized_pl'] + fin['realized_pl']
    with c4: render_kpi("الربح", safe_fmt(tpl), 'success' if tpl>=0 else 'danger')
    st.markdown("---")
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title="النمو"), use_container_width=True)

def render_pulse_dashboard():
    st.header("💓 نبض السوق")
    trades = fetch_table("Trades"); wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    if not syms: st.info("القائمة فارغة"); return
    data = fetch_batch_data(syms)
    cols = st.columns(4)
    for i, (s, info) in enumerate(data.items()):
        chg = ((info['price']-info['prev_close'])/info['prev_close'])*100 if info['prev_close']>0 else 0
        with cols[i%4]: render_ticker_card(s, "سهم", info['price'], chg)

def view_portfolio(fin, key):
    ts = "مضاربة" if key=='spec' else "استثمار"
    st.header(f"💼 {ts}")
    df = fin['all_trades']
    if df.empty: st.info("فارغة"); return
    sub = df[df['strategy'].astype(str).str.contains(ts, na=False)]
    t1,t2 = st.tabs(["الحالية", "الأرشيف"])
    with t1: 
        render_table(sub[sub['status']=='Open'], [('symbol','الرمز'),('quantity','الكمية'),('entry_price','شراء'),('gain','ربح')])
        with st.expander("بيع"):
            with st.form(f"s_{key}"):
                s=st.selectbox("سهم", sub['symbol'].unique()); p=st.number_input("سعر"); d=st.date_input("تاريخ")
                if st.form_submit_button("بيع"): execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'",(p,str(d),s,ts)); st.rerun()
    with t2: render_table(sub[sub['status']=='Close'], [('symbol','الرمز'),('gain','ربح'),('exit_date','تاريخ')])

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
