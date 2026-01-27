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

# --- 1. Navigation Bar (القائمة العلوية + الجانبية) ---
# --- 1. Navigation Bar (القائمة المنسدلة بجانب التحديث) ---
def render_navbar():
    # نقسم العرض إلى 10 أعمدة لتوزيع الأزرار
    cols = st.columns(10)
    
    # قائمة الأزرار الرئيسية (بدون زر التحديث، سنضعه يدوياً)
    buttons = [
        ('🏠 الرئيسية','home'), ('⚡ مضاربة','spec'), ('💎 استثمار','invest'), 
        ('💓 نبض','pulse'), ('📜 صكوك','sukuk'), ('🔍 تحليل','analysis'), 
        ('🧪 المختبر','backtest'), ('💰 السيولة','cash')
    ]
    
    # 1. رسم الأزرار الرئيسية (من 1 إلى 8)
    for i, (label, key) in enumerate(buttons):
        with cols[i]:
            if st.button(label, use_container_width=True): 
                st.session_state.page = key
                st.rerun()
    
    # 2. زر التحديث (في العمود التاسع)
    with cols[8]:
        if st.button('🔄 تحديث', use_container_width=True):
            st.session_state.page = 'update'
            st.rerun()

    # 3. زر القائمة (في العمود العاشر والأخير)
    with cols[9]:
        # القائمة المنسدلة بدلاً من السايدبار
        with st.popover("☰ القائمة", use_container_width=True):
            st.caption(f"👤 {st.session_state.get('username','Guest')}")
            st.markdown("---")
            
            if st.button("➕ إضافة صفقة", use_container_width=True): 
                st.session_state.page='add'; st.rerun()
            
            if st.button("🛠️ أدوات", use_container_width=True): 
                st.session_state.page='tools'; st.rerun()
            
            if st.button("⚙️ الإعدادات", use_container_width=True): 
                st.session_state.page='settings'; st.rerun()
            
            st.markdown("---")
            
            if st.button("🚪 خروج", use_container_width=True): 
                try: from security import logout; logout()
                except: st.session_state.clear(); st.rerun()
