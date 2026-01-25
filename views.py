import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time

# === الاستيرادات ===
from config import DEFAULT_COLORS, BACKUP_DIR
from components import render_navbar, render_kpi, render_table
from analytics import (calculate_portfolio_metrics, update_prices, create_smart_backup, 
                       generate_equity_curve, calculate_historical_drawdown)
# استيراد الشارت (تأكد أن charts.py سليم)
from charts import view_advanced_chart
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

# === أدوات مساعدة للعرض ===
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
        open_df['gain_pct'] = open_df.apply(lambda row: (row['gain']/row['total_cost']*100) if row['total_cost']>0 else 0, axis=1)

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

def view_cash_log():
    st.header("💵 سجل السيولة")
    fin = calculate_portfolio_metrics()
    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "التوزيعات"])
    
    with t1:
        st.markdown(f"**المجموع:** {fin['deposits']['amount'].sum():,.2f}")
        with st.expander("➕ إيداع جديد"):
             with st.form("dep"):
                 amt = st.number_input("المبلغ"); dt = st.date_input("التاريخ"); nt = st.text_input("ملاحظة")
                 if st.form_submit_button("حفظ"): execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s, %s, %s)", (str(dt), amt, nt)); st.rerun()
        render_table(fin['deposits'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
    
    with t2:
        st.markdown(f"**المجموع:** {fin['withdrawals']['amount'].sum():,.2f}")
        with st.expander("➖ سحب جديد"):
             with st.form("wit"):
                 amt = st.number_input("المبلغ"); dt = st.date_input("التاريخ"); nt = st.text_input("ملاحظة")
                 if st.form_submit_button("حفظ"): execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s, %s, %s)", (str(dt), amt, nt)); st.rerun()
        render_table(fin['withdrawals'], [('date','التاريخ'), ('amount','المبلغ'), ('note','ملاحظات')])
    
    with t3:
        st.markdown(f"**المجموع:** {fin['returns']['amount'].sum():,.2f}")
        render_table(fin['returns'], [('date','التاريخ'), ('symbol','الرمز'), ('amount','المبلغ')])

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
        t1, t2, t3, t4, t5 = st.tabs(["📊 المؤشرات", "📑 القوائم", "📝 الأطروحة", "📈 الشارت", "🏛️ كلاسيكي"])
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
    with c2: strat = st.selectbox("الاستراتيجية", ["Trend Follower", "Sniper"])
    with c3: cap = st.number_input("رأس المال", 100000)
    
    if st.button("🚀 تشغيل"):
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
    st.header("➕ تسجيل عملية")
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

def view_tools():
    st.header("🛠️ الأدوات")
    fin = calculate_portfolio_metrics()
    st.info("زكاة تقديرية: " + str(fin['market_val_open'] * 0.025775))

# === حل مشكلة السيولة والاستيراد (Mapping Fix) ===
def clean_and_fix_columns(df, table_name):
    """دالة تقوم بتنظيف وتصحيح أسماء الأعمدة لتطابق قاعدة البيانات بدقة"""
    if df is None: return None
    df.columns = df.columns.str.strip().str.lower()
    
    # 1. خرائط تصحيح (Mapping)
    # هذا يحل مشكلة: source/reason في ملفاتك -> note في قاعدة البيانات
    rename_map = {
        'source': 'note',
        'reason': 'note',
        'notes': 'note',
        'cost': 'amount',
        'value': 'amount'
    }
    df.rename(columns=rename_map, inplace=True)
    
    # 2. حذف الأعمدة غير المرغوبة (ID)
    if 'id' in df.columns: df = df.drop(columns=['id'])
    
    # 3. الفلترة الصارمة (Strict Filtering)
    # نحتفظ فقط بالأعمدة التي تقبلها قاعدة البيانات لهذا الجدول
    # ونحذف أي عمود زائد (مثل type في ReturnsGrants) الذي سبب المشكلة
    allowed_cols = {
        'Trades': ['symbol', 'company_name', 'sector', 'asset_type', 'date', 'quantity', 'entry_price', 'strategy', 'status', 'exit_date', 'exit_price', 'current_price'],
        'Deposits': ['date', 'amount', 'note'],
        'Withdrawals': ['date', 'amount', 'note'],
        'ReturnsGrants': ['date', 'symbol', 'company_name', 'amount'], # لا يوجد type هنا
        'Watchlist': ['symbol']
    }
    
    if table_name in allowed_cols:
        target_cols = allowed_cols[table_name]
        # احتفظ فقط بالأعمدة الموجودة في القائمة
        existing_cols = [c for c in df.columns if c in target_cols]
        df = df[existing_cols]
    
    # 4. تنظيف البيانات (تواريخ وأرقام)
    for col in df.columns:
        if 'date' in col:
            try: df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d')
            except: pass
        if df[col].dtype == 'object':
            try: df[col] = df[col].astype(str).str.replace(',', '')
            except: pass
            
    # تحويل NaN إلى None
    df = df.where(pd.notnull(df), None)
    return df

def save_dataframe_to_db(df, table_name):
    # نستخدم الدالة الجديدة للتنظيف والفلترة
    df_clean = clean_and_fix_columns(df, table_name)
    
    if df_clean is None or df_clean.empty: return
    
    records = df_clean.to_dict('records')
    
    with get_db() as conn:
        if not conn: st.error("لا يوجد اتصال"); return
        with conn.cursor() as cur:
            for row in records:
                cols = list(row.keys())
                vals = [v for v in row.values()]
                placeholders = ', '.join(['%s'] * len(vals))
                columns = ', '.join(cols)
                
                # جملة الإدخال
                query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
                
                try: cur.execute(query, vals)
                except Exception as e: 
                    print(f"Skipped row in {table_name}: {e}")
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
        
        # خريطة الربط (اسم الملف -> اسم الجدول)
        table_map = {
            'trades': 'Trades', 'deposits': 'Deposits', 
            'withdrawals': 'Withdrawals', 'returns': 'ReturnsGrants',
            'watchlist': 'Watchlist'
        }
        
        conn_check = get_db()
        with conn_check as conn:
            if not conn: st.error("لا يوجد اتصال"); st.stop()

        for file in uploaded_files:
            try:
                fname = file.name.lower()
                target = None
                
                # تحديد الجدول المستهدف
                if fname.endswith('.xlsx'):
                    xls = pd.ExcelFile(file)
                    for sheet in xls.sheet_names:
                        for key, val in table_map.items():
                            if key in sheet.lower(): target = val; break
                        if target:
                            df = pd.read_excel(file, sheet_name=sheet)
                            save_dataframe_to_db(df, target)
                            success += 1
                            status.text(f"تم: {sheet}")
                else: # CSV
                    for key, val in table_map.items():
                        if key in fname: target = val; break
                    if target:
                        try: df = pd.read_csv(file)
                        except: file.seek(0); df = pd.read_csv(file, encoding='cp1256')
                        save_dataframe_to_db(df, target)
                        success += 1
                        status.text(f"تم: {fname}")
                        
            except Exception as e: status.error(f"خطأ: {e}")
        
        if success > 0:
            st.success(f"تم استيراد {success} جداول بنجاح.")
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
    elif pg == 'profile': st.info("الملف الشخصي") # صفحة بسيطة للملف الشخصي
    elif pg == 'update':
        with st.spinner("تحديث..."): update_prices()
        st.session_state.page = 'home'; st.rerun()
