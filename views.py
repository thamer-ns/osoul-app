import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from config import DEFAULT_COLORS
from components import render_kpi, render_custom_table, render_ticker_card, safe_fmt
from analytics import calculate_portfolio_metrics, update_prices, generate_equity_curve
from database import execute_query, fetch_table
from market_data import get_static_info, get_tasi_data, get_chart_history, fetch_batch_data
from charts import render_technical_chart
from backtester import run_backtest
from financial_analysis import render_financial_dashboard_ui, get_fundamental_ratios, get_thesis, save_thesis
from classical_analysis import render_classical_analysis

# --- Full Navigation Bar ---
def render_navbar():
    cols = st.columns(9)
    buttons = [
        ('🏠 الرئيسية','home'), ('⚡ مضاربة','spec'), ('💎 استثمار','invest'), 
        ('💓 نبض','pulse'), ('📜 صكوك','sukuk'), ('🔍 تحليل','analysis'), 
        ('🧪 المختبر','backtest'), ('💰 السيولة','cash'), ('🔄 تحديث','update')
    ]
    
    for i, (label, key) in enumerate(buttons):
        if i < len(cols):
            with cols[i]:
                if st.button(label, use_container_width=True): 
                    st.session_state.page = key
                    st.rerun()
    
    with st.sidebar:
        st.write(f"مرحباً {st.session_state.get('username','User')}")
        if st.button("➕ إضافة صفقة", use_container_width=True): st.session_state.page='add'; st.rerun()
        if st.button("🛠️ أدوات", use_container_width=True): st.session_state.page='tools'; st.rerun()
        if st.button("🚪 خروج", use_container_width=True): 
            try: from security import logout; logout()
            except: st.session_state.clear(); st.rerun()

