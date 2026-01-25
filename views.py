import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import date
import time
import sqlite3 # لاستعادة البيانات من الملف القديم

from config import DEFAULT_COLORS, APP_NAME, APP_ICON
from components import safe_fmt
from analytics import (calculate_portfolio_metrics, update_prices, generate_equity_curve, run_backtest)
from database import execute_query, fetch_table, get_db
from market_data import get_static_info, get_tasi_data, get_chart_history
from data_source import get_company_details
from charts import view_advanced_chart 

try: from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui
except ImportError: 
    get_fundamental_ratios = lambda s: {'Score': 0}
    render_financial_dashboard_ui = lambda s: None

# === دوال الرسم والجدول بتصميم الجوهرة ===
def render_finance_table(df, cols_def):
    if df.empty:
        st.info("لا توجد بيانات للعرض")
        return
    C = st.session_state.custom_colors
    headers = "".join([f"<th>{label}</th>" for _, label in cols_def])
    rows_html = ""
    for _, row in df.iterrows():
        cells = ""
        is_closed = str(row.get('status', '')).lower() in ['close', 'sold', 'مغلقة']
        for col_key, _ in cols_def:
            val = row.get(col_key, "-")
            display = val
            if col_key == 'daily_change':
                if is_closed: display = "-"
                else:
                    color = C.get('success') if val >= 0 else C.get('danger')
                    display = f"<span style='color:{color}; direction:ltr; font-weight:bold;'>{abs(val):.2f}%</span>"
            elif col_key == 'status':
                is_open = not is_closed
                txt = "مفتوحة" if is_open else "مغلقة"
                bg = "#E3FCEF" if is_open else "#DFE1E6"
                fg = "#006644" if is_open else "#42526E"
                display = f"<span style='background:{bg}; color:{fg}; padding:4px 10px; border-radius:12px; font-size:0.8rem;'>{txt}</span>"
            elif col_key in ['date', 'exit_date']: display = str(val)[:10] if val else "-"
            elif isinstance(val, (int, float)):
                if col_key == 'quantity': display = f"{val:,.0f}"
                elif 'pct' in col_key or 'weight' in col_key: display = f"{val:.2f}%"
                else: display = f"{val:,.2f}"
                if col_key in ['gain', 'unrealized_pl', 'realized_pl']:
                    color = C.get('success') if val >= 0 else C.get('danger')
                    display = f"<span style='color:{color}; direction:ltr; font-weight:bold;'>{abs(val):,.2f}</span>"
            cells += f"<td>{display}</td>"
        rows_html += f"<tr>{cells}</tr>"
    st.markdown(f"""<div class="finance-table-container"><table class="finance-table"><thead><tr>{headers}</tr></thead><tbody>{rows_html}</tbody></table></div>""", unsafe_allow_html=True)

def render_kpi(label, value, color_condition=None):
    C = st.session_state.custom_colors
    val_c = C.get('main_text')
    if color_condition == "blue": val_c = C.get('primary')
    elif isinstance(color_condition, (int, float)): val_c = C.get('success') if color_condition >= 0 else C.get('danger')
    st.markdown(f"""<div class="kpi-box"><div class="kpi-title">{label}</div><div class="kpi-value" style="color: {val_c} !important;">{value}</div></div>""", unsafe_allow_html=True)

# === الصفحات ===
def view_dashboard(fin):
    try: tp, tc = get_tasi_data()
    except: tp, tc = 0, 0
    C = st.session_state.custom_colors
    ar, cl = ("🔼", C['success']) if tc >= 0 else ("🔽", C['danger'])
    st.markdown(f"""<div class="tasi-box"><div><div style="font-size:1.1rem; opacity:0.9;">المؤشر العام</div><div style="font-size:2.2rem; font-weight:900;">{safe_fmt(tp)}</div></div><div style="background:rgba(255,255,255,0.1); padding:10px 20px; border-radius:12px; font-weight:bold; direction:ltr; color:{cl} !important; border:1px solid rgba(255,255,255,0.2)">{ar} {safe_fmt(tc)}%</div></div>""", unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    with c1: render_kpi("الكاش المتوفر", safe_fmt(fin['cash']), "blue")
    with c2: render_kpi("صافي الاستثمار", safe_fmt(fin['total_deposited']-fin['total_withdrawn']))
    with c3: render_kpi("القيمة السوقية", safe_fmt(fin['market_val_open']))
    with c4: render_kpi("الربح/الخسارة", safe_fmt(fin['unrealized_pl']+fin['realized_pl']), fin['unrealized_pl']+fin['realized_pl'])
    
    st.markdown("---")
    if fin.get('projected_dividend_income', 0) > 0:
        st.info(f"💰 الدخل السنوي المتوقع من التوزيعات: **{safe_fmt(fin['projected_dividend_income'])}** ريال")
    
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title="نمو المحفظة"), use_container_width=True)

