import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time

# === الاستيرادات ===
from config import DEFAULT_COLORS, BACKUP_DIR
from components import render_navbar, render_kpi, render_table, render_ticker_card, safe_fmt
from analytics import (calculate_portfolio_metrics, update_prices, generate_equity_curve, calculate_historical_drawdown, run_backtest)
from database import execute_query, fetch_table, get_db, clear_all_data
from market_data import get_static_info, get_tasi_data, get_chart_history
from data_source import get_company_details
from charts import view_advanced_chart  # استيراد الشارت

try: from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui
except ImportError: 
    get_fundamental_ratios = lambda s: {'Score': 0}
    render_financial_dashboard_ui = lambda s: None

# ==========================================
# 1. دوال مساعدة
# ==========================================

def apply_sorting(df, cols_definition, key_suffix):
    """واجهة فرز عربية مع إخفاء العناوين الإنجليزية"""
    if df.empty: return df
    
    with st.expander("🔍 خيارات الترتيب", expanded=False):
        label_map = {label: col for col, label in cols_definition}
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.markdown("<p style='font-size:0.8rem; font-weight:bold; margin-bottom:0;'>رتب حسب:</p>", unsafe_allow_html=True)
            sort_col_label = st.selectbox("فرز", options=list(label_map.keys()), key=f"sc_{key_suffix}", label_visibility="collapsed")
        
        with c2:
            st.markdown("<p style='font-size:0.8rem; font-weight:bold; margin-bottom:0;'>الاتجاه:</p>", unsafe_allow_html=True)
            sort_order = st.radio("اتجاه", options=["تنازلي", "تصاعدي"], horizontal=True, key=f"so_{key_suffix}", label_visibility="collapsed")
            
    target_col = label_map[sort_col_label]
    try: return df.sort_values(by=target_col, ascending=(sort_order == "تصاعدي"))
    except: return df

# ==========================================
# 2. منطق الاستيراد
# ==========================================
def clean_and_fix_columns(df, table_name):
    if df is None or df.empty: return None
    df.columns = df.columns.astype(str).str.strip().str.lower()
    if 'id' in df.columns: df = df.drop(columns=['id'])

    if table_name in ['Deposits', 'Withdrawals']:
        if 'amount' not in df.columns:
            for c in ['cost', 'value', 'المبلغ']:
                if c in df.columns: df['amount'] = df[c]; break
        df = df.dropna(subset=['amount'])
        df['final_note'] = ''
        for col in ['source', 'reason', 'note', 'notes', 'statement']:
            if col in df.columns:
                df['final_note'] = df.apply(lambda r: (str(r['final_note']) + ' ' + str(r[col])) if str(r[col]) not in ['nan', 'None', ''] else str(r['final_note']), axis=1)
        df['note'] = df['final_note'].str.strip()
        target_cols = ['date', 'amount', 'note']
        for c in target_cols:
            if c not in df.columns: df[c] = None
        return df[target_cols]

    elif table_name == 'ReturnsGrants':
        if 'type' in df.columns: df.rename(columns={'type': 'note'}, inplace=True)
        target_cols = ['date', 'symbol', 'company_name', 'amount', 'note']
        if 'symbol' in df.columns: df['symbol'] = df['symbol'].astype(str).str.replace(r'\.0$', '', regex=True)
        for c in target_cols:
            if c not in df.columns: df[c] = None
        return df[target_cols]

    elif table_name == 'Trades':
        mapping = {
            'الرمز': 'symbol', 'ticker': 'symbol', 'code': 'symbol',
            'الشركة': 'company_name', 'company': 'company_name',
            'القطاع': 'sector', 'الكمية': 'quantity', 'qty': 'quantity',
            'السعر': 'entry_price', 'price': 'entry_price', 'cost': 'entry_price',
            'التاريخ': 'date', 'الاستراتيجية': 'strategy', 'type': 'strategy',
            'الحالة': 'status'
        }
        df.rename(columns=mapping, inplace=True)
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            df = df.dropna(subset=['symbol'])
            for idx, row in df.iterrows():
                if 'strategy' not in df.columns or pd.isna(row.get('strategy')):
                    df.at[idx, 'strategy'] = 'استثمار'
                if 'company_name' not in df.columns or pd.isna(row.get('company_name')):
                    name, sec = get_company_details(row['symbol'])
                    if name: df.at[idx, 'company_name'] = name
                    if sec: df.at[idx, 'sector'] = sec
        if 'status' not in df.columns: df['status'] = 'Open'
        if 'strategy' not in df.columns: df['strategy'] = 'استثمار'
        if 'asset_type' not in df.columns: df['asset_type'] = 'Stock'
        target_cols = ['symbol', 'company_name', 'sector', 'asset_type', 'date', 'quantity', 'entry_price', 'strategy', 'status', 'exit_date', 'exit_price', 'current_price']
        for c in target_cols:
            if c not in df.columns: df[c] = None
        return df[target_cols]
    return None