# --- 1. Dashboard ---
# في ملف views.py
def view_portfolio(fin, key):
    ts = "مضاربة" if key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    
    # CSS لتحسين شكل الصفوف والأزرار
    st.markdown("""
        <style>
        .stock-row { 
            background-color: white; padding: 10px; border-radius: 10px; 
            border: 1px solid #e5e7eb; margin-bottom: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);
            align-items: center;
        }
        .stButton button { border-radius: 8px; font-weight: bold; }
        </style>
    """, unsafe_allow_html=True)
    
    df = fin['all_trades']
    if df.empty:
        sub = pd.DataFrame()
    else:
        sub = df[df['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    op = sub[sub['status'] == 'Open'].copy()
    cl = sub[sub['status'] == 'Close'].copy()
    
    t1, t2 = st.tabs(["الصفقات القائمة", "الأرشيف"])
    
    # ==========================
    # 🟢 الصفقات القائمة (تصميم تفاعلي جديد)
    # ==========================
    with t1:
        # عرض الملخص (KPIs)
        total_cost = op['total_cost'].sum() if not op.empty else 0
        total_market = op['market_value'].sum() if not op.empty else 0
        total_gain = op['gain'].sum() if not op.empty else 0
        total_pct = (total_gain / total_cost * 100) if total_cost != 0 else 0.0
        
        k1, k2, k3, k4 = st.columns(4)
        with k1: render_kpi("التكلفة", safe_fmt(total_cost), "neutral", "💰")
        with k2: render_kpi("السوق", safe_fmt(total_market), "blue", "📊")
        with k3: render_kpi("الربح", safe_fmt(total_gain), "success" if total_gain >= 0 else "danger", "📈")
        with k4: render_kpi("النسبة", f"{total_pct:.2f}%", "success" if total_pct >= 0 else "danger", "٪")
        
        st.markdown("---")
        
        # زر الإضافة العلوي (مثل سهمي)
        c_add, c_sort = st.columns([1, 3])
        with c_add:
            if st.button("➕ إضافة / شراء سهم", use_container_width=True, type="primary"):
                st.session_state.page = 'add'
                st.rerun()

        if not op.empty:
            # تحضير البيانات
            from market_data import fetch_batch_data
            from data_source import get_company_details
            
            live_data = fetch_batch_data(op['symbol'].unique().tolist())
            op['prev_close'] = op['symbol'].apply(lambda x: live_data.get(x, {}).get('prev_close', 0))
            op['day_change'] = ((op['current_price'] - op['prev_close']) / op['prev_close'] * 100).fillna(0)

            # --- رسم الجدول التفاعلي (Header) ---
            h1, h2, h3, h4, h5, h6, h7 = st.columns([2, 1.5, 1.5, 1.5, 1.5, 1.5, 2])
            h1.markdown("**الشركة**")
            h2.markdown("**الكمية**")
            h3.markdown("**متوسط التكلفة**")
            h4.markdown("**السعر الحالي**")
            h5.markdown("**القيمة السوقية**")
            h6.markdown("**الربح/الخسارة**")
            h7.markdown("**إجراءات**") # مكان الأزرار
            
            # --- رسم الصفوف (Rows) ---
            for idx, row in op.iterrows():
                with st.container():
                    st.markdown('<div class="stock-row">', unsafe_allow_html=True)
                    c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 1.5, 1.5, 1.5, 1.5, 1.5, 2])
                    
                    # البيانات
                    with c1: 
                        name, _ = get_company_details(row['symbol'])
                        st.markdown(f"**{name}**\n<br><span style='color:#888; font-size:0.8em'>{row['symbol']}</span>", unsafe_allow_html=True)
                    with c2: st.markdown(f"{row['quantity']:,.0f}")
                    with c3: st.markdown(f"{row['entry_price']:,.2f}")
                    with c4: st.markdown(f"**{row['current_price']:,.2f}**")
                    with c5: st.markdown(f"{row['market_value']:,.0f}")
                    with c6: 
                        color = "green" if row['gain'] >= 0 else "red"
                        st.markdown(f"<span style='color:{color}; direction:ltr; font-weight:bold'>{row['gain']:+,.0f}</span>\n<br><span style='font-size:0.8em; color:{color}'>({row['gain_pct']:.1f}%)</span>", unsafe_allow_html=True)
                    
                    # الأزرار (شراء / بيع)
                    with c7:
                        b_buy, b_sell = st.columns(2)
                        
                        # زر الشراء (+)
                        with b_buy:
                            pop_buy = st.popover("➕", use_container_width=True)
                            with pop_buy:
                                st.markdown(f"**شراء المزيد: {row['symbol']}**")
                                with st.form(f"buy_{row['symbol']}_{idx}"):
                                    q_add = st.number_input("الكمية", min_value=1)
                                    p_add = st.number_input("السعر", value=float(row['current_price']))
                                    d_add = st.date_input("التاريخ", date.today())
                                    if st.form_submit_button("تأكيد الشراء"):
                                        at = "Sukuk" if "Sukuk" in str(row.get('asset_type','')) else "Stock"
                                        execute_query("INSERT INTO Trades (symbol, asset_type, date, quantity, entry_price, strategy, status) VALUES (%s,%s,%s,%s,%s,%s,'Open')", 
                                                      (row['symbol'], at, str(d_add), q_add, p_add, ts))
                                        st.success("تم")
                                        st.rerun()

                        # زر البيع (-)
                        with b_sell:
                            pop_sell = st.popover("➖", use_container_width=True)
                            with pop_sell:
                                st.markdown(f"**بيع: {row['symbol']}**")
                                with st.form(f"sell_{row['symbol']}_{idx}"):
                                    st.caption(f"الكمية المتوفرة: {row['quantity']}")
                                    p_exit = st.number_input("سعر البيع", value=float(row['current_price']))
                                    d_exit = st.date_input("تاريخ البيع", date.today())
                                    if st.form_submit_button("تأكيد البيع"):
                                        # تحديث الصفقة للإغلاق
                                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", 
                                                      (p_exit, str(d_exit), row['symbol'], ts))
                                        st.success("تم البيع")
                                        st.rerun()
                    
                    st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("لا توجد صفقات قائمة")

    # ==========================
    # 🔴 الأرشيف (كما هو)
    # ==========================
    with t2:
        if not cl.empty:
            render_custom_table(cl, [('company_name', 'الشركة', 'text'), ('symbol', 'الرمز', 'text'), 
                                     ('gain', 'الربح', 'colorful'), ('gain_pct', '%', 'percent'), 
                                     ('exit_date', 'تاريخ البيع', 'date')])
        else:
            st.info("الأرشيف فارغ")
