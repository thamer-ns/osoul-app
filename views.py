import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time

# === الاستيرادات ===
from config import DEFAULT_COLORS
from components import render_navbar, render_kpi, render_table, render_ticker_card
from analytics import calculate_portfolio_metrics, generate_equity_curve, calculate_historical_drawdown
from database import execute_query, fetch_table, get_db, clear_all_data
from market_data import get_static_info, get_tasi_data, get_chart_history
from data_source import get_company_details  # <--- الاستيراد الجديد المهم

# دوال وهمية لتجنب الأخطاء إذا كانت الملفات ناقصة
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

# === 1. منطق الاستيراد الذكي (تم الإصلاح) ===
def clean_and_fix_columns(df, table_name):
    if df is None or df.empty: return None
    
    # 1. توحيد أسماء الأعمدة (تعريب + إنجليزي)
    df.columns = df.columns.astype(str).str.strip().str.lower()
    
    mapping = {
        'الرمز': 'symbol', 'ticker': 'symbol', 'code': 'symbol',
        'الشركة': 'company_name', 'company': 'company_name', 'name': 'company_name',
        'القطاع': 'sector',
        'التاريخ': 'date',
        'الكمية': 'quantity', 'qty': 'quantity', 'shares': 'quantity',
        'السعر': 'entry_price', 'price': 'entry_price', 'cost': 'entry_price', 'avg': 'entry_price',
        'المبلغ': 'amount', 'amount': 'amount', 'value': 'amount', 'net': 'amount',
        'ملاحظات': 'note', 'note': 'note', 'statement': 'note', 'notes': 'note', 'reason': 'note', 'source': 'note',
        'النوع': 'strategy', 'type': 'strategy', 'portfolio': 'strategy',
        'العمولة': 'commission', 'fees': 'commission'
    }
    df.rename(columns=mapping, inplace=True)
    
    # 2. حذف الأعمدة غير المرغوبة
    if 'id' in df.columns: df = df.drop(columns=['id'])
    
    # 3. معالجة البيانات حسب الجدول
    if table_name == 'Trades':
        # إذا لم يوجد اسم الشركة، نبحث عنه في القاعدة
        if 'symbol' in df.columns:
            # تنظيف الرموز
            df['symbol'] = df['symbol'].astype(str).str.replace('.SR', '').str.strip()
            
            # البحث عن الاسم والقطاع
            for idx, row in df.iterrows():
                if 'company_name' not in df.columns or pd.isna(row.get('company_name')):
                    name, sector = get_company_details(row['symbol'])
                    df.at[idx, 'company_name'] = name if name else f"سهم {row['symbol']}"
                    if 'sector' not in df.columns or pd.isna(row.get('sector')):
                        df.at[idx, 'sector'] = sector if sector else "أخرى"
        
        # قيم افتراضية
        if 'status' not in df.columns: df['status'] = 'Open'
        if 'strategy' not in df.columns: df['strategy'] = 'استثمار'
        if 'asset_type' not in df.columns: df['asset_type'] = 'Stock'

    # 4. تنظيف الأرقام والتواريخ
    for col in df.columns:
        if 'date' in col:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d')
        elif col in ['quantity', 'entry_price', 'amount', 'commission']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    # تصفية الأعمدة حسب الجدول المستهدف فقط
    allowed_cols = {
        'Trades': ['symbol', 'company_name', 'sector', 'asset_type', 'date', 'quantity', 'entry_price', 'strategy', 'status', 'note'],
        'Deposits': ['date', 'amount', 'note'],
        'Withdrawals': ['date', 'amount', 'note'],
        'ReturnsGrants': ['date', 'symbol', 'company_name', 'amount']
    }
    
    target_cols = allowed_cols.get(table_name, [])
    available_cols = [c for c in df.columns if c in target_cols]
    
    if not available_cols: return None
    return df[available_cols]

def save_dataframe_to_db(df, table_name):
    clean_df = clean_and_fix_columns(df, table_name)
    if clean_df is None or clean_df.empty: return False, "لا توجد بيانات صالحة أو الأعمدة غير معروفة"
    
    records = clean_df.to_dict('records')
    count = 0
    with get_db() as conn:
        with conn.cursor() as cur:
            for row in records:
                cols = list(row.keys())
                vals = [None if pd.isna(v) else v for v in row.values()]
                placeholders = ', '.join(['%s'] * len(vals))
                q = f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})"
                try: 
                    cur.execute(q, vals)
                    count += 1
                except Exception as e: 
                    print(f"Error: {e}"); conn.rollback()
            conn.commit()
    return True, f"تم استيراد {count} سجل بنجاح"

