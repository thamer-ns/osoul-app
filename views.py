import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from config import DEFAULT_COLORS
from components import render_kpi, render_custom_table, render_ticker_card, safe_fmt
from analytics import calculate_portfolio_metrics, update_prices, generate_equity_curve
from database import execute_query, fetch_table
from market_data import get_static_info, get_tasi_data, get_chart_history, fetch_batch_data
from data_source import get_company_details 

# استيراد الوحدات مع حماية
try:
    from charts import render_technical_chart
    from backtester import run_backtest
    from financial_analysis import render_financial_dashboard_ui, get_fundamental_ratios, get_thesis, save_thesis
    from classical_analysis import render_classical_analysis
except ImportError:
    def render_technical_chart(*a): st.warning("وحدة الرسوم البيانية غير متوفرة")
    def run_backtest(*a): st.warning("وحدة الاختبار غير متوفرة"); return None
    def render_financial_dashboard_ui(*a): st.warning("التحليل المالي غير متوفر")
    def get_fundamental_ratios(*a): return {"Score": 0, "Rating": "N/A"}
    def get_thesis(*a): return {}
    def save_thesis(*a): pass
    def render_classical_analysis(*a): st.warning("التحليل الكلاسيكي غير متوفر")

# --- 1. Navigation Bar ---
def render_navbar():
    buttons = [
        ('🏠 الرئيسية','home'), ('⚡ مضاربة','spec'), ('💎 استثمار','invest'), 
        ('💓 نبض','pulse'), ('📜 صكوك','sukuk'), ('🔍 تحليل','analysis'), 
        ('🧪 المختبر','backtest'), ('💰 السيولة','cash'), ('🔄 تحديث','update')
    ]
    
    cols = st.columns(len(buttons) + 1)
    for i, (label, key) in enumerate(buttons):
        with cols[i]:
            type_btn = "primary" if st.session_state.page == key else "secondary"
            if st.button(label, key=f"nav_{key}", use_container_width=True, type=type_btn): 
                st.session_state.page = key
                st.rerun()
                
    with cols[-1]:
        with st.popover("👤 القائمة", use_container_width=True):
            st.write(f"مرحباً {st.session_state.get('username','User')}")
            if st.button("➕ إضافة صفقة", use_container_width=True): st.session_state.page='add'; st.rerun()
            if st.button("🛠️ أدوات", use_container_width=True): st.session_state.page='tools'; st.rerun()
            if st.button("⚙️ إعدادات", use_container_width=True): st.session_state.page='settings'; st.rerun()
            st.markdown("---")
            if st.button("🚪 خروج", use_container_width=True): 
                try: from security import logout; logout()
                except: st.session_state.clear(); st.rerun()
    st.markdown("---")

