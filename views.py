import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time

# === الاستيرادات ===
from config import DEFAULT_COLORS
from components import render_kpi, render_table, render_ticker_card, safe_fmt
from analytics import (calculate_portfolio_metrics, update_prices, generate_equity_curve, calculate_historical_drawdown)
from database import execute_query, fetch_table, get_db, clear_all_data
from market_data import get_static_info, get_tasi_data, get_chart_history, fetch_batch_data
from charts import render_technical_chart
try: from backtester import run_backtest
except: run_backtest = lambda *a: None

# === القائمة العلوية (كما كانت سابقاً بالضبط) ===
def render_navbar():
    # تقسيم الشاشة لـ 10 أعمدة كما في تصميمك القديم
    c1, c2, c3, c4, c5, c6, c7, c8, c9, c10 = st.columns([1, 1, 1, 1, 1, 1, 1.2, 1, 1, 1])
    
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
    with c10:
        with st.popover("👤 القائمة"):
            st.write(f"مرحباً، {st.session_state.get('username', 'زائر')}")
            if st.button("➕ إضافة صفقة", use_container_width=True): st.session_state.page = 'add'; st.rerun()
            if st.button("🛠️ أدوات", use_container_width=True): st.session_state.page = 'tools'; st.rerun()
            if st.button("⚙️ الإعدادات", use_container_width=True): st.session_state.page = 'settings'; st.rerun()
            if st.button("🚪 خروج", use_container_width=True): 
                try: from security import logout; logout()
                except: st.session_state.clear(); st.rerun()
    st.markdown("---")

# === 1. الصفحة الرئيسية (كما صممتها أنت) ===
def view_dashboard(fin):
    # قسم تاسي في الأعلى
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    
    arrow = "🔼" if t_change >= 0 else "🔽"
    color = "#006644" if t_change >= 0 else "#DE350B"
    
    st.markdown(f"""
    <div class="tasi-box">
        <div>
            <div style="font-size:0.9rem; color:#5E6C84; font-weight:bold;">المؤشر العام (TASI)</div>
            <div style="font-size:2rem; font-weight:900; color:#172B4D;">{t_price:,.2f}</div>
        </div>
        <div style="background:{color}15; color:{color}; padding:8px 20px; border-radius:6px; font-size:1.2rem; font-weight:bold; direction:ltr;">
            {arrow} {t_change:.2f}%
        </div>
    </div>
    """, unsafe_allow_html=True)

    # الكروت (KPIs)
    c1, c2, c3, c4 = st.columns(4)
    total_pl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c1: render_kpi("الكاش المتوفر", f"{fin['cash']:,.2f}", "blue")
    with c2: render_kpi("رأس المال المستثمر", f"{(fin['total_deposited']-fin['total_withdrawn']):,.2f}")
    with c3: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}")
    with c4: render_kpi("الربح الكلي", f"{total_pl:,.2f}", 'success' if total_pl >= 0 else 'danger')

    st.markdown("---")
    st.subheader("📈 نمو المحفظة")
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested'), use_container_width=True)

# === 2. صفحة نبض السوق (كما طلبت) ===
def render_pulse_dashboard():
    st.header("💓 نبض السوق")
    trades = fetch_table("Trades")
    watchlist = fetch_table("Watchlist")
    
    symbols = set()
    if not trades.empty: symbols.update(trades[trades['status']=='Open']['symbol'].unique())
    if not watchlist.empty: symbols.update(watchlist['symbol'].unique())
    
    if not symbols: st.info("القائمة فارغة"); return

    with st.spinner("جاري جلب الأسعار..."):
        data = fetch_batch_data(list(symbols))
    
    cols = st.columns(4)
    for i, (sym, info) in enumerate(data.items()):
        chg = 0.0
        if info['prev_close'] > 0:
            chg = ((info['price'] - info['prev_close']) / info['prev_close']) * 100
        with cols[i%4]:
            render_ticker_card(sym, "سهم", info['price'], chg)

