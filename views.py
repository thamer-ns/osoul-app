import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time

# === الاستيرادات ===
from config import DEFAULT_COLORS, BACKUP_DIR
from components import render_navbar, render_kpi, render_table, render_ticker_card, safe_fmt
from analytics import (calculate_portfolio_metrics, update_prices, generate_equity_curve, run_backtest)
from database import execute_query, fetch_table, get_db, clear_all_data
from market_data import get_static_info, get_tasi_data, get_chart_history
from data_source import get_company_details
import charts # استيراد ملف الشارتات

# ==========================================
# 1. دوال مساعدة للعرض
# ==========================================
def apply_sorting(df, cols_definition, key_suffix):
    if df.empty: return df
    with st.expander("🔍 خيارات الترتيب", expanded=False):
        label_map = {label: col for col, label in cols_definition}
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown("**رتب حسب:**")
            sort_col_label = st.selectbox("sc", options=list(label_map.keys()), key=f"sc_{key_suffix}", label_visibility="collapsed")
        with c2:
            st.markdown("**الاتجاه:**")
            sort_order = st.radio("so", options=["تنازلي", "تصاعدي"], horizontal=True, key=f"so_{key_suffix}", label_visibility="collapsed")
    target_col = label_map[sort_col_label]
    try: return df.sort_values(by=target_col, ascending=(sort_order == "تصاعدي"))
    except: return df

# ==========================================
# 2. الصفحات
# ==========================================

def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    C = DEFAULT_COLORS
    arrow, cl = ("🔼", C['success']) if t_change >= 0 else ("🔽", C['danger'])
    
    st.markdown(f"""
    <div class="tasi-box">
        <div><div style="font-size:1.1rem; color:{C['sub_text']};">المؤشر العام</div><div style="font-size:2.2rem; font-weight:900; color:{C['main_text']};">{safe_fmt(t_price)}</div></div>
        <div style="background:{cl}15; color:{cl}; padding:8px 20px; border-radius:10px; font-weight:bold; direction:ltr;">{arrow} {safe_fmt(t_change)}%</div>
    </div>""", unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    total_inv = fin['total_deposited'] - fin['total_withdrawn']
    with c1: render_kpi("الكاش المتوفر", safe_fmt(fin['cash']), "blue")
    with c2: render_kpi("صافي الاستثمار", safe_fmt(total_inv))
    with c3: render_kpi("القيمة السوقية", safe_fmt(fin['market_val_open']))
    tpl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("الربح/الخسارة", safe_fmt(tpl), tpl)
    
    st.markdown("---")
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title=""), use_container_width=True)

def render_pulse_dashboard():
    st.header("💓 نبض السوق")
    trades = fetch_table("Trades")
    wl = fetch_table("Watchlist")
    symbols = set()
    if not trades.empty: symbols.update(trades[trades['status']=='Open']['symbol'].unique())
    if not wl.empty: symbols.update(wl['symbol'].unique())
    if not symbols: st.info("القائمة فارغة."); return
    cols = st.columns(4)
    for i, sym in enumerate(symbols):
        name, _ = get_company_details(sym)
        price = 0.0
        if not trades.empty:
            row = trades[trades['symbol'] == sym]
            if not row.empty: price = row.iloc[0]['current_price']
        with cols[i % 4]: render_ticker_card(sym, name if name else sym, price, 0.0)