# --- 2. Dashboard ---
def view_dashboard(fin):
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
    
    st.markdown("##### 📊 ملخص الصفقات القائمة (Open)")
    o1, o2, o3, o4 = st.columns(4)
    with o1: render_kpi("التكلفة الإجمالية", safe_fmt(open_cost), "neutral", "💰")
    with o2: render_kpi("القيمة السوقية", safe_fmt(open_market), "blue", "📊")
    with o3: render_kpi("الربح الورقي", safe_fmt(open_pl), "success" if open_pl >= 0 else "danger", "📈")
    with o4: render_kpi("نسبة النمو", f"{open_pct:.2f}%", "success" if open_pct >= 0 else "danger", "٪")

    st.markdown("<div style='margin-bottom: 25px;'></div>", unsafe_allow_html=True)

    if not df.empty:
        closed_df = df[df['status'] == 'Close']
        closed_cost = closed_df['total_cost'].sum()
        closed_pl = fin['realized_pl']
        closed_sales = closed_df['market_value'].sum()
        closed_pct = (closed_pl / closed_cost * 100) if closed_cost != 0 else 0.0
    else:
        closed_cost = closed_pl = closed_sales = closed_pct = 0

    st.markdown("##### 📜 ملخص الصفقات المنفذة (Executed)")
    x1, x2, x3, x4 = st.columns(4)
    with x1: render_kpi("رأس المال المسترد", safe_fmt(closed_cost), "neutral", "↩️")
    with x2: render_kpi("السيولة العائدة", safe_fmt(closed_sales), "blue", "📥")
    with x3: render_kpi("الربح المحقق", safe_fmt(closed_pl), "success" if closed_pl >= 0 else "danger", "✅")
    with x4: render_kpi("العائد المحقق", f"{closed_pct:.2f}%", "success" if closed_pct >= 0 else "danger", "٪")

    st.markdown("---")

    if not df.empty:
        open_trades = df[df['status'] == 'Open']
        try:
            invest_val = open_trades[open_trades['strategy'].astype(str).str.contains('استثمار', na=False)]['market_value'].sum()
            spec_val = open_trades[open_trades['strategy'].astype(str).str.contains('مضاربة', na=False)]['market_value'].sum()
        except:
            invest_val = spec_val = 0
            
        sukuk_val = open_trades[open_trades['asset_type'] == 'Sukuk']['market_value'].sum()
        cash_val = fin['cash']
        alloc_df = pd.DataFrame({'Asset': ['استثمار', 'مضاربة', 'صكوك', 'كاش'], 'Value': [invest_val, spec_val, sukuk_val, cash_val]})
        alloc_df = alloc_df[alloc_df['Value'] > 0]
        
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.subheader("🥧 توزيع الأصول")
            if not alloc_df.empty:
                fig1 = px.pie(alloc_df, values='Value', names='Asset', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig1.update_layout(showlegend=True, margin=dict(t=0, b=0, l=0, r=0), height=250)
                st.plotly_chart(fig1, use_container_width=True)
            else: st.info("لا توجد أصول")

        with col_chart2:
            st.subheader("📈 نمو المحفظة")
            crv = generate_equity_curve(df)
            if not crv.empty: 
                fig3 = px.line(crv, x='date', y='cumulative_invested')
                fig3.update_traces(line_color='#0052CC', line_width=3)
                fig3.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250, yaxis_title="القيمة التراكمية")
                st.plotly_chart(fig3, use_container_width=True)
            else: st.info("لا توجد بيانات تاريخية")
    else:
        st.info("👋 مرحباً بك! ابدأ بإضافة صفقات.")