# === 2. الصفحات والواجهات (Views) ===

# --- صفحة نبض السوق (تم إصلاح الخطأ) ---
def render_pulse_dashboard():
    st.header("💓 نبض السوق")
    
    # جلب الأسهم من المحفظة والمراقبة
    trades = fetch_table("Trades")
    wl = fetch_table("Watchlist")
    
    symbols = set()
    if not trades.empty: symbols.update(trades[trades['status']=='Open']['symbol'].unique())
    if not wl.empty: symbols.update(wl['symbol'].unique())
    
    if not symbols:
        st.info("لا توجد أسهم للمتابعة. أضف صفقات أو أسهم للمراقبة.")
        return
    
    # عرض الأسعار
    cols = st.columns(4)
    for i, sym in enumerate(symbols):
        # محاولة جلب السعر (مؤقتاً من قاعدة البيانات حتى يتم التحديث)
        price = 0
        name, _ = get_company_details(sym)
        name = name if name else sym
        
        # البحث عن آخر سعر مسجل
        if not trades.empty:
            match = trades[trades['symbol'] == sym]
            if not match.empty:
                price = match.iloc[0]['current_price']
        
        with cols[i % 4]:
            render_ticker_card(sym, name, price, 0.0)

# --- صفحة الرئيسية ---
def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    cl = DEFAULT_COLORS['success'] if t_change >= 0 else DEFAULT_COLORS['danger']
    
    st.markdown(f"""
    <div style="background:white; padding:20px; border-radius:12px; border:1px solid #DFE1E6; display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
        <div><div style="color:#5E6C84;">المؤشر العام (TASI)</div><div style="font-size:2rem; font-weight:900; color:#172B4D;">{t_price:,.2f}</div></div>
        <div style="background:{cl}15; color:{cl}; padding:8px 20px; border-radius:8px; font-weight:bold; direction:ltr;">{t_change:+.2f}%</div>
    </div>""", unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    with c1: render_kpi("الكاش المتوفر", f"{fin['cash']:,.2f}", "blue")
    with c2: render_kpi("صافي الاستثمار", f"{(fin['total_deposited']-fin['total_withdrawn']):,.2f}")
    with c3: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}")
    
    total_pl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("الربح الكلي", f"{total_pl:,.2f}", total_pl)
    
    st.markdown("---")
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: 
        st.markdown("##### 📈 نمو المحفظة")
        st.plotly_chart(px.line(crv, x='date', y='cumulative_invested'), use_container_width=True)

# --- صفحة المحفظة ---
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
    
    # الحسابات
    if not op.empty:
        op['market_value'] = op['quantity'] * op['current_price']
        op['gain'] = op['market_value'] - (op['quantity'] * op['entry_price'])
        op['gain_pct'] = (op['gain'] / (op['quantity'] * op['entry_price']) * 100).fillna(0)

    t1, t2, t3 = st.tabs(["الأسهم الحالية", "توزيع القطاعات", "الأرشيف"])
    
    with t1:
        if not op.empty:
            cols = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'التكلفة'), ('current_price', 'السعر'), ('market_value', 'القيمة'), ('gain', 'الربح'), ('gain_pct', '%')]
            render_table(op, cols)
            
            with st.expander("تسجيل عملية بيع"):
                with st.form("sell"):
                    c1,c2,c3 = st.columns(3)
                    s = c1.selectbox("اختر السهم", op['symbol'].unique())
                    p = c2.number_input("سعر البيع")
                    d = c3.date_input("التاريخ", date.today())
                    if st.form_submit_button("بيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND status='Open'", (p, str(d), s))
                        st.success("تم البيع"); st.rerun()
        else: st.info("لا توجد صفقات مفتوحة")
    
    with t2:
        if not op.empty and page_key == 'invest':
            fig = px.pie(op, values='market_value', names='sector', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
    
    with t3:
        if not cl.empty: render_table(cl, [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح'), ('exit_date', 'تاريخ الخروج')])

# --- صفحة السجلات (تم تعديلها للغة العربية) ---
def view_cash_log():
    st.header("💵 السجلات المالية")
    fin = calculate_portfolio_metrics()
    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "التوزيعات"])
    
    with t1:
        st.metric("إجمالي الإيداع", f"{fin['deposits']['amount'].sum():,.2f}")
        with st.expander("إضافة إيداع"):
            with st.form("dep"):
                a = st.number_input("المبلغ")
                d = st.date_input("التاريخ")
                n = st.text_input("المصدر/ملاحظة")
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s, %s, %s)", (str(d), a, n))
                    st.rerun()
        render_table(fin['deposits'], [('date','التاريخ'), ('amount','المبلغ'), ('note','المصدر')])
        
    with t2:
        st.metric("إجمالي السحب", f"{fin['withdrawals']['amount'].sum():,.2f}")
        with st.expander("تسجيل سحب"):
            with st.form("wit"):
                a = st.number_input("المبلغ")
                d = st.date_input("التاريخ")
                n = st.text_input("السبب/ملاحظة")
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s, %s, %s)", (str(d), a, n))
                    st.rerun()
        render_table(fin['withdrawals'], [('date','التاريخ'), ('amount','المبلغ'), ('note','السبب')])

