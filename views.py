import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

from components import render_navbar, render_kpi, render_table
from analytics import (calculate_portfolio_metrics, update_prices, create_smart_backup, 
                       generate_equity_curve, calculate_historical_drawdown)
from charts import render_technical_chart
from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui, get_thesis, save_thesis
from market_data import get_static_info, get_tasi_data, get_chart_history 
from database import execute_query, fetch_table, get_db, clear_all_data

try: from backtester import run_backtest
except ImportError: 
    def run_backtest(*args): return None

def safe_fmt(val, suffix=""):
    try: return f"{float(val):.2f}{suffix}"
    except: return "غير متاح"

def apply_sorting(df, cols_definition, key_suffix):
    if df.empty: return df
    with st.expander("🔍 فرز", expanded=False):
        label_to_col = {label: col for col, label in cols_definition}
        c1, c2 = st.columns([2, 1])
        sel = c1.selectbox("حسب:", list(label_to_col.keys()), key=f"sc_{key_suffix}")
        ord = c2.radio("الترتيب:", ["تنازلي", "تصاعدي"], horizontal=True, key=f"so_{key_suffix}")
    return df.sort_values(by=label_to_col[sel], ascending=(ord == "تصاعدي"))

def view_dashboard(fin):
    try: tp, tc = get_tasi_data()
    except: tp, tc = 0, 0
    ar, cl = ("🔼", "#006644") if tc >= 0 else ("🔽", "#DE350B")
    st.markdown(f"<div style='background:white;padding:20px;border-radius:8px;display:flex;justify-content:space-between;align-items:center;'><div><div style='color:#5E6C84;'>المؤشر العام</div><div style='font-size:2rem;font-weight:900;'>{tp:,.2f}</div></div><div style='background:{cl}15;color:{cl};padding:8px 20px;border-radius:6px;font-size:1.2rem;font-weight:bold;direction:ltr;'>{ar} {tc:+.2f}%</div></div>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    with c1: render_kpi("الكاش", f"{fin['cash']:,.2f}", "blue")
    with c2: render_kpi("المستثمر", f"{(fin['total_deposited']-fin['total_withdrawn']):,.2f}")
    with c3: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}")
    tpl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("صافي الربح", f"{tpl:,.2f}", 'success' if tpl >= 0 else 'danger')
    curve = generate_equity_curve(fin['all_trades'])
    if not curve.empty: st.plotly_chart(px.line(curve, x='date', y='cumulative_invested', title="نمو المحفظة"), use_container_width=True)

