import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

from config import DEFAULT_COLORS
from components import render_kpi, render_ticker_card, safe_fmt, render_custom_table
from analytics import calculate_portfolio_metrics, update_prices, generate_equity_curve
from database import execute_query, fetch_table, get_db, clear_all_data
from market_data import get_static_info, get_tasi_data, get_chart_history, fetch_batch_data
from charts import render_technical_chart
from backtester import run_backtest
from financial_analysis import render_financial_dashboard_ui, get_fundamental_ratios, get_thesis, save_thesis
from classical_analysis import render_classical_analysis

# --- القائمة العلوية ---
def render_navbar():
    c1, c2, c3, c4, c5, c6, c7, c8, c9, c10 = st.columns(10)
    buttons = [
        ('🏠 الرئيسية', 'home'), ('⚡ مضاربة', 'spec'), ('💎 استثمار', 'invest'),
        ('💓 نبض', 'pulse'), ('📜 صكوك', 'sukuk'), ('🔍 تحليل', 'analysis'),
        ('🧪 المختبر', 'backtest'), ('💰 السيولة', 'cash'), ('🔄 تحديث', 'update')
    ]
    for i, (lbl, key) in enumerate(buttons):
        with [c1,c2,c3,c4,c5,c6,c7,c8,c9][i]:
            if st.button(lbl, use_container_width=True): st.session_state.page = key; st.rerun()
    with c10:
        with st.popover("👤 القائمة"):
            st.write(f"مرحباً {st.session_state.get('username','User')}")
            if st.button("➕ إضافة", use_container_width=True): st.session_state.page='add'; st.rerun()
            if st.button("⚙️ إعدادات", use_container_width=True): st.session_state.page='settings'; st.rerun()
            if st.button("خروج", use_container_width=True): st.session_state.clear(); st.rerun()
    st.markdown("---")

# --- الصفحات ---
def view_dashboard(fin):
    try: tp, tc = get_tasi_data()
    except: tp, tc = 0, 0
    col = "#006644" if tc >= 0 else "#DE350B"
    st.markdown(f"<div class='tasi-box'><div><b>المؤشر العام (TASI)</b><h2>{tp:,.2f}</h2></div><div style='color:{col}'><b>{tc:+.2f}%</b></div></div>", unsafe_allow_html=True)
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi("الكاش المتوفر", safe_fmt(fin['cash']), "blue")
    with c2: render_kpi("رأس المال المستثمر", safe_fmt(fin['total_deposited']-fin['total_withdrawn']))
    with c3: render_kpi("القيمة السوقية", safe_fmt(fin['market_val_open']))
    tpl = fin['unrealized_pl'] + fin['realized_pl']
    with c4: render_kpi("الربح/الخسارة", safe_fmt(tpl), 'success' if tpl>=0 else 'danger')
    
    st.markdown("---")
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title="النمو"), use_container_width=True)

# === المحفظة (التصميم مطابق للصورة 522 و 524) ===
def view_portfolio(fin, key):
    ts = "مضاربة" if key=='spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    df = fin['all_trades']
    
    if df.empty: st.info("المحفظة فارغة"); return
    sub = df[df['strategy'].astype(str).str.contains(ts, na=False)]
    
    open_df = sub[sub['status']=='Open'].copy()
    closed_df = sub[sub['status']=='Close'].copy()
    
    # التبويبات
    t1, t2 = st.tabs(["الصفقات القائمة", "الأرشيف"])
    
    with t1:
        if not open_df.empty:
            # شريط الفلتر والتعديل فوق الجدول (كما في الصورة)
            c_act1, c_act2 = st.columns([3, 1])
            with c_act1:
                sel_deal = st.selectbox("اختر صفقة للتعديل/الإغلاق:", open_df.apply(lambda x: f"{x['symbol']} - {x['company_name']} ({x['date']})", axis=1))
            with c_act2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("📝 تعديل التفاصيل", type="primary", use_container_width=True):
                    st.toast("خاصية التعديل قيد التطوير")

            # === الجدول المخصص (HTML) ===
            # الأعمدة وترتيبها كما في الصور
            table_config = [
                ('company_name', 'الشركة', 'text'),
                ('symbol', 'الرمز', 'text'),
                ('sector', 'القطاع', 'text'),
                ('status', 'الحالة', 'badge'),
                ('quantity', 'الكمية', 'money'),
                ('entry_price', 'شراء', 'money'),
                ('total_cost', 'التكلفة', 'money'),
                ('current_price', 'سعر السوق/البيع', 'money'),
                ('market_value', 'القيمة', 'money'),
                ('gain', 'الربح/الخسارة', 'colorful'),
                ('gain_pct', 'النسبة %', 'percent'),
                ('weight', 'الوزن', 'percent'),
                ('daily_change', 'تغير يومي', 'percent'),
                ('date', 'التاريخ', 'date')
            ]
            render_custom_table(open_df, table_config)
            
            # خيار البيع السريع
            with st.expander("تسجيل بيع سريع"):
                with st.form(f"quick_sell_{key}"):
                    c1,c2 = st.columns(2)
                    s = c1.selectbox("السهم", open_df['symbol'].unique())
                    p = c2.number_input("سعر البيع")
                    d = st.date_input("التاريخ", date.today())
                    if st.form_submit_button("بيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'",(p,str(d),s,ts))
                        st.success("تم"); st.rerun()
        else: st.info("لا توجد صفقات مفتوحة")

    with t2:
        if not closed_df.empty:
            render_custom_table(closed_df, [('company_name','الشركة','text'), ('symbol','الرمز','text'), ('gain','الربح','colorful'), ('exit_date','تاريخ البيع','date')])

