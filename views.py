import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time

# === الاستيرادات ===
from config import DEFAULT_COLORS, BACKUP_DIR
from components import render_navbar, render_kpi, render_table, render_ticker_card
from analytics import (calculate_portfolio_metrics, update_prices, generate_equity_curve, calculate_historical_drawdown, run_backtest)
from database import execute_query, fetch_table, get_db, clear_all_data
from market_data import get_static_info, get_tasi_data, get_chart_history
from data_source import get_company_details

# دوال وهمية
try: from charts import view_advanced_chart
except ImportError: view_advanced_chart = lambda s: st.info("الشارت غير متوفر")
try: from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui, get_thesis, save_thesis
except ImportError: 
    get_fundamental_ratios = lambda s: {'Score': 0, 'Opinions': [], 'P/E':0, 'P/B':0, 'ROE':0, 'Fair_Value':0}
    render_financial_dashboard_ui = lambda s: None
    get_thesis = lambda s: None
    save_thesis = lambda s,t,tg,r: None
try: from classical_analysis import render_classical_analysis
except ImportError: render_classical_analysis = lambda s: st.info("التحليل الكلاسيكي غير متوفر")

# ==========================================
# 1. الدوال المساعدة
# ==========================================

def safe_fmt(val, suffix=""):
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

# ==========================================
# 2. منطق الاستيراد (كما هو - ممتاز)
# ==========================================

