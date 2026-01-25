import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time
import io

# === الاستيرادات ===
from config import DEFAULT_COLORS, BACKUP_DIR
from components import render_navbar, render_kpi, render_table
from analytics import (calculate_portfolio_metrics, update_prices, create_smart_backup, 
                       generate_equity_curve, calculate_historical_drawdown)
# الاستيراد الآن سيعمل لأننا أضفنا الدالتين في charts.py
from charts import view_advanced_chart, render_technical_chart
from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui, get_thesis, save_thesis
from market_data import get_static_info, get_tasi_data, get_chart_history 
from database import execute_query, fetch_table, get_db, clear_all_data

# === استيراد الوحدات الاختيارية ===
try: from backtester import run_backtest
except ImportError: 
    def run_backtest(*args): return None

try: from pulse import render_pulse_dashboard
except ImportError: 
    def render_pulse_dashboard(): st.info("وحدة النبض قيد الإنشاء")

try: from classical_analysis import render_classical_analysis
except ImportError:
    def render_classical_analysis(s): st.info("التحليل الكلاسيكي غير متاح")

# === أدوات مساعدة ===
def safe_fmt(val, suffix=""):
    if val is None: return "غير متاح"
    try:
        num = float(val)
        if num == 0 and suffix == "": return "0.00"
        return f"{num:.2f}{suffix}"
    except: return "غير متاح"

def apply_sorting(df, cols_definition, key_suffix):
    if df.empty: return df
    with st.expander("🔍 أدوات الفرز والتصفية", expanded=False):
        label_to_col = {label: col for col, label in cols_definition}
        sort_options = list(label_to_col.keys())
        c1, c2 = st.columns([2, 1])
        with c1: selected = st.selectbox("فرز حسب:", sort_options, key=f"sc_{key_suffix}")
        with c2: order = st.radio("الترتيب:", ["تنازلي", "تصاعدي"], horizontal=True, key=f"so_{key_suffix}")
    target = label_to_col[selected]
    asc = (order == "تصاعدي")
    try: return df.sort_values(by=target, ascending=asc)
    except: return df

# === الصفحات ===

