import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time

# === الاستيرادات ===
from config import DEFAULT_COLORS
from components import render_navbar, render_kpi, render_table, render_ticker_card
from analytics import (calculate_portfolio_metrics, update_prices, generate_equity_curve, calculate_historical_drawdown)
from database import execute_query, fetch_table, get_db, clear_all_data
from market_data import get_static_info, get_tasi_data
from data_source import get_company_details

# === دوال وهمية (للحماية) ===
try: from charts import render_technical_chart
except: render_technical_chart = lambda s: st.warning("الشارت غير متوفر")
try: from backtester import run_backtest
except: run_backtest = lambda a,b,c: None
try: from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui, get_thesis, save_thesis
except: 
    get_fundamental_ratios = lambda s: {'Score': 0, 'Opinions': [], 'P/E':0, 'P/B':0, 'ROE':0, 'Fair_Value':0}
    render_financial_dashboard_ui = lambda s: None
    get_thesis = lambda s: None
    save_thesis = lambda s,t,tg,r: None

# === 1. الدالة المخصصة لملفاتك (Fix) ===
def clean_and_fix_columns(df, table_name):
    """تنظيف البيانات وتجهيزها لقاعدة البيانات بناءً على ملفاتك"""
    if df is None or df.empty: return None
    
    # 1. توحيد أسماء الأعمدة وحذف المسافات
    df.columns = df.columns.astype(str).str.strip().str.lower()
    
    # 2. حذف عمود ID لأنه يسبب مشاكل مع قاعدة البيانات
    if 'id' in df.columns: 
        df = df.drop(columns=['id'])

    # --- معالجة جدول الصفقات (Trades) ---
    if table_name == 'Trades':
        # التأكد من وجود الأعمدة الأساسية
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
        
        # تحويل الرموز إلى نصوص (مهم جداً)
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str).str.replace('.0', '', regex=False).str.strip()
            
            # محاولة جلب الاسم والقطاع إذا كانا فارغين
            for idx, row in df.iterrows():
                if 'company_name' not in df.columns or pd.isna(row.get('company_name')):
                    name, sector = get_company_details(row['symbol'])
                    if name: df.at[idx, 'company_name'] = name
                    if sector and ('sector' not in df.columns or pd.isna(row.get('sector'))):
                        df.at[idx, 'sector'] = sector

        # تعبئة القيم الافتراضية
        if 'status' not in df.columns: df['status'] = 'Open'
        if 'strategy' not in df.columns: df['strategy'] = 'استثمار'
        if 'asset_type' not in df.columns: df['asset_type'] = 'Stock'
        
        # الأعمدة المطلوبة
        target_cols = ['symbol', 'company_name', 'sector', 'asset_type', 'date', 'quantity', 'entry_price', 'strategy', 'status', 'exit_date', 'exit_price', 'current_price']
        # إضافة النواقص كـ None
        for c in target_cols:
            if c not in df.columns: df[c] = None
            
        return df[target_cols]

    # --- معالجة جدول الإيداعات (Deposits) ---
    elif table_name == 'Deposits':
        # دمج source و note في عمود واحد
        df['final_note'] = ''
        if 'source' in df.columns: df['final_note'] = df['source'].astype(str).replace('nan', '')
        if 'note' in df.columns: df['final_note'] = df['final_note'] + ' ' + df['note'].astype(str).replace('nan', '')
        
        # إعادة التسمية
        df['note'] = df['final_note'].str.strip()
        
        target_cols = ['date', 'amount', 'note']
        for c in target_cols:
            if c not in df.columns: df[c] = None
            
        return df[target_cols]

    # --- معالجة جدول السحوبات (Withdrawals) ---
    elif table_name == 'Withdrawals':
        # دمج reason و note
        df['final_note'] = ''
        if 'reason' in df.columns: df['final_note'] = df['reason'].astype(str).replace('nan', '')
        if 'note' in df.columns: df['final_note'] = df['final_note'] + ' ' + df['note'].astype(str).replace('nan', '')
        
        df['note'] = df['final_note'].str.strip()
        
        target_cols = ['date', 'amount', 'note']
        for c in target_cols:
            if c not in df.columns: df[c] = None
            
        return df[target_cols]
    
    # --- معالجة التوزيعات (ReturnsGrants) ---
    elif table_name == 'ReturnsGrants':
        target_cols = ['date', 'symbol', 'company_name', 'amount']
        if 'symbol' in df.columns: df['symbol'] = df['symbol'].astype(str).str.replace('.0', '')
        
        for c in target_cols:
            if c not in df.columns: df[c] = None
        return df[target_cols]

    return None