def save_dataframe_to_db(df, table_name):
    clean_df = clean_and_fix_columns(df, table_name)
    if clean_df is None or clean_df.empty: return False, "الملف فارغ"
    if table_name == 'Trades': clean_df = clean_df[clean_df['quantity'] > 0]
    if table_name in ['Deposits', 'Withdrawals']: clean_df = clean_df[clean_df['amount'] > 0]
    for col in clean_df.columns:
        if 'date' in col: clean_df[col] = pd.to_datetime(clean_df[col], errors='coerce').dt.strftime('%Y-%m-%d')
        elif col in ['amount', 'quantity', 'entry_price', 'exit_price', 'current_price']:
            clean_df[col] = pd.to_numeric(clean_df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    clean_df = clean_df.dropna(subset=['date'])
    records = clean_df.to_dict('records')
    count = 0
    with get_db() as conn:
        with conn.cursor() as cur:
            for row in records:
                cols = list(row.keys())
                vals = [None if pd.isna(v) or v == '' else v for v in row.values()]
                placeholders = ', '.join(['%s'] * len(vals))
                q = f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})"
                try: cur.execute(q, vals); conn.commit(); count += 1
                except: conn.rollback()
    return True, f"تم استيراد {count} سجل"

# ==========================================
# 3. الصفحات
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
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title="نمو المحفظة"), use_container_width=True)

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
    
    # === تجهيز البيانات والأعمدة (التعديل هنا: تحويل البيانات لأرقام إجبارياً) ===
    if not df.empty:
        # 1. تحويل الأعمدة الرقمية لضمان عدم وجود نصوص
        cols_to_numeric = ['quantity', 'entry_price', 'current_price', 'exit_price']
        for c in cols_to_numeric:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)

        # 2. التأكد من وجود prev_close كرقم
        if 'prev_close' not in df.columns: 
            df['prev_close'] = df['current_price']
        else:
            df['prev_close'] = pd.to_numeric(df['prev_close'], errors='coerce').fillna(df['current_price'])

        # 3. بيانات إضافية
        if 'year_high' not in df.columns: df['year_high'] = 0.0
        if 'year_low' not in df.columns: df['year_low'] = 0.0
        
        # 4. الحسابات
        df['total_cost'] = df['quantity'] * df['entry_price']
        df['market_value'] = df['quantity'] * df['current_price']
        
        # حساب التغير اليومي (الآن آمن)
        df['daily_change'] = df.apply(lambda x: ((x['current_price'] - x['prev_close']) / x['prev_close'] * 100) if x['prev_close'] > 0 else 0.0, axis=1)

        # حساب الوزن (للمفتوح)
        total_market_open = df[df['status']=='Open']['market_value'].sum()
        df['weight'] = df.apply(lambda x: (x['market_value'] / total_market_open * 100) if x['status']=='Open' and total_market_open > 0 else 0, axis=1)
        
        # الربح والخسارة
        df['gain'] = df.apply(lambda x: (x['market_value'] - x['total_cost']) if x['status']=='Open' else ((x['exit_price'] - x['entry_price']) * x['quantity']), axis=1)
        df['gain_pct'] = (df['gain'] / df['total_cost'] * 100).fillna(0)

    # === تعريف الأعمدة المطلوبة بالترتيب ===
    COLS_FULL = [
        ('company_name', 'اسم الشركة'), 
        ('sector', 'القطاع'), 
        ('status', 'الحالة'),
        ('symbol', 'رمز الشركة'), 
        ('date', 'تاريخ الشراء'), 
        ('exit_date', 'تاريخ البيع'),
        ('quantity', 'الكمية'), 
        ('entry_price', 'سعر الشراء'), 
        ('total_cost', 'التكلفة'),
        ('year_high', 'اعلى سنوي'), 
        ('current_price', 'السعر الحالي'), 
        ('year_low', 'ادنى سنوي'),
        ('market_value', 'سعر السوق'), 
        ('gain', 'الربح والخسارة'), 
        ('gain_pct', 'نسبة الربح والخسارة'),
        ('weight', 'وزن السهم'), 
        ('daily_change', 'نسبة التغير اليومي'), 
        ('prev_close', 'اغلاق الامس')
    ]

    if not df.empty:
        op = df[df['status']=='Open'].copy()
        market_val = op['quantity'].mul(op['current_price']).sum() if not op.empty else 0
        total_cost = op['quantity'].mul(op['entry_price']).sum() if not op.empty else 0
        unrealized = market_val - total_cost
        
        cl = df[df['status']=='Close'].copy()
        realized_profit = ((cl['exit_price'] - cl['entry_price']) * cl['quantity']).sum() if not cl.empty else 0

        c1, c2, c3, c4 = st.columns(4)
        with c1: render_kpi("القيمة السوقية", safe_fmt(market_val), "blue")
        with c2: render_kpi("التكلفة", safe_fmt(total_cost))
        with c3: render_kpi("الربح العائم", safe_fmt(unrealized), unrealized)
        with c4: render_kpi("الربح المحقق", safe_fmt(realized_profit), realized_profit)
        st.markdown("---")

    if df.empty: st.info("المحفظة فارغة"); return

    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()

    t1, t2, t3 = st.tabs(["الأسهم الحالية", "تحليل الأداء", "الأرشيف"])
    with t1:
        if not open_df.empty:
            render_table(apply_sorting(open_df, COLS_FULL, page_key), COLS_FULL)
            
            with st.expander("🔻 بيع سهم"):
                with st.form("sell"):
                    c1,c2 = st.columns(2)
                    st.markdown("<div style='font-size:0.8rem; font-weight:bold;'>اختر السهم:</div>", unsafe_allow_html=True)
                    s = c1.selectbox("s", open_df['symbol'].unique(), label_visibility="collapsed")
                    st.markdown("<div style='font-size:0.8rem; font-weight:bold;'>سعر البيع:</div>", unsafe_allow_html=True)
                    p = c2.number_input("p", min_value=0.0, label_visibility="collapsed")
                    st.markdown("<div style='font-size:0.8rem; font-weight:bold;'>تاريخ البيع:</div>", unsafe_allow_html=True)
                    d = st.date_input("d", date.today(), label_visibility="collapsed")
                    if st.form_submit_button("تأكيد البيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, ts))
                        st.success("تم البيع"); time.sleep(0.5); st.rerun()
        else: st.info("لا توجد أسهم حالية")
    
    with t2:
        if not open_df.empty and page_key == 'invest':
            fig = px.pie(open_df, values='market_value', names='sector', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            
    with t3:
        if not closed_df.empty: 
            closed_df['net_sales'] = closed_df['quantity'] * closed_df['exit_price']
            closed_df['realized_gain'] = closed_df['net_sales'] - closed_df['total_cost']
            closed_df['gain_pct'] = (closed_df['realized_gain'] / closed_df['total_cost'] * 100).fillna(0)
            
            sum_gain = closed_df['realized_gain'].sum()
            sum_sales = closed_df['net_sales'].sum()
            total_pct = (sum_gain / closed_df['total_cost'].sum() * 100) if closed_df['total_cost'].sum() else 0
            
            c_a, c_b, c_c = st.columns(3)
            with c_a: render_kpi("صافي البيع", safe_fmt(sum_sales), "blue")
            with c_b: render_kpi("إجمالي الربح", safe_fmt(sum_gain), sum_gain)
            with c_c: render_kpi("النسبة الكلية", safe_fmt(total_pct)+"%", sum_gain)
            
            # إضافة أعمدة خاصة بالأرشيف للجداول
            ARCHIVE_COLS = COLS_FULL + [('net_sales', 'صافي البيع'), ('realized_gain', 'الربح المحقق')]
            render_table(closed_df, ARCHIVE_COLS)
        else: st.info("الأرشيف فارغ")

def view_cash_log():
    st.header("💵 سجل السيولة")
    fin = calculate_portfolio_metrics()
    c1, c2, c3 = st.columns(3)
    net = fin['deposits']['amount'].sum() - fin['withdrawals']['amount'].sum()
    with c1: render_kpi("إجمالي الإيداعات", safe_fmt(fin['deposits']['amount'].sum()), "success")
    with c2: render_kpi("إجمالي السحوبات", safe_fmt(fin['withdrawals']['amount'].sum()), "danger")
    with c3: render_kpi("صافي التمويل", safe_fmt(net), "blue")
    st.markdown("---")

    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "التوزيعات"])
    with t1:
        with st.expander("➕ تسجيل إيداع جديد"):
            with st.form("new_dep"):
                c1, c2 = st.columns(2)
                st.markdown("**المبلغ:**")
                amt = c1.number_input("d_a", min_value=0.0, step=100.0, label_visibility="collapsed")
                st.markdown("**التاريخ:**")
                dt = c2.date_input("d_d", date.today(), label_visibility="collapsed")
                st.markdown("**ملاحظة:**")
                nt = st.text_input("d_n", label_visibility="collapsed")
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s, %s, %s)", (str(dt), amt, nt))
                    st.success("تم"); st.rerun()
        render_table(fin['deposits'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
    
    with t2:
        with st.expander("➖ تسجيل سحب جديد"):
            with st.form("new_wit"):
                c1, c2 = st.columns(2)
                st.markdown("**المبلغ:**")
                amt = c1.number_input("w_a", min_value=0.0, step=100.0, label_visibility="collapsed")
                st.markdown("**التاريخ:**")
                dt = c2.date_input("w_d", date.today(), label_visibility="collapsed")
                st.markdown("**السبب:**")
                nt = st.text_input("w_n", label_visibility="collapsed")
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s, %s, %s)", (str(dt), amt, nt))
                    st.success("تم"); st.rerun()
        render_table(fin['withdrawals'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
        
    with t3:
        with st.expander("💰 تسجيل توزيعات"):
            with st.form("new_ret"):
                c1, c2, c3 = st.columns(3)
                st.markdown("**الرمز:**")
                sym = c1.text_input("r_s", label_visibility="collapsed")
                st.markdown("**المبلغ:**")
                amt = c2.number_input("r_a", min_value=0.0, label_visibility="collapsed")
                st.markdown("**التاريخ:**")
                dt = c3.date_input("r_d", date.today(), label_visibility="collapsed")
                st.markdown("**النوع:**")
                nt = st.text_input("r_n", label_visibility="collapsed")
                if st.form_submit_button("حفظ"):
                    comp, _ = get_company_details(sym)
                    execute_query("INSERT INTO ReturnsGrants (date, symbol, company_name, amount, note) VALUES (%s, %s, %s, %s, %s)", (str(dt), sym, comp, amt, nt))
                    st.success("تم"); st.rerun()
        render_table(fin['returns'], [('date','التاريخ'), ('symbol','الرمز'), ('amount','المبلغ'), ('note', 'النوع')])

def view_add_trade():
    st.header("➕ تسجيل صفقة جديدة")
    with st.container():
        st.info("إضافة صفقات يدوياً.")
        with st.form("add_manual_trade"):
            c1, c2 = st.columns(2)
            st.markdown("**رمز السهم:**")
            sym = c1.text_input("t_s", label_visibility="collapsed")
            st.markdown("**المحفظة:**")
            strat = c2.selectbox("t_st", ["استثمار", "مضاربة", "صكوك"], label_visibility="collapsed")
            c3, c4, c5 = st.columns(3)
            st.markdown("**الكمية:**")
            qty = c3.number_input("t_q", min_value=1.0, label_visibility="collapsed")
            st.markdown("**السعر:**")
            price = c4.number_input("t_p", min_value=0.0, step=0.01, label_visibility="collapsed")
            st.markdown("**التاريخ:**")
            dt = c5.date_input("t_d", date.today(), label_visibility="collapsed")
            if st.form_submit_button("حفظ"):
                if sym and qty > 0 and price > 0:
                    comp, sec = get_company_details(sym)
                    atype = "Sukuk" if strat == "صكوك" else "Stock"
                    execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Open', %s)", (sym, comp, sec, atype, str(dt), qty, price, strat, price))
                    st.success("تم الحفظ"); st.cache_data.clear(); st.rerun()
                else: st.error("البيانات ناقصة")

def view_analysis(fin):
    st.header("🔬 مركز التحليل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c1, c2 = st.columns([1, 2])
    st.markdown("**بحث:**")
    ns = c1.text_input("s_search", label_visibility="collapsed")
    if ns and ns not in syms: syms.insert(0, ns)
    
    st.markdown("**اختر الشركة:**")
    sym = c2.selectbox("s_select", syms, label_visibility="collapsed") if syms else None
    
    if sym:
        n, s = get_company_details(sym)
        st.markdown(f"### {n if n else sym} ({sym})")
        # تمت إعادة ترتيب التبويبات والمحتوى كما كان
        t1, t2, t3, t4, t5 = st.tabs(["📊 المؤشرات", "📑 القوائم", "📝 الأطروحة", "📈 الشارت", "🏛️ كلاسيكي"])
        with t1:
            d = get_fundamental_ratios(sym)
            c1,c2 = st.columns([1,3])
            c1.metric("التقييم", f"{d['Score']}/10")
            render_financial_dashboard_ui(sym)
        with t2: st.info("بيانات القوائم المالية")
        with t3: st.info("مساحة كتابة الأطروحة")
        with t4: 
            view_advanced_chart(sym) # استخدام الشارت القديم القوي
        with t5: st.info("التحليل الكلاسيكي")

def view_backtester_ui(fin):
    st.header("🧪 مختبر الاستراتيجيات")
    c1, c2, c3 = st.columns(3)
    with c1: 
        st.markdown("**السهم:**")
        syms = list(set(fin['all_trades']['symbol'].unique().tolist() + ["1120"]))
        symbol = st.selectbox("b_s", syms, label_visibility="collapsed")
    with c2: 
        st.markdown("**الاستراتيجية:**")
        strat = st.selectbox("b_st", ["Trend Follower", "Sniper"], label_visibility="collapsed")
    with c3: 
        st.markdown("**رأس المال:**")
        cap = st.number_input("b_c", 100000, label_visibility="collapsed")
        
    if st.button("🚀 تشغيل"):
        df_hist = get_chart_history(symbol, period="2y")
        if df_hist is not None and len(df_hist) > 50:
            res = run_backtest(df_hist, strat, cap)
            if res:
                c1, c2 = st.columns(2)
                c1.metric("العائد", safe_fmt(res['return_pct']) + "%")
                c2.metric("الرصيد النهائي", safe_fmt(res['final_value']))
                st.line_chart(res['df']['Portfolio_Value'])
        else: st.error("بيانات غير كافية")

def view_settings():
    st.header("⚙️ الإعدادات")
    st.markdown("### 📥 استيراد البيانات")
    uploaded_files = st.file_uploader("ملفات Excel/CSV", accept_multiple_files=True)
    if uploaded_files and st.button("بدء الاستيراد"):
        maps = {'trade': 'Trades', 'dep': 'Deposits', 'wit': 'Withdrawals', 'ret': 'ReturnsGrants'}
        count = 0
        for f in uploaded_files:
            try:
                tn = 'Trades'
                for k,v in maps.items():
                    if k in f.name.lower(): tn = v; break
                df = pd.read_excel(f) if f.name.endswith('xlsx') else pd.read_csv(f)
                ok, msg = save_dataframe_to_db(df, tn)
                if ok: 
                    st.success(f"✅ {f.name}: {msg}")
                    count += 1
                else: st.error(f"❌ {f.name}: {msg}")
            except Exception as e: st.error(f"خطأ في {f.name}: {e}")
        if count > 0: time.sleep(1); st.cache_data.clear(); st.rerun()

    st.divider()
    st.markdown("### ⚠️ إدارة البيانات")
    with st.expander("خيارات الحذف"):
        c1, c2 = st.columns(2)
        del_tr = c1.checkbox("حذف الصفقات")
        del_ca = c2.checkbox("حذف السيولة")
        if st.button("تأكيد الحذف"):
            if del_tr: execute_query("TRUNCATE TABLE Trades RESTART IDENTITY CASCADE;")
            if del_ca: 
                execute_query("TRUNCATE TABLE Deposits RESTART IDENTITY CASCADE;")
                execute_query("TRUNCATE TABLE Withdrawals RESTART IDENTITY CASCADE;")
                execute_query("TRUNCATE TABLE ReturnsGrants RESTART IDENTITY CASCADE;")
            st.success("تم الحذف"); time.sleep(1); st.rerun()

def view_sukuk_portfolio(fin):
    st.header("📜 الصكوك")
    df = fin['all_trades']
    if df.empty: st.info("لا توجد بيانات"); return
        
    sk = df[df['asset_type']=='Sukuk'].copy()
    if sk.empty: st.info("لا توجد صكوك"); return
    
    render_table(sk, [('company_name', 'اسم الصك'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'الشراء'), ('market_value', 'القيمة'), ('gain', 'الربح')])

def view_tools():
    st.header("🛠️ الأدوات")
    fin = calculate_portfolio_metrics()
    st.info(f"الزكاة التقديرية: {safe_fmt(fin['market_val_open']*0.025775)} ريال")

# === الموجه ===
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