def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    C = DEFAULT_COLORS
    
    arrow = "🔼" if t_change >= 0 else "🔽"
    color = C['success'] if t_change >= 0 else C['danger']
    
    st.markdown(f"""
    <div class="tasi-box">
        <div>
            <div style="font-size:1.2rem; color:{C['sub_text']}; margin-bottom:5px;">المؤشر العام (TASI)</div>
            <div style="font-size:2.5rem; font-weight:900; color:{C['main_text']};">{t_price:,.2f}</div>
        </div>
        <div style="text-align:left;">
            <div style="background:{color}20; color:{color}; padding:10px 25px; border-radius:12px; font-size:1.4rem; font-weight:bold; direction:ltr; border:1px solid {color}50;">
                {arrow} {t_change:+.2f}%
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 🏦 الملخص المالي")
    c1, c2, c3, c4 = st.columns(4)
    total_invested_pocket = fin['total_deposited'] - fin['total_withdrawn']
    total_pl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c1: render_kpi("النقد المتوفر", f"{fin['cash']:,.2f}", "blue")
    with c2: render_kpi("رأس المال المستثمر", f"{total_invested_pocket:,.2f}")
    with c3: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}")
    with c4: render_kpi("صافي الأرباح الكلية", f"{total_pl:,.2f}", total_pl)
    st.markdown("---")
    
    st.markdown("### 📈 نمو المحفظة")
    curve_data = generate_equity_curve(fin['all_trades'])
    if not curve_data.empty and 'date' in curve_data.columns:
        fig = px.line(curve_data, x='date', y='cumulative_invested')
        fig.update_layout(yaxis_title="القيمة (ريال)", xaxis_title="التاريخ", font=dict(family="Cairo"), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        fig.update_traces(line_color=C['primary'], line_width=3)
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("📉 لا توجد بيانات كافية لرسم منحنى النمو.")

def view_portfolio(fin, page_key):
    target_strat = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {target_strat}")
    all_data = fin['all_trades']
    df_strat = pd.DataFrame()
    if not all_data.empty and 'strategy' in all_data.columns:
        all_data['strategy'] = all_data['strategy'].astype(str).str.strip()
        df_strat = all_data[(all_data['strategy'] == target_strat) & (all_data['asset_type'] != 'Sukuk')].copy()
    
    if df_strat.empty: st.warning(f"المحفظة فارغة.")
    if 'status' not in df_strat.columns: df_strat['status'] = 'Open'

    open_df = df_strat[df_strat['status']=='Open'].copy()
    closed_df = df_strat[df_strat['status']=='Close'].copy()
    
    if not open_df.empty:
        open_df['total_cost'] = open_df['quantity'] * open_df['entry_price']
        open_df['market_value'] = open_df['quantity'] * open_df['current_price']
        open_df['gain'] = open_df['market_value'] - open_df['total_cost']
        open_df['gain_pct'] = open_df.apply(lambda row: (row['gain']/row['total_cost']*100) if row['total_cost']>0 else 0, axis=1)

    t1, t2, t3 = st.tabs([f"القائمة ({len(open_df)})", "تحليل الأداء", f"الأرشيف ({len(closed_df)})"])
    with t1:
        if page_key == 'invest':
            st.markdown("#### 🎯 التوزيع القطاعي")
            if not open_df.empty:
                sec_sum = open_df.groupby('sector').agg({'market_value':'sum'}).reset_index()
                fig = px.pie(sec_sum, values='market_value', names='sector', hole=0.4)
                fig.update_layout(font=dict(family="Cairo"))
                st.plotly_chart(fig, use_container_width=True)

        if not open_df.empty:
            cols_op = [
                ('company_name', 'اسم الشركة'), ('symbol', 'الرمز'), ('sector', 'القطاع'),
                ('date', 'تاريخ الشراء'), ('quantity', 'الكمية'), ('entry_price', 'سعر الشراء'),
                ('total_cost', 'التكلفة'), ('current_price', 'السعر الحالي'), ('market_value', 'سعر السوق'),
                ('gain', 'الربح'), ('gain_pct', '%'), ('weight', 'الوزن'), ('daily_change', 'يومي')
            ]
            render_table(apply_sorting(open_df, cols_op, page_key), cols_op)
            with st.expander("🔴 تسجيل بيع"):
                with st.form(f"sell_{page_key}"):
                    c1, c2, c3 = st.columns(3)
                    sel = c1.selectbox("السهم", open_df['symbol'].unique())
                    ep = c2.number_input("سعر البيع", min_value=0.01)
                    ed = c3.date_input("التاريخ", date.today())
                    if st.form_submit_button("تأكيد البيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (ep, str(ed), sel, target_strat))
                        st.success("تم البيع"); st.cache_data.clear(); st.rerun()
        else: st.info("لا توجد صفقات مفتوحة.")

    with t2:
        if not open_df.empty:
            dd = calculate_historical_drawdown(open_df)
            if not dd.empty:
                st.markdown("##### 📉 أقصى تراجع")
                fig = px.area(dd, x='date', y='drawdown', color_discrete_sequence=['#EF4444'])
                st.plotly_chart(fig, use_container_width=True)
    with t3:
        if not closed_df.empty: 
            render_table(closed_df, [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح'), ('gain_pct', '%'), ('exit_date', 'تاريخ البيع')])
        else: st.info("سجل فارغ.")

def view_sukuk_portfolio(fin):
    st.header("📜 محفظة الصكوك")
    sukuk_df = fin['all_trades'][fin['all_trades']['asset_type'] == 'Sukuk'].copy() if not fin['all_trades'].empty else pd.DataFrame()
    if sukuk_df.empty: st.warning("لا توجد صكوك."); return
    open_sukuk = sukuk_df[sukuk_df['status'] == 'Open']
    cols = [('company_name', 'اسم الصك'), ('symbol', 'الرمز'), ('quantity', 'العدد'), ('entry_price', 'سعر الشراء'), ('current_price', 'السعر الحالي'), ('market_value', 'القيمة السوقية'), ('gain_pct', 'النمو %')]
    render_table(open_sukuk, cols)

def view_analysis(fin):
    st.header("🔬 مركز التحليل الشامل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    symbols = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c_search, c_sel = st.columns([1, 2])
    with c_search: new_search = st.text_input("بحث عن رمز جديد")
    if new_search and new_search not in symbols: symbols.insert(0, new_search)
    with c_sel: symbol = st.selectbox("اختر الشركة", symbols) if symbols else None
    
    if symbol:
        n, s = get_static_info(symbol)
        st.markdown(f"### {n} ({symbol})")
        t1, t2, t3, t4, t5 = st.tabs(["📊 المؤشرات", "📑 القوائم المالية", "📝 الأطروحة", "📈 فني", "🏛️ كلاسيكي"])
        with t1:
            d = get_fundamental_ratios(symbol)
            c_sc, c_det = st.columns([1, 3])
            with c_sc:
                color = "#10B981" if d['Score'] >= 7 else "#EF4444"
                st.markdown(f"<div style='text-align:center; padding:15px; border:2px solid {color}; border-radius:15px;'><div style='font-size:3rem; font-weight:bold; color:{color};'>{d['Score']}/10</div><div style='font-weight:bold;'>{d['Rating']}</div></div>", unsafe_allow_html=True)
            with c_det:
                for op in d['Opinions']: st.write(f"• {op}")
            st.markdown("---")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("P/E", safe_fmt(d['P/E']))
            k2.metric("P/B", safe_fmt(d['P/B']))
            k3.metric("ROE", safe_fmt(d['ROE'], "%"))
            k4.metric("Fair Value", safe_fmt(d['Fair_Value']))
        with t2: render_financial_dashboard_ui(symbol)
        with t3:
            curr = get_thesis(symbol)
            with st.form("thesis"):
                target = st.number_input("الهدف", value=(curr['target_price'] if curr is not None else 0.0))
                text = st.text_area("الأطروحة", value=(curr['thesis_text'] if curr is not None else ""))
                if st.form_submit_button("حفظ"): save_thesis(symbol, text, target, "Hold"); st.success("تم")
        with t4: render_technical_chart(symbol)
        with t5: render_classical_analysis(symbol)

def view_backtester_ui(fin):
    st.header("🧪 مختبر الاستراتيجيات")
    c1, c2, c3 = st.columns(3)
    with c1: 
        syms = list(set(fin['all_trades']['symbol'].unique().tolist() + ["1120.SR", "2222.SR"]))
        symbol = st.selectbox("السهم", syms)
    with c2: strat = st.selectbox("الاستراتيجية", ["Trend Follower (جون ميرفي)", "Sniper (هجين)"])
    with c3: cap = st.number_input("رأس المال", 100000)
    
    if st.button("🚀 تشغيل المحاكاة"):
        df_hist = get_chart_history(symbol, period="2y")
        if df_hist is not None and len(df_hist) > 50:
            res = run_backtest(df_hist, strat, cap)
            if res:
                c_res1, c_res2 = st.columns(2)
                c_res1.metric("العائد", f"{res['return_pct']:.2f}%")
                c_res2.metric("النهائي", f"{res['final_value']:,.2f}")
                st.line_chart(res['df']['Portfolio_Value'])
                st.dataframe(res['trades_log'])
        else: st.error("بيانات غير كافية")

def view_add_trade():
    st.header("➕ إضافة عملية")
    with st.form("add"):
        c1, c2 = st.columns(2)
        sym = c1.text_input("الرمز")
        strat = c2.selectbox("المحفظة", ["استثمار", "مضاربة", "صكوك"])
        c3, c4, c5 = st.columns(3)
        qty = c3.number_input("الكمية", min_value=1.0)
        price = c4.number_input("السعر", min_value=0.0)
        date_ex = c5.date_input("التاريخ", date.today())
        if st.form_submit_button("حفظ"):
            n, s = get_static_info(sym)
            atype = "Sukuk" if strat == "صكوك" else "Stock"
            execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Open', %s)", (sym, n, s, atype, str(date_ex), qty, price, strat, price))
            st.success("تم"); st.cache_data.clear()

def view_cash_log():
    st.header("💵 سجل السيولة")
    fin = calculate_portfolio_metrics()
    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "التوزيعات"])
    with t1:
        st.markdown(f"**المجموع:** {fin['deposits']['amount'].sum() if not fin['deposits'].empty else 0:,.2f}")
        with st.expander("➕ إيداع جديد"):
             with st.form("dep"):
                 amt = st.number_input("المبلغ"); dt = st.date_input("التاريخ"); nt = st.text_input("ملاحظة")
                 if st.form_submit_button("حفظ"): execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s, %s, %s)", (str(dt), amt, nt)); st.success("تم"); st.rerun()
        render_table(fin['deposits'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
    with t2:
        st.markdown(f"**المجموع:** {fin['withdrawals']['amount'].sum() if not fin['withdrawals'].empty else 0:,.2f}")
        with st.expander("➖ سحب جديد"):
             with st.form("wit"):
                 amt = st.number_input("المبلغ"); dt = st.date_input("التاريخ"); nt = st.text_input("ملاحظة")
                 if st.form_submit_button("حفظ"): execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s, %s, %s)", (str(dt), amt, nt)); st.success("تم"); st.rerun()
        render_table(fin['withdrawals'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
    with t3:
        st.markdown(f"**المجموع:** {fin['returns']['amount'].sum() if not fin['returns'].empty else 0:,.2f}")
        with st.expander("💰 تسجيل توزيعات"):
             with st.form("ret"):
                 sym = st.text_input("الرمز"); amt = st.number_input("المبلغ"); dt = st.date_input("التاريخ")
                 if st.form_submit_button("حفظ"): execute_query("INSERT INTO ReturnsGrants (date, symbol, amount) VALUES (%s, %s, %s)", (str(dt), sym, amt)); st.success("تم"); st.rerun()
        render_table(fin['returns'], [('date','التاريخ'), ('symbol','الرمز'), ('amount','المبلغ')])

def view_tools():
    st.header("🛠️ الأدوات")
    fin = calculate_portfolio_metrics()
    st.info("زكاة تقديرية (2.5775%): " + str(fin['market_val_open'] * 0.025775))

# === دوال الاستيراد الذكية (Fix: Column Mapping & Filtering) ===
def clean_data_for_import(df):
    if df is None: return None
    df.columns = df.columns.str.strip().str.lower()
    
    # 1. خرائط تصحيح أسماء الأعمدة (Mapping)
    column_mapping = {
        'source': 'note',   # في ملفات الودائع
        'reason': 'note',   # في ملفات السحب
        'notes': 'note',
        'cost': 'amount',
        'value': 'amount'
    }
    df.rename(columns=column_mapping, inplace=True)

    if 'id' in df.columns: df = df.drop(columns=['id'])
    df = df.where(pd.notnull(df), None)
    
    for col in df.columns:
        if df[col].dtype == 'object':
            try: df[col] = df[col].apply(lambda x: str(x).replace('٫', '.').replace(',', '') if x is not None else x)
            except: pass
            
    for date_col in ['date', 'exit_date']:
        if date_col in df.columns:
            try:
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce').dt.strftime('%Y-%m-%d')
                df[date_col] = df[date_col].replace({pd.NaT: None, 'NaT': None})
            except: pass
    return df

def save_dataframe_to_db(df, table_name):
    df_clean = clean_data_for_import(df)
    if df_clean is None or df_clean.empty: return
    
    # 2. الفلترة الذكية: السماح فقط بالأعمدة الموجودة في القاعدة
    allowed_columns = {
        'Trades': ['symbol', 'company_name', 'sector', 'asset_type', 'date', 'quantity', 'entry_price', 'strategy', 'status', 'exit_date', 'exit_price', 'current_price'],
        'Deposits': ['date', 'amount', 'note'],
        'Withdrawals': ['date', 'amount', 'note'],
        'ReturnsGrants': ['date', 'symbol', 'company_name', 'amount'],
        'Watchlist': ['symbol']
    }
    
    if table_name not in allowed_columns: return
    
    # فلترة الأعمدة الزائدة (مثل source و type)
    valid_cols = [c for c in df_clean.columns if c in allowed_columns[table_name]]
    if not valid_cols: return
    
    df_final = df_clean[valid_cols].copy()
    records = df_final.to_dict('records')
    
    with get_db() as conn:
        if not conn: st.error("فشل الاتصال"); return
        with conn.cursor() as cur:
            for row in records:
                cols = list(row.keys())
                vals = [None if pd.isna(v) else v for v in row.values()]
                placeholders = ', '.join(['%s'] * len(vals))
                columns = ', '.join(cols)
                query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
                try: cur.execute(query, vals)
                except Exception as e: 
                    print(f"Skipped row in {table_name}: {e}")
                    conn.rollback()
            conn.commit()

def view_settings():
    st.header("⚙️ الإعدادات العامة")
    st.markdown("### 📤 النسخ الاحتياطي")
    if st.button("📦 حفظ نسخة احتياطية"):
        if create_smart_backup(): st.success("تم الحفظ في backups")
        else: st.error("فشل النسخ")
    
    st.markdown("---")
    st.markdown("### 📥 إدارة البيانات (الاستيراد)")
    
    if st.button("🗑️ حذف جميع البيانات (تهيئة)", type="primary"):
        clear_all_data()
        st.warning("تم مسح البيانات!"); st.cache_data.clear(); st.rerun()

    uploaded_files = st.file_uploader(
        "ارفع ملفات (CSV) أو (Excel شامل backup_latest.xlsx)", 
        type=['csv', 'xlsx'], 
        accept_multiple_files=True
    )
    
    if uploaded_files and st.button("🚀 بدء الاستيراد"):
        success_count = 0
        progress = st.progress(0)
        status = st.empty()
        
        table_map = {
            'trades': 'Trades', 'deposits': 'Deposits', 
            'withdrawals': 'Withdrawals', 'returns': 'ReturnsGrants',
            'watchlist': 'Watchlist', 'sector': 'SectorTargets',
            'thesis': 'InvestmentThesis'
        }

        conn_check = get_db()
        with conn_check as conn:
            if conn is None: st.error("❌ لا يوجد اتصال!"); st.stop()

        for i, file in enumerate(uploaded_files):
            try:
                fname = file.name.lower()
                if fname.endswith('.xlsx'):
                    xls = pd.ExcelFile(file)
                    for sheet in xls.sheet_names:
                        sheet_lower = sheet.lower()
                        target_table = None
                        for key, t_name in table_map.items():
                            if key in sheet_lower: target_table = t_name; break
                        if target_table:
                            df = pd.read_excel(file, sheet_name=sheet)
                            if not df.empty:
                                status.text(f"معالجة {sheet}...")
                                save_dataframe_to_db(df, target_table)
                                success_count += 1
                elif fname.endswith('.csv'):
                    target_table = None
                    for key, t_name in table_map.items():
                        if key in fname: target_table = t_name; break
                    if target_table:
                        try: df = pd.read_csv(file, encoding='utf-8')
                        except: file.seek(0); df = pd.read_csv(file, encoding='cp1256')
                        if not df.empty:
                            save_dataframe_to_db(df, target_table)
                            success_count += 1
                            status.text(f"✅ تم: {fname}")
            except Exception as e: status.error(f"خطأ: {e}")
            progress.progress((i + 1) / len(uploaded_files))
        
        if success_count > 0:
            st.success(f"تم! ({success_count} جداول).")
            st.cache_data.clear(); time.sleep(2); st.rerun()

# === الموجه (Router) ===
def router():
    render_navbar()
    if 'page' not in st.session_state: st.session_state.page = 'home'
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
    elif pg == 'add': view_add_trade()
    elif pg == 'settings': view_settings()
    elif pg == 'update':
        with st.spinner("تحديث الأسعار..."): update_prices()
        st.session_state.page = 'home'; st.rerun()