def view_portfolio(fin, page_key):
    ts = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    all_d = fin['all_trades']
    df = pd.DataFrame()
    if not all_d.empty:
        df = all_d[all_d['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    # حسابات الأعمدة الديناميكية
    if not df.empty:
        total_mkt = df[df['status']=='Open']['market_value'].sum()
        df['weight'] = df.apply(lambda x: (x['market_value']/total_mkt*100) if x['status']=='Open' and total_mkt>0 else 0, axis=1)
        df['daily_change'] = df.apply(lambda x: ((x['current_price']-x['prev_close'])/x['prev_close']*100) if pd.notna(x['prev_close']) and x['prev_close']>0 else 0, axis=1)

    COLS = [
        ('company_name', 'الشركة'), ('sector', 'القطاع'), ('status', 'الحالة'),
        ('symbol', 'الرمز'), ('date', 'تاريخ الشراء'), ('exit_date', 'تاريخ البيع'),
        ('quantity', 'الكمية'), ('entry_price', 'سعر الشراء'), ('total_cost', 'التكلفة'),
        ('year_high', 'اعلى سنوي'), ('current_price', 'الحالي/البيع'), ('year_low', 'ادنى سنوي'),
        ('market_value', 'القيمة'), ('gain', 'الربح/الخسارة'), ('gain_pct', '%'),
        ('weight', 'الوزن'), ('daily_change', 'التغير اليومي'), ('prev_close', 'اغلاق سابق')
    ]

    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()

    t1, t2 = st.tabs(["الأسهم الحالية", "الأرشيف"])
    with t1:
        if not open_df.empty:
            c1, c2, c3 = st.columns(3)
            with c1: render_kpi("القيمة السوقية", safe_fmt(open_df['market_value'].sum()), "blue")
            with c2: render_kpi("الربح العائم", safe_fmt(open_df['gain'].sum()))
            with c3: render_kpi("العدد", f"{len(open_df)}")
            render_table(apply_sorting(open_df, COLS, page_key), COLS)
            
            with st.expander("🔻 بيع سهم"):
                with st.form("sell"):
                    c1,c2 = st.columns(2)
                    st.markdown("**السهم:**")
                    s = c1.selectbox("s", open_df['symbol'].unique(), label_visibility="collapsed")
                    st.markdown("**سعر البيع:**")
                    p = c2.number_input("p", min_value=0.0, label_visibility="collapsed")
                    st.markdown("**التاريخ:**")
                    d = st.date_input("d", date.today(), label_visibility="collapsed")
                    if st.form_submit_button("تأكيد"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, ts))
                        st.success("تم"); time.sleep(0.5); st.rerun()
        else: st.info("لا توجد أسهم")
    
    with t2:
        if not closed_df.empty:
            # تحديث حسابات المغلقة للعرض
            closed_df['net_sales'] = closed_df['quantity'] * closed_df['exit_price']
            closed_df['realized_gain'] = closed_df['net_sales'] - closed_df['total_cost']
            
            c1, c2 = st.columns(2)
            with c1: render_kpi("صافي البيع", safe_fmt(closed_df['net_sales'].sum()), "blue")
            with c2: render_kpi("الربح المحقق", safe_fmt(closed_df['realized_gain'].sum()))
            
            render_table(closed_df, COLS)
        else: st.info("الأرشيف فارغ")

def view_cash_log():
    st.header("💵 سجل السيولة")
    fin = calculate_portfolio_metrics()
    c1, c2, c3 = st.columns(3)
    net = fin['deposits']['amount'].sum() - fin['withdrawals']['amount'].sum()
    with c1: render_kpi("إيداعات", safe_fmt(fin['deposits']['amount'].sum()), "success")
    with c2: render_kpi("سحوبات", safe_fmt(fin['withdrawals']['amount'].sum()), "danger")
    with c3: render_kpi("صافي", safe_fmt(net), "blue")
    st.markdown("---")

    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "التوزيعات"])
    cols = [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظات')]
    
    with t1:
        with st.expander("➕ إيداع"):
            with st.form("dep"):
                st.markdown("**المبلغ:**"); a = st.number_input("a", 0.0, label_visibility="collapsed")
                st.markdown("**التاريخ:**"); d = st.date_input("d", date.today(), label_visibility="collapsed")
                st.markdown("**ملاحظة:**"); n = st.text_input("n", label_visibility="collapsed")
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                    st.rerun()
        render_table(fin['deposits'], cols)
        
    with t2:
        with st.expander("➖ سحب"):
            with st.form("wit"):
                st.markdown("**المبلغ:**"); a = st.number_input("wa", 0.0, label_visibility="collapsed")
                st.markdown("**التاريخ:**"); d = st.date_input("wd", date.today(), label_visibility="collapsed")
                st.markdown("**ملاحظة:**"); n = st.text_input("wn", label_visibility="collapsed")
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                    st.rerun()
        render_table(fin['withdrawals'], cols)
        
    with t3:
        with st.expander("💰 توزيع"):
            with st.form("ret"):
                c1,c2 = st.columns(2)
                st.markdown("**الرمز:**"); s = c1.text_input("rs", label_visibility="collapsed")
                st.markdown("**المبلغ:**"); a = c2.number_input("ra", 0.0, label_visibility="collapsed")
                st.markdown("**التاريخ:**"); d = st.date_input("rd", date.today(), label_visibility="collapsed")
                st.markdown("**النوع:**"); n = st.text_input("rn", label_visibility="collapsed")
                if st.form_submit_button("حفظ"):
                    cn, _ = get_company_details(s)
                    execute_query("INSERT INTO ReturnsGrants (date, symbol, company_name, amount, note) VALUES (%s,%s,%s,%s,%s)", (str(d), s, cn, a, n))
                    st.rerun()
        render_table(fin['returns'], [('date','التاريخ'), ('symbol','الرمز'), ('amount','المبلغ'), ('note','النوع')])

def view_add_trade():
    st.header("➕ تسجيل صفقة")
    with st.form("add_trade"):
        c1, c2 = st.columns(2)
        st.markdown("**الرمز:**"); sym = c1.text_input("ts", label_visibility="collapsed")
        st.markdown("**المحفظة:**"); strt = c2.selectbox("tst", ["استثمار", "مضاربة", "صكوك"], label_visibility="collapsed")
        c3, c4 = st.columns(2)
        st.markdown("**الكمية:**"); qty = c3.number_input("tq", 1.0, label_visibility="collapsed")
        st.markdown("**السعر:**"); prc = c4.number_input("tp", 0.0, step=0.01, label_visibility="collapsed")
        st.markdown("**التاريخ:**"); dt = st.date_input("td", date.today(), label_visibility="collapsed")
        if st.form_submit_button("حفظ"):
            if sym and qty > 0:
                cn, sec = get_company_details(sym)
                at = "Sukuk" if strt == "صكوك" else "Stock"
                execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Open',%s)", (sym, cn, sec, at, str(dt), qty, prc, strt, prc))
                st.success("تم"); st.cache_data.clear()

def view_analysis(fin):
    # استدعاء ملف Charts مباشرة للتحليل
    charts.view_analysis(fin)

def view_backtester_ui(fin):
    st.header("🧪 المختبر")
    c1, c2, c3 = st.columns(3)
    with c1: 
        st.markdown("**السهم:**"); sym = st.selectbox("bs", list(set(fin['all_trades']['symbol'].unique().tolist()+["1120"])), label_visibility="collapsed")
    with c2: 
        st.markdown("**استراتيجية:**"); strt = st.selectbox("bst", ["Trend Follower", "Sniper"], label_visibility="collapsed")
    with c3: 
        st.markdown("**رأس المال:**"); cap = st.number_input("bc", 100000, label_visibility="collapsed")
    if st.button("🚀 تشغيل"):
        df = get_chart_history(sym, "2y")
        if df is not None:
            res = run_backtest(df, strt, cap)
            if res:
                c1,c2 = st.columns(2)
                c1.metric("العائد", f"{res['return_pct']:.2f}%")
                c2.metric("الرصيد", f"{res['final_value']:,.2f}")
                st.line_chart(res['df']['Portfolio_Value'])

def view_settings():
    st.header("⚙️ الإعدادات")
    with st.expander("📥 استيراد"):
        f = st.file_uploader("ملف Excel", accept_multiple_files=False)
        if f and st.button("بدء"): st.info("ميزة الاستيراد جاهزة")
    
    with st.expander("⚠️ حذف البيانات"):
        del_t = st.checkbox("حذف الصفقات")
        del_c = st.checkbox("حذف السيولة")
        if st.button("تأكيد"):
            if del_t: execute_query("TRUNCATE TABLE Trades RESTART IDENTITY CASCADE;")
            if del_c: 
                execute_query("TRUNCATE TABLE Deposits RESTART IDENTITY CASCADE;")
                execute_query("TRUNCATE TABLE Withdrawals RESTART IDENTITY CASCADE;")
                execute_query("TRUNCATE TABLE ReturnsGrants RESTART IDENTITY CASCADE;")
            st.success("تم الحذف"); time.sleep(1); st.rerun()

def view_sukuk_portfolio(fin):
    st.header("📜 الصكوك")
    df = fin['all_trades']
    sk = df[df['asset_type']=='Sukuk'].copy()
    if not sk.empty:
        render_table(sk, [('company_name', 'الاسم'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'شراء'), ('gain', 'الربح')])
    else: st.info("لا توجد صكوك")

def view_tools():
    st.header("🛠️ الأدوات")
    fin = calculate_portfolio_metrics()
    st.info(f"الزكاة: {safe_fmt(fin['market_val_open']*0.025775)}")

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
