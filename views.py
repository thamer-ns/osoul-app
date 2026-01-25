import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time

# الاستيرادات
from config import DEFAULT_COLORS
from components import render_navbar, render_kpi, render_table, render_ticker_card
from analytics import (calculate_portfolio_metrics, update_prices, generate_equity_curve, calculate_historical_drawdown)
from database import execute_query, fetch_table, get_db, clear_all_data
from market_data import get_static_info, get_tasi_data, get_chart_history

# استيرادات اختيارية
try: from charts import render_technical_chart
except: render_technical_chart = lambda s: st.info("الشارت غير متاح")
try: from backtester import run_backtest
except: run_backtest = lambda a,b,c: None
try: from financial_analysis import get_fundamental_ratios, get_thesis, save_thesis
except: 
    get_fundamental_ratios = lambda s: {'Score': 0, 'Opinions': [], 'P/E':0, 'P/B':0, 'ROE':0, 'Fair_Value':0}
    get_thesis = lambda s: None
    save_thesis = lambda s,t,tg,r: None

# --- دوال مساعدة ---
def clean_and_fix_columns(df, table_name):
    if df is None: return None
    df.columns = df.columns.str.strip().str.lower()
    rename_map = {'source': 'note', 'reason': 'note', 'notes': 'note', 'cost': 'amount', 'value': 'amount', 'type': 'strategy'}
    df.rename(columns=rename_map, inplace=True)
    if 'id' in df.columns: df = df.drop(columns=['id'])
    
    # تنظيف التواريخ والأرقام
    for col in df.columns:
        if 'date' in col:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d')
        if df[col].dtype == 'object':
            df[col] = df[col].astype(str).str.replace(',', '').str.strip()
    return df

def save_dataframe_to_db(df, table_name):
    df = clean_and_fix_columns(df, table_name)
    if df is None or df.empty: return
    records = df.to_dict('records')
    with get_db() as conn:
        with conn.cursor() as cur:
            for row in records:
                cols = list(row.keys())
                vals = [v for v in row.values()]
                placeholders = ', '.join(['%s'] * len(vals))
                q = f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})"
                try: cur.execute(q, vals)
                except: conn.rollback()
            conn.commit()

# --- الصفحات ---
def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    cl = DEFAULT_COLORS['success'] if t_change >= 0 else DEFAULT_COLORS['danger']
    
    st.markdown(f"""
    <div style="background:white; padding:20px; border-radius:12px; border:1px solid #DFE1E6; display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
        <div><div style="color:#5E6C84;">المؤشر العام</div><div style="font-size:2rem; font-weight:900; color:#172B4D;">{t_price:,.2f}</div></div>
        <div style="background:{cl}15; color:{cl}; padding:8px 20px; border-radius:8px; font-weight:bold; direction:ltr;">{t_change:+.2f}%</div>
    </div>""", unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    with c1: render_kpi("الكاش المتوفر", f"{fin['cash']:,.2f}", "blue")
    with c2: render_kpi("صافي الاستثمار", f"{(fin['total_deposited']-fin['total_withdrawn']):,.2f}")
    with c3: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}")
    with c4: render_kpi("الربح الكلي", f"{(fin['unrealized_pl']+fin['realized_pl']+fin['total_returns']):,.2f}", (fin['unrealized_pl']+fin['realized_pl']+fin['total_returns']))
    
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title="نمو المحفظة"), use_container_width=True)