def save_dataframe_to_db(df, table_name):
    clean_df = clean_and_fix_columns(df, table_name)
    if clean_df is None or clean_df.empty: return False, "الملف فارغ أو غير متوافق"
    
    # تنظيف التواريخ والأرقام أخيراً
    for col in clean_df.columns:
        if 'date' in col:
            clean_df[col] = pd.to_datetime(clean_df[col], errors='coerce').dt.strftime('%Y-%m-%d')
        elif col in ['amount', 'quantity', 'entry_price', 'exit_price']:
            clean_df[col] = pd.to_numeric(clean_df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    records = clean_df.to_dict('records')
    count = 0
    
    with get_db() as conn:
        if not conn: return False, "لا يوجد اتصال"
        with conn.cursor() as cur:
            for row in records:
                cols = list(row.keys())
                vals = [None if pd.isna(v) or v == '' else v for v in row.values()]
                placeholders = ', '.join(['%s'] * len(vals))
                q = f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})"
                try: 
                    cur.execute(q, vals)
                    count += 1
                except Exception as e: 
                    conn.rollback()
                    # طباعة الخطأ في الكونسول للمساعدة
                    print(f"Failed row in {table_name}: {e}")
            conn.commit()
            
    return True, f"تم استيراد {count} صف بنجاح"

# === 2. الصفحات ===

def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    C = DEFAULT_COLORS
    arrow = "🔼" if t_change >= 0 else "🔽"
    cl = C['success'] if t_change >= 0 else C['danger']
    
    st.markdown(f"""
    <div class="tasi-box">
        <div>
            <div style="font-size:1.1rem; color:{C['sub_text']};">المؤشر العام</div>
            <div style="font-size:2.2rem; font-weight:900; color:{C['main_text']};">{t_price:,.2f}</div>
        </div>
        <div style="background:{cl}15; color:{cl}; padding:8px 20px; border-radius:10px; font-weight:bold; direction:ltr;">{arrow} {t_change:+.2f}%</div>
    </div>""", unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    total_inv = fin['total_deposited'] - fin['total_withdrawn']
    total_pl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    
    with c1: render_kpi("الكاش المتوفر", f"{fin['cash']:,.2f}", "blue")
    with c2: render_kpi("صافي الاستثمار", f"{total_inv:,.2f}")
    with c3: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}")
    with c4: render_kpi("الربح/الخسارة", f"{total_pl:,.2f}", total_pl)
    
    st.markdown("---")
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: 
        st.markdown("##### 📈 نمو المحفظة")
        st.plotly_chart(px.line(crv, x='date', y='cumulative_invested'), use_container_width=True)

def render_pulse_dashboard():
    st.header("💓 نبض السوق")
    trades = fetch_table("Trades")
    wl = fetch_table("Watchlist")
    
    symbols = set()
    if not trades.empty: symbols.update(trades[trades['status']=='Open']['symbol'].unique())
    if not wl.empty: symbols.update(wl['symbol'].unique())
    
    if not symbols:
        st.warning("القائمة فارغة. أضف أسهم للمحفظة.")
        return
        
    cols = st.columns(4)
    for i, sym in enumerate(symbols):
        # البحث عن السعر والاسم
        name, _ = get_company_details(sym)
        name = name if name else sym
        price = 0.0
        
        # محاولة إيجاد السعر
        if not trades.empty:
            row = trades[trades['symbol'] == sym]
            if not row.empty:
                price = row.iloc[0]['current_price']
                
        with cols[i % 4]:
            render_ticker_card(sym, name, price, 0.0)