# --- 3. Portfolio View ---
def view_portfolio(fin, key):
    ts = "مضاربة" if key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    
    st.markdown("""<style>.finance-table td, .finance-table th {white-space: nowrap !important;font-size: 0.85rem !important;vertical-align: middle !important;}</style>""", unsafe_allow_html=True)
    
    df = fin['all_trades']
    if df.empty:
        sub = pd.DataFrame(columns=['status', 'total_cost', 'market_value', 'gain', 'symbol', 'date', 'id'])
    else:
        sub = df[df['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    op = sub[sub['status'] == 'Open'].copy()
    cl = sub[sub['status'] == 'Close'].copy()
    
    t1, t2 = st.tabs(["الصفقات القائمة", "الأرشيف"])
    
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
        
        c_add, _ = st.columns([1, 4])
        with c_add:
            if st.button("➕ إضافة سهم", use_container_width=True, type="primary"):
                st.session_state.page = 'add'; st.rerun()
        
        if not op.empty:
            live_data = fetch_batch_data(op['symbol'].unique().tolist())
            op['status_ar'] = "مفتوحة"
            op['exit_date_display'] = "-"
            op['prev_close'] = op['symbol'].apply(lambda x: live_data.get(x, {}).get('prev_close', 0))
            op['year_high'] = op['symbol'].apply(lambda x: live_data.get(x, {}).get('year_high', 0))
            op['year_low'] = op['symbol'].apply(lambda x: live_data.get(x, {}).get('year_low', 0))
            op['day_change'] = op.apply(lambda r: ((r['current_price'] - r['prev_close']) / r['prev_close'] * 100) if r['prev_close'] > 0 else 0, axis=1)
            op['weight'] = (op['market_value'] / total_market * 100).fillna(0)

            c_sort, _ = st.columns([1, 3])
            sort_options = ["الرمز", "الشركة", "القطاع", "تاريخ الشراء", "الكمية", "التكلفة", "السعر الحالي", "القيمة السوقية (الوزن)", "الربح والخسارة", "نسبة الربح", "التغير اليومي"]
            sort_by = c_sort.selectbox(f"فرز {ts} حسب:", sort_options, key=f"sort_op_{key}")
            
            if sort_by == "الربح والخسارة": op = op.sort_values(by='gain', ascending=False)
            elif sort_by == "القيمة السوقية (الوزن)": op = op.sort_values(by='market_value', ascending=False)
            elif sort_by == "التغير اليومي": op = op.sort_values(by='day_change', ascending=False)
            elif sort_by == "نسبة الربح": op = op.sort_values(by='gain_pct', ascending=False)
            elif sort_by == "الشركة": op = op.sort_values(by='company_name')
            elif sort_by == "القطاع": op = op.sort_values(by='sector')
            elif sort_by == "التكلفة": op = op.sort_values(by='total_cost', ascending=False)
            else: op = op.sort_values(by='date', ascending=False)
            
            cols = [
                ('company_name', 'اسم الشركة', 'text'), ('sector', 'القطاع', 'text'),
                ('status_ar', 'الحالة', 'badge'), ('symbol', 'رمز الشركة', 'text'),
                ('date', 'تاريخ الشراء', 'date'), 
                ('quantity', 'الكمية', 'money'), ('entry_price', 'سعر الشراء', 'money'),
                ('total_cost', 'التكلفة', 'money'), 
                ('current_price', 'السعر الحالي', 'money'),
                ('market_value', 'سعر السوق', 'money'), ('gain', 'الربح والخسارة', 'colorful'),
                ('gain_pct', 'نسبة الربح والخسارة', 'percent'), ('weight', 'وزن السهم', 'percent'),
                ('day_change', 'نسبة التغير اليومي', 'percent')
            ]
            
            render_custom_table(op, cols)
            
            c_act1, c_act2 = st.columns(2)
            
            with c_act1:
                with st.expander("🔴 تسجيل بيع / إغلاق"):
                    sell_map = {f"{row['company_name']} ({row['symbol']}) - {row['quantity']} سهم": row['id'] for i, row in op.iterrows()}
                    sel_sell = st.selectbox("اختر الصفقة:", list(sell_map.keys()), key=f"sell_sel_{key}")
                    if sel_sell:
                        tid = sell_map[sel_sell]
                        with st.form(f"s_{tid}"):
                            p = st.number_input("سعر البيع")
                            d = st.date_input("تاريخ")
                            if st.form_submit_button("تأكيد"):
                                execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s", (p, str(d), tid))
                                st.success("تم البيع"); st.cache_data.clear(); st.rerun()
            
            with c_act2:
                with st.expander("✏️ تعديل صفقة (تصحيح خطأ)"):
                    edit_map = {f"{row['company_name']} - {row['date']}": row['id'] for i, row in op.iterrows()}
                    sel_edit = st.selectbox("اختر الصفقة:", list(edit_map.keys()), key=f"edit_sel_{key}")
                    if sel_edit:
                        tid = edit_map[sel_edit]
                        curr = op[op['id'] == tid].iloc[0]
                        with st.form(f"e_{tid}"):
                            nq = st.number_input("الكمية", value=float(curr['quantity']))
                            np = st.number_input("سعر الشراء", value=float(curr['entry_price']))
                            nd = st.date_input("تاريخ", pd.to_datetime(curr['date']))
                            if st.form_submit_button("حفظ"):
                                execute_query("UPDATE Trades SET quantity=%s, entry_price=%s, date=%s WHERE id=%s", (nq, np, str(nd), tid))
                                st.success("تم التعديل"); st.cache_data.clear(); st.rerun()
        else:
            st.info("لا توجد صفقات قائمة حالياً")

    with t2:
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

# --- 4. Sukuk View ---
def view_sukuk_portfolio(fin):
    st.header("📜 محفظة الصكوك")
    df = fin['all_trades']
    
    if df.empty: 
        sukuk = pd.DataFrame(columns=['asset_type', 'total_cost', 'market_value', 'gain', 'date', 'id', 'quantity', 'entry_price', 'symbol', 'company_name', 'status'])
    else: 
        sukuk = df[df['asset_type'] == 'Sukuk'].copy()
    
    # فصل البيانات
    op = sukuk[sukuk['status'] == 'Open'].copy()
    cl = sukuk[sukuk['status'] == 'Close'].copy()

    # إنشاء التبويبات
    t1, t2 = st.tabs(["الصكوك القائمة (Open)", "الأرشيف (Closed)"])

    # --- تبويب الصكوك المفتوحة ---
    with t1:
        total_cost = op['total_cost'].sum() if not op.empty else 0
        total_market = op['market_value'].sum() if not op.empty else 0
        total_gain = op['gain'].sum() if not op.empty else 0
        total_pct = (total_gain / total_cost * 100) if total_cost != 0 else 0.0
        
        k1, k2, k3, k4 = st.columns(4)
        with k1: render_kpi("إجمالي الاستثمار", safe_fmt(total_cost), "neutral", "🕌")
        with k2: render_kpi("القيمة الحالية", safe_fmt(total_market), "blue", "📊")
        with k3: render_kpi("الربح/الخسارة", safe_fmt(total_gain), "success" if total_gain >= 0 else "danger", "📈")
        with k4: render_kpi("النسبة %", f"{total_pct:.2f}%", "success" if total_pct >= 0 else "danger", "٪")
        
        st.markdown("---")
        
        c_add, _ = st.columns([1, 4])
        with c_add:
            if st.button("➕ إضافة صك", use_container_width=True, type="primary"):
                st.session_state.page = 'add'; st.rerun()

        # ✅ هنا كان الخطأ: تم إخراج الشرط من داخل الزر وضبط المسافات
        if not op.empty:
            op['company_name'] = op['company_name'].fillna(op['symbol'])
            op['months_held'] = ((pd.to_datetime(date.today()) - pd.to_datetime(op['date'])).dt.days / 30).astype(int)
            
            # اضافة السعر الحالي
            op['current_price'] = op['entry_price'] 
            
            c_sort, _ = st.columns([1, 3])
            sort_by = c_sort.selectbox("فرز الصكوك حسب:", ["التاريخ (الأحدث)", "القيمة (الأعلى)", "الاسم"], key="sort_sukuk")
            
            if "القيمة" in sort_by: op = op.sort_values(by='total_cost', ascending=False)
            elif "الاسم" in sort_by: op = op.sort_values(by='company_name')
            else: op = op.sort_values(by='date', ascending=False)

            cols = [
                ('company_name', 'اسم الصك', 'text'), 
                ('quantity', 'العدد', 'text'),  
                ('entry_price', 'التكلفة (للوحدة)', 'money'),
                ('current_price', 'السعر الحالي', 'money'),
                ('total_cost', 'الاجمالي', 'money'),
                ('months_held', 'المده (شهر)', 'text')
            ]
            render_custom_table(op, cols)
            
            c_act1, c_act2 = st.columns(2)
            with c_act1:
                with st.expander("💰 بيع / تصفية صك"):
                    sell_opts = {f"{row['company_name']} ({row['quantity']})": row['id'] for i, row in op.iterrows()}
                    sel_sell_id = st.selectbox("اختر الصك للبيع:", list(sell_opts.keys()), key="sell_sukuk_sel")
                    
                    if sel_sell_id:
                        tid_sell = sell_opts[sel_sell_id]
                        curr_sell = op[op['id'] == tid_sell].iloc[0]
                        with st.form(f"sell_form_s_{tid_sell}"):
                            st.write(f"تصفية: **{curr_sell['company_name']}**")
                            total_exit_amount = st.number_input("المبلغ المستلم كاملاً", min_value=0.0, step=100.0)
                            exit_date = st.date_input("تاريخ البيع", date.today())
                            if st.form_submit_button("تأكيد البيع"):
                                qty = float(curr_sell['quantity'])
                                if qty > 0:
                                    unit_exit_price = total_exit_amount / qty
                                    execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s", (unit_exit_price, str(exit_date), tid_sell))
                                    st.success("تم الحفظ"); st.cache_data.clear(); st.rerun()
                                else: st.error("خطأ: الكمية صفر")

            with c_act2:
                with st.expander("✏️ تعديل بيانات صك"):
                    edit_map_s = {f"{row['company_name']} - {row['date']}": row['id'] for i, row in op.iterrows()}
                    sel_label_s = st.selectbox("اختر الصك للتعديل:", list(edit_map_s.keys()), key="edit_sel_sukuk")
                    
                    if sel_label_s:
                        sukuk_id = edit_map_s[sel_label_s]
                        curr_s = op[op['id'] == sukuk_id].iloc[0]
                        with st.form(f"edit_form_s_{sukuk_id}"):
                            current_name = str(curr_s['company_name']) if curr_s['company_name'] else str(curr_s['symbol'])
                            n_name = st.text_input("اسم الصك", value=current_name)
                            c_s1, c_s2 = st.columns(2)
                            n_qty = c_s1.number_input("عدد الصكوك", value=float(curr_s['quantity']))
                            n_prc = c_s2.number_input("قيمة الصك", value=float(curr_s['entry_price']))
                            n_date = st.date_input("تاريخ الشراء", pd.to_datetime(curr_s['date']))
                            if st.form_submit_button("حفظ التصحيح"):
                                execute_query("UPDATE Trades SET symbol=%s, company_name=%s, quantity=%s, entry_price=%s, date=%s WHERE id=%s", (n_name, n_name, n_qty, n_prc, str(n_date), sukuk_id))
                                st.success("تم التعديل"); st.cache_data.clear(); st.rerun()
        else:
            st.info("لا توجد صكوك قائمة حالياً")

    # --- تبويب الأرشيف ---
    with t2:
        if not cl.empty:
            cl['company_name'] = cl['company_name'].fillna(cl['symbol'])
            cl['realized_return'] = cl['market_value'] - cl['total_cost']
            
            c_sort, _ = st.columns([1, 3])
            sort_by_cl = c_sort.selectbox("فرز الأرشيف حسب:", ["تاريخ البيع (الأحدث)", "الربح (الأعلى)"], key="sort_sukuk_cl")
            
            if "الربح" in sort_by_cl: cl = cl.sort_values(by='realized_return', ascending=False)
            else: cl = cl.sort_values(by='exit_date', ascending=False)

            cols_cl = [
                ('company_name', 'اسم الصك', 'text'), 
                ('total_cost', 'التكلفة', 'money'),
                ('market_value', 'قيمة البيع', 'money'),
                ('realized_return', 'الربح المحقق', 'colorful'),
                ('exit_date', 'تاريخ البيع', 'date')
            ]
            render_custom_table(cl, cols_cl)
        else:
            st.info("أرشيف الصكوك فارغ")

# --- 5. Cash Log View ---
# --- 5. Cash Log View (Updated with Edit Feature) ---
def view_cash_log():
    st.header("💰 السيولة والسجلات المالية")
    fin = calculate_portfolio_metrics()
    
    # جلب البيانات
    deposits = fin.get('deposits', pd.DataFrame())
    withdrawals = fin.get('withdrawals', pd.DataFrame())
    returns = fin.get('returns', pd.DataFrame())

    # عرض الملخص العلوي
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
    
    # --- 1. تبويب الإيداعات ---
    with t1:
        # أ: إضافة جديد
        with st.expander("➕ تسجيل إيداع جديد"):
            with st.form("add_dep"):
                a = st.number_input("المبلغ", min_value=0.0, step=100.0)
                d = st.date_input("التاريخ", date.today())
                n = st.text_input("ملاحظة")
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO Deposits (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                    st.success("تم"); st.cache_data.clear(); st.rerun()
        
        # ب: العرض والتعديل
        if not deposits.empty:
            render_custom_table(deposits.sort_values('date', ascending=False), cols_base)
            
            st.markdown("---")
            # ✅ قسم التعديل الجديد للإيداعات
            with st.expander("✏️ تعديل سجل إيداع سابق"):
                # ننشئ قائمة للاختيار
                dep_map = {f"{row['date']} - {row['amount']} ({row['note']})": row['id'] for i, row in deposits.iterrows()}
                sel_dep = st.selectbox("اختر العملية للتعديل:", list(dep_map.keys()), key="edit_dep_sel")
                
                if sel_dep:
                    tid = dep_map[sel_dep]
                    curr = deposits[deposits['id'] == tid].iloc[0]
                    with st.form(f"edit_dep_form_{tid}"):
                        na = st.number_input("المبلغ الصحيح", value=float(curr['amount']))
                        nd = st.date_input("التاريخ الصحيح", pd.to_datetime(curr['date']))
                        nn = st.text_input("ملاحظة", value=str(curr['note']) if curr['note'] else "")
                        
                        if st.form_submit_button("حفظ التعديلات"):
                            execute_query("UPDATE Deposits SET amount=%s, date=%s, note=%s WHERE id=%s", (na, str(nd), nn, tid))
                            st.success("تم التعديل بنجاح"); st.cache_data.clear(); st.rerun()

    # --- 2. تبويب السحوبات ---
    with t2:
        # أ: إضافة جديد
        with st.expander("➖ تسجيل سحب جديد"):
            with st.form("add_wit"):
                a = st.number_input("المبلغ", min_value=0.0, step=100.0)
                d = st.date_input("التاريخ", date.today())
                n = st.text_input("ملاحظة")
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO Withdrawals (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                    st.success("تم"); st.cache_data.clear(); st.rerun()
        
        # ب: العرض والتعديل
        if not withdrawals.empty:
            render_custom_table(withdrawals.sort_values('date', ascending=False), cols_base)
            
            st.markdown("---")
            # ✅ قسم التعديل الجديد للسحوبات
            with st.expander("✏️ تعديل سجل سحب سابق"):
                wit_map = {f"{row['date']} - {row['amount']} ({row['note']})": row['id'] for i, row in withdrawals.iterrows()}
                sel_wit = st.selectbox("اختر العملية للتعديل:", list(wit_map.keys()), key="edit_wit_sel")
                
                if sel_wit:
                    tid = wit_map[sel_wit]
                    curr = withdrawals[withdrawals['id'] == tid].iloc[0]
                    with st.form(f"edit_wit_form_{tid}"):
                        na = st.number_input("المبلغ الصحيح", value=float(curr['amount']))
                        nd = st.date_input("التاريخ الصحيح", pd.to_datetime(curr['date']))
                        nn = st.text_input("ملاحظة", value=str(curr['note']) if curr['note'] else "")
                        
                        if st.form_submit_button("حفظ التعديلات"):
                            execute_query("UPDATE Withdrawals SET amount=%s, date=%s, note=%s WHERE id=%s", (na, str(nd), nn, tid))
                            st.success("تم التعديل بنجاح"); st.cache_data.clear(); st.rerun()

    # --- 3. تبويب العوائد ---
    with t3:
        # أ: إضافة جديد
        with st.expander("💵 تسجيل عائد/توزيع"):
            with st.form("add_ret"):
                s = st.text_input("رمز السهم")
                a = st.number_input("المبلغ", min_value=0.0, step=10.0)
                d = st.date_input("التاريخ", date.today())
                if st.form_submit_button("حفظ"):
                    execute_query("INSERT INTO ReturnsGrants (date, symbol, amount) VALUES (%s,%s,%s)", (str(d), s, a))
                    st.success("تم"); st.cache_data.clear(); st.rerun()
        
        # ب: العرض والتعديل
        if not returns.empty:
            render_custom_table(returns.sort_values('date', ascending=False), cols_base)
            
            st.markdown("---")
            # ✅ قسم التعديل الجديد للعوائد
            with st.expander("✏️ تعديل سجل عائد سابق"):
                ret_map = {f"{row['date']} - {row['symbol']} - {row['amount']}": row['id'] for i, row in returns.iterrows()}
                sel_ret = st.selectbox("اختر العملية للتعديل:", list(ret_map.keys()), key="edit_ret_sel")
                
                if sel_ret:
                    tid = ret_map[sel_ret]
                    curr = returns[returns['id'] == tid].iloc[0]
                    with st.form(f"edit_ret_form_{tid}"):
                        ns = st.text_input("رمز السهم", value=str(curr['symbol']))
                        na = st.number_input("المبلغ الصحيح", value=float(curr['amount']))
                        nd = st.date_input("التاريخ الصحيح", pd.to_datetime(curr['date']))
                        
                        if st.form_submit_button("حفظ التعديلات"):
                            execute_query("UPDATE ReturnsGrants SET symbol=%s, amount=%s, date=%s WHERE id=%s", (ns, na, str(nd), tid))
                            st.success("تم التعديل بنجاح"); st.cache_data.clear(); st.rerun()


# --- Other Views ---
def view_analysis(fin):
    st.header("🔬 التحليل الشامل")
    trades = fin['all_trades']
    
    from database import fetch_table
    wl = fetch_table("Watchlist")
    syms = list(set(trades['symbol'].unique().tolist() + wl['symbol'].unique().tolist())) if not trades.empty else []
    
    c1, c2 = st.columns([1, 2])
    ns = c1.text_input("بحث")
    options = [ns] + syms if ns else syms
    sym = c2.selectbox("اختر", options) if options else None
    
    if sym:
        n, s = get_company_details(sym)
        st.markdown(f"### {n} ({sym})")
        
        # استيراد المحرك الذكي
        try: from ai_engine import generate_ai_report
        except ImportError: generate_ai_report = None

        # التبويبات (المستشار الذكي هو الأول)
        tabs = st.tabs(["🤖 المستشار الذكي", "💰 مالي", "📈 فني", "🏛️ كلاسيكي", "📝 أطروحة"])
        
        # 1. المستشار الذكي (AI Report)
        with tabs[0]:
            if generate_ai_report:
                report = generate_ai_report(sym)
                
                # عنوان التوصية الكبير
                st.markdown(f"""
                <div style="text-align:center; padding: 20px; background-color: #f8f9fa; border-radius: 15px; border: 2px solid {report['color']}; margin-bottom: 20px;">
                    <h2 style="color: {report['color']}; margin:0;">{report['recommendation']}</h2>
                    <p style="color: #666; margin-top:10px; font-size:1.1rem;">{report['strategy']}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # تفاصيل النقاط
                c_ai1, c_ai2 = st.columns(2)
                with c_ai1:
                    st.subheader("النقاط الفنية")
                    for r in report['tech_reasons']: st.write(f"• {r}")
                with c_ai2:
                    st.subheader("النقاط المالية")
                    for r in report['fund_reasons']: st.write(f"• {r}")
                    
            else:
                st.warning("محرك الذكاء الاصطناعي غير متوفر (تأكد من وجود ملف ai_engine.py)")

        # 2. المالي
        with tabs[1]: render_financial_dashboard_ui(sym)
            
        # 3. الفني
        with tabs[2]: render_technical_chart(sym)
            
        # 4. الكلاسيكي
        with tabs[3]: render_classical_analysis(sym)
            
        # 5. الأطروحة
        with tabs[4]:
            th = get_thesis(sym)
            curr_text = th['thesis_text'] if th else ""
            with st.form("save_thesis_form"):
                new_text = st.text_area("نص الأطروحة", value=curr_text, height=200)
                if st.form_submit_button("💾 حفظ الأطروحة"):
                    save_thesis(sym, new_text, 0, "Hold")
                    st.success("تم الحفظ")



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
            nm, sec = get_company_details(s)
            execute_query("INSERT INTO Trades (symbol, company_name, sector, asset_type, date, quantity, entry_price, strategy, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Open')", (s,nm,sec,at,str(d),q,p,t))
            st.success(f"تمت إضافة {nm}"); st.cache_data.clear()

def view_tools(): st.header("🛠️ أدوات"); st.info("الزكاة")

def view_settings():
    st.header("⚙️ إعدادات")
    st.info("الاستيراد")
    
    # --- كود النسخ الاحتياطي يجب أن يكون هنا (داخل الدالة) ---
    from analytics import create_smart_backup

    st.markdown("---")
    st.subheader("📦 النسخ الاحتياطي")
    
    if st.button("💾 إنشاء نسخة احتياطية الآن", key="btn_backup"):
        with st.spinner("جاري إنشاء الملف..."):
            file_data, file_name = create_smart_backup()
            
        if file_data:
            st.success("تم إنشاء النسخة بنجاح!")
            st.download_button(
                label="📥 اضغط لتحميل الملف",
                data=file_data,
                file_name=file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

def router():
    if 'page' not in st.session_state:
        st.session_state.page = 'home'
    
    if st.session_state.page == 'update' and 'username' not in st.session_state:
        st.session_state.page = 'home'
        st.rerun()
    
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
