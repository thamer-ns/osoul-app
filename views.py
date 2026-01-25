import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import time

# === الاستيرادات من المحرك القوي ===
from config import DEFAULT_COLORS
from analytics import (calculate_portfolio_metrics, update_prices, generate_equity_curve, run_backtest)
from database import execute_query, fetch_table, get_db
from market_data import get_static_info, get_tasi_data, get_chart_history
from data_source import get_company_details
# نستورد دوال التحليل والمختبر (إذا كانت موجودة في ملفاتك الأخرى)
try: from financial_analysis import render_financial_dashboard_ui
except: render_financial_dashboard_ui = lambda s: st.info("تحليل مالي غير متوفر")

# ==========================================
# 1. دوال التصميم (مأخوذة من البرنامج القديم الجميل)
# ==========================================

def render_navbar():
    if 'custom_colors' not in st.session_state:
        st.session_state.custom_colors = DEFAULT_COLORS.copy()
    C = st.session_state.custom_colors

    # الهيدر العائم الجميل
    st.markdown(f"""
    <div style="background-color: {C.get('card_bg')}; padding: 15px 25px; border-bottom: 1px solid {C.get('border')}; margin-bottom: 30px; display: flex; align-items: center; justify-content: space-between; border-radius: 16px; box-shadow: 0 4px 15px rgba(0,0,0,0.03);">
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="font-size: 2.2rem; background: #EFF6FF; width:55px; height:55px; display:flex; align-items:center; justify-content:center; border-radius:12px;">💎</div>
            <div>
                <h2 style="margin: 0; color: {C.get('primary')} !important; font-weight: 800; font-size: 1.4rem;">أصولي</h2>
                <span style="font-size: 0.8rem; color: {C.get('sub_text')}; font-weight: 600;">بوابتك الذكية للاستثمار</span>
            </div>
        </div>
        <div style="text-align: left; background-color: {C.get('page_bg')}; padding: 8px 16px; border-radius: 10px; border:1px solid {C.get('border')};">
            <div style="font-weight: 800; color: {C.get('main_text')}; font-size: 0.9rem;">مرحباً بك</div>
            <div style="font-weight: 600; color: {C.get('sub_text')}; font-size: 0.75rem; direction: ltr;">{date.today().strftime('%Y-%m-%d')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # شريط التنقل المدمج (كل الخيارات)
    c_nav, c_refresh = st.columns([8, 1])
    with c_nav:
        cols = st.columns(8)
        # دمجنا خيارات البرنامجين هنا
        labels = ['الرئيسية', 'مضاربة', 'استثمار', 'صكوك', 'السيولة', 'التحليل', 'المختبر', 'الإعدادات']
        keys = ['home', 'spec', 'invest', 'sukuk', 'cash', 'analysis', 'backtest', 'settings']
        
        for i, (col, label, key) in enumerate(zip(cols, labels, keys)):
            is_active = (st.session_state.get('page') == key)
            btn_type = "primary" if is_active else "secondary"
            if col.button(label, key=f"nav_{i}", use_container_width=True, type=btn_type):
                st.session_state.page = key
                st.rerun()
    
    with c_refresh:
        if st.button("تحديث 🔄", use_container_width=True):
            with st.spinner("جاري جلب الأسعار المباشرة..."):
                update_prices()
                time.sleep(0.5); st.rerun()
    st.markdown("---")

def render_kpi(label, value, color_condition=None):
    C = st.session_state.custom_colors
    val_c = C.get('main_text')
    
    # منطق الألوان الذكي
    if color_condition == "blue": val_c = C.get('primary')
    elif isinstance(color_condition, (int, float)):
        val_c = C.get('success') if color_condition >= 0 else C.get('danger')
            
    st.markdown(f"""
    <div class="kpi-box" style="background:{C.get('card_bg')}; padding:20px; border-radius:16px; border:1px solid {C.get('border')}; text-align:right; box-shadow:0 4px 6px -1px rgba(0,0,0,0.05); transition: transform 0.2s;">
        <div style="color:{C.get('sub_text')}; font-size:0.9rem; font-weight:700; margin-bottom:8px;">{label}</div>
        <div style="color:{val_c} !important; font-size:1.7rem; font-weight:900; direction:ltr; font-family:'Cairo';">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_finance_table(df, cols_def):
    if df.empty:
        st.info("لا توجد بيانات للعرض")
        return

    C = st.session_state.custom_colors
    headers = "".join([f"<th>{label}</th>" for _, label in cols_def])
    rows_html = ""
    
    for _, row in df.iterrows():
        cells = ""
        for k, _ in cols_def:
            val = row.get(k)
            
            # === منطق "غير موجود" ===
            # إذا كانت القيمة None أو NaN أو نص فارغ، نعرض "غير موجود"
            if pd.isna(val) or val == "" or val is None:
                disp = "<span style='color:#A0AEC0; font-size:0.8rem; font-style:italic;'>غير موجود</span>"
            
            # إذا كانت سنة (High/Low) وهي صفر، نعتبرها غير موجودة
            elif k in ['year_high', 'year_low', 'prev_close'] and (val == 0 or val == 0.0):
                 disp = "<span style='color:#A0AEC0; font-size:0.8rem; font-style:italic;'>غير موجود</span>"
            
            else:
                # === تنسيق البيانات الموجودة ===
                disp = val
                
                if 'date' in k and val: 
                    disp = f"<span style='color:{C['sub_text']}; font-family:monospace;'>{str(val)[:10]}</span>"
                
                elif k == 'status':
                    # الحالة بتصميم جميل
                    status_map = {'Open': 'مفتوحة', 'Close': 'مغلقة'}
                    s_txt = status_map.get(val, val)
                    bg = "#DCFCE7" if val == 'Open' else "#F3F4F6"
                    fg = "#166534" if val == 'Open' else "#4B5563"
                    disp = f"<span style='background:{bg}; color:{fg}; padding:4px 10px; border-radius:8px; font-size:0.75rem; font-weight:800;'>{s_txt}</span>"
                
                elif isinstance(val, (int, float)):
                    # تنسيق الأرقام
                    formatted_num = f"{val:,.2f}"
                    
                    # تلوين الأرباح والخسائر والتغير
                    if k in ['gain', 'gain_pct', 'daily_change', 'unrealized_pl', 'realized_pl']:
                        color = C.get('success') if val >= 0 else C.get('danger')
                        suffix = "%" if 'pct' in k or 'change' in k else ""
                        # إضافة سهم
                        arrow = "▲" if val >= 0 else "▼"
                        disp = f"<span style='color:{color}; direction:ltr; font-weight:bold;'>{formatted_num}{suffix}</span>"
                    
                    elif k == 'weight':
                        disp = f"<span style='color:{C['primary']}; direction:ltr; font-weight:bold;'>{formatted_num}%</span>"
                    
                    elif k == 'quantity':
                        disp = f"<span style='font-weight:800;'>{val:,.0f}</span>"
                    
                    else:
                        disp = f"<span style='direction:ltr; font-weight:600;'>{formatted_num}</span>"
            
            cells += f"<td>{disp}</td>"
        rows_html += f"<tr>{cells}</tr>"
        
    st.markdown(f"""
    <div class="finance-table-container">
        <div style="overflow-x: auto;">
            <table class="finance-table">
                <thead><tr>{headers}</tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# 2. الصفحات (المدمجة)
# ==========================================

def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    C = st.session_state.custom_colors
    
    # صندوق تاسي (التصميم القديم الجميل)
    arrow = "▲" if t_change >= 0 else "▼"
    color = "#36B37E" if t_change >= 0 else "#FF5630"
    st.markdown(f"""
    <div class="tasi-box" style="background: linear-gradient(120deg, {C['primary']} 0%, #0f172a 100%); padding: 30px; border-radius: 20px; color: white; display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; box-shadow: 0 10px 30px -5px rgba(0, 82, 204, 0.3);">
        <div><div style="font-size:1.1rem; opacity:0.9; margin-bottom:5px;">المؤشر العام (TASI)</div><div style="font-size:2.5rem; font-weight:900;">{t_price:,.2f}</div></div>
        <div style="background:rgba(255,255,255,0.15); padding:10px 25px; border-radius:15px; font-size:1.3rem; font-weight:bold; direction:ltr; color:{color} !important; border:1px solid rgba(255,255,255,0.2)">{t_change:+.2f}% {arrow}</div>
    </div>""", unsafe_allow_html=True)
    
    # البطاقات الرئيسية
    c1, c2, c3, c4 = st.columns(4)
    total_net = fin['total_deposited'] - fin['total_withdrawn']
    with c1: render_kpi("النقد المتوفر (الكاش)", f"{fin['cash']:,.2f}", "blue")
    with c2: render_kpi("صافي الاستثمار", f"{total_net:,.2f}")
    with c3: render_kpi("القيمة السوقية للمحفظة", f"{fin['market_val_open']:,.2f}")
    total_pl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("الربح/الخسارة الكلي", f"{total_pl:,.2f}", total_pl)
    
    st.markdown("---")
    
    # الرسم البياني (من البرنامج الجديد)
    crv = generate_equity_curve(fin['all_trades'])
    if not crv.empty:
        st.markdown("### 📈 نمو المحفظة عبر الزمن")
        st.plotly_chart(px.line(crv, x='date', y='cumulative_invested', title=""), use_container_width=True)

def view_portfolio(fin, page_key):
    ts = "مضاربة" if page_key == 'spec' else "استثمار"
    st.markdown(f"### 💼 محفظة {ts}")
    
    all_d = fin['all_trades']
    df = pd.DataFrame()
    if not all_d.empty:
        df = all_d[all_d['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    if df.empty:
        st.info("لا توجد بيانات لهذه المحفظة.")
        return

    # === الحسابات المتقدمة للأعمدة المطلوبة ===
    # 1. الوزن (Weight)
    total_market_val = df[df['status']=='Open']['market_value'].sum()
    df['weight'] = df.apply(lambda x: (x['market_value'] / total_market_val * 100) if x['status']=='Open' and total_market_val > 0 else 0, axis=1)
    
    # 2. التغير اليومي (Daily Change)
    # ملاحظة: prev_close يجب أن يأتي من التحديث اليومي للأسعار
    df['daily_change'] = df.apply(lambda x: ((x['current_price'] - x['prev_close']) / x['prev_close'] * 100) if pd.notna(x['prev_close']) and x['prev_close'] > 0 and x['current_price'] > 0 else 0, axis=1)

    # === قائمة الأعمدة المطلوبة بدقة ===
    cols_order = [
        ('company_name', 'اسم الشركة'),
        ('sector', 'القطاع'),
        ('status', 'الحالة'),
        ('symbol', 'رمز الشركة'),
        ('date', 'تاريخ الشراء'),
        ('exit_date', 'تاريخ البيع'),
        ('quantity', 'الكمية'),
        ('entry_price', 'سعر الشراء'),
        ('total_cost', 'التكلفة'),
        ('year_high', 'اعلى سنوي'),
        ('current_price', 'السعر الحالي'), # أو سعر البيع للمغلقة
        ('year_low', 'ادنى سنوي'),
        ('market_value', 'سعر السوق'), # أو قيمة البيع للمغلقة
        ('gain', 'الربح والخسارة'),
        ('gain_pct', 'نسبة الربح والخسارة'),
        ('weight', 'وزن السهم'),
        ('daily_change', 'نسبة التغير اليومي'),
        ('prev_close', 'اغلاق الامس')
    ]

    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()

    t1, t2 = st.tabs(["الأسهم الحالية", "الأرشيف (المغلقة)"])
    
    with t1:
        if not open_df.empty:
            # ملخص سريع
            c1, c2, c3, c4 = st.columns(4)
            with c1: render_kpi("القيمة السوقية", f"{open_df['market_value'].sum():,.2f}", "blue")
            with c2: render_kpi("التكلفة", f"{open_df['total_cost'].sum():,.2f}")
            with c3: render_kpi("الربح العائم", f"{open_df['gain'].sum():,.2f}", open_df['gain'].sum())
            with c4: render_kpi("عدد الشركات", f"{len(open_df)}")
            
            # الجدول
            render_finance_table(open_df, cols_order)
            
            # نموذج البيع (مدمج)
            with st.expander("🔻 تسجيل عملية بيع"):
                with st.form("sell_form"):
                    c_s1, c_s2 = st.columns(2)
                    st.markdown("**اختر السهم للبيع:**")
                    sym_sell = c_s1.selectbox("s", open_df['symbol'].unique(), label_visibility="collapsed")
                    st.markdown("**سعر البيع:**")
                    price_sell = c_s2.number_input("p", min_value=0.0, label_visibility="collapsed")
                    st.markdown("**تاريخ البيع:**")
                    date_sell = st.date_input("d", date.today(), label_visibility="collapsed")
                    if st.form_submit_button("تأكيد البيع"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (price_sell, str(date_sell), sym_sell, ts))
                        st.success("تم البيع"); time.sleep(0.5); st.rerun()
        else:
            st.info("لا توجد أسهم حالية.")

    with t2:
        if not closed_df.empty:
            # تحديث أعمدة الأرشيف للعرض الصحيح
            closed_df['current_price'] = closed_df['exit_price'] # في الأرشيف السعر الحالي هو سعر الخروج
            closed_df['market_value'] = closed_df['quantity'] * closed_df['exit_price'] # قيمة البيع
            closed_df['gain'] = closed_df['market_value'] - closed_df['total_cost']
            closed_df['gain_pct'] = (closed_df['gain'] / closed_df['total_cost'] * 100).fillna(0)
            # تصفير الأعمدة غير المنطقية للمغلق
            closed_df['weight'] = 0
            closed_df['daily_change'] = 0
            closed_df['year_high'] = None # عرض "غير موجود"
            closed_df['year_low'] = None
            closed_df['prev_close'] = None

            # ملخص الأرشيف
            realized = closed_df['gain'].sum()
            net_sales = closed_df['market_value'].sum()
            
            c_a1, c_a2 = st.columns(2)
            with c_a1: render_kpi("صافي المبيعات (كاش عائد)", f"{net_sales:,.2f}", "blue")
            with c_a2: render_kpi("الربح المحقق", f"{realized:,.2f}", realized)
            
            render_finance_table(closed_df, cols_order)
        else:
            st.info("الأرشيف فارغ.")

def view_cash_log():
    st.header("💵 سجل السيولة")
    fin = calculate_portfolio_metrics()
    
    c1, c2, c3 = st.columns(3)
    net_fund = fin['deposits']['amount'].sum() - fin['withdrawals']['amount'].sum()
    with c1: render_kpi("إجمالي الإيداعات", f"{fin['deposits']['amount'].sum():,.2f}", "success")
    with c2: render_kpi("إجمالي السحوبات", f"{fin['withdrawals']['amount'].sum():,.2f}", "danger")
    with c3: render_kpi("صافي التمويل", f"{net_fund:,.2f}", "blue")
    st.markdown("---")
    
    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "التوزيعات"])
    
    # جداول السيولة المبسطة (كما في القديم)
    liq_cols = [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'الملاحظات')]
    
    with t1:
        with st.expander("➕ إضافة إيداع"):
            with st.form("add_dep"):
                st.markdown("**المبلغ:**")
                amt = st.number_input("d_a", min_value=0.0, step=100.0, label_visibility="collapsed")
                st.markdown("**التاريخ:**")
                dt = st.date_input("d_d", date.today(), label_visibility="collapsed")
                st.markdown("**ملاحظات:**")
                nt = st.text_input("d_n", label_visibility="collapsed")
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s, %s, %s)", (str(dt), amt, nt))
                    st.rerun()
        render_finance_table(fin['deposits'], liq_cols)
        
    with t2:
        with st.expander("➖ إضافة سحب"):
            with st.form("add_wit"):
                st.markdown("**المبلغ:**")
                amt = st.number_input("w_a", min_value=0.0, step=100.0, label_visibility="collapsed")
                st.markdown("**التاريخ:**")
                dt = st.date_input("w_d", date.today(), label_visibility="collapsed")
                st.markdown("**ملاحظات:**")
                nt = st.text_input("w_n", label_visibility="collapsed")
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s, %s, %s)", (str(dt), amt, nt))
                    st.rerun()
        render_finance_table(fin['withdrawals'], liq_cols)
        
    with t3:
        ret_cols = [('date', 'التاريخ'), ('symbol', 'الرمز'), ('company_name', 'الشركة'), ('amount', 'المبلغ'), ('note', 'النوع')]
        with st.expander("💰 إضافة عائد"):
            with st.form("add_ret"):
                c_r1, c_r2 = st.columns(2)
                st.markdown("**الرمز:**")
                sym = c_r1.text_input("r_s", label_visibility="collapsed")
                st.markdown("**المبلغ:**")
                amt = c_r2.number_input("r_a", min_value=0.0, label_visibility="collapsed")
                st.markdown("**التاريخ:**")
                dt = st.date_input("r_d", date.today(), label_visibility="collapsed")
                st.markdown("**النوع:**")
                nt = st.text_input("r_n", label_visibility="collapsed")
                if st.form_submit_button("حفظ"):
                    comp, _ = get_company_details(sym)
                    execute_query("INSERT INTO ReturnsGrants (date, symbol, company_name, amount, note) VALUES (%s, %s, %s, %s, %s)", (str(dt), sym, comp, amt, nt))
                    st.rerun()
        render_finance_table(fin['returns'], ret_cols)

def view_sukuk_portfolio(fin):
    st.header("📜 الصكوك")
    df = fin['all_trades']
    if df.empty: st.info("لا توجد بيانات"); return
        
    sk = df[df['asset_type']=='Sukuk'].copy()
    if sk.empty: st.info("لا توجد صكوك"); return
    
    # نفس الأعمدة للمحفظة العادية
    cols_order = [
        ('company_name', 'اسم الصك'),
        ('symbol', 'الرمز'),
        ('status', 'الحالة'),
        ('date', 'تاريخ الشراء'),
        ('quantity', 'الكمية'),
        ('entry_price', 'سعر الشراء'),
        ('market_value', 'القيمة الحالية'),
        ('gain', 'الربح'),
        ('gain_pct', 'النسبة')
    ]
    render_finance_table(sk, cols_order)

def view_add_trade():
    st.header("➕ تسجيل صفقة جديدة")
    with st.container():
        with st.form("new_trade"):
            c1, c2 = st.columns(2)
            st.markdown("**رمز السهم:**")
            sym = c1.text_input("t_s", label_visibility="collapsed")
            st.markdown("**المحفظة:**")
            strat = c2.selectbox("t_st", ["استثمار", "مضاربة", "صكوك"], label_visibility="collapsed")
            
            c3, c4, c5 = st.columns(3)
            st.markdown("**الكمية:**")
            qty = c3.number_input("t_q", min_value=1.0, label_visibility="collapsed")
            st.markdown("**السعر:**")
            price = c4.number_input("t_p", min_value=0.0, step=0.01, label_visibility="collapsed")
            st.markdown("**التاريخ:**")
            dt = c5.date_input("t_d", date.today(), label_visibility="collapsed")
            
            if st.form_submit_button("حفظ الصفقة"):
                if sym and qty > 0 and price > 0:
                    comp, sec = get_company_details(sym)
                    atype = "Sukuk" if strat == "صكوك" else "Stock"
                    execute_query(
                        "INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status, current_price) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Open', %s)",
                        (sym, comp, sec, atype, str(dt), qty, price, strat, price)
                    )
                    st.success("تم الحفظ"); st.cache_data.clear(); st.rerun()
                else:
                    st.error("البيانات ناقصة")

def view_analysis(fin):
    st.header("🔬 مركز التحليل")
    # استدعاء التحليل من البرنامج الجديد
    render_financial_dashboard_ui(None) 

def view_backtester_ui(fin):
    st.header("🧪 مختبر الاستراتيجيات")
    c1, c2, c3 = st.columns(3)
    with c1: 
        st.markdown("**السهم:**")
        syms = list(set(fin['all_trades']['symbol'].unique().tolist() + ["1120"]))
        symbol = st.selectbox("b_s", syms, label_visibility="collapsed")
    with c2: 
        st.markdown("**الاستراتيجية:**")
        strat = st.selectbox("b_st", ["Trend Follower", "Sniper"], label_visibility="collapsed")
    with c3: 
        st.markdown("**رأس المال:**")
        cap = st.number_input("b_c", 100000, label_visibility="collapsed")
        
    if st.button("🚀 تشغيل"):
        df_hist = get_chart_history(symbol, period="2y")
        if df_hist is not None and len(df_hist) > 50:
            res = run_backtest(df_hist, strat, cap)
            if res:
                c1, c2 = st.columns(2)
                c1.metric("العائد", f"{res['return_pct']:.2f}%")
                c2.metric("الرصيد النهائي", f"{res['final_value']:,.2f}")
                st.line_chart(res['df']['Portfolio_Value'])
        else: st.error("بيانات غير كافية")

def view_settings():
    st.header("⚙️ الإعدادات")
    # دمج ميزة الاستيراد والحذف
    with st.expander("📥 استيراد بيانات (Excel/CSV)"):
        f = st.file_uploader("اختر ملف", accept_multiple_files=False)
        if f and st.button("استيراد"):
            st.info("يتم التطوير لربط الاستيراد بالقاعدة الجديدة...") # يمكن إضافة كود الاستيراد هنا
            
    with st.expander("⚠️ منطقة الخطر (حذف البيانات)"):
        c1, c2 = st.columns(2)
        del_tr = c1.checkbox("حذف الصفقات")
        del_ca = c2.checkbox("حذف السيولة")
        if st.button("تأكيد الحذف"):
            if del_tr: execute_query("TRUNCATE TABLE Trades RESTART IDENTITY CASCADE;")
            if del_ca: 
                execute_query("TRUNCATE TABLE Deposits RESTART IDENTITY CASCADE;")
                execute_query("TRUNCATE TABLE Withdrawals RESTART IDENTITY CASCADE;")
                execute_query("TRUNCATE TABLE ReturnsGrants RESTART IDENTITY CASCADE;")
            st.success("تم الحذف"); time.sleep(1); st.rerun()

# === الموجه الرئيسي ===
def router():
    render_navbar()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    
    if pg == 'home': view_dashboard(fin)
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'sukuk': view_sukuk_portfolio(fin)
    elif pg == 'cash': view_cash_log()
    elif pg == 'analysis': view_analysis(fin)
    elif pg == 'backtest': view_backtester_ui(fin)
    elif pg == 'settings': view_settings()
    elif pg == 'add': view_add_trade()
    else: view_dashboard(fin)