def view_portfolio(fin, page_key):
    ts = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    all_d = fin['all_trades']
    
    df = pd.DataFrame()
    if not all_d.empty:
        df = all_d[all_d['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    if df.empty: st.info("المحفظة فارغة."); return
    
    op = df[df['status']=='Open'].copy()
    cl = df[df['status']=='Close'].copy()
    
    # تحديث الحسابات للعرض
    if not op.empty:
        op['total_cost'] = op['quantity'] * op['entry_price']
        op['market_value'] = op['quantity'] * op['current_price']
        op['gain'] = op['market_value'] - op['total_cost']
        op['gain_pct'] = (op['gain'] / op['total_cost'] * 100).fillna(0)

    t1, t2, t3 = st.tabs(["الأسهم الحالية", "تحليل", "الأرشيف"])
    with t1:
        if not op.empty:
            cols = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'التكلفة'), ('current_price', 'السعر'), ('market_value', 'القيمة'), ('gain', 'الربح'), ('gain_pct', '%')]
            render_table(apply_sorting(op, cols, page_key), cols)
            
            with st.expander("بيع"):
                with st.form("sell"):
                    c1,c2 = st.columns(2)
                    s = c1.selectbox("السهم", op['symbol'].unique())
                    p = c2.number_input("سعر البيع")
                    d = st.date_input("التاريخ", date.today())
                    if st.form_submit_button("تأكيد"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, ts))
                        st.success("تم"); st.cache_data.clear(); st.rerun()
        else: st.info("لا توجد مراكز مفتوحة")
    
    with t2:
        if not op.empty and page_key == 'invest':
            fig = px.pie(op, values='market_value', names='sector', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
    
    with t3:
        if not cl.empty: render_table(cl, [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح'), ('exit_date', 'خروج')])

def view_cash_log():
    st.header("💵 سجل السيولة")
    fin = calculate_portfolio_metrics()
    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "التوزيعات"])
    
    with t1:
        st.markdown(f"**المجموع:** {fin['deposits']['amount'].sum():,.2f}")
        render_table(fin['deposits'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
    with t2:
        st.markdown(f"**المجموع:** {fin['withdrawals']['amount'].sum():,.2f}")
        render_table(fin['withdrawals'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
    with t3:
        st.markdown(f"**المجموع:** {fin['returns']['amount'].sum():,.2f}")
        render_table(fin['returns'], [('date','التاريخ'), ('symbol','الرمز'), ('amount','المبلغ')])

def view_analysis(fin):
    st.header("🔬 التحليل الشامل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c1, c2 = st.columns([1, 2])
    ns = c1.text_input("بحث")
    if ns and ns not in syms: syms.insert(0, ns)
    sym = c2.selectbox("اختر", syms) if syms else None
    
    if sym:
        n, s = get_company_details(sym)
        st.markdown(f"### {n if n else sym}")
        t1, t2, t3 = st.tabs(["مالي", "فني", "مختبر"])
        with t1:
            d = get_fundamental_ratios(sym)
            c1,c2 = st.columns([1,3])
            c1.metric("التقييم", f"{d['Score']}/10")
            render_financial_dashboard_ui(sym)
        with t2:
            view_advanced_chart(sym)
        with t3:
            st.info("استخدم صفحة المختبر للتحليل المتقدم")

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
        else: st.error("بيانات غير كافية للباك تست")

def view_settings():
    st.header("⚙️ الإعدادات")
    st.info("الملفات المدعومة: Trades, Deposits, Withdrawals, ReturnsGrants")
    
    uploaded_files = st.file_uploader("ملفات Excel/CSV", accept_multiple_files=True)
    if uploaded_files and st.button("بدء الاستيراد"):
        maps = {'trade': 'Trades', 'dep': 'Deposits', 'wit': 'Withdrawals', 'ret': 'ReturnsGrants'}
        count = 0
        for f in uploaded_files:
            try:
                # تحديد الجدول
                tn = 'Trades'
                for k,v in maps.items():
                    if k in f.name.lower(): tn = v; break
                
                # قراءة
                df = pd.read_excel(f) if f.name.endswith('xlsx') else pd.read_csv(f)
                
                # حفظ
                ok, msg = save_dataframe_to_db(df, tn)
                if ok: 
                    st.success(f"✅ {f.name}: {msg}")
                    count += 1
                else: st.error(f"❌ {f.name}: {msg}")
            except Exception as e: st.error(f"خطأ في {f.name}: {e}")
            
        if count > 0: 
            time.sleep(1); st.cache_data.clear(); st.rerun()

    st.divider()
    if st.button("⚠️ تصفير البيانات", type="primary"):
        clear_all_data()
        st.warning("تم الحذف"); st.rerun()

def view_sukuk_portfolio(fin):
    st.header("📜 الصكوك")
    df = fin['all_trades']
    if not df.empty:
        sk = df[df['asset_type']=='Sukuk']
        if not sk.empty: render_table(sk, [('company_name','الاسم'), ('quantity','العدد'), ('entry_price','الشراء')]); return
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
    elif pg == 'update': 
        with st.spinner("تحديث..."): update_prices()
        st.session_state.page='home'; st.rerun()