def view_portfolio(fin, page_key):
    ts = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 {ts}"); all_d = fin['all_trades']
    df = all_d[(all_d['strategy'] == ts) & (all_d['asset_type'] != 'Sukuk')].copy() if not all_d.empty else pd.DataFrame()
    
    if df.empty: 
        st.warning("المحفظة فارغة (أضف صفقات أولاً).")
        # لا نوقف الدالة هنا، بل نكمل لنعرض الأهداف القطاعية حتى والمحفظة فارغة
    
    if 'status' not in df.columns: df['status'] = 'Open'
    op = df[df['status']=='Open'].copy(); cl = df[df['status']=='Close'].copy()
    if not op.empty:
        op['total_cost'] = op['quantity'] * op['entry_price']; op['market_value'] = op['quantity'] * op['current_price']
        op['gain'] = op['market_value'] - op['total_cost']; op['gain_pct'] = (op['gain']/op['total_cost']*100)
    
    t1,t2,t3 = st.tabs([f"قائمة ({len(op)})", "أداء", f"أرشيف ({len(cl)})"])
    with t1:
        if page_key == 'invest':
            # --- إصلاح الخطأ هنا ---
            if not op.empty:
                ss = op.groupby('sector').agg({'market_value':'sum'}).reset_index()
                ss['current_weight'] = (ss['market_value']/ss['market_value'].sum()*100)
            else:
                ss = pd.DataFrame(columns=['sector','market_value', 'current_weight'])

            sv = fetch_table("SectorTargets"); al = set(ss['sector'].tolist())
            if not sv.empty: al.update(sv['sector'].tolist())
            
            # التأكد من عدم وجود قيم فارغة قبل الدمج
            de = pd.DataFrame({'sector': list(al)})
            
            # *** التعديل الحاسم: توحيد أنواع البيانات لتجنب ValueError ***
            if not de.empty: de['sector'] = de['sector'].astype(str)
            if not ss.empty: ss['sector'] = ss['sector'].astype(str)
            if not sv.empty: sv['sector'] = sv['sector'].astype(str)
            
            de = pd.merge(de, ss, on='sector', how='left').fillna(0)
            de = pd.merge(de, sv, on='sector', how='left').fillna(0) if not sv.empty else de.assign(target_percentage=0.0)
            
            with st.expander("تعديل الأهداف"):
                ed = st.data_editor(de, column_config={"sector": st.column_config.TextColumn("القطاع", disabled=True)}, hide_index=True, use_container_width=True)
                if st.button("حفظ"):
                    execute_query("DELETE FROM SectorTargets")
                    for _, r in ed.iterrows():
                        if r['target_percentage'] > 0: execute_query("INSERT INTO SectorTargets (sector, target_percentage) VALUES (%s, %s)", (r['sector'], r['target_percentage']))
                    st.success("تم"); st.rerun()

        if not op.empty:
            cs = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'شراء'), ('current_price', 'حالي'), ('market_value', 'سوق'), ('gain', 'ربح'), ('gain_pct', '%')]
            render_table(apply_sorting(op, cs, page_key), cs)
            with st.expander("بيع"):
                with st.form(f"s_{page_key}"):
                    c1,c2,c3 = st.columns(3); s = c1.selectbox("سهم", op['symbol'].unique()); p = c2.number_input("سعر", min_value=0.01); d = c3.date_input("تاريخ", date.today())
                    if st.form_submit_button("تأكيد"): execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, ts)); st.success("تم"); st.rerun()
    with t2:
        if not op.empty: 
            dd = calculate_historical_drawdown(op)
            if not dd.empty: st.plotly_chart(px.area(dd, x='date', y='drawdown'), use_container_width=True)
    with t3:
        if not cl.empty: render_table(cl, [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('gain', 'الربح'), ('exit_date', 'تاريخ')])

def view_sukuk_portfolio(fin):
    st.header("📜 صكوك"); sk = fin['all_trades'][fin['all_trades']['asset_type'] == 'Sukuk'] if not fin['all_trades'].empty else pd.DataFrame()
    if sk.empty: st.warning("لا يوجد"); return
    op = sk[sk['status'] == 'Open']; st.metric("إجمالي", f"{op['quantity'].mul(op['entry_price']).sum():,.2f}")
    render_table(op, [('company_name', 'اسم'), ('symbol', 'رمز'), ('quantity', 'عدد'), ('entry_price', 'شراء')])

def view_analysis(fin):
    st.header("🔬 تحليل"); wl = fetch_table("Watchlist")
    sl = list(set(fin['all_trades']['symbol'].unique().tolist() + (wl['symbol'].unique().tolist() if not wl.empty else [])))
    c1,c2 = st.columns([1,2]); ns = c1.text_input("بحث"); sym = c2.selectbox("اختر", [ns]+sl if ns else sl) if sl or ns else None
    if sym:
        n, s = get_static_info(sym); st.markdown(f"### {n} ({sym})")
        t1,t2,t3,t4,t5 = st.tabs(["مؤشرات", "قوائم", "أطروحة", "فني", "كلاسيكي"])
        with t1:
            d = get_fundamental_ratios(sym); c1,c2=st.columns([1,3]); c1.metric("Score", f"{d['Score']}/10", d['Rating'])
            with c2: 
                for o in d['Opinions']: st.write(f"• {o}")
            st.metric("Fair Value", safe_fmt(d['Fair_Value']))
        with t2: render_financial_dashboard_ui(sym)
        with t3:
            cr = get_thesis(sym)
            with st.form("th"):
                tg = st.number_input("هدف", value=cr['target_price'] if cr else 0.0); tx = st.text_area("نص", value=cr['thesis_text'] if cr else "")
                if st.form_submit_button("حفظ"): save_thesis(sym, tx, tg, "Hold"); st.success("تم")
        with t4: render_technical_chart(sym, "2y", "1d")
        with t5: from classical_analysis import render_classical_analysis; render_classical_analysis(sym)

