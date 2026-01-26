import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time

# استيراد المكتبات والمكونات
from config import DEFAULT_COLORS
from components import render_navbar, render_kpi, render_table, render_ticker_card, safe_fmt
from analytics import (calculate_portfolio_metrics, update_prices, generate_equity_curve, run_backtest)
from database import execute_query, fetch_table
from market_data import get_static_info, get_tasi_data, get_chart_history
from data_source import get_company_details
from charts import view_advanced_chart

# محاولة استيراد التحليل المالي والكلاسيكي (مع حماية في حال عدم وجود الملفات)
try: from financial_analysis import get_fundamental_ratios, render_financial_dashboard_ui
except ImportError: 
    get_fundamental_ratios = lambda s: {'Score': 0}
    render_financial_dashboard_ui = lambda s: st.info("بيانات القوائم المالية غير متوفرة حالياً")

try: from classical_analysis import render_classical_analysis
except ImportError:
    render_classical_analysis = lambda s: st.info("التحليل الكلاسيكي قيد التجهيز")

# ---------------------------------------------------------
# 1. لوحة القيادة (Dashboard)
# ---------------------------------------------------------
def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    C = DEFAULT_COLORS
    arrow, cl = ("🔼", C['success']) if t_change >= 0 else ("🔽", C['danger'])
    
    # صندوق تاسي الفاخر
    st.markdown(f"""
    <div class="tasi-box">
        <div>
            <div style="font-size:1.1rem; opacity:0.9;">المؤشر العام (TASI)</div>
            <div style="font-size:2.5rem; font-weight:900;">{safe_fmt(t_price)}</div>
        </div>
        <div style="background:rgba(255,255,255,0.2); padding:10px 25px; border-radius:12px; font-weight:bold; font-size:1.4rem; direction:ltr;">
            {arrow} {t_change:.2f}%
        </div>
    </div>""", unsafe_allow_html=True)
    
    # مؤشرات الأداء الرئيسية (KPIs)
    c1,c2,c3,c4 = st.columns(4)
    with c1: render_kpi("الكاش المتوفر", safe_fmt(fin['cash']), "blue")
    with c2: render_kpi("صافي الاستثمار", safe_fmt(fin['total_deposited'] - fin['total_withdrawn']))
    with c3: render_kpi("القيمة السوقية", safe_fmt(fin['market_val_open']))
    tpl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("الأرباح الكلية", safe_fmt(tpl), tpl)
    
    st.markdown("---")
    
    # رسم نمو المحفظة
    st.subheader("📈 نمو المحفظة")
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty: 
        fig = px.line(crv, x='date', y='cumulative_invested', title="")
        fig.update_layout(xaxis_title="التاريخ", yaxis_title="القيمة")
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# 2. المحفظة (Portfolio) - بكل تفاصيلها
# ---------------------------------------------------------
def view_portfolio(fin, page_key):
    ts = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    all_d = fin['all_trades']
    
    df = pd.DataFrame()
    if not all_d.empty:
        # فلترة حسب الاستراتيجية
        df = all_d[all_d['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    if df.empty: st.info("المحفظة فارغة"); return

    # تعريف الأعمدة الكاملة (كما طلبت)
    COLS = [
        ('company_name', 'الشركة'), ('sector', 'القطاع'), ('status', 'الحالة'),
        ('symbol', 'الرمز'), ('date', 'تاريخ الشراء'), ('exit_date', 'تاريخ البيع'),
        ('quantity', 'الكمية'), ('entry_price', 'سعر الشراء'), ('total_cost', 'التكلفة'),
        ('year_high', 'اعلى سنوي'), ('current_price', 'السعر الحالي'), ('year_low', 'ادنى سنوي'),
        ('market_value', 'سعر السوق'), ('gain', 'الربح/الخسارة'), ('gain_pct', 'النسبة %'),
        ('weight', 'الوزن'), ('daily_change', 'تغير يومي'), ('prev_close', 'اغلاق سابق')
    ]

    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()

    # ملخص سريع بالأرقام
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi("القيمة السوقية", safe_fmt(open_df['market_value'].sum() if not open_df.empty else 0), "blue")
    with c2: render_kpi("التكلفة", safe_fmt(open_df['total_cost'].sum() if not open_df.empty else 0))
    with c3: render_kpi("الربح العائم", safe_fmt(open_df['gain'].sum() if not open_df.empty else 0))
    with c4: render_kpi("الربح المحقق", safe_fmt(closed_df['gain'].sum() if not closed_df.empty else 0))
    st.markdown("---")

    # التبويبات الثلاثة
    t1, t2, t3 = st.tabs(["📋 الأسهم الحالية", "📊 تحليل الأداء", "🗄️ الأرشيف"])
    
    with t1:
        if not open_df.empty:
            # خيارات الفرز
            c_sort, _ = st.columns([1, 4])
            with c_sort:
                st.markdown("**ترتيب حسب:**")
                sort_opt = st.radio("sort_r", ["الأحدث", "الأعلى ربحاً"], horizontal=True, label_visibility="collapsed")
            
            if sort_opt == "الأعلى ربحاً": open_df = open_df.sort_values(by="gain", ascending=False)
            else: open_df = open_df.sort_values(by="date", ascending=False)

            render_table(open_df, COLS)
            
            # قسم البيع
            with st.expander("🔻 تسجيل بيع سهم"):
                with st.form("sell"):
                    c1,c2 = st.columns(2)
                    st.markdown("**اختر السهم:**"); s = c1.selectbox("s", open_df['symbol'].unique(), label_visibility="collapsed")
                    st.markdown("**سعر البيع:**"); p = c2.number_input("p", min_value=0.0, label_visibility="collapsed")
                    st.markdown("**تاريخ البيع:**"); d = st.date_input("d", date.today(), label_visibility="collapsed")
                    if st.form_submit_button("تأكيد البيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, ts))
                        st.success("تم البيع"); time.sleep(0.5); st.rerun()
        else: st.info("لا توجد أسهم حالية")
    
    with t2:
        if not open_df.empty:
            st.markdown("#### توزيع المحفظة حسب القطاعات")
            fig = px.pie(open_df, values='market_value', names='sector', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("لا توجد بيانات للتحليل")
            
    with t3:
        if not closed_df.empty:
            closed_df['net_sales'] = closed_df['quantity'] * closed_df['exit_price']
            closed_df['realized_gain'] = closed_df['net_sales'] - closed_df['total_cost']
            # إضافة أعمدة خاصة بالأرشيف
            ARCHIVE_COLS = COLS + [('net_sales', 'صافي البيع'), ('realized_gain', 'الربح المحقق')]
            render_table(closed_df.sort_values('exit_date', ascending=False), ARCHIVE_COLS)
        else: st.info("الأرشيف فارغ")

# ---------------------------------------------------------
# 3. مركز التحليل (Analysis Center) - شامل
# ---------------------------------------------------------
def view_analysis(fin):
    st.header("🔬 مركز التحليل الشامل")
    trades = fin['all_trades']
    wl = fetch_table("Watchlist")
    
    # تجميع الرموز من المحفظة والمفضلة
    symbols = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c1, c2 = st.columns([1, 2])
    with c1: 
        st.markdown("**بحث برمز جديد:**")
        ns = st.text_input("s_search", label_visibility="collapsed")
    if ns and ns not in symbols: symbols.insert(0, ns)
    
    with c2:
        st.markdown("**أو اختر من القائمة:**")
        sym = st.selectbox("s_select", symbols, label_visibility="collapsed") if symbols else None
    
    if sym:
        n, s = get_company_details(sym)
        st.markdown(f"### {n} ({sym})")
        
        # التبويبات الخمسة للتحليل
        t1, t2, t3, t4, t5 = st.tabs(["📊 المؤشرات الأساسية", "📑 القوائم المالية", "📝 الأطروحة", "📈 التحليل الفني", "🏛️ التحليل الكلاسيكي"])
        
        with t1:
            d = get_fundamental_ratios(sym)
            c1,c2 = st.columns([1,3])
            c1.metric("التقييم العام", f"{d.get('Score', 0)}/10")
            # عرض بقية المؤشرات
            st.json(d) if d else st.info("لا توجد بيانات")
            
        with t2: 
            render_financial_dashboard_ui(sym)
            
        with t3: 
            st.info("مساحة لكتابة الأطروحة الاستثمارية (قيد التطوير)")
            
        with t4: 
            view_advanced_chart(sym)
            
        with t5: 
            render_classical_analysis(sym)

# ---------------------------------------------------------
# 4. مختبر الاستراتيجيات (Backtester)
# ---------------------------------------------------------
def view_backtester_ui(fin):
    st.header("🧪 مختبر الاستراتيجيات")
    
    c1, c2, c3 = st.columns(3)
    with c1: 
        st.markdown("**السهم:**")
        # قائمة افتراضية لتجنب الخطأ إذا كانت القائمة فارغة
        all_syms = list(set(fin['all_trades']['symbol'].unique().tolist() + ["1120"]))
        sym = st.selectbox("bs", all_syms, label_visibility="collapsed")
    with c2: 
        st.markdown("**الاستراتيجية:**")
        strat = st.selectbox("bst", ["Trend Follower", "Sniper"], label_visibility="collapsed")
    with c3: 
        st.markdown("**رأس المال الافتراضي:**")
        cap = st.number_input("bc", 100000, label_visibility="collapsed")
        
    if st.button("🚀 تشغيل الاختبار"):
        with st.spinner("جاري تحليل البيانات التاريخية..."):
            df = get_chart_history(sym, "2y")
            if df is not None and not df.empty:
                res = run_backtest(df, strat, cap)
                if res:
                    # عرض النتائج
                    k1, k2, k3 = st.columns(3)
                    k1.metric("العائد الكلي", f"{res['return_pct']:.2f}%", delta_color="normal")
                    k2.metric("الرصيد النهائي", safe_fmt(res['final_value']))
                    k3.metric("عدد الصفقات", res.get('trades_count', 0))
                    
                    st.line_chart(res['df']['Portfolio_Value'])
                    
                    with st.expander("سجل الصفقات التفصيلي"):
                        st.dataframe(res.get('trades_log', pd.DataFrame()))
            else: 
                st.error("بيانات السهم غير كافية للاختبار")

# ---------------------------------------------------------
# 5. الصفحات الأخرى (نبض السوق، السيولة، الصكوك، الأدوات)
# ---------------------------------------------------------
def render_pulse_dashboard():
    st.header("💓 نبض السوق")
    trades = fetch_table("Trades"); wl = fetch_table("Watchlist")
    syms = list(set(trades[trades['status']=='Open']['symbol'].tolist() + wl['symbol'].tolist())) if not trades.empty else []
    if not syms: st.info("القائمة فارغة"); return
    
    cols = st.columns(4)
    for i, s in enumerate(syms):
        n, _ = get_company_details(s)
        row = trades[trades['symbol']==s]
        p = row.iloc[0]['current_price'] if not row.empty else 0.0
        # هنا يمكن إضافة التغير إذا توفر
        with cols[i%4]: render_ticker_card(s, n, p, 0.0)

def view_cash_log():
    st.header("💵 سجل السيولة")
    fin = calculate_portfolio_metrics()
    c1, c2, c3 = st.columns(3)
    net = fin['deposits']['amount'].sum() - fin['withdrawals']['amount'].sum()
    
    with c1: render_kpi("إجمالي الإيداعات", safe_fmt(fin['deposits']['amount'].sum()), "success")
    with c2: render_kpi("إجمالي السحوبات", safe_fmt(fin['withdrawals']['amount'].sum()), "danger")
    with c3: render_kpi("صافي التمويل", safe_fmt(net), "blue")
    st.markdown("---")
    
    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "العوائد"])
    cols = [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظات')]
    with t1: render_table(fin['deposits'].sort_values('date', ascending=False), cols)
    with t2: render_table(fin['withdrawals'].sort_values('date', ascending=False), cols)
    with t3: render_table(fin['returns'].sort_values('date', ascending=False), [('date','التاريخ'), ('symbol','الرمز'), ('amount','المبلغ'), ('note','النوع')])

def view_sukuk_portfolio(fin):
    st.header("📜 الصكوك")
    df = fin['all_trades']
    if 'asset_type' not in df.columns: st.info("لا توجد بيانات"); return
    
    sk = df[df['asset_type']=='Sukuk'].copy()
    if not sk.empty:
        render_table(sk, [('company_name', 'الاسم'), ('symbol', 'الرمز'), ('quantity', 'الكمية'), ('entry_price', 'شراء'), ('gain', 'الربح')])
    else: st.info("لا توجد صكوك")

def view_add_operations():
    st.header("➕ مركز العمليات")
    tab1, tab2 = st.tabs(["📈 تسجيل صفقة (أسهم)", "💰 حركة مالية (كاش)"])
    
    with tab1:
        with st.form("trade_form"):
            c1, c2 = st.columns(2)
            st.markdown("**رمز السهم:**"); s = c1.text_input("s", label_visibility="collapsed")
            st.markdown("**نوع المحفظة:**"); st_t = c2.selectbox("st", ["استثمار", "مضاربة", "صكوك"], label_visibility="collapsed")
            c3, c4, c5 = st.columns(3)
            st.markdown("**الكمية:**"); q = c3.number_input("q", 1.0, label_visibility="collapsed")
            st.markdown("**السعر:**"); p = c4.number_input("p", 0.0, label_visibility="collapsed")
            st.markdown("**التاريخ:**"); d = c5.date_input("d", date.today(), label_visibility="collapsed")
            
            if st.form_submit_button("حفظ الصفقة"):
                if s and q > 0:
                    n, sec = get_company_details(s)
                    at = "Sukuk" if st_t == "صكوك" else "Stock"
                    execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Open',%s)", (s, n, sec, at, str(d), q, p, st_t, p))
                    st.success("تم الحفظ بنجاح"); st.cache_data.clear()
                else: st.error("تأكد من إدخال الرمز والكمية")

    with tab2:
        with st.form("cash_form"):
            c1, c2 = st.columns(2)
            st.markdown("**النوع:**"); ty = c1.selectbox("t", ["إيداع نقدي", "سحب نقدي", "توزيعات"], label_visibility="collapsed")
            st.markdown("**المبلغ:**"); am = c2.number_input("a", 0.0, label_visibility="collapsed")
            st.markdown("**التاريخ:**"); da = st.date_input("da", date.today(), label_visibility="collapsed")
            st.markdown("**ملاحظة / الرمز:**"); no = st.text_input("no", label_visibility="collapsed")
            
            if st.form_submit_button("حفظ الحركة"):
                if am > 0:
                    if "إيداع" in ty: execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s,%s,%s)", (str(da), am, no))
                    elif "سحب" in ty: execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s,%s,%s)", (str(da), am, no))
                    else: execute_query("INSERT INTO ReturnsGrants (date, symbol, amount, note) VALUES (%s,%s,%s,%s)", (str(da), no, am, "توزيعات"))
                    st.success("تم التسجيل"); st.rerun()
                else: st.error("المبلغ يجب أن يكون أكبر من صفر")

def view_tools():
    st.header("🛠️ الأدوات")
    fin = calculate_portfolio_metrics()
    st.info(f"زكاة الأسهم التقريبية: {safe_fmt(fin['market_val_open']*0.025775)}")

def view_settings():
    st.header("⚙️ الإعدادات")
    with st.expander("📥 استيراد بيانات (Excel/CSV)"):
        f = st.file_uploader("اختر الملف", accept_multiple_files=False)
        if f: st.info("الميزة جاهزة للاستيراد")
    
    with st.expander("📎 إدارة المرفقات"):
        doc = st.file_uploader("رفع مستند PDF/Image", type=['pdf', 'png', 'jpg'])
        if doc and st.button("حفظ المستند"):
            try:
                bytes_data = doc.getvalue()
                execute_query("INSERT INTO Documents (file_name, file_data) VALUES (%s, %s)", (doc.name, bytes_data))
                st.success("تم الرفع")
            except Exception as e: st.error(f"خطأ: {e}")

# ---------------------------------------------------------
# الموجه الرئيسي (Router)
# ---------------------------------------------------------
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
    elif pg == 'add': view_add_operations()
    elif pg == 'update': 
        with st.spinner("جاري تحديث الأسعار..."): update_prices()
        st.session_state.page='home'; st.rerun()