# --- 2. Dashboard (الرئيسية - محسنة) ---
def view_dashboard(fin):
    from data_source import get_company_details
    try: tp, tc = get_tasi_data()
    except: tp, tc = 0, 0
    ar = "🔼" if tc >= 0 else "🔽"
    
    st.markdown(f"""
    <div class="tasi-card">
        <div><div style="opacity:0.9;">المؤشر العام (TASI)</div><div style="font-size:2.5rem; font-weight:900;">{safe_fmt(tp)}</div></div>
        <div style="background:rgba(255,255,255,0.2); padding:5px 15px; border-radius:10px; font-weight:bold; direction:ltr;">{ar} {tc:.2f}%</div>
    </div>""", unsafe_allow_html=True)
    
    c1, c2, c3, c4 = st.columns(4)
    total_pl = fin['unrealized_pl'] + fin['realized_pl']
    total_assets = fin['market_val_open'] + fin['cash']
    cash_pct = (fin['cash'] / total_assets * 100) if total_assets else 0

    with c1: render_kpi(f"الكاش ({cash_pct:.1f}%)", safe_fmt(fin['cash']), "blue", "💵")
    with c2: render_kpi("صافي الإيداعات", safe_fmt(fin['total_deposited']-fin['total_withdrawn']), "neutral", "🏗️")
    with c3: render_kpi("إجمالي الأصول", safe_fmt(total_assets), "neutral", "🏦")
    with c4: render_kpi("صافي الربح الكلي", safe_fmt(total_pl), 'success' if total_pl>=0 else 'danger', "📈")
    
    st.markdown("---")
    
    df = fin['all_trades']
    open_cost = fin['cost_open']
    open_market = fin['market_val_open']
    open_pl = fin['unrealized_pl']
    open_pct = (open_pl / open_cost * 100) if open_cost != 0 else 0.0
    
    # 🆕 إضافة: لوحة المتصدرين (Leaderboard)
    if not df.empty:
        open_trades = df[df['status'] == 'Open'].copy()
        if not open_trades.empty:
            # جلب البيانات الحية لحساب التغير اليومي
            live_data = fetch_batch_data(open_trades['symbol'].unique().tolist())
            open_trades['day_change'] = open_trades['symbol'].apply(lambda x: ((live_data.get(x, {}).get('price', 0) - live_data.get(x, {}).get('prev_close', 0)) / live_data.get(x, {}).get('prev_close', 1) * 100))
            
            best = open_trades.loc[open_trades['gain_pct'].idxmax()]
            worst = open_trades.loc[open_trades['gain_pct'].idxmin()]
            heaviest = open_trades.loc[open_trades['market_value'].idxmax()]
            
            st.markdown("##### 🏅 لوحة المتصدرين")
            l1, l2, l3, l4 = st.columns(4)
            l1.metric("🥇 الأفضل أداءً", best['company_name'], f"{best['gain_pct']:.1f}%")
            l2.metric("🔻 الأسوأ أداءً", worst['company_name'], f"{worst['gain_pct']:.1f}%")
            l3.metric("⚖️ الأكبر وزناً", heaviest['company_name'], safe_fmt(heaviest['market_value']))
            l4.metric("📈 الأصول القائمة", f"{len(open_trades)}", "صفقة")
            st.markdown("---")

    # ملخصات العمليات
    col_kpi1, col_kpi2 = st.columns(2)
    with col_kpi1:
        st.markdown("##### 📊 ملخص الصفقات القائمة (Open)")
        o1, o2 = st.columns(2)
        with o1: render_kpi("التكلفة", safe_fmt(open_cost), "neutral", "💰")
        with o2: render_kpi("الربح الورقي", safe_fmt(open_pl), "success" if open_pl >= 0 else "danger", "📈")

    with col_kpi2:
        if not df.empty:
            closed_df = df[df['status'] == 'Close']
            closed_pl = fin['realized_pl']
        else: closed_pl = 0
        st.markdown("##### 📜 ملخص الصفقات المنفذة (Closed)")
        x1, x2 = st.columns(2)
        with x1: render_kpi("الربح المحقق", safe_fmt(closed_pl), "success" if closed_pl >= 0 else "danger", "✅")
        with x2: render_kpi("إجمالي العوائد", safe_fmt(fin['total_returns']), "blue", "🎁")

    st.markdown("---")

    # الرسوم البيانية
    if not df.empty:
        open_trades = df[df['status'] == 'Open']
        
        # تحضير البيانات للرسم
        invest_val = open_trades[open_trades['strategy'].astype(str).str.contains('استثمار')]['market_value'].sum()
        spec_val = open_trades[open_trades['strategy'].astype(str).str.contains('مضاربة')]['market_value'].sum()
        sukuk_val = open_trades[open_trades['asset_type'] == 'Sukuk']['market_value'].sum()
        cash_val = fin['cash']
        
        alloc_df = pd.DataFrame({
            'Asset': ['استثمار', 'مضاربة', 'صكوك', 'كاش'],
            'Value': [invest_val, spec_val, sukuk_val, cash_val]
        })
        alloc_df = alloc_df[alloc_df['Value'] > 0]
        
        c_top, c_curve = st.columns([1, 2])
        
        with c_top:
            st.subheader("🥧 توزيع الأصول")
            if not alloc_df.empty:
                fig1 = px.pie(alloc_df, values='Value', names='Asset', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig1.update_layout(showlegend=True, margin=dict(t=0, b=0, l=0, r=0), height=250)
                st.plotly_chart(fig1, use_container_width=True)
            else: st.info("لا توجد أصول")

        with c_curve:
            st.subheader("📈 نمو المحفظة")
            crv = generate_equity_curve(df)
            if not crv.empty: 
                fig3 = px.line(crv, x='date', y='cumulative_invested')
                fig3.update_traces(line_color='#0052CC', line_width=3)
                fig3.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250, yaxis_title="القيمة التراكمية")
                st.plotly_chart(fig3, use_container_width=True)
            else: st.info("لا توجد بيانات تاريخية")
    else:
        st.info("👋 مرحباً بك! ابدأ بإضافة صفقات أو رصيد لتفعيل لوحة القيادة.")