def render_pulse_dashboard():
    st.header("💓 نبض السوق")
    if st.button("تحديث الأسعار 🔄"):
        with st.spinner("جاري التحديث..."): update_prices(); st.rerun()
    trades = fetch_table("Trades")
    wl = fetch_table("Watchlist")
    syms = list(set(trades[trades['status']=='Open']['symbol'].tolist() + wl['symbol'].tolist()))
    if not syms: st.info("القائمة فارغة"); return
    cols = st.columns(4)
    for i, s in enumerate(syms):
        n, _ = get_company_details(s)
        p, c = 0.0, 0.0
        row = trades[trades['symbol']==s]
        if not row.empty:
            p = row.iloc[0]['current_price']
            pr = row.iloc[0]['prev_close']
            if pr > 0: c = ((p-pr)/pr)*100
        with cols[i%4]: render_ticker_card(s, n or s, p, c)

def view_portfolio(fin, page_key):
    ts = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    df = fin['all_trades']
    if df.empty: st.info("فارغة"); return
    df = df[df['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    COLS = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('sector', 'القطاع'), ('status', 'الحالة'),
            ('quantity', 'الكمية'), ('entry_price', 'شراء'), ('total_cost', 'التكلفة'),
            ('current_price', 'سعر السوق'), ('market_value', 'القيمة'), ('gain', 'الربح'), ('gain_pct', 'النسبة'),
            ('daily_change', 'يومي')]
    
    op = df[df['status']=='Open']
    if not op.empty:
        c1,c2,c3,c4 = st.columns(4)
        with c1: render_kpi("القيمة السوقية", safe_fmt(op['market_value'].sum()), "blue")
        with c2: render_kpi("التكلفة", safe_fmt(op['total_cost'].sum()))
        with c3: render_kpi("الربح العائم", safe_fmt(fin['unrealized_pl']), fin['unrealized_pl'])
        with c4: render_kpi("الربح المحقق", safe_fmt(fin['realized_pl']), fin['realized_pl'])
        st.markdown("---")
        render_finance_table(op.sort_values('date', ascending=False), COLS)
    else: st.info("لا توجد أسهم مفتوحة")

def view_analysis(fin):
    st.header("🔬 التحليل والمختبر")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].tolist() + wl['symbol'].tolist()))
    
    c1, c2 = st.columns([1, 2])
    with c1: ns = st.text_input("بحث", label_visibility="collapsed")
    if ns and ns not in syms: syms.insert(0, ns)
    with c2: sym = st.selectbox("اختر السهم", syms, label_visibility="collapsed") if syms else None
    
    if sym:
        n, _ = get_company_details(sym)
        st.markdown(f"### {n} ({sym})")
        t1, t2, t3 = st.tabs(["📊 المؤشرات", "📈 الشارت", "🧪 المختبر"])
        with t1:
            d = get_fundamental_ratios(sym)
            st.metric("التقييم", f"{d.get('Score',0)}/10")
            render_financial_dashboard_ui(sym)
        with t2: view_advanced_chart(sym)
        with t3:
            st.markdown("#### اختبار الاستراتيجيات")
            c1,c2 = st.columns(2)
            strat = c1.selectbox("الاستراتيجية", ["Trend Follower", "Sniper"])
            cap = c2.number_input("رأس المال", 100000)
            if st.button("🚀 محاكاة"):
                df = get_chart_history(sym, "2y")
                res = run_backtest(df, strat, cap)
                if res:
                    st.success(f"العائد: {res['return_pct']:.2f}%")
                    st.line_chart(res['df']['Portfolio_Value'])
                else: st.error("لا توجد بيانات")

