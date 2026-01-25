import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time

# === الاستيرادات ===
from config import DEFAULT_COLORS, BACKUP_DIR
from components import render_navbar, render_kpi, render_table, render_ticker_card
from analytics import (calculate_portfolio_metrics, update_prices, create_smart_backup, 
                       generate_equity_curve, calculate_historical_drawdown, run_backtest)
from charts import view_advanced_chart
from market_data import get_static_info, get_tasi_data, get_chart_history 
from database import execute_query, fetch_table, get_db, clear_all_data
from data_source import get_company_details

# استيرادات التحليل (Fallback)
try: from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui, get_thesis, save_thesis
except ImportError:
    def get_fundamental_ratios(*args): return {'Score': 0, 'Rating': '-', 'Opinions': [], 'P/E':0, 'P/B':0, 'ROE':0, 'Fair_Value':0}
    def render_financial_dashboard_ui(*args): st.info("التحليل المالي قيد التجهيز")
    def get_thesis(*args): return None
    def save_thesis(*args): pass

try: from classical_analysis import render_classical_analysis
except ImportError:
    def render_classical_analysis(s): st.info("التحليل الكلاسيكي غير متاح")

# ==========================================
# 1. الدوال المساعدة (تم رفعها للأعلى لمنع الخطأ)
# ==========================================

def safe_fmt(val, suffix=""):
    try: return f"{float(val):,.2f}{suffix}"
    except: return "-"

def apply_sorting(df, cols_definition, key_suffix):
    """دالة الفرز التي كانت تسبب المشكلة - الآن مكانها صحيح"""
    if df.empty: return df
    with st.expander("🔍 خيارات الفرز", expanded=False):
        label_to_col = {label: col for col, label in cols_definition}
        c1, c2 = st.columns([2, 1])
        with c1: selected = st.selectbox("فرز حسب:", list(label_to_col.keys()), key=f"sc_{key_suffix}")
        with c2: order = st.radio("الترتيب:", ["تنازلي", "تصاعدي"], horizontal=True, key=f"so_{key_suffix}")
    target = label_to_col[selected]
    try: return df.sort_values(by=target, ascending=(order == "تصاعدي"))
    except: return df

# === منطق الاستيراد (معالجة السيولة والأسهم) ===
def clean_and_fix_columns(df, table_name):
    if df is None: return None
    df.columns = df.columns.str.strip().str.lower()
    
    # --- معالجة خاصة لملفات السيولة (Deposits/Withdrawals) ---
    if table_name in ['Deposits', 'Withdrawals']:
        # دمج الملاحظات من (source, reason, note)
        df['final_note'] = ''
        if 'source' in df.columns: df['final_note'] = df['final_note'] + ' ' + df['source'].astype(str).replace('nan', '')
        if 'reason' in df.columns: df['final_note'] = df['final_note'] + ' ' + df['reason'].astype(str).replace('nan', '')
        if 'note' in df.columns: df['final_note'] = df['final_note'] + ' ' + df['note'].astype(str).replace('nan', '')
        
        df['note'] = df['final_note'].str.strip()
        
        # توحيد المبلغ
        if 'amount' not in df.columns:
            if 'cost' in df.columns: df['amount'] = df['cost']
            elif 'value' in df.columns: df['amount'] = df['value']
    
    # خريطة عامة لباقي الأعمدة
    rename_map = {
        'cost': 'amount', 'value': 'amount', 
        'ticker': 'symbol', 'code': 'symbol',
        'price': 'entry_price', 'avg_price': 'entry_price'
    }
    df.rename(columns=rename_map, inplace=True)
    
    if 'id' in df.columns: df = df.drop(columns=['id'])
    
    allowed_cols = {
        'Trades': ['symbol', 'company_name', 'sector', 'asset_type', 'date', 'quantity', 'entry_price', 'strategy', 'status', 'exit_date', 'exit_price', 'current_price'],
        'Deposits': ['date', 'amount', 'note'],
        'Withdrawals': ['date', 'amount', 'note'],
        'ReturnsGrants': ['date', 'symbol', 'company_name', 'amount'],
        'Watchlist': ['symbol']
    }
    
    if table_name in allowed_cols:
        target_cols = allowed_cols[table_name]
        # إضافة الأعمدة الناقصة كـ None
        for col in target_cols:
            if col not in df.columns: df[col] = None
        
        df = df[target_cols]
        
        # تعبئة القيم الناقصة للأسهم
        if table_name == 'Trades':
            if 'status' not in df.columns: df['status'] = 'Open'
            # الاستراتيجية الافتراضية إذا كانت فارغة هي "استثمار"
            if 'strategy' not in df.columns: df['strategy'] = 'استثمار'
            if 'asset_type' not in df.columns: df['asset_type'] = 'Stock'
            
            for idx, row in df.iterrows():
                if pd.isna(row.get('company_name')) or pd.isna(row.get('sector')):
                    name, sec = get_company_details(row['symbol'])
                    if pd.isna(row.get('company_name')) and name: df.at[idx, 'company_name'] = name
                    if pd.isna(row.get('sector')) and sec: df.at[idx, 'sector'] = sec
                
                # التأكد من وجود استراتيجية
                if pd.isna(row.get('strategy')) or str(row.get('strategy')).strip() == '':
                    df.at[idx, 'strategy'] = 'استثمار'

    # تنظيف
    for col in df.columns:
        if 'date' in col:
            try: df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d')
            except: pass
        if df[col].dtype == 'object':
            try: df[col] = df[col].astype(str).str.replace(',', '')
            except: pass
            
    df = df.where(pd.notnull(df), None)
    return df

