import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from logic import get_tasi_data, fetch_batch_data, get_static_info, enrich_data_frame, update_market_data_batch, get_financial_summary, get_sector_recommendations
from database import get_db
from config import DEFAULT_COLORS, PRESET_THEMES, APP_NAME, APP_ICON
from datetime import date
import time

def render_navbar():
    if 'custom_colors' not in st.session_state:
        st.session_state.custom_colors = DEFAULT_COLORS.copy()
    C = st.session_state.custom_colors
    username = st.session_state.get('username', 'مستخدم')

    # الهيدر العلوي
    st.markdown(f"""
    <div style="background-color: {C.get('card_bg')}; padding: 15px 25px; border-bottom: 1px solid {C.get('border')}; margin-bottom: 30px; display: flex; align-items: center; justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="font-size: 2.2rem;">{APP_ICON}</div>
            <div>
                <h2 style="margin: 0; color: {C['primary']} !important; font-weight: 900; line-height: 1.2;">{APP_NAME}</h2>
                <span style="font-size: 0.8rem; color: {C.get('sub_text')}; font-weight: 600;">لوحة البيانات المالية</span>
            </div>
        </div>
        <div style="text-align: left;">
            <div style="color: {C['primary']}; font-weight: bold; font-size: 0.95rem;">مرحباً، {username} 👋</div>
            <div style="font-weight: bold; color: {C.get('main_text')}; direction: ltr;">{date.today().strftime('%Y-%m-%d')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # القائمة العلوية (تم دمج زر التحديث والخروج)
    cols = st.columns(9, gap="small")
    labels = ['الرئيسية', 'مضاربة', 'استثمار', 'السيولة', 'التحليل', 'إضافة صفقة', 'الإعدادات', 'تحديث', 'خروج']
    keys = ['home', 'spec', 'invest', 'cash', 'analysis', 'add', 'settings', 'update', 'logout']
    
    for col, label, key in zip(cols, labels, keys):
        is_active = (st.session_state.get('page') == key)
        
        if key == 'logout':
            if col.button(label, key=f"nav_{key}", use_container_width=True, type="secondary"):
                st.session_state.page = key
                st.rerun()
        
        elif key == 'update':
            # زر التحديث
            if col.button("تحديث 🔄", key=f"nav_{key}", use_container_width=True, type="secondary"):
                with st.spinner("جاري تحديث الأسعار..."):
                    update_market_data_batch()
                    time.sleep(0.5)
                    st.rerun()
        
        else:
            btn_type = "primary" if is_active else "secondary"
            if col.button(label, key=f"nav_{key}", use_container_width=True, type=btn_type):
                st.session_state.page = key
                if 'editing_id' in st.session_state: del st.session_state['editing_id']
                st.rerun()
    
    st.markdown("---")

def render_kpi(label, value, color_condition=None):
    C = st.session_state.custom_colors
    val_c = C.get('main_text', '#000000')
    
    if color_condition is not None:
        if isinstance(color_condition, str) and color_condition == "blue":
             val_c = C.get('primary')
        elif isinstance(color_condition, (int, float)):
            if color_condition >= 0: val_c = C.get('success')
            else: val_c = C.get('danger')
            
    st.markdown(f"""<div class="kpi-box"><div class="kpi-title">{label}</div><div class="kpi-value" style="color: {val_c} !important;">{value}</div></div>""", unsafe_allow_html=True)

def render_recommendation_card(title, suggestions, reason):
    C = st.session_state.custom_colors
    st.markdown(f"""
    <div style="background-color: {C['card_bg']}; border-right: 5px solid {C['primary']}; padding: 15px; border-radius: 10px; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid {C['border']};">
        <div style="color: {C['primary']}; font-weight: 800; font-size: 1.1rem; margin-bottom: 5px;">📍 قطاع مقترح: {title}</div>
        <div style="color: {C['main_text']}; font-size: 0.95rem; margin-bottom: 5px;"><b>شركات مقترحة:</b> {suggestions}</div>
        <div style="color: {C['sub_text']}; font-size: 0.85rem; font-style: italic;">{reason}</div>
    </div>
    """, unsafe_allow_html=True)

def view_smart_insights(fin):
    C = st.session_state.custom_colors
    projected_income = fin.get('projected_dividend_income', 0)
    market_val = fin.get('market_val_open', 1)
    yield_pct = (projected_income / market_val * 100) if market_val > 0 else 0
    
    st.markdown(f"<h3 style='color: {C['primary']}'>💰 الدخل السلبي (توقعات التوزيعات)</h3>", unsafe_allow_html=True)
    c_div1, c_div2 = st.columns(2)
    with c_div1: render_kpi("الدخل السنوي المتوقع", f"{projected_income:,.2f}", "blue")
    with c_div2: render_kpi("نسبة العائد (Yield)", f"{yield_pct:.2f}%", yield_pct)
    st.caption("ملاحظة: هذه التوقعات مبنية على آخر توزيعات معلنة للشركات وقد تتغير.")
    st.markdown("---")

    st.markdown(f"<h3 style='color: {C['primary']}'>💡 تحسين المحفظة</h3>", unsafe_allow_html=True)
    recs = get_sector_recommendations(fin)
    
    if not recs:
        st.success("محفظتك متنوعة بشكل ممتاز وتغطي أغلب القطاعات!")
    else:
        col1, col2 = st.columns(2)
        for i, rec in enumerate(recs[:4]): 
            with col1 if i % 2 == 0 else col2:
                render_recommendation_card(rec['sector'], rec['suggestions'], rec['reason'])

def render_finance_table(df, cols_def):
    C = st.session_state.custom_colors
    headers = "".join([f"<th>{label}</th>" for _, label in cols_def])
    rows_html = ""
    for _, row in df.iterrows():
        cells = ""
        is_closed_trade = (str(row.get('status')).lower() in ['close', 'مغلقة'])
        for col_key, _ in cols_def:
            val = row.get(col_key, "-")
            display_val = val
            
            if col_key == 'daily_change':
                if is_closed_trade:
                     display_val = "<span style='color:#999'>-</span>"
                else:
                    color = C.get('success') if val >= 0 else C.get('danger')
                    display_val = f"<span style='color:{color}; direction:ltr; font-weight:bold;'>{abs(val):.2f}%</span>"
            elif col_key == 'status':
                is_open = (str(val).lower() in ['open', 'مفتوحة'])
                display_val = "مفتوحة" if is_open else "مغلقة"
                bg = "#E3FCEF" if is_open else "#DFE1E6"
                fg = C.get('success') if is_open else C.get('sub_text')
                display_val = f"<span style='background:{bg}; color:{fg}; padding:4px 10px; border-radius:12px; font-size:0.8rem;'>{display_val}</span>"
            elif col_key in ['date', 'exit_date']:
                display_val = str(val)[:10] if val else "-"
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                if col_key in ['quantity', 'companies_count']: display_val = f"{val:,.0f}"
                elif 'pct' in col_key or 'weight' in col_key: display_val = f"{val:.2f}%"
                else: display_val = f"{val:,.2f}"
                
                if col_key in ['gain', 'gain_pct', 'unrealized_pl', 'realized_pl', 'remaining_to_target']:
                    color = C.get('success') if val >= 0 else C.get('danger')
                    display_val = f"<span style='color:{color}; direction:ltr; font-weight:bold;'>{abs(val):,.2f}</span>"
                    if 'pct' in col_key: display_val += "%"
            
            cells += f"<td>{display_val}</td>"
        rows_html += f"<tr>{cells}</tr>"
    st.markdown(f"""<div style="overflow-x: auto;"><table class="finance-table"><thead><tr>{headers}</tr></thead><tbody>{rows_html}</tbody></table></div>""", unsafe_allow_html=True)

def render_edit_page(row, table_name, return_key):
    C = st.session_state.custom_colors
    st.markdown(f"""<div style="background:{C.get('card_bg')}; padding:20px; border-radius:10px; border:1px solid {C.get('border')}; margin-bottom:20px;"><h3 style="color: {C.get('primary')}; margin-bottom: 10px;">🛠 تعديل التفاصيل</h3><div style="color: {C.get('sub_text')};">المعرف: {row['id']}</div></div>""", unsafe_allow_html=True)
    with st.container():
        current_date = pd.to_datetime(row['date']).date() if row['date'] else date.today()
        new_date = st.date_input("التاريخ", current_date)
        
        close_trade = False
        exit_p = 0.0

        if table_name == "Trades":
            c1, c2 = st.columns(2)
            new_qty = c1.number_input("الكمية", value=float(row['quantity']))
            new_price = c2.number_input("سعر الشراء", value=float(row['entry_price']))
            
            st.markdown("#### حالة الصفقة")
            is_closed = (row['status'] == 'Close')
            close_trade = st.checkbox("صفقة مغلقة (تم البيع)؟", value=is_closed)
            if close_trade:
                val_exit = float(row['exit_price']) if row['exit_price'] > 0 else float(row['current_price'])
                exit_p = st.number_input("سعر البيع", value=val_exit, min_value=0.0)
        
        elif table_name in ["Deposits", "Withdrawals", "ReturnsGrants"]:
            new_amount = st.number_input("المبلغ", value=float(row['amount']))
            new_note = st.text_input("ملاحظات", value=row.get('note', ''))
            
        st.markdown("---")
        c_save, c_del, c_back = st.columns([2, 2, 1])
        if c_save.button("💾 حفظ التعديلات", type="primary", use_container_width=True):
            try:
                with get_db() as conn:
                    if table_name == "Trades":
                        if close_trade:
                            conn.execute("UPDATE Trades SET quantity=?, entry_price=?, date=?, exit_price=?, status='Close' WHERE id=?", (new_qty, new_price, str(new_date), exit_p, row['id']))
                        else:
                            conn.execute("UPDATE Trades SET quantity=?, entry_price=?, date=?, status='Open', exit_price=0 WHERE id=?", (new_qty, new_price, str(new_date), row['id']))
                    else:
                        conn.execute(f"UPDATE {table_name} SET amount=?, date=?, note=? WHERE id=?", (new_amount, str(new_date), new_note, row['id']))
                    conn.commit()
                st.success("تم الحفظ"); time.sleep(0.5); del st.session_state['editing_id']; st.rerun()
            except Exception as e: st.error(f"خطأ: {e}")
        if c_del.button("🗑 حذف السجل", use_container_width=True):
            st.session_state['conf_del'] = True
        if st.session_state.get('conf_del'):
            if st.button("تأكيد الحذف النهائي"):
                with get_db() as conn:
                    conn.execute(f"DELETE FROM {table_name} WHERE id=?", (row['id'],))
                    conn.commit()
                st.success("تم الحذف"); del st.session_state['editing_id']; del st.session_state['conf_del']; st.rerun()
        if c_back.button("عودة", use_container_width=True):
            del st.session_state['editing_id']; st.rerun()

PORTFOLIO_COLS = [('company_name', 'الشركة'), ('symbol', 'الرمز'), ('sector', 'القطاع'), ('status', 'الحالة'), ('quantity', 'الكمية'), ('entry_price', 'شراء'), ('total_cost', 'التكلفة'), ('current_price', 'سعر السوق/البيع'), ('market_value', 'القيمة'), ('gain', 'الربح/الخسارة'), ('gain_pct', 'النسبة %'), ('weight', 'الوزن'), ('daily_change', 'تغير يومي'), ('date', 'التاريخ')]

def view_portfolio(fin, strat):
    if 'editing_id' in st.session_state and st.session_state.get('edit_type') == 'Trades':
        target = fin['all_trades'][fin['all_trades']['id'] == st.session_state['editing_id']]
        if not target.empty: render_edit_page(target.iloc[0], "Trades", strat); return
            
    st.markdown(f"### 💼 محفظة {strat}")
    strat_key = "مضاربة" if strat == "مضاربة" else "استثمار"
    df = fin['all_trades'][fin['all_trades']['strategy'] == strat_key].copy()
    
    if not df.empty:
        total_cost = df['total_cost'].sum()
        market_val = df['market_value'].sum()
        total_gain = df['gain'].sum()
        
        c1, c2, c3, c4 = st.columns(4)
        with c1: render_kpi("التكلفة الإجمالية", f"{total_cost:,.2f}")
        with c2: render_kpi("القيمة الحالية", f"{market_val:,.2f}")
        with c3: render_kpi("الربح/الخسارة الكلي", f"{total_gain:+,.2f}", total_gain)
        total_pct = (total_gain / total_cost * 100) if total_cost > 0 else 0
        with c4: render_kpi("نسبة الأداء", f"{total_pct:+.2f}%", total_pct)
        
        st.markdown("---")
        
        st.markdown("<div class='section-header'>تحليل القطاعات (العمليات القائمة)</div>", unsafe_allow_html=True)
        if not df[df['status']=='Open'].empty:
            from logic import calculate_sector_distribution
            sector_df = calculate_sector_distribution(df, df[df['status']=='Open']['total_cost'].sum())
            if not sector_df.empty:
                render_finance_table(sector_df, [
                    ('sector', 'القطاع'), ('companies_count', 'عدد الشركات'), ('sector_cost', 'التكلفة'), 
                    ('current_weight', 'الوزن الحالي %'), ('target_weight', 'الوزن المستهدف %'), 
                    ('remaining_to_target', 'المتبقي للهدف')
                ])
        else: st.info("لا توجد عمليات قائمة لعرض تحليل القطاعات")

        st.markdown("<div class='section-header'>تفاصيل الصفقات</div>", unsafe_allow_html=True)
        c_sort, c_sel = st.columns([1, 2])
        sort_by = c_sort.selectbox(f"فرز {strat} حسب:", ["التاريخ (الأحدث)", "الربح (الأعلى)", "الوزن (الأعلى)"])
        if sort_by == "الربح (الأعلى)": df = df.sort_values(by='gain', ascending=False)
        elif sort_by == "الوزن (الأعلى)": df = df.sort_values(by='weight', ascending=False)
        else: df = df.sort_values(by='date', ascending=False)
        
        render_finance_table(df, PORTFOLIO_COLS)
        
        st.markdown("---")
        opts = {row['id']: f"{row['symbol']} - {row['company_name']} ({str(row['date'])[:10]})" for _, row in df.iterrows()}
        sel_id = c_sel.selectbox("اختر صفقة للتعديل/الإغلاق:", list(opts.keys()), format_func=lambda x: opts[x])
        if c_sel.button("📝 تعديل التفاصيل", type="primary"):
            st.session_state['editing_id'] = sel_id
            st.session_state['edit_type'] = 'Trades'
            st.rerun()
    else: st.info(f"لا توجد صفقات في {strat}")

def view_liquidity():
    if 'editing_id' in st.session_state and st.session_state.get('edit_type') in ['Deposits', 'Withdrawals', 'ReturnsGrants']:
        t_name = st.session_state['edit_type']
        with get_db() as conn:
            target = pd.read_sql(f"SELECT * FROM {t_name} WHERE id = ?", conn, params=(st.session_state['editing_id'],))
        if not target.empty: render_edit_page(target.iloc[0], t_name, "cash"); return
    st.header("السجلات المالية")
    sort_liq = st.selectbox("فرز السجلات حسب:", ["التاريخ (الأحدث)", "المبلغ (الأعلى)"])
    fin = get_financial_summary() 
    def apply_sort(d):
        if sort_liq == "المبلغ (الأعلى)": return d.sort_values(by='amount', ascending=False)
        return d.sort_values(by='date', ascending=False)
    with get_db() as conn:
        dep = pd.read_sql("SELECT * FROM Deposits", conn)
        wit = pd.read_sql("SELECT * FROM Withdrawals", conn)
        ret = pd.read_sql("SELECT * FROM ReturnsGrants", conn)
    tab1, tab2, tab3 = st.tabs(["📥 الإيداعات", "📤 السحوبات", "🎁 العوائد"])
    def handle_liq_tab(df, t_name, cols, k):
        if not df.empty:
            df = apply_sort(df)
            render_finance_table(df, cols)
            opts = {row['id']: f"{str(row['date'])[:10]} - {row.get('amount', 0):,.2f}" for _, row in df.iterrows()}
            c_s = st.columns([1, 2])[1]
            sid = c_s.selectbox("اختر للتعديل:", list(opts.keys()), format_func=lambda x: opts[x], key=f"sl_{k}")
            if c_s.button("تعديل", key=f"bt_{k}"):
                st.session_state['editing_id'] = sid
                st.session_state['edit_type'] = t_name
                st.rerun()
        else: st.info("لا يوجد")
    with tab1:
        st.markdown(f"الإجمالي: {fin['deposits']['amount'].sum():,.2f}")
        handle_liq_tab(fin['deposits'], "Deposits", [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظات')], "d")
    with tab2:
        st.markdown(f"الإجمالي: {fin['withdrawals']['amount'].sum():,.2f}")
        handle_liq_tab(fin['withdrawals'], "Withdrawals", [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظات')], "w")
    with tab3:
        st.markdown(f"الإجمالي: {fin['returns']['amount'].sum():,.2f}")
        if not fin['returns'].empty: fin['returns'] = enrich_data_frame(fin['returns'])
        handle_liq_tab(fin['returns'], "ReturnsGrants", [('symbol', 'الرمز'), ('company_name', 'الشركة'), ('date', 'التاريخ'), ('amount', 'المبلغ')], "r")

def view_dashboard(fin):
    try: tasi_price, tasi_change = get_tasi_data()
    except: tasi_price, tasi_change = 0, 0
    C = st.session_state.custom_colors
    if tasi_price:
        arrow = "🔼" if tasi_change >= 0 else "🔽"
        color = "#36B37E" if tasi_change >= 0 else "#FF5630"
        st.markdown(f"""<div class="tasi-box"><div><div style="font-size:1.1rem; opacity:0.9;">المؤشر العام</div><div style="font-size:2rem; font-weight:900;">{tasi_price:,.2f}</div></div><div style="background:rgba(255,255,255,0.1); padding:10px 20px; border-radius:12px; font-size:1.2rem; font-weight:bold; direction:ltr; color:{color} !important; border:1px solid rgba(255,255,255,0.2)">{arrow} {tasi_change:.2f}%</div></div>""", unsafe_allow_html=True)
    
    st.markdown("<div class='section-header'>مصدر الأموال</div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi("ما تم إيداعه", f"{fin['total_deposited']:,.2f}", "blue")
    with c2: render_kpi("ما تم سحبه", f"{fin['total_withdrawn']:,.2f}", "blue") 
    with c3: render_kpi("إجمالي المستثمر (من جيبي)", f"{fin['total_deposited'] - fin['total_withdrawn']:,.2f}", "blue")
    with c4: render_kpi("النقد المتوفر (الكاش)", f"{fin['cash']:,.2f}", 1)

    st.markdown("<div class='section-header'>تفاصيل الأداء</div>", unsafe_allow_html=True)
    
    col_exec, col_exist = st.columns(2)
    
    with col_exec:
        st.markdown("##### ✅ العمليات المنفذة (المغلقة)")
        c_ex1, c_ex2 = st.columns(2)
        with c_ex1: render_kpi("التكلفة الأساسية", f"{fin['cost_closed']:,.2f}")
        with c_ex2: render_kpi("المبلغ بعد البيع", f"{fin['sales_closed']:,.2f}")
        
        c_ex3, c_ex4 = st.columns(2)
        with c_ex3: render_kpi("الربح/الخسارة المحقق", f"{fin['realized_pl']:+,.2f}", fin['realized_pl'])
        pct_realized = (fin['realized_pl'] / fin['cost_closed'] * 100) if fin['cost_closed'] > 0 else 0
        with c_ex4: render_kpi("نسبة الأداء", f"{pct_realized:+.2f}%", pct_realized)

    with col_exist:
        st.markdown("##### ⏳ العمليات القائمة (المفتوحة)")
        c_op1, c_op2 = st.columns(2)
        with c_op1: render_kpi("التكلفة الحالية", f"{fin['cost_open']:,.2f}")
        with c_op2: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}")
        
        c_op3, c_op4 = st.columns(2)
        with c_op3: render_kpi("الربح/الخسارة العائم", f"{fin['unrealized_pl']:+,.2f}", fin['unrealized_pl'])
        pct_unrealized = (fin['unrealized_pl'] / fin['cost_open'] * 100) if fin['cost_open'] > 0 else 0
        with c_op4: render_kpi("نسبة الأداء", f"{pct_unrealized:+.2f}%", pct_unrealized)

    st.markdown("---")
    c_ret1, c_ret2 = st.columns(2)
    with c_ret1: render_kpi("اجمالي العوائد (التوزيعات)", f"{fin['total_returns']:,.2f}", 1)
    with c_ret2: render_kpi("صافي قيمة الأصول (Equity)", f"{fin['equity']:,.2f}", "blue")

    st.markdown("---")
    view_smart_insights(fin)
    
    c_chart, c_watch = st.columns([2, 1])
    with c_chart:
        st.markdown("### 📊 توزيع الأصول")
        trades = fin['all_trades']
        if not trades.empty:
            open_df = trades[trades['status']=='Open'].copy()
            if not open_df.empty:
                open_df['Cost'] = open_df['quantity'] * open_df['entry_price']
                fig = px.pie(open_df, values='Cost', names='sector', hole=0.6, color_discrete_sequence=px.colors.sequential.Blues_r)
                fig.update_traces(textposition='outside', textinfo='percent+label')
                fig.update_layout(showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color=C.get('main_text'))
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("المحفظة فارغة")
    with c_watch:
        st.subheader("⭐️ المتابعة")
        with get_db() as conn:
            try: watch = pd.read_sql("SELECT symbol FROM Watchlist", conn)
            except: watch = pd.DataFrame(columns=['symbol'])
        if not watch.empty:
            prices = fetch_batch_data(watch['symbol'].tolist())
            for sym in watch['symbol']:
                d = prices.get(sym, {'price':0, 'change_pct':0})
                n, _ = get_static_info(sym)
                clr = C.get('success') if d.get('change_pct',0)>=0 else C.get('danger')
                st.markdown(f"""<div class="kpi-box" style="display:flex; justify-content:space-between; margin-bottom:10px;"><div><b>{n}</b><br><small>{sym}</small></div><div style="text-align:left;"><b>{d['price']:.2f}</b><br><span style="color:{clr}; direction:ltr; font-weight:bold;">{d.get('change_pct',0):+.2f}%</span></div></div>""", unsafe_allow_html=True)
        else: st.info("القائمة فارغة")

def view_add_trade():
    C = st.session_state.custom_colors
    st.markdown(f"<h3 style='text-align:center; color:{C.get('primary')};'>تسجيل عملية جديدة</h3>", unsafe_allow_html=True)
    
    with st.form("new_trade_form"):
        c1, c2 = st.columns(2)
        sym = c1.text_input("رمز السهم")
        n, s = get_static_info(sym) if sym else ("", "")
        comp = c2.text_input("اسم الشركة", value=n)
        c3, c4 = st.columns(2)
        date_t = c3.date_input("تاريخ الشراء", date.today())
        strat = c4.selectbox("نوع المحفظة", ["مضاربة", "استثمار"])
        c5, c6 = st.columns(2)
        qty = c5.number_input("الكمية", min_value=1.0)
        price = c6.number_input("سعر الشراء", min_value=0.0)
        
        if st.form_submit_button("حفظ العملية", type="primary"):
            if sym:
                try:
                    with get_db() as conn:
                        conn.execute("INSERT INTO Trades (symbol, company_name, sector, date, quantity, entry_price, strategy, status, current_price) VALUES (?,?,?,?,?,?,?,?,?)", (sym, comp, s, str(date_t), qty, price, strat, "Open", price))
                        conn.commit()
                    st.success("تم الحفظ"); time.sleep(0.5); st.cache_data.clear(); st.rerun()
                except Exception as e: st.error(f"خطأ: {e}")
            else: st.error("الرمز مطلوب")
    
    st.markdown("---")
    
    with st.expander("🧮 حاسبة تعديل المتوسط (للتبريد/التعديل)"):
        c_calc1, c_calc2 = st.columns(2)
        old_qty = c_calc1.number_input("الكمية الحالية لديك", min_value=0.0, step=1.0)
        old_avg = c_calc2.number_input("متوسط السعر الحالي", min_value=0.0)
        
        c_calc3, c_calc4 = st.columns(2)
        new_price_market = c_calc3.number_input("سعر السهم الحالي بالسوق", min_value=0.0)
        target_qty = c_calc4.number_input("كم سهم تريد أن تشتري؟", min_value=0.0, step=1.0)
        
        if target_qty > 0 and new_price_market > 0:
            total_qty = old_qty + target_qty
            total_cost = (old_qty * old_avg) + (target_qty * new_price_market)
            new_avg = total_cost / total_qty
            st.info(f"💡 إذا اشتريت {target_qty} سهم بسعر {new_price_market}، سيصبح متوسطك الجديد: **{new_avg:.2f}**")

def view_settings():
    st.header("⚙️ الإعدادات")
    C = st.session_state.custom_colors
    
    # --- قسم استيراد البيانات (تم إصلاحه ليدعم السيولة والأعمدة المختلفة) ---
    with st.expander("📥 استيراد بيانات سابقة (من ملف Excel)"):
        st.warning("تحذير: هذا الخيار سيضيف البيانات للموجودة حالياً.")
        uploaded_file = st.file_uploader("اختر ملف النسخة الاحتياطية (Excel)", type=['xlsx'])
        
        if uploaded_file is not None:
            if st.button("بدء الاستيراد"):
                try:
                    xls = pd.ExcelFile(uploaded_file)
                    imported_count = 0
                    
                    with get_db() as conn:
                        # 1. استيراد الصفقات (Trades)
                        if 'Trades' in xls.sheet_names:
                            df_t = pd.read_excel(xls, 'Trades')
                            # تنظيف: حذف عمود id لأنه سيتعارض، وحذف الأعمدة الفارغة
                            if 'id' in df_t.columns: df_t = df_t.drop(columns=['id'])
                            
                            # اختيار الأعمدة التي نحتاجها فقط (لتجنب الأخطاء)
                            valid_cols = ['symbol', 'company_name', 'sector', 'date', 'quantity', 'entry_price', 
                                          'strategy', 'status', 'exit_date', 'exit_price', 'current_price', 
                                          'prev_close', 'year_high', 'year_low']
                            df_t = df_t[[c for c in df_t.columns if c in valid_cols]]
                            
                            df_t.to_sql('Trades', conn, if_exists='append', index=False)
                            st.success(f"✅ تم استيراد الصفقات: {len(df_t)} صفقة.")
                            imported_count += 1
                        
                        # 2. استيراد الإيداعات (Deposits)
                        if 'Deposits' in xls.sheet_names:
                            df_d = pd.read_excel(xls, 'Deposits')
                            if 'id' in df_d.columns: df_d = df_d.drop(columns=['id'])
                            # في ملفك العمود اسمه source ونحن نحتاجه note
                            if 'source' in df_d.columns: df_d.rename(columns={'source': 'note'}, inplace=True)
                            
                            valid_cols = ['date', 'amount', 'note']
                            df_d = df_d[[c for c in df_d.columns if c in valid_cols]]
                            
                            df_d.to_sql('Deposits', conn, if_exists='append', index=False)
                            st.success(f"✅ تم استيراد الإيداعات: {len(df_d)} عملية.")
                            imported_count += 1

                        # 3. استيراد السحوبات (Withdrawals)
                        if 'Withdrawals' in xls.sheet_names:
                            df_w = pd.read_excel(xls, 'Withdrawals')
                            if 'id' in df_w.columns: df_w = df_w.drop(columns=['id'])
                            # في ملفك العمود اسمه reason ونحن نحتاجه note
                            if 'reason' in df_w.columns: df_w.rename(columns={'reason': 'note'}, inplace=True)
                            
                            valid_cols = ['date', 'amount', 'note']
                            df_w = df_w[[c for c in df_w.columns if c in valid_cols]]
                            
                            df_w.to_sql('Withdrawals', conn, if_exists='append', index=False)
                            st.success(f"✅ تم استيراد السحوبات: {len(df_w)} عملية.")
                            imported_count += 1

                        # 4. استيراد العوائد (ReturnsGrants)
                        if 'ReturnsGrants' in xls.sheet_names:
                            df_r = pd.read_excel(xls, 'ReturnsGrants')
                            if 'id' in df_r.columns: df_r = df_r.drop(columns=['id'])
                            
                            valid_cols = ['date', 'symbol', 'company_name', 'amount']
                            df_r = df_r[[c for c in df_r.columns if c in valid_cols]]
                            
                            df_r.to_sql('ReturnsGrants', conn, if_exists='append', index=False)
                            st.success(f"✅ تم استيراد العوائد: {len(df_r)} عملية.")
                            imported_count += 1
                            
                        conn.commit()
                        
                    if imported_count > 0:
                        st.balloons()
                        st.success("تمت عملية الاستيراد بنجاح! يرجى تحديث الصفحة.")
                        st.cache_data.clear()
                    else:
                        st.warning("لم يتم العثور على صفحات مطابقة في الملف.")
                        
                except Exception as e:
                    st.error(f"حدث خطأ أثناء الاستيراد: {e}")

    # --- باقي الإعدادات ---
    st.markdown(f"<h3 style='color: {C['main_text']}'>🎨 تخصيص المظهر والألوان</h3>", unsafe_allow_html=True)
    selected_theme = st.selectbox("اختر نمط الألوان الجاهز:", list(PRESET_THEMES.keys()))
    if st.button("تطبيق الثيم"):
        st.session_state.custom_colors = PRESET_THEMES[selected_theme].copy()
        st.rerun()
    
    with st.expander("🛠 تخصيص يدوي للألوان"):
        col1, col2 = st.columns(2)
        new_text_color = col1.color_picker("لون النصوص الرئيسية", C.get('main_text'))
        new_sub_text = col2.color_picker("لون العناوين الفرعية والأيقونات", C.get('sub_text'))
        col3, col4 = st.columns(2)
        new_bg_color = col3.color_picker("لون الخلفية", C.get('page_bg'))
        new_card_color = col4.color_picker("لون البطاقات", C.get('card_bg'))
        col5, col6 = st.columns(2)
        new_primary = col5.color_picker("اللون الرئيسي (للأزرار والنشط)", C.get('primary'))
        new_success = col6.color_picker("لون الأرباح (أخضر)", C.get('success'))
        
        if st.button("تطبيق التخصيص"):
            st.session_state.custom_colors.update({
                'main_text': new_text_color,
                'sub_text': new_sub_text,
                'page_bg': new_bg_color,
                'card_bg': new_card_color,
                'primary': new_primary,
                'success': new_success
            })
            st.rerun()
            
    if st.button("استعادة الافتراضي"):
        st.session_state.custom_colors = DEFAULT_COLORS.copy()
        st.rerun()
        
    with st.expander("قائمة المتابعة"):
        c1, c2 = st.columns([3, 1])
        add_s = c1.text_input("رمز السهم")
        if c2.button("إضافة", key="add_w"):
            with get_db() as conn: conn.execute("INSERT OR IGNORE INTO Watchlist (symbol) VALUES (?)", (add_s,))
            st.success("تم"); st.cache_data.clear()
            
    with st.expander("تعديل الصفقات (للحذف فقط)"):
        with get_db() as conn: df = pd.read_sql("SELECT * FROM Trades ORDER BY date DESC", conn)
        if not df.empty:
            del_id = st.number_input("أدخل معرف الصفقة (ID) لحذفها:", step=1)
            if st.button("🗑 حذف الصفقة المحددة"):
                with get_db() as conn: conn.execute("DELETE FROM Trades WHERE id=?", (del_id,)); conn.commit()
                st.success("تم الحذف"); st.rerun()
        else: st.info("لا توجد صفقات")