def view_backtester_ui(fin):
    st.header("🧪 مختبر"); c1,c2,c3 = st.columns(3)
    with c1: sy = st.selectbox("سهم", list(set(fin['all_trades']['symbol'].unique().tolist() + ["1120.SR"])))
    with c2: stg = st.selectbox("خطة", ["Trend Follower (جون ميرفي)", "Sniper (هجين)"])
    with c3: cp = st.number_input("رأس مال", value=100000)
    if st.button("بدء"):
        r = run_backtest(get_chart_history(sy, "2y", "1d"), stg, cp)
        if r: st.success("تم"); st.metric("عائد", f"{r['return_pct']:.2f}%"); st.line_chart(r['df']['Portfolio_Value']); st.dataframe(r['trades_log'])
        else: st.error("بيانات ناقصة")

def view_add_trade():
    st.header("➕ إضافة"); 
    with st.form("add"):
        c1,c2 = st.columns(2); s = c1.text_input("رمز"); t = c2.selectbox("نوع", ["استثمار", "مضاربة", "صكوك"])
        c3,c4,c5 = st.columns(3); q = c3.number_input("كمية", 1.0); p = c4.number_input("سعر", 0.0); d = c5.date_input("تاريخ", date.today())
        if st.form_submit_button("حفظ"):
            n, sec = get_static_info(s); at = "Sukuk" if t=="صكوك" else "Stock"
            execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Open', %s)", (s, n, sec, at, str(d), q, p, t, p))
            st.success("تم"); st.cache_data.clear()

def view_cash_log():
    st.header("💵 سيولة"); fin = calculate_portfolio_metrics()
    t1,t2,t3 = st.tabs(["إيداع", "سحب", "توزيع"])
    with t1:
        with st.expander("جديد"):
            with st.form("d"):
                a = st.number_input("مبلغ"); d = st.date_input("تاريخ"); n = st.text_input("ملاحظة")
                if st.form_submit_button("حفظ"): execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s, %s, %s)", (str(d), a, n)); st.rerun()
        render_table(fin['deposits'], [('date','تاريخ'), ('amount','مبلغ'), ('note','ملاحظة')])
    with t2:
        with st.expander("جديد"):
            with st.form("w"):
                a = st.number_input("مبلغ"); d = st.date_input("تاريخ"); n = st.text_input("ملاحظة")
                if st.form_submit_button("حفظ"): execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s, %s, %s)", (str(d), a, n)); st.rerun()
        render_table(fin['withdrawals'], [('date','تاريخ'), ('amount','مبلغ')])
    with t3:
        with st.expander("جديد"):
            with st.form("r"):
                s = st.text_input("رمز"); a = st.number_input("مبلغ"); d = st.date_input("تاريخ")
                if st.form_submit_button("حفظ"): execute_query("INSERT INTO ReturnsGrants (date, symbol, amount) VALUES (%s, %s, %s)", (str(d), s, a)); st.rerun()
        render_table(fin['returns'], [('date','تاريخ'), ('symbol','رمز'), ('amount','مبلغ')])

def view_tools(): st.header("🛠️ أدوات"); st.info(f"زكاة: {calculate_portfolio_metrics()['market_val_open']*0.025775:,.2f}")
def view_settings(): st.header("⚙️ إعدادات"); st.button("حذف الكل", on_click=lambda: (clear_all_data(), st.rerun()))

def router():
    render_navbar()
    if 'page' not in st.session_state: st.session_state.page = 'home'
    pg = st.session_state.page; fin = calculate_portfolio_metrics()
    if pg == 'home': view_dashboard(fin)
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