def save_dataframe_to_db(df, table_name):
    df_clean = clean_and_fix_columns(df, table_name)
    if df_clean is None or df_clean.empty: return False
    
    records = df_clean.to_dict('records')
    with get_db() as conn:
        if not conn: st.error("لا يوجد اتصال"); return False
        with conn.cursor() as cur:
            for row in records:
                cols = list(row.keys())
                vals = [v for v in row.values()]
                placeholders = ', '.join(['%s'] * len(vals))
                columns = ', '.join(cols)
                query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
                try: cur.execute(query, vals)
                except Exception as e: conn.rollback()
            conn.commit()
    return True

# ==========================================
# 2. الصفحات (Views)
# ==========================================

def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    C = DEFAULT_COLORS
    arrow = "🔼" if t_change >= 0 else "🔽"
    color = C['success'] if t_change >= 0 else C['danger']
    
    st.markdown(f"""
    <div class="tasi-box">
        <div><div style="font-size:1.2rem; color:{C['sub_text']};">المؤشر العام</div><div style="font-size:2.5rem; font-weight:900; color:{C['main_text']};">{t_price:,.2f}</div></div>
        <div style="background:{color}20; color:{color}; padding:10px 25px; border-radius:12px; font-weight:bold; direction:ltr;">{arrow} {t_change:+.2f}%</div>
    </div>""", unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    total_inv = fin['total_deposited'] - fin['total_withdrawn']
    with c1: render_kpi("الكاش المتوفر", f"{fin['cash']:,.2f}", "blue")
    with c2: render_kpi("صافي الاستثمار", f"{total_inv:,.2f}")
    with c3: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}")
    with c4: render_kpi("الربح/الخسارة", f"{(fin['unrealized_pl'] + fin['realized_pl']):,.2f}", fin['unrealized_pl'])
    
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
    if not symbols: st.warning("القائمة فارغة."); return
    cols = st.columns(4)
    for i, sym in enumerate(symbols):
        name, _ = get_company_details(sym)
        price = 0.0
        if not trades.empty:
            row = trades[trades['symbol'] == sym]
            if not row.empty: price = row.iloc[0]['current_price']
        with cols[i % 4]: render_ticker_card(sym, name if name else sym, price, 0.0)

def view_portfolio(fin, page_key):
    target_strat = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {target_strat}")
    all_d = fin['all_trades']
    
    df = pd.DataFrame()
    if not all_d.empty:
        # استخدام contains للبحث المرن عن الاستراتيجية
        df = all_d[all_d['strategy'].astype(str).str.contains(target_strat, na=False)].copy()
    
    if df.empty: st.info(f"محفظة {target_strat} فارغة."); return

    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()
    
    if not open_df.empty:
        open_df['market_value'] = open_df['quantity'] * open_df['current_price']
        open_df['gain'] = open_df['market_value'] - (open_df['quantity'] * open_df['entry_price'])
        open_df['gain_pct'] = (open_df['gain'] / (open_df['quantity'] * open_df['entry_price']) * 100).fillna(0)

    t1, t2, t3 = st.tabs(["الأسهم الحالية", "تحليل الأداء", "الأرشيف"])
    with t1:
        if not open_df.empty:
            cols = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'التكلفة'), ('current_price', 'السعر'), ('market_value', 'القيمة'), ('gain', 'الربح'), ('gain_pct', '%')]
            # apply_sorting الآن موجودة ولن تسبب خطأ
            render_table(apply_sorting(open_df, cols, page_key), cols)
            
            with st.expander("بيع"):
                with st.form("sell"):
                    c1,c2 = st.columns(2)
                    s = c1.selectbox("السهم", open_df['symbol'].unique())
                    p = c2.number_input("سعر البيع")
                    d = st.date_input("التاريخ", date.today())
                    if st.form_submit_button("تأكيد"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, target_strat))
                        st.success("تم"); st.cache_data.clear(); st.rerun()
        else: st.info("لا توجد مراكز مفتوحة")
    
    with t2:
        if not open_df.empty and page_key == 'invest':
            fig = px.pie(open_df, values='market_value', names='sector', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
    with t3:
        if not closed_df.empty: render_table(closed_df, [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح'), ('exit_date', 'خروج')])

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
        st.markdown(f"### {n if n else sym} ({sym})")
        # التبويبات الخمسة كما طلبت
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
                tn = 'Trades'
                for k,v in maps.items():
                    if k in f.name.lower(): tn = v; break
                
                df = pd.read_excel(f) if f.name.endswith('xlsx') else pd.read_csv(f)
                ok = save_dataframe_to_db(df, tn)
                if ok: 
                    st.success(f"✅ {f.name}: تم")
                    count += 1
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
    elif pg == 'add': st.info("استخدم الإعدادات للاستيراد")
    elif pg == 'update': 
        with st.spinner("تحديث..."): update_prices()
        st.session_state.page='home'; st.rerun()
