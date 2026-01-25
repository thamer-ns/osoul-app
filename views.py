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
# تأكد أن charts.py محدث ليحتوي view_advanced_chart
from charts import view_advanced_chart, render_technical_chart
from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui, get_thesis, save_thesis
from market_data import get_static_info, get_tasi_data, get_chart_history 
from database import execute_query, fetch_table, get_db, clear_all_data

# === استيراد الصفحات الاختيارية ===
try: from backtester import run_backtest
except ImportError: 
    def run_backtest(*args): return None

try: from pulse import render_pulse_dashboard
except ImportError: 
    def render_pulse_dashboard(): st.info("🚧 صفحة نبض السوق قيد الصيانة")

try: from classical_analysis import render_classical_analysis
except ImportError:
    def render_classical_analysis(s): st.info("التحليل الكلاسيكي غير متاح")

# === أدوات مساعدة ===
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

def safe_fmt(val, suffix=""):
    try: return f"{float(val):,.2f}{suffix}"
    except: return "-"

# === الصفحات الرئيسية ===
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
    total_invested = fin['total_deposited'] - fin['total_withdrawn']
    total_pl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    
    with c1: render_kpi("الكاش المتوفر", f"{fin['cash']:,.2f}", "blue")
    with c2: render_kpi("صافي الاستثمار", f"{total_invested:,.2f}")
    with c3: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}")
    with c4: render_kpi("الأرباح الكلية", f"{total_pl:,.2f}", total_pl)
    
    st.markdown("---")
    st.markdown("### 📈 نمو المحفظة")
    curve_data = generate_equity_curve(fin['all_trades'])
    if not curve_data.empty:
        fig = px.line(curve_data, x='date', y='cumulative_invested')
        fig.update_layout(yaxis_title="القيمة", xaxis_title="التاريخ", font=dict(family="Cairo"), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        fig.update_traces(line_color=C['primary'], line_width=3)
        st.plotly_chart(fig, use_container_width=True)

def view_portfolio(fin, page_key):
    target_strat = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {target_strat}")
    all_data = fin['all_trades']
    
    if not all_data.empty:
        df = all_data[all_data['strategy'].astype(str).str.strip() == target_strat].copy()
    else: df = pd.DataFrame()
    
    if df.empty: st.info("المحفظة فارغة."); return

    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()
    
    if not open_df.empty:
        open_df['total_cost'] = open_df['quantity'] * open_df['entry_price']
        open_df['market_value'] = open_df['quantity'] * open_df['current_price']
        open_df['gain'] = open_df['market_value'] - open_df['total_cost']
        open_df['gain_pct'] = (open_df['gain'] / open_df['total_cost']) * 100

    t1, t2, t3 = st.tabs([f"القائمة ({len(open_df)})", "تحليل الأداء", f"الأرشيف ({len(closed_df)})"])
    
    with t1:
        if page_key == 'invest' and not open_df.empty:
            st.markdown("#### 🎯 التوزيع القطاعي")
            fig = px.pie(open_df, values='market_value', names='sector', hole=0.4)
            fig.update_layout(font=dict(family="Cairo"))
            st.plotly_chart(fig, use_container_width=True)

        if not open_df.empty:
            cols = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('date', 'التاريخ'), ('quantity', 'الكمية'), 
                    ('entry_price', 'الشراء'), ('current_price', 'الحالي'), ('gain', 'الربح'), ('gain_pct', '%')]
            render_table(apply_sorting(open_df, cols, page_key), cols)
            
            with st.expander("🔴 تسجيل بيع"):
                with st.form(f"sell_{page_key}"):
                    c1, c2, c3 = st.columns(3)
                    sel = c1.selectbox("السهم", open_df['symbol'].unique())
                    ep = c2.number_input("سعر البيع", min_value=0.01)
                    ed = c3.date_input("التاريخ", date.today())
                    if st.form_submit_button("تأكيد"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (ep, str(ed), sel, target_strat))
                        st.success("تم"); st.cache_data.clear(); st.rerun()
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
            render_table(closed_df, [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح'), ('exit_date', 'تاريخ البيع')])

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
    
    symbols = []
    if not trades.empty: symbols.extend(trades['symbol'].unique().tolist())
    if not wl.empty: symbols.extend(wl['symbol'].unique().tolist())
    symbols = list(set(symbols))
    
    c_search, c_sel = st.columns([1, 2])
    with c_search: new_search = st.text_input("بحث عن رمز جديد (مثال: 1120)")
    if new_search and new_search not in symbols: symbols.insert(0, new_search)
    
    with c_sel: symbol = st.selectbox("اختر الشركة للتحليل", symbols) if symbols else None
    
    if symbol:
        n, s = get_static_info(symbol)
        st.markdown(f"### {n} ({symbol})")
        t1, t2, t3, t4, t5 = st.tabs(["📊 المؤشرات المالية", "📑 القوائم", "📝 الأطروحة", "📈 الشارت الفني", "🏛️ كلاسيكي"])
        
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
            k1.metric("مكرر الربح (P/E)", safe_fmt(d['P/E']))
            k2.metric("مضاعف الدفترية (P/B)", safe_fmt(d['P/B']))
            k3.metric("العائد على الحقوق (ROE)", safe_fmt(d['ROE'], "%"))
            k4.metric("القيمة العادلة", safe_fmt(d['Fair_Value']))
            
        with t2: render_financial_dashboard_ui(symbol)
        with t3:
            curr = get_thesis(symbol)
            with st.form("thesis"):
                target = st.number_input("السعر المستهدف", value=(curr['target_price'] if curr is not None else 0.0))
                text = st.text_area("الأطروحة الاستثمارية", value=(curr['thesis_text'] if curr is not None else ""))
                if st.form_submit_button("حفظ الأطروحة"): save_thesis(symbol, text, target, "Hold"); st.success("تم الحفظ")
        with t4: render_technical_chart(symbol)
        with t5: render_classical_analysis(symbol)

def view_backtester_ui(fin):
    st.header("🧪 مختبر الاستراتيجيات")
    c1, c2, c3 = st.columns(3)
    with c1: 
        syms = list(set(fin['all_trades']['symbol'].unique().tolist() + ["1120.SR", "2222.SR"]))
        symbol = st.selectbox("السهم للاختبار", syms)
    with c2: strat = st.selectbox("نوع الاستراتيجية", ["Trend Follower (جون ميرفي)", "Sniper (هجين)"])
    with c3: cap = st.number_input("رأس المال الافتراضي", 100000)
    
    if st.button("🚀 تشغيل المحاكاة"):
        df_hist = get_chart_history(symbol, period="2y")
        if df_hist is not None and len(df_hist) > 50:
            res = run_backtest(df_hist, strat, cap)
            if res:
                c_res1, c_res2 = st.columns(2)
                c_res1.metric("العائد الكلي", f"{res['return_pct']:.2f}%")
                c_res2.metric("القيمة النهائية", f"{res['final_value']:,.2f}")
                st.line_chart(res['df']['Portfolio_Value'])
                with st.expander("سجل الصفقات"):
                    st.dataframe(res['trades_log'])
        else: st.error("بيانات السهم غير كافية للاختبار")

def view_add_trade():
    st.header("➕ تسجيل عملية جديدة")
    with st.form("add"):
        c1, c2 = st.columns(2)
        sym = c1.text_input("رمز السهم (مثال: 1120)")
        strat = c2.selectbox("المحفظة", ["استثمار", "مضاربة", "صكوك"])
        c3, c4, c5 = st.columns(3)
        qty = c3.number_input("الكمية", min_value=1.0)
        price = c4.number_input("سعر التنفيذ", min_value=0.0)
        date_ex = c5.date_input("تاريخ العملية", date.today())
        if st.form_submit_button("حفظ العملية"):
            n, s = get_static_info(sym)
            atype = "Sukuk" if strat == "صكوك" else "Stock"
            execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Open', %s)", (sym, n, s, atype, str(date_ex), qty, price, strat, price))
            st.success("تم الحفظ بنجاح"); st.cache_data.clear()

def view_cash_log():
    st.header("💵 سجل السيولة")
    fin = calculate_portfolio_metrics()
    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "التوزيعات"])
    
    with t1:
        st.markdown(f"**المجموع:** {fin['deposits']['amount'].sum():,.2f}")
        with st.expander("➕ تسجيل إيداع نقدي"):
             with st.form("dep"):
                 amt = st.number_input("المبلغ"); dt = st.date_input("التاريخ"); nt = st.text_input("ملاحظة")
                 if st.form_submit_button("حفظ"): execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s, %s, %s)", (str(dt), amt, nt)); st.success("تم"); st.rerun()
        render_table(fin['deposits'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
    
    with t2:
        st.markdown(f"**المجموع:** {fin['withdrawals']['amount'].sum():,.2f}")
        with st.expander("➖ تسجيل سحب نقدي"):
             with st.form("wit"):
                 amt = st.number_input("المبلغ"); dt = st.date_input("التاريخ"); nt = st.text_input("ملاحظة")
                 if st.form_submit_button("حفظ"): execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s, %s, %s)", (str(dt), amt, nt)); st.success("تم"); st.rerun()
        render_table(fin['withdrawals'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
    
    with t3:
        st.markdown(f"**المجموع:** {fin['returns']['amount'].sum():,.2f}")
        with st.expander("💰 تسجيل توزيعات أرباح"):
             with st.form("ret"):
                 sym = st.text_input("رمز السهم"); amt = st.number_input("المبلغ المستلم"); dt = st.date_input("التاريخ")
                 if st.form_submit_button("حفظ"): execute_query("INSERT INTO ReturnsGrants (date, symbol, amount) VALUES (%s, %s, %s)", (str(dt), sym, amt)); st.success("تم"); st.rerun()
        render_table(fin['returns'], [('date','التاريخ'), ('symbol','الرمز'), ('amount','المبلغ')])

def view_tools():
    st.header("🛠️ الأدوات")
    fin = calculate_portfolio_metrics()
    st.info("زكاة المحفظة التقديرية (2.5775% من القيمة السوقية): " + str(fin['market_val_open'] * 0.025775))

# === حل مشكلة السيولة جذرياً (Clean & Map) ===
def clean_and_map_columns(df):
    if df is None: return None
    df.columns = df.columns.str.strip().str.lower()
    
    # 1. خرائط تصحيح أسماء الأعمدة (Mapping)
    # هذا يحل مشكلة: Error inserting row in Deposits: column "source" does not exist
    column_mapping = {
        'source': 'note',   # في ملفات الودائع
        'reason': 'note',   # في ملفات السحب
        'notes': 'note',
        'cost': 'amount',
        'value': 'amount'
    }
    df.rename(columns=column_mapping, inplace=True)
    
    if 'id' in df.columns: df = df.drop(columns=['id'])
    
    # تحويل التواريخ
    for col in df.columns:
        if 'date' in col:
            try: df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d')
            except: pass
            
    # تحويل الأرقام (إزالة الفواصل)
    for col in df.columns:
        if df[col].dtype == 'object':
            try: df[col] = df[col].astype(str).str.replace(',', '')
            except: pass
            
    return df

def save_dataframe_to_db(df, table_name):
    df = clean_and_map_columns(df)
    if df is None or df.empty: return

    # 3. الفلترة الذكية: إدخال الأعمدة الموجودة في قاعدة البيانات فقط
    # هذا يحل مشكلة: column "type" does not exist في ReturnsGrants
    allowed_cols = {
        'Trades': ['symbol', 'company_name', 'sector', 'asset_type', 'date', 'quantity', 'entry_price', 'strategy', 'status', 'exit_date', 'exit_price', 'current_price'],
        'Deposits': ['date', 'amount', 'note'],
        'Withdrawals': ['date', 'amount', 'note'],
        'ReturnsGrants': ['date', 'symbol', 'company_name', 'amount'], # تم استبعاد 'type' لأنه غير موجود
        'Watchlist': ['symbol']
    }
    
    if table_name not in allowed_cols: return
    
    # الاحتفاظ فقط بالأعمدة المسموحة
    valid_cols = [c for c in df.columns if c in allowed_cols[table_name]]
    df_final = df[valid_cols].copy()
    
    records = df_final.to_dict('records')
    
    with get_db() as conn:
        if not conn: return
        with conn.cursor() as cur:
            for row in records:
                cols = list(row.keys())
                vals = [None if pd.isna(v) else v for v in row.values()]
                placeholders = ', '.join(['%s'] * len(vals))
                columns = ', '.join(cols)
                query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
                try: cur.execute(query, vals)
                except Exception as e: 
                    # طباعة الخطأ في الكونسول فقط وتكملة الباقي
                    print(f"Error inserting into {table_name}: {e}")
                    conn.rollback()
            conn.commit()

def view_settings():
    st.header("⚙️ الإعدادات")
    st.markdown("### 📥 استيراد البيانات")
    
    if st.button("🗑️ حذف جميع البيانات (تهيئة)", type="primary"):
        clear_all_data()
        st.warning("تم المسح."); st.cache_data.clear(); st.rerun()

    uploaded_files = st.file_uploader("ملفات Excel/CSV", type=['csv', 'xlsx'], accept_multiple_files=True)
    
    if uploaded_files and st.button("🚀 بدء الاستيراد"):
        success = 0
        status = st.empty()
        table_map = {
            'trades': 'Trades', 'deposits': 'Deposits', 
            'withdrawals': 'Withdrawals', 'returns': 'ReturnsGrants',
            'watchlist': 'Watchlist'
        }
        
        # التأكد من الاتصال
        conn_check = get_db()
        with conn_check as conn:
            if not conn: st.error("لا يوجد اتصال بالقاعدة"); st.stop()

        for file in uploaded_files:
            try:
                fname = file.name.lower()
                if fname.endswith('.xlsx'):
                    xls = pd.ExcelFile(file)
                    for sheet in xls.sheet_names:
                        target = None
                        for key, val in table_map.items():
                            if key in sheet.lower(): target = val; break
                        if target:
                            df = pd.read_excel(file, sheet_name=sheet)
                            save_dataframe_to_db(df, target)
                            success += 1
                            status.text(f"تم معالجة: {sheet}")
                
                elif fname.endswith('.csv'):
                    target = None
                    for key, val in table_map.items():
                        if key in fname: target = val; break
                    if target:
                        try: df = pd.read_csv(file)
                        except: file.seek(0); df = pd.read_csv(file, encoding='cp1256')
                        save_dataframe_to_db(df, target)
                        success += 1
                        status.text(f"تم معالجة: {fname}")
            except Exception as e: st.error(f"خطأ: {e}")
        
        if success > 0:
            st.success(f"تم استيراد {success} ملفات/جداول بنجاح.")
            st.cache_data.clear()
            time.sleep(2)
            st.rerun()

# === الموجه ===
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
        with st.spinner("تحديث..."): update_prices()
        st.session_state.page = 'home'; st.rerun()