def view_settings():
    st.header("⚙️ الإعدادات")
    
    # === أداة استعادة البيانات (الحل لمشكلتك) ===
    st.markdown("### 📥 استعادة البيانات القديمة")
    st.info("إذا فقدت بياناتك، ارفع ملف `stocks.db` هنا وسيتم استعادتها فوراً.")
    
    f = st.file_uploader("ارفع ملف stocks.db", type=['db', 'sqlite', 'sql'], key="restore_uploader")
    if f:
        if st.button("⚠️ بدء الاستعادة (سيتم دمج البيانات)", type="primary"):
            try:
                # حفظ الملف مؤقتاً
                with open("temp_restore.db", "wb") as temp:
                    temp.write(f.getbuffer())
                
                # قراءة البيانات منه
                con_old = sqlite3.connect("temp_restore.db")
                
                # استعادة الصفقات
                trades = pd.read_sql("SELECT * FROM Trades", con_old)
                count = 0
                for _, r in trades.iterrows():
                    # التأكد من أسماء الأعمدة لتناسب القاعدة الجديدة
                    sym = r.get('symbol')
                    qty = r.get('quantity', 0)
                    price = r.get('entry_price', 0)
                    if sym and qty > 0:
                        execute_query("""
                            INSERT INTO Trades (symbol, company_name, sector, date, quantity, entry_price, strategy, status, current_price)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (sym, r.get('company_name'), r.get('sector'), r.get('date'), qty, price, r.get('strategy', 'مضاربة'), 'Open', price))
                        count += 1
                
                # استعادة السيولة (Deposits)
                deposits = pd.read_sql("SELECT * FROM Deposits", con_old)
                for _, r in deposits.iterrows():
                    execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s, %s, %s)", (r.get('date'), r.get('amount'), r.get('note')))
                
                st.success(f"تم استعادة {count} صفقة و {len(deposits)} عملية إيداع بنجاح!")
                con_old.close()
                st.balloons()
            except Exception as e:
                st.error(f"حدث خطأ أثناء الاستعادة: {e}")

def view_add_operations():
    st.header("➕ مركز العمليات")
    tab1, tab2 = st.tabs(["أسهم", "كاش"])
    with tab1:
        with st.form("trade"):
            c1,c2 = st.columns(2)
            op = c1.selectbox("العملية", ["شراء", "بيع"])
            strat = c2.selectbox("المحفظة", ["استثمار", "مضاربة"])
            sym = st.text_input("الرمز")
            qty = st.number_input("الكمية", 1.0)
            price = st.number_input("السعر", 0.0)
            if st.form_submit_button("تنفيذ"):
                if op == "شراء":
                    n,s = get_company_details(sym)
                    execute_query("INSERT INTO Trades (symbol, company_name, sector, date, quantity, entry_price, strategy, status, current_price) VALUES (%s,%s,%s,%s,%s,%s,%s,'Open',%s)", (sym,n,s,str(date.today()),qty,price,strat,price))
                else:
                    execute_query("UPDATE Trades SET status='Close', exit_price=%s WHERE symbol=%s AND status='Open'", (price, sym))
                st.success("تم")
    with tab2:
        with st.form("cash"):
            t = st.selectbox("النوع", ["إيداع", "سحب"])
            a = st.number_input("المبلغ")
            if st.form_submit_button("حفظ"):
                tbl = "Deposits" if t == "إيداع" else "Withdrawals"
                execute_query(f"INSERT INTO {tbl} (date, amount) VALUES (%s, %s)", (str(date.today()), a))
                st.success("تم")

def view_cash_log():
    st.header("💵 السجل المالي")
    fin = calculate_portfolio_metrics()
    c1, c2 = st.columns(2)
    c1.metric("إيداعات", f"{fin['total_deposited']:,.2f}")
    c2.metric("سحوبات", f"{fin['total_withdrawn']:,.2f}")
    st.table(fin['deposits'])

def router():
    if 'custom_colors' not in st.session_state: st.session_state.custom_colors = DEFAULT_COLORS.copy()
    C = st.session_state.custom_colors
    
    # الناف بار (تصميم الجوهرة)
    st.markdown(f"""
    <div class="navbar-box">
        <div style="display:flex; align-items:center; gap:10px;">
            <div style="font-size:2rem;">{APP_ICON}</div>
            <div><h2 style="margin:0; color:{C['primary']}">{APP_NAME}</h2></div>
        </div>
        <div>{date.today()}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # أزرار التنقل
    cols = st.columns(7)
    keys = ['home', 'spec', 'invest', 'cash', 'analysis', 'add', 'settings']
    labels = ['الرئيسية', 'مضاربة', 'استثمار', 'السيولة', 'التحليل', 'إضافة', 'الإعدادات']
    for col, key, lbl in zip(cols, keys, labels):
        if col.button(lbl, key=key, type="primary" if st.session_state.page==key else "secondary", use_container_width=True):
            st.session_state.page = key
            st.rerun()
            
    # التوجيه
    fin = calculate_portfolio_metrics()
    pg = st.session_state.page
    if pg == 'home': view_dashboard(fin)
    elif pg == 'pulse': render_pulse_dashboard()
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'cash': view_cash_log()
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'settings': view_settings()
    elif pg == 'add': view_add_operations()
