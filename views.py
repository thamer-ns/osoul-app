import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time

# === الاستيرادات ===
from config import DEFAULT_COLORS, BACKUP_DIR
from components import render_kpi, render_table, render_ticker_card, safe_fmt
from analytics import (calculate_portfolio_metrics, update_prices, create_smart_backup, 
                       generate_equity_curve, calculate_historical_drawdown)
from charts import render_technical_chart
from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui, get_thesis, save_thesis
from market_data import get_static_info, get_tasi_data, get_chart_history, fetch_batch_data
from database import execute_query, fetch_table, get_db, clear_all_data

# === استيراد الوحدات الاختيارية ===
try: from backtester import run_backtest
except ImportError: 
    def run_backtest(*args): return None

try: from classical_analysis import render_classical_analysis
except ImportError:
    def render_classical_analysis(s): st.info("التحليل الكلاسيكي غير متاح")

# === أدوات مساعدة للعرض ===
def safe_fmt_val(val, suffix=""):
    try: return f"{float(val):,.2f}{suffix}"
    except: return "-"

def apply_sorting(df, cols_definition, key_suffix):
    if df.empty: return df
    with st.expander("🔍 خيارات الفرز", expanded=False):
        label_to_col = {label: col for col, label in cols_definition}
        c1, c2 = st.columns([2, 1])
        with c1: selected = st.selectbox("فرز حسب:", list(label_to_col.keys()), key=f"sc_{key_suffix}")
        with c2: order = st.radio("الترتيب:", ["تنازلي", "تصاعدي"], horizontal=True, key=f"so_{key_suffix}")
    target = label_to_col[selected]
    try: return df.sort_values(by=target, ascending=(order == "تصاعدي"))
    except: return df

# === القائمة العلوية (كما صممتها أنت) ===
def render_navbar():
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

# === الصفحات ===
def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    C = DEFAULT_COLORS
    
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

    st.markdown("### 📊 الملخص المالي")
    c1, c2, c3, c4 = st.columns(4)
    total_pl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    
    with c1: render_kpi("الكاش المتوفر", f"{fin['cash']:,.2f}", "blue")
    with c2: render_kpi("رأس المال المستثمر", f"{(fin['total_deposited']-fin['total_withdrawn']):,.2f}")
    with c3: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}")
    with c4: render_kpi("صافي الربح الكلي", f"{total_pl:,.2f}", 'success' if total_pl >= 0 else 'danger')
    
    st.markdown("---")
    st.markdown("### 📈 نمو المحفظة")
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested'), use_container_width=True)

# === نبض السوق (مدمج ومصلح) ===
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