def view_portfolio(fin, page_key):
    ts = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    all_d = fin['all_trades']
    df = all_d[all_d['strategy'].astype(str).str.contains(ts, na=False)].copy() if not all_d.empty else pd.DataFrame()
    
    if df.empty: st.info("فارغة"); return
    
    op = df[df['status']=='Open'].copy()
    cl = df[df['status']=='Close'].copy()
    
    if not op.empty:
        op['market_value'] = op['quantity'] * op['current_price']
        op['gain'] = op['market_value'] - (op['quantity']*op['entry_price'])
        op['gain_pct'] = (op['gain']/(op['quantity']*op['entry_price'])*100)

    t1, t2, t3 = st.tabs(["الأسهم الحالية", "توزيع القطاعات", "الأرشيف"])
    
    with t1:
        if not op.empty:
            cols = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'التكلفة'), ('current_price', 'السعر'), ('market_value', 'القيمة'), ('gain', 'الربح'), ('gain_pct', '%')]
            render_table(op, cols)
            with st.expander("تسجيل بيع"):
                with st.form("sell"):
                    c1,c2,c3 = st.columns(3)
                    s = c1.selectbox("السهم", op['symbol'].unique())
                    p = c2.number_input("سعر البيع")
                    d = c3.date_input("التاريخ", date.today())
                    if st.form_submit_button("بيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND status='Open'", (p, str(d), s))
                        st.success("تم"); st.rerun()
    
    with t2:
        if not op.empty and page_key == 'invest':
            col_a, col_b = st.columns([2, 1])
            with col_a:
                fig = px.pie(op, values='market_value', names='sector', hole=0.4, title="التوزيع الحالي")
                st.plotly_chart(fig, use_container_width=True)
            with col_b:
                st.markdown("#### الأهداف القطاعية")
                targets = fetch_table("SectorTargets")
                if not targets.empty: render_table(targets, [('sector', 'القطاع'), ('target_percentage', 'الهدف %')])
                else: st.info("لم تحدد أهدافاً بعد.")
    
    with t3:
        if not cl.empty: render_table(cl, [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح')])

def render_pulse_dashboard():
    st.header("💓 نبض السوق")
    trades = fetch_table("Trades")
    wl = fetch_table("Watchlist")
    
    symbols = set()
    if not trades.empty: symbols.update(trades[trades['status']=='Open']['symbol'].unique())
    if not wl.empty: symbols.update(wl['symbol'].unique())
    
    if not symbols: st.warning("لا توجد أسهم للمتابعة."); return
    
    # شبكة الأسعار (Ticker Grid)
    cols = st.columns(4)
    for i, sym in enumerate(symbols):
        # هنا نفترض البيانات موجودة في DB، وفي الواقع يجب تحديثها عبر زر "تحديث"
        row = trades[trades['symbol']==sym].iloc[0] if not trades[trades['symbol']==sym].empty else None
        price = row['current_price'] if row is not None else 0
        name = row['company_name'] if row is not None else sym
        
        with cols[i % 4]:
            render_ticker_card(sym, name, price, 0.0) # التغير 0 مؤقتاً

def view_tools():
    st.header("🛠️ أدوات المستثمر")
    t1, t2, t3 = st.tabs(["⚖️ حاسبة الزكاة", "🛡️ إدارة المخاطر", "📐 نقاط الارتكاز"])
    
    with t1:
        fin = calculate_portfolio_metrics()
        zakat = fin['market_val_open'] * 0.025775
        st.metric("الزكاة التقديرية (2.5775%)", f"{zakat:,.2f} ريال", help="على القيمة السوقية الحالية")
    
    with t2:
        st.markdown("##### حاسبة حجم الصفقة (Position Size)")
        cap = st.number_input("رأس المال الكلي", value=100000)
        risk = st.number_input("نسبة المخاطرة (%)", value=1.0)
        entry = st.number_input("سعر الدخول", value=0.0)
        stop = st.number_input("سعر وقف الخسارة", value=0.0)
        if entry > stop > 0:
            risk_amt = cap * (risk/100)
            shares = risk_amt / (entry - stop)
            st.success(f"الكمية المقترحة: {int(shares)} سهم")
            st.info(f"المبلغ المطلوب: {shares*entry:,.2f}")
    
    with t3:
        st.markdown("##### حساب الدعوم والمقاومات")
        h = st.number_input("القمة (High)")
        l = st.number_input("القاع (Low)")
        c = st.number_input("الإغلاق (Close)")
        if st.button("احسب"):
            pp = (h + l + c) / 3
            r1 = (2 * pp) - l
            s1 = (2 * pp) - h
            st.metric("الارتكاز (PP)", f"{pp:.2f}")
            c1, c2 = st.columns(2)
            c1.warning(f"مقاومة 1: {r1:.2f}"); c2.success(f"دعم 1: {s1:.2f}")

def view_analysis(fin):
    st.header("🔬 التحليل الشامل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c1, c2 = st.columns([1, 2])
    ns = c1.text_input("بحث رمز")
    if ns and ns not in syms: syms.insert(0, ns)
    sym = c2.selectbox("اختر السهم", syms) if syms else None
    
    if sym:
        n, s = get_static_info(sym); st.markdown(f"### {n} ({sym})")
        t1, t2, t3 = st.tabs(["البيانات المالية", "الأطروحة", "الشارت"])
        with t1:
            d = get_fundamental_ratios(sym)
            col1, col2 = st.columns(2)
            col1.metric("التقييم", f"{d['Score']}/10")
            col2.metric("القيمة العادلة", f"{d['Fair_Value']}")
            render_financial_dashboard_ui(sym)
        with t2:
            th = get_thesis(sym)
            with st.form("thesis_form"):
                txt = st.text_area("لماذا اشتريت/تراقب هذا السهم؟", value=th['thesis_text'] if th else "")
                tgt = st.number_input("السعر المستهدف", value=th['target_price'] if th else 0.0)
                if st.form_submit_button("حفظ الأطروحة"):
                    save_thesis(sym, txt, tgt, "Hold")
                    st.success("تم الحفظ")
        with t3: render_technical_chart(sym)

def view_settings():
    st.header("⚙️ الإعدادات")
    st.info("ارفع ملفاتك وسيقوم النظام بتصحيح الأعمدة تلقائياً.")
    fls = st.file_uploader("ملفات Excel/CSV", accept_multiple_files=True)
    if fls and st.button("استيراد"):
        maps = {'trades': 'Trades', 'dep': 'Deposits', 'wit': 'Withdrawals', 'watch': 'Watchlist'}
        for f in fls:
            try:
                t = next((v for k, v in maps.items() if k in f.name.lower()), 'Trades')
                df = pd.read_excel(f) if f.name.endswith('xlsx') else pd.read_csv(f)
                save_dataframe_to_db(df, t)
                st.success(f"تم {f.name} -> {t}")
            except Exception as e: st.error(f"خطأ {f.name}: {e}")
    
    if st.button("مسح كل البيانات (Format)", type="primary"):
        clear_all_data(); st.rerun()

def router():
    render_navbar()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    
    if pg == 'home': view_dashboard(fin)
    elif pg == 'pulse': render_pulse_dashboard()
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'sukuk': st.info("محفظة الصكوك")
    elif pg == 'tools': view_tools()
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'settings': view_settings()
    elif pg == 'add': 
        st.header("إضافة يدوية"); 
        with st.form("a"): 
            s = st.text_input("رمز"); q = st.number_input("كمية"); p = st.number_input("سعر")
            if st.form_submit_button("حفظ"): execute_query(f"INSERT INTO Trades (symbol, quantity, entry_price, status) VALUES ('{s}', {q}, {p}, 'Open')"); st.success("تم")
    elif pg == 'update':
        with st.spinner("تحديث الأسعار..."): update_prices(); st.session_state.page='home'; st.rerun()