# === السيولة (مطابق للصورة 525) ===
def view_cash_log():
    st.header("السجلات المالية")
    fin = calculate_portfolio_metrics()
    
    # 1. شريط الفرز (اختياري كما في الصورة)
    st.selectbox("فرز السجلات حسب:", ["التاريخ (الأحدث)", "المبلغ (الأعلى)"])
    
    # 2. التبويبات (أيقونات + نص)
    t1, t2, t3 = st.tabs(["📥 الإيداعات", "📤 السحوبات", "🎁 العوائد"])
    
    # تعريف أعمدة الجدول البسيط
    cols_simple = [('date', 'التاريخ', 'date'), ('amount', 'المبلغ', 'money'), ('note', 'ملاحظات', 'text')]
    
    with t1:
        st.markdown(f"<h5 style='text-align:left'>الإجمالي: {fin['deposits']['amount'].sum():,.2f}</h5>", unsafe_allow_html=True)
        render_custom_table(fin['deposits'], cols_simple)
        with st.expander("إضافة إيداع"):
            with st.form("d"):
                a=st.number_input("المبلغ"); d=st.date_input("التاريخ"); n=st.text_input("ملاحظة")
                if st.form_submit_button("حفظ"): execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s,%s,%s)",(str(d),a,n)); st.rerun()
    
    with t2:
        st.markdown(f"<h5 style='text-align:left'>الإجمالي: {fin['withdrawals']['amount'].sum():,.2f}</h5>", unsafe_allow_html=True)
        render_custom_table(fin['withdrawals'], cols_simple)
        with st.expander("إضافة سحب"):
            with st.form("w"):
                a=st.number_input("المبلغ"); d=st.date_input("تاريخ"); n=st.text_input("ملاحظة")
                if st.form_submit_button("حفظ"): execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s,%s,%s)",(str(d),a,n)); st.rerun()

    with t3:
        st.markdown(f"<h5 style='text-align:left'>الإجمالي: {fin['returns']['amount'].sum():,.2f}</h5>", unsafe_allow_html=True)
        render_custom_table(fin['returns'], cols_simple + [('symbol', 'الرمز', 'text')])
        with st.expander("إضافة عائد"):
            with st.form("r"):
                s=st.text_input("الرمز"); a=st.number_input("المبلغ"); d=st.date_input("التاريخ")
                if st.form_submit_button("حفظ"): execute_query("INSERT INTO ReturnsGrants (date, symbol, amount) VALUES (%s,%s,%s)",(str(d),s,a)); st.rerun()

# باقي الصفحات (التحليل، المختبر..) كما هي في الرد السابق
def view_analysis(fin):
    st.header("🔬 التحليل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    c1,c2=st.columns([1,2]); ns=c1.text_input("بحث"); sym=c2.selectbox("اختر", [ns]+syms if ns else syms) if syms or ns else None
    if sym:
        n, s = get_static_info(sym); st.markdown(f"### {n} ({sym})")
        t1,t2,t3,t4,t5 = st.tabs(["مؤشرات", "فني", "قوائم", "كلاسيكي", "أطروحة"])
        with t1: d=get_fundamental_ratios(sym); st.metric("التقييم", f"{d['Score']}/10"); st.write(d.get('Opinions'))
        with t2: render_technical_chart(sym)
        with t3: render_financial_dashboard_ui(sym)
        with t4: render_classical_analysis(sym)
        with t5: 
            th=get_thesis(sym); st.text_area("نص", value=th['thesis_text'] if th else "")

def view_backtester_ui(fin):
    st.header("🧪 المختبر")
    c1,c2,c3 = st.columns(3)
    sym = c1.selectbox("السهم", ["1120.SR", "2010.SR"] + fin['all_trades']['symbol'].unique().tolist() if not fin['all_trades'].empty else [])
    strat = c2.selectbox("خطة", ["Trend Follower", "Sniper"])
    cap = c3.number_input("مبلغ", 100000)
    if st.button("بدء"):
        res = run_backtest(get_chart_history(sym, "2y"), strat, cap)
        if res:
            st.metric("العائد", f"{res['return_pct']:.2f}%")
            st.line_chart(res['df']['Portfolio_Value'])
            st.dataframe(res['trades_log'])

def render_pulse_dashboard():
    st.header("💓 نبض السوق")
    st.info("سيتم عرض الأسعار هنا") # يمكن ربطها بـ fetch_batch_data

def view_sukuk_portfolio(fin): st.header("📜 صكوك"); render_custom_table(fin['all_trades'][fin['all_trades']['asset_type']=='Sukuk'], [('symbol','رمز','text'),('quantity','كمية','money')])
def view_add_trade():
    st.header("➕ إضافة")
    with st.form("add"):
        c1,c2=st.columns(2); s=c1.text_input("رمز"); t=c2.selectbox("نوع", ["استثمار","مضاربة","صكوك"])
        c3,c4,c5=st.columns(3); q=c3.number_input("كمية"); p=c4.number_input("سعر"); d=c5.date_input("تاريخ", date.today())
        if st.form_submit_button("حفظ"):
            at = "Sukuk" if t=="صكوك" else "Stock"
            execute_query("INSERT INTO Trades (symbol, asset_type, date, quantity, entry_price, strategy, status) VALUES (%s,%s,%s,%s,%s,%s,'Open')", (s,at,str(d),q,p,t))
            st.success("تم"); st.cache_data.clear()
def view_tools(): st.header("🛠️ أدوات"); st.info("الزكاة")
def view_settings(): st.header("⚙️ إعدادات"); st.info("الاستيراد")

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