# --- 2. Portfolio View (Updated Columns) ---
def view_portfolio(fin, key):
    ts = "مضاربة" if key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    
    # CSS لتنسيق الجدول العريض
    st.markdown("""
        <style>
        .finance-table td, .finance-table th {
            white-space: nowrap !important;
            font-size: 0.85rem !important;
            vertical-align: middle !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    df = fin['all_trades']
    if df.empty:
        sub = pd.DataFrame(columns=['status', 'total_cost', 'market_value', 'gain', 'symbol', 'date'])
    else:
        sub = df[df['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    op = sub[sub['status'] == 'Open'].copy()
    cl = sub[sub['status'] == 'Close'].copy()
    
    t1, t2 = st.tabs(["الصفقات القائمة", "الأرشيف"])
    
    # --- تبويب القائمة ---
    with t1:
        total_cost = op['total_cost'].sum() if not op.empty else 0
        total_market = op['market_value'].sum() if not op.empty else 0
        total_gain = op['gain'].sum() if not op.empty else 0
        total_pct = (total_gain / total_cost * 100) if total_cost != 0 else 0.0
        
        k1, k2, k3, k4 = st.columns(4)
        with k1: render_kpi("إجمالي التكلفة", safe_fmt(total_cost), "neutral", "💰")
        with k2: render_kpi("سعر السوق", safe_fmt(total_market), "blue", "📊")
        with k3: render_kpi("الربح/الخسارة", safe_fmt(total_gain), "success" if total_gain >= 0 else "danger", "📈")
        with k4: render_kpi("النسبة %", f"{total_pct:.2f}%", "success" if total_pct >= 0 else "danger", "٪")
        
        st.markdown("---")
        
        if not op.empty:
            # --- تحضير البيانات الإضافية ---
            # ✅ تصحيح الاستيراد هنا
            from market_data import fetch_batch_data
            from data_source import get_company_details
            
            live_data = fetch_batch_data(op['symbol'].unique().tolist())
            
            op['sector'] = op['symbol'].apply(lambda x: get_company_details(x)[1])
            op['status_ar'] = "مفتوحة"
            op['exit_date_display'] = "-"
            
            op['prev_close'] = op['symbol'].apply(lambda x: live_data.get(x, {}).get('prev_close', 0))
            op['year_high'] = op['symbol'].apply(lambda x: live_data.get(x, {}).get('year_high', 0))
            op['year_low'] = op['symbol'].apply(lambda x: live_data.get(x, {}).get('year_low', 0))
            
            op['day_change'] = ((op['current_price'] - op['prev_close']) / op['prev_close'] * 100).fillna(0)
            op['weight'] = (op['market_value'] / total_market * 100).fillna(0)

            # --- الفرز ---
            c_sort, _ = st.columns([1, 3])
            sort_options = [
                "الرمز", "الشركة", "القطاع", "تاريخ الشراء", "الكمية", 
                "التكلفة", "السعر الحالي", "القيمة السوقية (الوزن)", 
                "الربح والخسارة", "نسبة الربح", "التغير اليومي"
            ]
            sort_by = c_sort.selectbox(f"فرز {ts} حسب:", sort_options, key=f"sort_op_{key}")
            
            if sort_by == "الربح والخسارة": op = op.sort_values(by='gain', ascending=False)
            elif sort_by == "القيمة السوقية (الوزن)": op = op.sort_values(by='market_value', ascending=False)
            elif sort_by == "التغير اليومي": op = op.sort_values(by='day_change', ascending=False)
            elif sort_by == "نسبة الربح": op = op.sort_values(by='gain_pct', ascending=False)
            elif sort_by == "الشركة": op = op.sort_values(by='company_name')
            elif sort_by == "القطاع": op = op.sort_values(by='sector')
            elif sort_by == "التكلفة": op = op.sort_values(by='total_cost', ascending=False)
            else: op = op.sort_values(by='date', ascending=False)
            
            # --- الأعمدة التفصيلية ---
            cols = [
                ('company_name', 'اسم الشركة', 'text'),
                ('sector', 'القطاع', 'text'),
                ('status_ar', 'الحالة', 'badge'),
                ('symbol', 'رمز الشركة', 'text'),
                ('date', 'تاريخ الشراء', 'date'),
                ('exit_date_display', 'تاريخ البيع', 'text'),
                ('quantity', 'الكمية', 'money'),
                ('entry_price', 'سعر الشراء', 'money'),
                ('total_cost', 'التكلفة', 'money'),
                ('year_high', 'اعلى سنوي', 'money'),
                ('current_price', 'السعر الحالي', 'money'),
                ('year_low', 'ادنى سنوي', 'money'),
                ('market_value', 'سعر السوق', 'money'),
                ('gain', 'الربح والخسارة', 'colorful'),
                ('gain_pct', 'نسبة الربح والخسارة', 'percent'),
                ('weight', 'وزن السهم', 'percent'),
                ('day_change', 'نسبة التغير اليومي', 'percent'),
                ('prev_close', 'اغلاق الامس', 'money')
            ]
            
            render_custom_table(op, cols)
            
            with st.expander("🔴 تسجيل بيع"):
                with st.form(f"s_{key}"):
                    s = st.selectbox("سهم", op['symbol'].unique())
                    p = st.number_input("سعر البيع")
                    d = st.date_input("تاريخ")
                    if st.form_submit_button("تأكيد"):
                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), s, ts))
                        st.rerun()
        else:
            st.info("لا توجد صفقات قائمة حالياً")

    # --- تبويب الأرشيف ---
    with t2:
        total_cost = cl['total_cost'].sum() if not cl.empty else 0
        total_exit = cl['market_value'].sum() if not cl.empty else 0
        total_gain = cl['gain'].sum() if not cl.empty else 0
        total_pct = (total_gain / total_cost * 100) if total_cost != 0 else 0.0
        
        k1, k2, k3, k4 = st.columns(4)
        with k1: render_kpi("إجمالي التكلفة", safe_fmt(total_cost), "neutral", "📜")
        with k2: render_kpi("قيمة البيع", safe_fmt(total_exit), "blue", "💵")
        with k3: render_kpi("الربح المحقق", safe_fmt(total_gain), "success" if total_gain >= 0 else "danger", "✅")
        with k4: render_kpi("النسبة %", f"{total_pct:.2f}%", "success" if total_pct >= 0 else "danger", "٪")
        
        st.markdown("---")

        if not cl.empty:
            c_sort, _ = st.columns([1, 3])
            sort_by = c_sort.selectbox(f"فرز {ts} (أرشيف) حسب:", ["التاريخ (الأحدث)", "الربح (الأعلى)", "قيمة البيع (الأعلى)"], key=f"sort_cl_{key}")
            
            if "الربح" in sort_by: cl = cl.sort_values(by='gain', ascending=False)
            elif "قيمة البيع" in sort_by: cl = cl.sort_values(by='market_value', ascending=False)
            else: cl = cl.sort_values(by='exit_date', ascending=False)

            render_custom_table(cl, [('company_name', 'الشركة', 'text'), ('symbol', 'الرمز', 'text'), 
                                     ('gain', 'الربح', 'colorful'), ('gain_pct', '%', 'percent'), 
                                     ('exit_date', 'تاريخ البيع', 'date')])
        else:
            st.info("الأرشيف فارغ")

# --- 3. Sukuk View ---
def view_sukuk_portfolio(fin):
    st.header("📜 محفظة الصكوك")
    df = fin['all_trades']
    
    if df.empty: sukuk = pd.DataFrame(columns=['asset_type', 'total_cost', 'market_value', 'gain', 'date'])
    else: sukuk = df[df['asset_type'] == 'Sukuk'].copy()
    
    total_cost = sukuk['total_cost'].sum() if not sukuk.empty else 0
    total_market = sukuk['market_value'].sum() if not sukuk.empty else 0
    total_gain = sukuk['gain'].sum() if not sukuk.empty else 0
    total_pct = (total_gain / total_cost * 100) if total_cost != 0 else 0.0
    
    k1, k2, k3, k4 = st.columns(4)
    with k1: render_kpi("إجمالي الاستثمار", safe_fmt(total_cost), "neutral", "🕌")
    with k2: render_kpi("القيمة الحالية", safe_fmt(total_market), "blue", "📊")
    with k3: render_kpi("الربح/الخسارة", safe_fmt(total_gain), "success" if total_gain >= 0 else "danger", "📈")
    with k4: render_kpi("النسبة %", f"{total_pct:.2f}%", "success" if total_pct >= 0 else "danger", "٪")
    
    st.markdown("---")
    
    if not sukuk.empty:
        c_sort, _ = st.columns([1, 3])
        sort_by = c_sort.selectbox("فرز الصكوك حسب:", ["التاريخ (الأحدث)", "القيمة (الأعلى)", "الربح (الأعلى)"], key="sort_sukuk")
        
        if "القيمة" in sort_by: sukuk = sukuk.sort_values(by='market_value', ascending=False)
        elif "الربح" in sort_by: sukuk = sukuk.sort_values(by='gain', ascending=False)
        else: sukuk = sukuk.sort_values(by='date', ascending=False)

        render_custom_table(sukuk, [('symbol', 'رمز', 'text'), ('company_name', 'اسم الصك', 'text'), 
                                    ('quantity', 'القيمة الاسمية', 'money'), ('current_price', 'السعر الحالي', 'money'),
                                    ('gain', 'الربح', 'colorful')])
    else:
        st.info("لا توجد صكوك مضافة")

# --- 4. Cash Log View ---
def view_cash_log():
    st.header("💰 السيولة والسجلات المالية")
    fin = calculate_portfolio_metrics()
    
    deposits = fin.get('deposits', pd.DataFrame())
    withdrawals = fin.get('withdrawals', pd.DataFrame())
    returns = fin.get('returns', pd.DataFrame())

    c1, c2, c3 = st.columns(3)
    d_sum = deposits['amount'].sum() if not deposits.empty else 0
    w_sum = withdrawals['amount'].sum() if not withdrawals.empty else 0
    r_sum = returns['amount'].sum() if not returns.empty else 0
    
    with c1: render_kpi("إجمالي الإيداعات", safe_fmt(d_sum), "success", "📥")
    with c2: render_kpi("إجمالي السحوبات", safe_fmt(w_sum), "danger", "📤")
    with c3: render_kpi("إجمالي العوائد", safe_fmt(r_sum), "blue", "🎁")
    
    st.markdown("---")
    t1, t2, t3 = st.tabs(["📥 سجل الإيداعات", "📤 سجل السحوبات", "🎁 سجل العوائد"])
    cols_base = [('date', 'التاريخ', 'date'), ('amount', 'المبلغ', 'money'), ('note', 'ملاحظات', 'text')]
    
    with t1:
        with st.expander("➕ تسجيل إيداع جديد"):
            with st.form("add_dep"):
                a = st.number_input("المبلغ", min_value=0.0, step=100.0)
                d = st.date_input("التاريخ", date.today())
                n = st.text_input("ملاحظة")
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                    st.success("تم"); st.rerun()
        if not deposits.empty:
            sb = st.selectbox("فرز الإيداعات حسب:", ["التاريخ (الأحدث)", "المبلغ (الأعلى)"], key="sort_dep")
            if "المبلغ" in sb: deposits = deposits.sort_values('amount', ascending=False)
            else: deposits = deposits.sort_values('date', ascending=False)
            render_custom_table(deposits, cols_base)

    with t2:
        with st.expander("➖ تسجيل سحب جديد"):
            with st.form("add_wit"):
                a = st.number_input("المبلغ", min_value=0.0, step=100.0)
                d = st.date_input("التاريخ", date.today())
                n = st.text_input("ملاحظة")
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                    st.success("تم"); st.rerun()
        if not withdrawals.empty:
            sb = st.selectbox("فرز السحوبات حسب:", ["التاريخ (الأحدث)", "المبلغ (الأعلى)"], key="sort_wit")
            if "المبلغ" in sb: withdrawals = withdrawals.sort_values('amount', ascending=False)
            else: withdrawals = withdrawals.sort_values('date', ascending=False)
            render_custom_table(withdrawals, cols_base)

    with t3:
        with st.expander("💵 تسجيل عائد/توزيع"):
            with st.form("add_ret"):
                s = st.text_input("رمز السهم")
                a = st.number_input("المبلغ", min_value=0.0, step=10.0)
                d = st.date_input("التاريخ", date.today())
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO ReturnsGrants (date, symbol, amount) VALUES (%s,%s,%s)", (str(d), s, a))
                    st.success("تم"); st.rerun()
        if not returns.empty:
            sb = st.selectbox("فرز العوائد حسب:", ["التاريخ (الأحدث)", "المبلغ (الأعلى)"], key="sort_ret")
            if "المبلغ" in sb: returns = returns.sort_values('amount', ascending=False)
            else: returns = returns.sort_values('date', ascending=False)
            render_custom_table(returns, cols_base)

# --- Other Views ---
def view_analysis(fin):
    st.header("🔬 التحليل"); trades = fin['all_trades']; from database import fetch_table; wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    c1,c2=st.columns([1,2]); ns=c1.text_input("بحث"); sym=c2.selectbox("اختر", [ns]+syms if ns else syms) if syms or ns else None
    if sym:
        n, s = get_static_info(sym); st.markdown(f"### {n} ({sym})")
        t1,t2,t3,t4,t5 = st.tabs(["مؤشرات", "فني", "قوائم", "كلاسيكي", "أطروحة"])
        with t1: d=get_fundamental_ratios(sym); st.metric("التقييم", f"{d['Score']}/10", d['Rating']); st.write(d.get('Opinions'))
        with t2: render_technical_chart(sym)
        with t3: render_financial_dashboard_ui(sym)
        with t4: render_classical_analysis(sym)
        with t5: th=get_thesis(sym); st.text_area("نص", value=th['thesis_text'] if th else "")

def view_backtester_ui(fin):
    st.header("🧪 المختبر"); c1,c2,c3 = st.columns(3)
    sym = c1.selectbox("السهم", ["1120.SR"] + fin['all_trades']['symbol'].unique().tolist())
    strat = c2.selectbox("خطة", ["Trend Follower", "Sniper"]); cap = c3.number_input("مبلغ", 100000)
    if st.button("بدء"):
        res = run_backtest(get_chart_history(sym, "2y"), strat, cap)
        if res: st.metric("العائد", f"{res['return_pct']:.2f}%"); st.line_chart(res['df']['Portfolio_Value']); st.dataframe(res['trades_log'])

def render_pulse_dashboard():
    st.header("💓 نبض السوق"); trades = fetch_table("Trades"); wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    if not syms: st.info("فارغة"); return
    data = fetch_batch_data(syms); cols = st.columns(4)
    for i, (s, info) in enumerate(data.items()):
        chg = ((info['price']-info['prev_close'])/info['prev_close'])*100 if info['prev_close']>0 else 0
        with cols[i%4]: render_ticker_card(s, "سهم", info['price'], chg)

def view_add_trade():
    st.header("➕ إضافة صفقة"); 
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