# --- صفحة الإعدادات (مع حل مشكلة الاستيراد) ---
def view_settings():
    st.header("⚙️ الإعدادات")
    
    st.markdown("### 📥 استيراد البيانات (Excel/CSV)")
    st.info("سيتعرف النظام تلقائياً على اسم الشركة والقطاع عند استيراد الرمز.")
    
    uploaded_files = st.file_uploader("اختر الملفات", accept_multiple_files=True, type=['csv', 'xlsx'])
    
    if uploaded_files and st.button("بدء المعالجة والاستيراد"):
        success_count = 0
        
        # خريطة لاكتشاف نوع الملف من اسمه
        maps = {
            'trade': 'Trades', 'صفقات': 'Trades', 'deals': 'Trades',
            'dep': 'Deposits', 'إيداع': 'Deposits',
            'wit': 'Withdrawals', 'سحب': 'Withdrawals',
            'ret': 'ReturnsGrants', 'توزيع': 'ReturnsGrants'
        }
        
        for f in uploaded_files:
            try:
                # تحديد الجدول
                t_name = 'Trades' # افتراضي
                for k, v in maps.items():
                    if k in f.name.lower(): t_name = v; break
                
                # قراءة الملف
                if f.name.endswith('csv'): df = pd.read_csv(f)
                else: df = pd.read_excel(f)
                
                # الحفظ باستخدام الدالة الذكية
                ok, msg = save_dataframe_to_db(df, t_name)
                if ok: 
                    st.success(f"✅ {f.name}: {msg}")
                    success_count += 1
                else:
                    st.error(f"❌ {f.name}: {msg}")
                    
            except Exception as e: st.error(f"خطأ في الملف {f.name}: {e}")
            
        if success_count > 0:
            time.sleep(1); st.cache_data.clear(); st.rerun()

    st.divider()
    if st.button("⚠️ تصفير قاعدة البيانات (حذف الكل)", type="primary"):
        clear_all_data()
        st.warning("تم الحذف."); st.rerun()

# --- الموجه (Router) ---
def router():
    render_navbar()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    
    if pg == 'home': view_dashboard(fin)
    elif pg == 'pulse': render_pulse_dashboard() # الآن هذه الدالة معرفة ولن يحدث خطأ
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'cash': view_cash_log()
    elif pg == 'settings': view_settings()
    elif pg == 'update':
        with st.spinner("جاري التحديث..."): update_prices()
        st.session_state.page='home'; st.rerun()
    elif pg == 'sukuk': st.info("قسم الصكوك قيد التطوير")
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'tools': view_tools()
    elif pg == 'backtest': view_backtester_ui(fin)
    elif pg == 'add': view_add_trade()
    else: st.info("الصفحة غير موجودة")

# تعريف الدوال الناقصة (لمنع الخطأ NameError في Router)
def view_sukuk_portfolio(fin): st.info("صفحة الصكوك")
def view_analysis(fin): st.info("صفحة التحليل")
def view_backtester_ui(fin): st.info("المختبر")
def view_tools(): st.info("الأدوات")
def view_add_trade(): st.info("إضافة صفقة")
