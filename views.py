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
# 1. دوال مساعدة (للتنسيق والتعريب)
# ==========================================

def safe_fmt(val, suffix=""):
    """تقريب صارم لمنزلتين عشريتين"""
    try:
        f_val = float(val)
        return f"{f_val:,.2f}{suffix}"
    except:
        return str(val)

def apply_sorting(df, cols_definition, key_suffix):
    """واجهة فرز معربة بالكامل وبدون نصوص إنجليزية"""
    if df.empty: return df
    
    with st.expander("🔍 خيارات الترتيب", expanded=False):
        label_map = {label: col for col, label in cols_definition}
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.markdown("###### رتب حسب:") # عنوان عربي بديل
            sort_col_label = st.selectbox(
                "رتب حسب", # Label مخفي
                options=list(label_map.keys()), 
                key=f"sort_col_{key_suffix}",
                label_visibility="collapsed" # إخفاء النص الإنجليزي
            )
        
        with c2:
            st.markdown("###### الاتجاه:") # عنوان عربي بديل
            sort_order = st.radio(
                "الاتجاه", # Label مخفي
                options=["تنازلي", "تصاعدي"], 
                horizontal=True,
                key=f"sort_dir_{key_suffix}",
                label_visibility="collapsed" # إخفاء النص الإنجليزي
            )
            
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
        df['final_note'] = ''
        for col in ['source', 'reason', 'note', 'notes', 'statement', 'المصدر', 'السبب', 'ملاحظات']:
            if col in df.columns:
                df['final_note'] = df.apply(lambda r: (str(r['final_note']) + ' ' + str(r[col])) if str(r[col]) not in ['nan', 'None', ''] else str(r['final_note']), axis=1)
        df['note'] = df['final_note'].str.strip()
        if 'amount' not in df.columns:
            for c in ['cost', 'value', 'المبلغ']:
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
            'الرمز': 'symbol', 'ticker': 'symbol', 
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
                if 'strategy' not in df.columns or pd.isna(row.get('strategy')):
                    df.at[idx, 'strategy'] = 'استثمار'
                if 'company_name' not in df.columns or pd.isna(row.get('company_name')):
                    name, sec = get_company_details(row['symbol'])
                    if name: df.at[idx, 'company_name'] = name
                    if sec and ('sector' not in df.columns or pd.isna(row.get('sector'))):
                        df.at[idx, 'sector'] = sec

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
# 3. الصفحات (Views) - محدثة بالتقريب والتعريب
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
    
    if not df.empty:
        op = df[df['status']=='Open'].copy()
        market_val = op['quantity'].mul(op['current_price']).sum() if not op.empty else 0
        total_cost = op['quantity'].mul(op['entry_price']).sum() if not op.empty else 0
        unrealized = market_val - total_cost
        
        cl = df[df['status']=='Close'].copy()
        realized_profit = 0
        if not cl.empty:
            realized_profit = ((cl['exit_price'] - cl['entry_price']) * cl['quantity']).sum()

        c1, c2, c3, c4 = st.columns(4)
        with c1: render_kpi("القيمة السوقية (مفتوح)", safe_fmt(market_val), "blue")
        with c2: render_kpi("التكلفة (مفتوح)", safe_fmt(total_cost))
        with c3: render_kpi("الربح غير المحقق", safe_fmt(unrealized), unrealized)
        with c4: render_kpi("الربح المحقق (أرشيف)", safe_fmt(realized_profit), realized_profit)
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
                    st.markdown("###### اختر السهم للبيع")
                    s = c1.selectbox("السهم", open_df['symbol'].unique(), label_visibility="collapsed")
                    st.markdown("###### سعر البيع")
                    p = c2.number_input("السعر", min_value=0.01, label_visibility="collapsed")
                    st.markdown("###### تاريخ البيع")
                    d = st.date_input("التاريخ", date.today(), label_visibility="collapsed")
                    if st.form_submit_button("تأكيد البيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, ts))
                        st.success("تم البيع"); st.cache_data.clear(); st.rerun()
        else: st.info("لا توجد مراكز مفتوحة")
    
    with t2:
        if not open_df.empty and page_key == 'invest':
            fig = px.pie(open_df, values='market_value', names='sector', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
    with t3:
        if not closed_df.empty: 
            closed_df['net_sales'] = closed_df['quantity'] * closed_df['exit_price']
            closed_df['total_cost'] = closed_df['quantity'] * closed_df['entry_price']
            closed_df['realized_gain'] = closed_df['net_sales'] - closed_df['total_cost']
            closed_df['gain_pct'] = (closed_df['realized_gain'] / closed_df['total_cost'] * 100).fillna(0)
            
            sum_gain = closed_df['realized_gain'].sum()
            sum_sales = closed_df['net_sales'].sum()
            total_pct = (sum_gain / closed_df['total_cost'].sum() * 100) if closed_df['total_cost'].sum() else 0
            
            c_a, c_b, c_c = st.columns(3)
            with c_a: render_kpi("صافي البيع", safe_fmt(sum_sales), "blue")
            with c_b: render_kpi("إجمالي الربح", safe_fmt(sum_gain), sum_gain)
            with c_c: render_kpi("نسبة الربح", safe_fmt(total_pct)+"%", sum_gain)
            
            render_table(closed_df, [
                ('company_name', 'الشركة'), ('symbol', 'الرمز'), 
                ('quantity', 'الكمية'), ('entry_price', 'شراء'), 
                ('exit_price', 'بيع'), ('net_sales', 'صافي البيع'), 
                ('realized_gain', 'الربح'), ('gain_pct', '%'), 
                ('exit_date', 'تاريخ')
            ])

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
                st.markdown("###### المبلغ")
                amt = c1.number_input("مبلغ", min_value=0.0, step=100.0, label_visibility="collapsed")
                st.markdown("###### التاريخ")
                dt = c2.date_input("تاريخ", date.today(), label_visibility="collapsed")
                st.markdown("###### ملاحظة")
                nt = st.text_input("ملاحظة", label_visibility="collapsed")
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s, %s, %s)", (str(dt), amt, nt))
                    st.success("تم"); st.rerun()
        render_table(fin['deposits'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
    
    with t2:
        with st.expander("➖ تسجيل سحب جديد"):
            with st.form("new_wit"):
                c1, c2 = st.columns(2)
                st.markdown("###### المبلغ")
                amt = c1.number_input("مبلغ", min_value=0.0, step=100.0, label_visibility="collapsed")
                st.markdown("###### التاريخ")
                dt = c2.date_input("تاريخ", date.today(), label_visibility="collapsed")
                st.markdown("###### السبب")
                nt = st.text_input("سبب", label_visibility="collapsed")
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s, %s, %s)", (str(dt), amt, nt))
                    st.success("تم"); st.rerun()
        render_table(fin['withdrawals'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
        
    with t3:
        with st.expander("💰 تسجيل توزيعات"):
            with st.form("new_ret"):
                c1, c2, c3 = st.columns(3)
                st.markdown("###### الرمز")
                sym = c1.text_input("رمز", label_visibility="collapsed")
                st.markdown("###### المبلغ")
                amt = c2.number_input("مبلغ", min_value=0.0, label_visibility="collapsed")
                st.markdown("###### التاريخ")
                dt = c3.date_input("تاريخ", date.today(), label_visibility="collapsed")
                st.markdown("###### النوع")
                nt = st.text_input("نوع", label_visibility="collapsed")
                if st.form_submit_button("حفظ"):
                    comp_name, _ = get_company_details(sym)
                    execute_query("INSERT INTO ReturnsGrants (date, symbol, company_name, amount, note) VALUES (%s, %s, %s, %s, %s)", (str(dt), sym, comp_name, amt, nt))
                    st.success("تم"); st.rerun()
        render_table(fin['returns'], [('date','التاريخ'), ('symbol','الرمز'), ('amount','المبلغ'), ('note', 'النوع')])

def view_add_trade():
    st.header("➕ تسجيل صفقة جديدة")
    with st.container():
        st.info("استخدم هذه الصفحة لإضافة صفقات شراء فردية يدوياً.")
        with st.form("add_manual_trade"):
            c1, c2 = st.columns(2)
            st.markdown("###### رمز السهم")
            sym = c1.text_input("الرمز", label_visibility="collapsed")
            st.markdown("###### المحفظة")
            strat = c2.selectbox("المحفظة", ["استثمار", "مضاربة", "صكوك"], label_visibility="collapsed")
            
            c3, c4, c5 = st.columns(3)
            st.markdown("###### الكمية")
            qty = c3.number_input("الكمية", min_value=1, label_visibility="collapsed")
            st.markdown("###### السعر")
            price = c4.number_input("السعر", min_value=0.0, step=0.01, label_visibility="collapsed")
            st.markdown("###### التاريخ")
            dt = c5.date_input("التاريخ", date.today(), label_visibility="collapsed")
            
            if st.form_submit_button("حفظ الصفقة"):
                if sym and qty > 0 and price > 0:
                    name, sector = get_company_details(sym)
                    atype = "Sukuk" if strat == "صكوك" else "Stock"
                    execute_query("""INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Open', %s)""", (sym, name, sector, atype, str(dt), qty, price, strat, price))
                    st.success("تمت الإضافة بنجاح!"); st.cache_data.clear()
                else: st.error("الرجاء تعبئة جميع البيانات")

def view_analysis(fin):
    st.header("🔬 مركز التحليل الشامل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c1, c2 = st.columns([1, 2])
    st.markdown("###### بحث عن رمز")
    ns = c1.text_input("بحث", label_visibility="collapsed")
    if ns and ns not in syms: syms.insert(0, ns)
    
    st.markdown("###### اختر الشركة")
    sym = c2.selectbox("اختر", syms, label_visibility="collapsed") if syms else None
    
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
        st.markdown("###### السهم")
        syms = list(set(fin['all_trades']['symbol'].unique().tolist() + ["1120"]))
        symbol = st.selectbox("سهم", syms, label_visibility="collapsed")
    with c2: 
        st.markdown("###### الاستراتيجية")
        strat = st.selectbox("استراتيجية", ["Trend Follower (جون ميرفي)", "Sniper (هجين)"], label_visibility="collapsed")
    with c3: 
        st.markdown("###### رأس المال")
        cap = st.number_input("رأس المال", 100000, label_visibility="collapsed")
        
    if st.button("🚀 تشغيل المحاكاة"):
        df_hist = get_chart_history(symbol, period="2y")
        if df_hist is not None and len(df_hist) > 50:
            res = run_backtest(df_hist, strat, cap)
            if res:
                c1, c2 = st.columns(2)
                c1.metric("العائد", safe_fmt(res['return_pct']) + "%")
                c2.metric("الرصيد النهائي", safe_fmt(res['final_value']))
                st.line_chart(res['df']['Portfolio_Value'])
                st.dataframe(res['trades_log'])
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
    with st.expander("خيارات الحذف (تصفير البيانات)"):
        st.warning("تحذير: هذا الإجراء لا يمكن التراجع عنه.")
        c1, c2 = st.columns(2)
        del_trades = c1.checkbox("حذف جميع الصفقات (Trades)", value=False)
        del_cash = c2.checkbox("حذف سجلات السيولة (إيداع/سحب/عوائد)", value=False)
        
        if st.button("تأكيد الحذف المحدد", type="primary"):
            if del_trades:
                execute_query("TRUNCATE TABLE Trades RESTART IDENTITY CASCADE;")
                st.success("تم حذف الصفقات.")
            if del_cash:
                execute_query("TRUNCATE TABLE Deposits RESTART IDENTITY CASCADE;")
                execute_query("TRUNCATE TABLE Withdrawals RESTART IDENTITY CASCADE;")
                execute_query("TRUNCATE TABLE ReturnsGrants RESTART IDENTITY CASCADE;")
                st.success("تم حذف السيولة.")
            if not del_trades and not del_cash:
                st.info("لم تقم باختيار أي شيء للحذف.")
            else:
                time.sleep(1); st.cache_data.clear(); st.rerun()

def view_sukuk_portfolio(fin):
    st.header("📜 الصكوك")
    df = fin['all_trades']
    
    if not df.empty:
        sk = df[df['asset_type']=='Sukuk']
        if not sk.empty:
            op_sk = sk[sk['status'] == 'Open'].copy()
            cl_sk = sk[sk['status'] == 'Close'].copy()
            
            t1, t2 = st.tabs(["الصكوك الحالية", "أرشيف الصكوك"])
            
            with t1:
                if not op_sk.empty:
                    total_val = op_sk['quantity'].mul(op_sk['entry_price']).sum()
                    render_kpi("إجمالي الصكوك الحالية", safe_fmt(total_val), "blue")
                    st.markdown("---")
                    render_table(op_sk, [('company_name','الاسم'), ('quantity','العدد'), ('entry_price','الشراء')])
                else: st.info("لا توجد صكوك قائمة")
            
            with t2:
                if not cl_sk.empty:
                    cl_sk['net_sales'] = cl_sk['quantity'] * cl_sk['exit_price']
                    cl_sk['realized_gain'] = cl_sk['net_sales'] - (cl_sk['quantity'] * cl_sk['entry_price'])
                    
                    sum_gain = cl_sk['realized_gain'].sum()
                    sum_sales = cl_sk['net_sales'].sum()
                    
                    c_a, c_b = st.columns(2)
                    with c_a: render_kpi("صافي بيع الصكوك", safe_fmt(sum_sales), "blue")
                    with c_b: render_kpi("إجمالي الربح المحقق", safe_fmt(sum_gain), sum_gain)
                    
                    render_table(cl_sk, [
                        ('company_name', 'الاسم'), ('quantity', 'العدد'), 
                        ('entry_price', 'شراء'), ('exit_price', 'بيع'), 
                        ('net_sales', 'صافي البيع'), ('realized_gain', 'الربح')
                    ])
                else: st.info("الأرشيف فارغ")
            return
    st.info("لا توجد بيانات صكوك")

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
