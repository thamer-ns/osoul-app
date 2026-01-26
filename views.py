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

# ==========================================
# 1. لوحة القيادة (Dashboard)
# ==========================================
def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    C = DEFAULT_COLORS
    arrow, cl = ("🔼", C['success']) if t_change >= 0 else ("🔽", C['danger'])
    
    st.markdown(f"""
    <div class="tasi-box">
        <div><div style="font-size:1.1rem; opacity:0.9;">المؤشر العام (TASI)</div><div style="font-size:2.5rem; font-weight:900;">{safe_fmt(t_price)}</div></div>
        <div style="background:rgba(255,255,255,0.2); padding:10px 25px; border-radius:12px; font-weight:bold; font-size:1.4rem;">{arrow} {t_change:.2f}%</div>
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
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title=""), use_container_width=True)

# ==========================================
# 2. المحفظة (Portfolio) - النسخة الكاملة
# ==========================================
def view_portfolio(fin, page_key):
    ts = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    all_d = fin['all_trades']
    
    # فلترة الاستراتيجية
    df = pd.DataFrame()
    if not all_d.empty:
        df = all_d[all_d['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    if df.empty: st.info("المحفظة فارغة"); return

    # الأعمدة الكاملة التي طلبتها
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

    # ملخص سريع
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi("القيمة السوقية", safe_fmt(open_df['market_value'].sum() if not open_df.empty else 0), "blue")
    with c2: render_kpi("التكلفة", safe_fmt(open_df['total_cost'].sum() if not open_df.empty else 0))
    with c3: render_kpi("الربح العائم", safe_fmt(open_df['gain'].sum() if not open_df.empty else 0))
    with c4: render_kpi("الربح المحقق", safe_fmt(closed_df['gain'].sum() if not closed_df.empty else 0))
    st.markdown("---")

    # التبويبات الثلاثة
    t1, t2, t3 = st.tabs(["📋 الأسهم الحالية", "📊 تحليل الأداء", "🗄️ الأرشيف"])
    
    with t1:
        if not open_df.empty:
            # خيار الفرز البسيط
            c_sort, _ = st.columns([1, 4])
            with c_sort:
                st.markdown("**ترتيب حسب:**")
                sort_opt = st.radio("sort_r", ["الأحدث", "الأعلى ربحاً"], horizontal=True, label_visibility="collapsed")
            
            if sort_opt == "الأعلى ربحاً": open_df = open_df.sort_values(by="gain", ascending=False)
            else: open_df = open_df.sort_values(by="date", ascending=False)

            render_table(open_df, COLS)
            
            # منطقة البيع السريع
            with st.expander("🔻 بيع سهم"):
                with st.form("sell"):
                    c1,c2 = st.columns(2)
                    st.markdown("**اختر السهم:**"); s = c1.selectbox("s", open_df['symbol'].unique(), label_visibility="collapsed")
                    st.markdown("**سعر البيع:**"); p = c2.number_input("p", min_value=0.0, label_visibility="collapsed")
                    st.markdown("**تاريخ البيع:**"); d = st.date_input("d", date.today(), label_visibility="collapsed")
                    if st.form_submit_button("تأكيد البيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, ts))
                        st.success("تم البيع"); time.sleep(0.5); st.rerun()
        else: st.info("لا توجد أسهم حالية")
    
    with t2:
        if not open_df.empty and page_key == 'invest':
            st.markdown("#### توزيع المحفظة حسب القطاعات")
            fig = px.pie(open_df, values='market_value', names='sector', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            
    with t3:
        if not closed_df.empty:
            closed_df['net_sales'] = closed_df['quantity'] * closed_df['exit_price']
            closed_df['realized_gain'] = closed_df['net_sales'] - closed_df['total_cost']
            
            # أعمدة إضافية للأرشيف
            ARCHIVE_COLS = COLS + [('net_sales', 'صافي البيع'), ('realized_gain', 'الربح المحقق')]
            render_table(closed_df.sort_values('exit_date', ascending=False), ARCHIVE_COLS)
        else: st.info("الأرشيف فارغ")

# ==========================================
# 3. الصفحات الأخرى (نبض السوق، السيولة، التحليل)
# ==========================================
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

def view_cash_log():
    st.header("💵 سجل السيولة")
    fin = calculate_portfolio_metrics()
    c1, c2, c3 = st.columns(3)
    net = fin['deposits']['amount'].sum() - fin['withdrawals']['amount'].sum()
    with c1: render_kpi("إجمالي الإيداعات", safe_fmt(fin['deposits']['amount'].sum()), "success")
    with c2: render_kpi("إجمالي السحوبات", safe_fmt(fin['withdrawals']['amount'].sum()), "danger")
    with c3: render_kpi("صافي التمويل", safe_fmt(net), "blue")
    st.markdown("---")
    
    t1, t2, t3 = st.tabs(["سجل الإيداعات", "سجل السحوبات", "سجل العوائد"])
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
    tab1, tab2 = st.tabs(["📈 تسجيل صفقة (أسهم)", "💰 حركة مالية (كاش)"])
    with tab1:
        with st.form("tr"):
            c1, c2 = st.columns(2)
            st.markdown("**رمز السهم:**"); s = c1.text_input("s", label_visibility="collapsed")
            st.markdown("**نوع المحفظة:**"); st_t = c2.selectbox("st", ["استثمار", "مضاربة", "صكوك"], label_visibility="collapsed")
            c3, c4, c5 = st.columns(3)
            st.markdown("**الكمية:**"); q = c3.number_input("q", 1.0, label_visibility="collapsed")
            st.markdown("**السعر:**"); p = c4.number_input("p", 0.0, label_visibility="collapsed")
            st.markdown("**التاريخ:**"); d = c5.date_input("d", date.today(), label_visibility="collapsed")
            if st.form_submit_button("حفظ الصفقة"):
                n, sec = get_company_details(s)
                at = "Sukuk" if st_t == "صكوك" else "Stock"
                execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Open',%s)", (s, n, sec, at, str(d), q, p, st_t, p))
                st.success("تم الحفظ"); st.cache_data.clear()
    with tab2:
        with st.form("ca"):
            c1, c2 = st.columns(2)
            st.markdown("**النوع:**"); ty = c1.selectbox("t", ["إيداع نقدي", "سحب نقدي", "توزيعات"], label_visibility="collapsed")
            st.markdown("**المبلغ:**"); am = c2.number_input("a", 0.0, label_visibility="collapsed")
            st.markdown("**التاريخ:**"); da = st.date_input("da", date.today(), label_visibility="collapsed")
            st.markdown("**ملاحظة / الرمز:**"); no = st.text_input("no", label_visibility="collapsed")
            if st.form_submit_button("حفظ الحركة"):
                if "إيداع" in ty: execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s,%s,%s)", (str(da), am, no))
                elif "سحب" in ty: execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s,%s,%s)", (str(da), am, no))
                else: execute_query("INSERT INTO ReturnsGrants (date, symbol, amount, note) VALUES (%s,%s,%s,%s)", (str(da), no, am, "توزيعات"))
                st.success("تم"); st.rerun()

def view_analysis(fin):
    st.header("🔬 مركز التحليل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    symbols = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c1, c2 = st.columns([1, 2])
    with c1: 
        st.markdown("**بحث:**")
        ns = st.text_input("s_search", label_visibility="collapsed")
    if ns and ns not in symbols: symbols.insert(0, ns)
    
    with c2:
        st.markdown("**اختر الشركة:**")
        sym = st.selectbox("s_select", symbols, label_visibility="collapsed") if symbols else None
    
    if sym:
        n, s = get_company_details(sym)
        st.markdown(f"### {n} ({sym})")
        t1, t2, t3, t4, t5 = st.tabs(["📊 المؤشرات", "📑 القوائم", "📝 الأطروحة", "📈 الشارت", "🏛️ كلاسيكي"])
        with t1:
            d = get_fundamental_ratios(sym)
            c1,c2 = st.columns([1,3])
            c1.metric("التقييم", f"{d['Score']}/10")
            render_financial_dashboard_ui(sym)
        with t2: st.info("البيانات المالية")
        with t3: st.info("الأطروحة")
        with t4: view_advanced_chart(sym)
        with t5: st.info("التحليل الكلاسيكي")

def view_backtester_ui(fin):
    st.header("🧪 المختبر")
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown("**السهم:**"); sym = st.selectbox("bs", list(set(fin['all_trades']['symbol'].unique().tolist()+["1120"])), label_visibility="collapsed")
    with c2: st.markdown("**استراتيجية:**"); strat = st.selectbox("bst", ["Trend Follower", "Sniper"], label_visibility="collapsed")
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

def view_tools():
    st.header("🛠️ الأدوات")
    fin = calculate_portfolio_metrics()
    st.info(f"الزكاة: {safe_fmt(fin['market_val_open']*0.025775)}")

def view_settings():
    st.header("⚙️ الإعدادات")
    with st.expander("📥 استيراد بيانات (Excel/CSV)"):
        f = st.file_uploader("اختر الملف", accept_multiple_files=False)
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