# --- 3. Portfolio View (محسنة: فرز + تفاعلية) ---
# --- 3. Portfolio View (معدلة بالتصميم الجديد) ---
def view_portfolio(fin, key):
    ts = "مضاربة" if key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    
    # 1. CSS مستوحى من تصميم finance-table الذي طلبته
    st.markdown("""
        <style>
        /* حاوية الجدول كاملة */
        .finance-container {
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(0,0,0,0.03);
            background-color: white;
            margin-bottom: 25px;
        }
        
        /* رأس الجدول */
        .finance-header {
            background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
            padding: 15px 10px;
            border-bottom: 2px solid #e5e7eb;
            font-weight: 800;
            color: #1e293b; /* Primary Dark */
            font-size: 0.95rem;
            display: flex;
            align-items: center;
        }
        
        /* صفوف البيانات */
        .finance-row {
            padding: 12px 10px;
            border-bottom: 1px solid #f1f5f9;
            transition: all 0.2s ease;
            background-color: white;
            color: #334155;
            display: flex;
            align-items: center;
            font-size: 0.95rem;
        }
        
        /* تأثير التمرير (Hover) */
        .finance-row:hover {
            background-color: #f0f9ff !important;
        }
        
        /* تنسيق الأرقام والألوان */
        .val-success { color: #10b981; font-weight: bold; }
        .val-danger { color: #ef4444; font-weight: bold; }
        .val-neutral { color: #64748b; }
        
        /* تنسيق حالة الصفقة (Badge) */
        .status-badge {
            background-color: #E3FCEF;
            color: #006644;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: bold;
        }
        
        /* ضبط المحاذاة داخل الأعمدة */
        div[data-testid="stVerticalBlock"] > div > div[data-testid="stHorizontalBlock"] {
            align-items: center;
        }
        </style>
    """, unsafe_allow_html=True)
    
    df = fin['all_trades']
    if df.empty: sub = pd.DataFrame()
    else: sub = df[df['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    op = sub[sub['status'] == 'Open'].copy()
    cl = sub[sub['status'] == 'Close'].copy()
    
    t1, t2 = st.tabs(["الصفقات القائمة", "الأرشيف"])
    
    with t1:
        # الملخص (KPIs) - كما هو
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
        
        # شريط الأدوات والفرز
        c_add, c_sort = st.columns([1, 3])
        with c_add:
            if st.button("➕ إضافة / شراء", type="primary", use_container_width=True):
                st.session_state.page = 'add'; st.rerun()
        
        if not op.empty:
            from market_data import fetch_batch_data
            from data_source import get_company_details
            
            # تحضير البيانات
            live_data = fetch_batch_data(op['symbol'].unique().tolist())
            op['sector'] = op['symbol'].apply(lambda x: get_company_details(x)[1])
            op['prev_close'] = op['symbol'].apply(lambda x: live_data.get(x, {}).get('prev_close', 0))
            op['day_change'] = ((op['current_price'] - op['prev_close']) / op['prev_close'] * 100).fillna(0)
            op['weight'] = (op['market_value'] / total_market * 100).fillna(0)

            # منطق الفرز
            with c_sort:
                sort_options = {
                    "الربح والخسارة": "gain", "القيمة السوقية": "market_value",
                    "نسبة الربح %": "gain_pct", "التغير اليومي": "day_change",
                    "تاريخ الشراء": "date", "الاسم": "company_name"
                }
                sort_sel = st.selectbox("فرز حسب:", list(sort_options.keys()), label_visibility="collapsed")
                sort_col = sort_options[sort_sel]
                ascending = True if sort_col in ["company_name", "date"] else False
                op = op.sort_values(by=sort_col, ascending=ascending)

            # === بناء الجدول بتصميم Finance Table ===
            
            # 1. بداية حاوية الجدول
            st.markdown('<div class="finance-container">', unsafe_allow_html=True)
            
            # 2. رأس الجدول (Header)
            st.markdown('<div class="finance-header">', unsafe_allow_html=True)
            h1, h2, h3, h4, h5, h6, h7 = st.columns([2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.5])
            h1.markdown("الشركة / الرمز")
            h2.markdown("الكمية")
            h3.markdown("التكلفة")
            h4.markdown("آخر سعر (يومي)")
            h5.markdown("القيمة (الوزن)")
            h6.markdown("الربح الصافي")
            h7.markdown("إجراءات")
            st.markdown('</div>', unsafe_allow_html=True) # إغلاق الرأس

            # 3. صفوف البيانات (Rows)
            for idx, row in op.iterrows():
                # حاوية الصف مع كلاس finance-row
                with st.container():
                    st.markdown('<div class="finance-row">', unsafe_allow_html=True)
                    c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.5])
                    
                    name, _ = get_company_details(row['symbol'])
                    
                    # العمود 1: الاسم والرمز والحالة
                    with c1: 
                        st.markdown(f"**{name}** <span class='status-badge'>مفتوحة</span><br><span style='color:#64748b; font-size:0.8em'>{row['symbol']}</span>", unsafe_allow_html=True)
                    
                    # العمود 2: الكمية
                    with c2: st.markdown(f"**{row['quantity']:,.0f}**")
                    
                    # العمود 3: التكلفة
                    with c3: st.markdown(f"{row['entry_price']:,.2f}")
                    
                    # العمود 4: السعر والتغير اليومي
                    with c4: 
                        dc = row['day_change']
                        clr_dc = "#10b981" if dc >= 0 else "#ef4444"
                        st.markdown(f"**{row['current_price']:,.2f}**<br><span style='color:{clr_dc}; direction:ltr; font-size:0.85em'>{dc:+.2f}%</span>", unsafe_allow_html=True)
                        
                    # العمود 5: القيمة والوزن
                    with c5: 
                        st.markdown(f"**{row['market_value']:,.0f}**<br><span style='color:#64748b; font-size:0.8em'>{row['weight']:.1f}%</span>", unsafe_allow_html=True)
                        
                    # العمود 6: الربح
                    with c6:
                        color_cls = "val-success" if row['gain'] >= 0 else "val-danger"
                        st.markdown(f"<span class='{color_cls}'>{row['gain']:+,.0f}</span><br><span class='{color_cls}' style='font-size:0.85em'>{row['gain_pct']:.1f}%</span>", unsafe_allow_html=True)
                    
                    # العمود 7: الأزرار التفاعلية (حافظنا عليها)
                    with c7:
                        b_col1, b_col2 = st.columns(2)
                        with b_col1:
                            pop_buy = st.popover("➕", help="شراء")
                            with pop_buy:
                                st.markdown(f"**شراء: {name}**")
                                with st.form(f"buy_{row['symbol']}_{idx}"):
                                    q = st.number_input("الكمية", 1); p = st.number_input("السعر", value=float(row['current_price']))
                                    d = st.date_input("التاريخ", date.today())
                                    if st.form_submit_button("شراء"):
                                        at = "Sukuk" if "Sukuk" in str(row.get('asset_type','')) else "Stock"
                                        execute_query("INSERT INTO Trades (symbol, asset_type, date, quantity, entry_price, strategy, status) VALUES (%s,%s,%s,%s,%s,%s,'Open')", (row['symbol'], at, str(d), q, p, ts))
                                        st.success("تم"); st.rerun()
                        with b_col2:
                            pop_sell = st.popover("➖", help="بيع")
                            with pop_sell:
                                st.markdown(f"**بيع: {name}**")
                                with st.form(f"sell_{row['symbol']}_{idx}"):
                                    st.caption(f"الكمية: {row['quantity']}")
                                    p = st.number_input("سعر البيع", value=float(row['current_price']))
                                    d = st.date_input("تاريخ", date.today())
                                    if st.form_submit_button("بيع"):
                                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), row['symbol'], ts))
                                        st.success("تم"); st.rerun()
                    
                    st.markdown('</div>', unsafe_allow_html=True) # إغلاق div الصف
            
            st.markdown('</div>', unsafe_allow_html=True) # إغلاق حاوية الجدول
        else:
            st.info("لا توجد صفقات قائمة")

    with t2:
        if not cl.empty:
            render_custom_table(cl, [('company_name', 'الشركة', 'text'), ('symbol', 'الرمز', 'text'), ('gain', 'الربح', 'colorful'), ('gain_pct', '%', 'percent'), ('exit_date', 'تاريخ البيع', 'date')])
        else:
            st.info("الأرشيف فارغ")
# --- 4. Sukuk View ---
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

# --- 5. Cash Log View ---
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