# === 3. المحفظة (استثمار/مضاربة) ===
def view_portfolio(fin, page_key):
    ts = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    all_d = fin['all_trades']
    
    df = pd.DataFrame()
    if not all_d.empty:
        df = all_d[all_d['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    if df.empty: st.warning("المحفظة فارغة"); return

    if 'status' not in df.columns: df['status'] = 'Open'
    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()

    # حسابات سريعة
    if not open_df.empty:
        open_df['total_cost'] = open_df['quantity'] * open_df['entry_price']
        open_df['market_value'] = open_df['quantity'] * open_df['current_price']
        open_df['gain'] = open_df['market_value'] - open_df['total_cost']
        open_df['gain_pct'] = (open_df['gain'] / open_df['total_cost']) * 100

    t1, t2, t3 = st.tabs([f"القائمة ({len(open_df)})", "الأداء", "الأرشيف"])
    
    with t1:
        if not open_df.empty:
            cols = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'ت.شراء'), ('current_price', 'سوق'), ('gain', 'الربح'), ('gain_pct', '%')]
            render_table(open_df, cols)
            
            with st.expander("بيع"):
                with st.form(f"sell_{page_key}"):
                    c1,c2 = st.columns(2)
                    s = c1.selectbox("سهم", open_df['symbol'].unique())
                    p = c2.number_input("سعر البيع")
                    d = st.date_input("التاريخ", date.today())
                    if st.form_submit_button("بيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, ts))
                        st.success("تم"); st.cache_data.clear(); st.rerun()
    with t2:
        if not open_df.empty:
            st.plotly_chart(px.pie(open_df, values='market_value', names='sector', title="التوزيع القطاعي"), use_container_width=True)
    with t3:
        if not closed_df.empty: render_table(closed_df, [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح'), ('exit_date', 'تاريخ')])

# === 4. التحليل ===
def view_analysis(fin):
    st.header("🔬 التحليل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c1,c2 = st.columns([1,2])
    ns = c1.text_input("بحث")
    if ns and ns not in syms: syms.insert(0, ns)
    sym = c2.selectbox("اختر", syms) if syms else None
    
    if sym:
        render_technical_chart(sym)

# === 5. السيولة والاستيراد ===
def clean_and_fix_columns(df):
    """دالة الإصلاح التي طلبتها"""
    if df is None: return None
    df.columns = df.columns.str.strip().str.lower()
    
    # تحويل المسميات كما تريد
    rename_map = {'source': 'note', 'reason': 'note', 'notes': 'note', 'cost': 'amount', 'value': 'amount'}
    df.rename(columns=rename_map, inplace=True)
    
    # تنظيف
    if 'id' in df.columns: df = df.drop(columns=['id'])
    return df

def save_dataframe_to_db(df, table_name):
    df = clean_and_fix_columns(df)
    # فلترة الأعمدة حسب الجدول
    allowed = {
        'Trades': ['symbol', 'company_name', 'sector', 'asset_type', 'date', 'quantity', 'entry_price', 'strategy', 'status'],
        'Deposits': ['date', 'amount', 'note'],
        'Withdrawals': ['date', 'amount', 'note']
    }
    if table_name in allowed:
        cols = [c for c in df.columns if c in allowed[table_name]]
        df = df[cols]
    
    records = df.to_dict('records')
    with get_db() as conn:
        with conn.cursor() as cur:
            for row in records:
                cols = list(row.keys())
                vals = [str(v) for v in row.values()]
                q = f"INSERT INTO {table_name} ({','.join(cols)}) VALUES ({','.join(['%s']*len(vals))})"
                try: cur.execute(q, vals)
                except: conn.rollback()
            conn.commit()
    return True

def view_settings():
    st.header("⚙️ الإعدادات")
    with st.expander("📥 استيراد ملف (Excel/CSV)"):
        f = st.file_uploader("اختر الملف", type=['xlsx', 'csv'])
        if f and st.button("استيراد"):
            try:
                if f.name.endswith('xlsx'): df = pd.read_excel(f)
                else: df = pd.read_csv(f)
                
                # منطق بسيط: إذا فيه quantity فهو صفقات، إذا amount فهو كاش
                tbl = "Trades"
                if 'amount' in df.columns or 'cost' in df.columns: tbl = "Deposits"
                
                save_dataframe_to_db(df, tbl)
                st.success("تم الاستيراد")
            except Exception as e: st.error(f"خطأ: {e}")
    
    if st.button("حذف كل البيانات"):
        clear_all_data()
        st.warning("تم الحذف"); st.rerun()

def view_cash_log():
    st.header("💵 السجلات")
    fin = calculate_portfolio_metrics()
    t1,t2 = st.tabs(["إيداع", "سحب"])
    with t1: render_table(fin['deposits'], [('date','تاريخ'),('amount','مبلغ'),('note','ملاحظة')])
    with t2: render_table(fin['withdrawals'], [('date','تاريخ'),('amount','مبلغ')])

def view_add_trade():
    st.header("➕ إضافة")
    with st.form("add"):
        c1,c2=st.columns(2); s=c1.text_input("رمز"); t=c2.selectbox("نوع", ["استثمار","مضاربة","صكوك"])
        c3,c4,c5=st.columns(3); q=c3.number_input("كمية"); p=c4.number_input("سعر"); d=c5.date_input("تاريخ", date.today())
        if st.form_submit_button("حفظ"):
            execute_query("INSERT INTO Trades (symbol, company_name, date, quantity, entry_price, strategy, status) VALUES (%s,%s,%s,%s,%s,%s,'Open')", (s, s, str(d), q, p, t))
            st.success("تم"); st.cache_data.clear()

def view_backtester_ui(fin): st.header("🧪 المختبر"); st.info("قريباً")
def view_sukuk_portfolio(fin): st.header("📜 صكوك"); st.info("قائمة الصكوك")
def view_tools(): st.header("🛠️ أدوات"); st.info("حاسبة الزكاة")

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