def clean_and_fix_columns(df, table_name):
    if df is None or df.empty: return None
    df.columns = df.columns.astype(str).str.strip().str.lower()
    if 'id' in df.columns: df = df.drop(columns=['id'])

    if table_name in ['Deposits', 'Withdrawals']:
        df['final_note'] = ''
        for col in ['source', 'reason', 'note', 'notes', 'statement', 'المصدر', 'السبب', 'ملاحظات']:
            if col in df.columns:
                df['final_note'] = df['final_note'] + ' ' + df[col].astype(str).replace('nan', '').replace('None', '')
        df['note'] = df['final_note'].str.strip()
        if 'amount' not in df.columns:
            for c in ['cost', 'value', 'المبلغ', 'القيمة']:
                if c in df.columns: df['amount'] = df[c]; break
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
            'القطاع': 'sector',
            'الكمية': 'quantity', 'qty': 'quantity',
            'السعر': 'entry_price', 'price': 'entry_price', 'cost': 'entry_price',
            'التاريخ': 'date',
            'الاستراتيجية': 'strategy', 'type': 'strategy',
            'الحالة': 'status'
        }
        df.rename(columns=mapping, inplace=True)
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            for idx, row in df.iterrows():
                if 'strategy' not in df.columns or pd.isna(row.get('strategy')): df.at[idx, 'strategy'] = 'استثمار'
                if 'company_name' not in df.columns or pd.isna(row.get('company_name')):
                    name, sec = get_company_details(row['symbol'])
                    if name: df.at[idx, 'company_name'] = name
                    if sec and ('sector' not in df.columns or pd.isna(row.get('sector'))): df.at[idx, 'sector'] = sec

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
    if clean_df is None or clean_df.empty: return False, "الملف غير صالح"
    for col in clean_df.columns:
        if 'date' in col: clean_df[col] = pd.to_datetime(clean_df[col], errors='coerce').dt.strftime('%Y-%m-%d')
        elif col in ['amount', 'quantity', 'entry_price', 'exit_price', 'current_price']:
            clean_df[col] = pd.to_numeric(clean_df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    clean_df = clean_df.dropna(subset=['date'])
    records = clean_df.to_dict('records')
    count = 0
    with get_db() as conn:
        if not conn: return False, "فشل الاتصال"
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
# 3. الصفحات (Views)
# ==========================================

def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    C = DEFAULT_COLORS
    arrow, cl = ("🔼", C['success']) if t_change >= 0 else ("🔽", C['danger'])
    
    st.markdown(f"""
    <div class="tasi-box">
        <div><div style="font-size:1.1rem; color:{C['sub_text']};">المؤشر العام</div><div style="font-size:2.2rem; font-weight:900; color:{C['main_text']};">{t_price:,.2f}</div></div>
        <div style="background:{cl}15; color:{cl}; padding:8px 20px; border-radius:10px; font-weight:bold; direction:ltr;">{arrow} {t_change:+.2f}%</div>
    </div>""", unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    total_inv = fin['total_deposited'] - fin['total_withdrawn']
    with c1: render_kpi("الكاش المتوفر", f"{fin['cash']:,.2f}", "blue")
    with c2: render_kpi("صافي الاستثمار", f"{total_inv:,.2f}")
    with c3: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}")
    tpl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("الربح/الخسارة", f"{tpl:,.2f}", tpl)
    
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
    
    # === الأيقونات والملخص ===
    if not df.empty:
        op = df[df['status']=='Open'].copy()
        market_val = op['quantity'].mul(op['current_price']).sum() if not op.empty else 0
        total_cost = op['quantity'].mul(op['entry_price']).sum() if not op.empty else 0
        unrealized = market_val - total_cost
        
        c1, c2, c3, c4 = st.columns(4)
        with c1: render_kpi("قيمة المحفظة", f"{market_val:,.2f}", "blue")
        with c2: render_kpi("التكلفة", f"{total_cost:,.2f}")
        with c3: render_kpi("الربح غير المحقق", f"{unrealized:,.2f}", unrealized)
        with c4: render_kpi("عدد الشركات", f"{len(op)}")
        st.markdown("---")

    if df.empty: st.info(f"محفظة {ts} فارغة."); return

    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()
    
    if not open_df.empty:
        open_df['total_cost'] = open_df['quantity'] * open_df['entry_price']
        open_df['market_value'] = open_df['quantity'] * open_df['current_price']
        open_df['gain'] = open_df['market_value'] - open_df['total_cost']
        open_df['gain_pct'] = (open_df['gain'] / open_df['total_cost'] * 100).fillna(0)

    t1, t2, t3 = st.tabs(["الأسهم الحالية", "تحليل الأداء", "الأرشيف (مغلقة)"])
    with t1:
        if not open_df.empty:
            cols = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'متوسط'), ('current_price', 'حالي'), ('market_value', 'القيمة'), ('gain', 'الربح'), ('gain_pct', '%')]
            render_table(apply_sorting(open_df, cols, page_key), cols)
            
            with st.expander("بيع"):
                with st.form("sell"):
                    c1,c2 = st.columns(2)
                    s = c1.selectbox("السهم", open_df['symbol'].unique())
                    p = c2.number_input("سعر البيع")
                    d = st.date_input("التاريخ", date.today())
                    if st.form_submit_button("تأكيد"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, ts))
                        st.success("تم"); st.cache_data.clear(); st.rerun()
        else: st.info("لا توجد مراكز مفتوحة")
    
    with t2:
        if not open_df.empty and page_key == 'invest':
            fig = px.pie(open_df, values='market_value', names='sector', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
    with t3:
        if not closed_df.empty: 
            closed_df['realized_gain'] = (closed_df['exit_price'] - closed_df['entry_price']) * closed_df['quantity']
            render_table(closed_df, [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('exit_price', 'سعر البيع'), ('realized_gain', 'الربح المحقق'), ('exit_date', 'تاريخ')])

def view_cash_log():
    st.header("💵 سجل السيولة")
    fin = calculate_portfolio_metrics()
    
    # === الأيقونات عادت ===
    c1, c2, c3 = st.columns(3)
    net = fin['deposits']['amount'].sum() - fin['withdrawals']['amount'].sum()
    with c1: render_kpi("إجمالي الإيداعات", f"{fin['deposits']['amount'].sum():,.2f}", "success")
    with c2: render_kpi("إجمالي السحوبات", f"{fin['withdrawals']['amount'].sum():,.2f}", "danger")
    with c3: render_kpi("صافي التمويل", f"{net:,.2f}", "blue")
    st.markdown("---")

    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "التوزيعات"])
    
    # === إعادة نماذج الإضافة اليدوية ===
    with t1:
        with st.expander("➕ تسجيل إيداع جديد"):
            with st.form("new_dep"):
                col_a, col_b = st.columns(2)
                amt = col_a.number_input("المبلغ", min_value=0.0, step=100.0)
                dt = col_b.date_input("التاريخ", date.today())
                nt = st.text_input("ملاحظة / المصدر")
                if st.form_submit_button("حفظ الإيداع"):
                    execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s, %s, %s)", (str(dt), amt, nt))
                    st.success("تم الحفظ"); st.rerun()
        render_table(fin['deposits'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
        
    with t2:
        with st.expander("➖ تسجيل سحب جديد"):
            with st.form("new_wit"):
                col_a, col_b = st.columns(2)
                amt = col_a.number_input("المبلغ", min_value=0.0, step=100.0)
                dt = col_b.date_input("التاريخ", date.today())
                nt = st.text_input("ملاحظة / السبب")
                if st.form_submit_button("حفظ السحب"):
                    execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s, %s, %s)", (str(dt), amt, nt))
                    st.success("تم الحفظ"); st.rerun()
        render_table(fin['withdrawals'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
        
    with t3:
        with st.expander("💰 تسجيل توزيعات/عوائد"):
            with st.form("new_ret"):
                col_a, col_b, col_c = st.columns(3)
                sym = col_a.text_input("رمز السهم")
                amt = col_b.number_input("المبلغ", min_value=0.0)
                dt = col_c.date_input("التاريخ", date.today())
                nt = st.text_input("نوع التوزيع (مثلاً: ربع سنوي)")
                if st.form_submit_button("حفظ العائد"):
                    comp_name, _ = get_company_details(sym)
                    execute_query("INSERT INTO ReturnsGrants (date, symbol, company_name, amount, note) VALUES (%s, %s, %s, %s, %s)", (str(dt), sym, comp_name, amt, nt))
                    st.success("تم الحفظ"); st.rerun()
        render_table(fin['returns'], [('date','التاريخ'), ('symbol','الرمز'), ('amount','المبلغ'), ('note', 'النوع')])

# === استعادة صفحة "إضافة صفقة" اليدوية ===
def view_add_trade():
    st.header("➕ تسجيل صفقة جديدة")
    with st.container():
        st.info("استخدم هذه الصفحة لإضافة صفقات شراء فردية يدوياً.")
        with st.form("add_manual_trade"):
            c1, c2 = st.columns(2)
            sym = c1.text_input("رمز السهم (مثال: 1120)")
            strat = c2.selectbox("المحفظة / الاستراتيجية", ["استثمار", "مضاربة", "صكوك"])
            
            c3, c4, c5 = st.columns(3)
            qty = c3.number_input("الكمية", min_value=1)
            price = c4.number_input("سعر الشراء", min_value=0.0, step=0.01)
            dt = c5.date_input("تاريخ الشراء", date.today())
            
            if st.form_submit_button("حفظ الصفقة"):
                if sym and qty > 0 and price > 0:
                    name, sector = get_company_details(sym)
                    atype = "Sukuk" if strat == "صكوك" else "Stock"
                    execute_query(
                        """INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Open', %s)""", 
                        (sym, name, sector, atype, str(dt), qty, price, strat, price)
                    )
                    st.success("تمت الإضافة بنجاح!"); st.cache_data.clear()
                else:
                    st.error("الرجاء تعبئة جميع البيانات بشكل صحيح")

def view_analysis(fin):
    st.header("🔬 مركز التحليل الشامل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c1, c2 = st.columns([1, 2])
    ns = c1.text_input("بحث")
    if ns and ns not in syms: syms.insert(0, ns)
    sym = c2.selectbox("اختر", syms) if syms else None
    
    if sym:
        n, s = get_company_details(sym)
        st.markdown(f"### {n if n else sym} ({sym})")
        t1, t2, t3, t4, t5 = st.tabs(["📊 المؤشرات", "📑 القوائم", "📝 الأطروحة", "📈 الشارت", "🏛️ كلاسيكي"])
        with t1:
            d = get_fundamental_ratios(sym)
            c1,c2 = st.columns([1,3])
            c1.metric("التقييم", f"{d['Score']}/10")
            render_financial_dashboard_ui(sym)
        with t2: view_advanced_chart(sym)
        with t3: st.info("اذهب لصفحة المختبر للتحليل المتقدم")

def view_backtester_ui(fin):
    st.header("🧪 مختبر الاستراتيجيات")
    c1, c2, c3 = st.columns(3)
    with c1: 
        syms = list(set(fin['all_trades']['symbol'].unique().tolist() + ["1120"]))
        symbol = st.selectbox("السهم", syms)
    with c2: strat = st.selectbox("الاستراتيجية", ["Trend Follower (جون ميرفي)", "Sniper (هجين)"])
    with c3: cap = st.number_input("رأس المال", 100000)
    if st.button("🚀 تشغيل"):
        df_hist = get_chart_history(symbol, period="2y")
        if df_hist is not None and len(df_hist) > 50:
            res = run_backtest(df_hist, strat, cap)
            if res:
                c1, c2 = st.columns(2)
                c1.metric("العائد", f"{res['return_pct']:.2f}%")
                c2.metric("الرصيد النهائي", f"{res['final_value']:,.2f}")
                st.line_chart(res['df']['Portfolio_Value'])
                st.dataframe(res['trades_log'])
        else: st.error("بيانات غير كافية")

def view_settings():
    st.header("⚙️ الإعدادات")
    if st.button("🔎 فحص جدول الإيداعات"):
        d = fetch_table("Deposits")
        st.write(f"عدد صفوف الإيداع: {len(d)}")
        if not d.empty: st.dataframe(d.head())
        else: st.warning("الجدول فارغ")

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
            
        if count > 0: 
            time.sleep(1); st.cache_data.clear(); st.rerun()

    st.divider()
    if st.button("⚠️ تصفير البيانات (Format)", type="primary"):
        clear_all_data()
        st.warning("تم الحذف"); st.rerun()

def view_sukuk_portfolio(fin):
    st.header("📜 الصكوك")
    df = fin['all_trades']
    
    # === أيقونات الصكوك ===
    if not df.empty:
        sk = df[df['asset_type']=='Sukuk']
        if not sk.empty:
            total = sk['quantity'].mul(sk['entry_price']).sum()
            render_kpi("إجمالي الصكوك", f"{total:,.2f}", "blue")
            st.markdown("---")
            render_table(sk, [('company_name','الاسم'), ('quantity','العدد'), ('entry_price','الشراء')]); return
    st.info("لا توجد صكوك")

def view_tools():
    st.header("🛠️ الأدوات")
    fin = calculate_portfolio_metrics()
    st.info(f"الزكاة التقديرية: {fin['market_val_open']*0.025775:,.2f} ريال")

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
    elif pg == 'add': view_add_trade() # تم إعادة التوجيه للصفحة اليدوية
    elif pg == 'update': 
        with st.spinner("تحديث..."): update_prices()
        st.session_state.page='home'; st.rerun()