def view_portfolio(fin, page_key):
    target_strat = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {target_strat}")
    all_data = fin['all_trades']
    
    df = pd.DataFrame()
    if not all_data.empty:
        df = all_data[all_data['strategy'].astype(str).str.contains(target_strat, na=False)].copy()
    
    if df.empty: st.warning("المحفظة فارغة"); return

    if 'status' not in df.columns: df['status'] = 'Open'
    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()

    # حسابات
    if not open_df.empty:
        open_df['total_cost'] = open_df['quantity'] * open_df['entry_price']
        open_df['market_value'] = open_df['quantity'] * open_df['current_price']
        open_df['gain'] = open_df['market_value'] - open_df['total_cost']
        open_df['gain_pct'] = (open_df['gain'] / open_df['total_cost']) * 100

    t1, t2, t3 = st.tabs([f"القائمة ({len(open_df)})", "تحليل الأداء", f"الأرشيف ({len(closed_df)})"])
    
    with t1:
        if not open_df.empty:
            cols = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'ت.شراء'), ('current_price', 'سوق'), ('market_value', 'القيمة'), ('gain', 'الربح'), ('gain_pct', '%')]
            render_table(apply_sorting(open_df, cols, page_key), cols)
            
            with st.expander("🔴 تسجيل بيع"):
                with st.form(f"sell_{page_key}"):
                    c1,c2 = st.columns(2)
                    s = c1.selectbox("السهم", open_df['symbol'].unique())
                    p = c2.number_input("سعر البيع")
                    d = st.date_input("التاريخ", date.today())
                    if st.form_submit_button("تأكيد البيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, target_strat))
                        st.success("تم"); st.cache_data.clear(); st.rerun()
    with t2:
        if not open_df.empty:
            st.plotly_chart(px.pie(open_df, values='market_value', names='sector', title="التوزيع القطاعي"), use_container_width=True)
    with t3:
        if not closed_df.empty: render_table(closed_df, [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح'), ('exit_date', 'تاريخ البيع')])

def view_analysis(fin):
    st.header("🔬 مركز التحليل الشامل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c1,c2 = st.columns([1,2])
    ns = c1.text_input("بحث عن رمز")
    if ns and ns not in syms: syms.insert(0, ns)
    sym = c2.selectbox("اختر الشركة", syms) if syms else None
    
    if sym:
        n, s = get_static_info(sym)
        st.markdown(f"### {n} ({sym})")
        t1,t2,t3,t4,t5 = st.tabs(["📊 المؤشرات", "📈 التحليل الفني", "📑 القوائم المالية", "🏛️ الكلاسيكي", "📝 الأطروحة"])
        
        with t1:
            d = get_fundamental_ratios(sym)
            st.metric("التقييم", f"{d.get('Score',0)}/10")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("P/E", safe_fmt_val(d.get('P/E')))
            k2.metric("P/B", safe_fmt_val(d.get('P/B')))
            k3.metric("ROE", safe_fmt_val(d.get('ROE'), '%'))
            k4.metric("Fair Value", safe_fmt_val(d.get('Fair_Value')))
        with t2: render_technical_chart(sym)
        with t3: render_financial_dashboard_ui(sym)
        with t4: render_classical_analysis(sym)
        with t5:
            th = get_thesis(sym)
            with st.form("th"):
                tx = st.text_area("النص", value=th['thesis_text'] if th else "")
                tg = st.number_input("الهدف", value=th['target_price'] if th else 0.0)
                if st.form_submit_button("حفظ"): save_thesis(sym, tx, tg, "Hold"); st.success("تم")

def view_cash_log():
    st.header("💰 السيولة")
    fin = calculate_portfolio_metrics()
    c1,c2,c3 = st.columns(3)
    with c1: render_kpi("إجمالي الإيداعات", safe_fmt_val(fin['deposits']['amount'].sum()), "success")
    with c2: render_kpi("إجمالي السحوبات", safe_fmt_val(fin['withdrawals']['amount'].sum()), "danger")
    with c3: render_kpi("إجمالي العوائد", safe_fmt_val(fin['returns']['amount'].sum()), "blue")
    st.markdown("---")
    
    t1,t2,t3 = st.tabs(["الإيداعات", "السحوبات", "العوائد"])
    with t1:
        with st.expander("➕ تسجيل إيداع"):
            with st.form("d"):
                a=st.number_input("مبلغ"); d=st.date_input("تاريخ"); n=st.text_input("ملاحظة")
                if st.form_submit_button("حفظ"): execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s,%s,%s)", (str(d),a,n)); st.rerun()
        render_table(fin['deposits'], [('date','تاريخ'),('amount','مبلغ'),('note','ملاحظة')])
    with t2:
        with st.expander("➖ تسجيل سحب"):
            with st.form("w"):
                a=st.number_input("مبلغ"); d=st.date_input("تاريخ"); n=st.text_input("ملاحظة")
                if st.form_submit_button("حفظ"): execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s,%s,%s)", (str(d),a,n)); st.rerun()
        render_table(fin['withdrawals'], [('date','تاريخ'),('amount','مبلغ'),('note','ملاحظة')])
    with t3:
        with st.expander("💵 تسجيل عائد"):
            with st.form("r"):
                s=st.text_input("رمز"); a=st.number_input("مبلغ"); d=st.date_input("تاريخ")
                if st.form_submit_button("حفظ"): execute_query("INSERT INTO ReturnsGrants (date, symbol, amount) VALUES (%s,%s,%s)", (str(d),s,a)); st.rerun()
        render_table(fin['returns'], [('date','تاريخ'),('symbol','رمز'),('amount','مبلغ')])

def view_backtester_ui(fin):
    st.header("🧪 مختبر الاستراتيجيات")
    c1, c2, c3 = st.columns(3)
    
    # التأكد من وجود رموز
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
                with st.expander("سجل العمليات"): st.dataframe(res['trades_log'], use_container_width=True)
            else: st.error("بيانات غير كافية")

def view_sukuk_portfolio(fin):
    st.header("📜 الصكوك")
    df = fin['all_trades']
    if 'asset_type' in df.columns:
        sk = df[df['asset_type']=='Sukuk']
        if not sk.empty: render_table(sk, [('company_name','اسم'),('symbol','رمز'),('quantity','كمية'),('entry_price','سعر')])
        else: st.warning("لا يوجد")

def view_add_trade():
    st.header("➕ إضافة")
    with st.form("add"):
        c1,c2=st.columns(2); s=c1.text_input("رمز"); t=c2.selectbox("نوع", ["استثمار","مضاربة","صكوك"])
        c3,c4,c5=st.columns(3); q=c3.number_input("كمية"); p=c4.number_input("سعر"); d=c5.date_input("تاريخ", date.today())
        if st.form_submit_button("حفظ"):
            at = "Sukuk" if t=="صكوك" else "Stock"
            execute_query("INSERT INTO Trades (symbol, asset_type, date, quantity, entry_price, strategy, status) VALUES (%s,%s,%s,%s,%s,%s,'Open')", (s,at,str(d),q,p,t))
            st.success("تم"); st.cache_data.clear()

# === دالة الاستيراد (مهمة جداً) ===
def clean_and_fix_columns(df):
    if df is None: return None
    df.columns = df.columns.str.strip().str.lower()
    rename_map = {'source': 'note', 'reason': 'note', 'notes': 'note', 'cost': 'amount', 'value': 'amount'}
    df.rename(columns=rename_map, inplace=True)
    if 'id' in df.columns: df = df.drop(columns=['id'])
    return df

def save_dataframe_to_db(df, table_name):
    df = clean_and_fix_columns(df)
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
                tbl = "Trades"
                if 'amount' in df.columns: tbl = "Deposits"
                save_dataframe_to_db(df, tbl)
                st.success("تم الاستيراد")
            except Exception as e: st.error(f"خطأ: {e}")
            
    if st.button("حذف كل البيانات"):
        clear_all_data()
        st.warning("تم الحذف"); st.rerun()

def view_tools(): st.header("🛠️ أدوات"); st.info("الزكاة")

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
