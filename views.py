import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from analytics import calculate_portfolio_metrics, update_prices, create_smart_backup
from components import render_kpi, render_table, render_navbar
from charts import view_advanced_chart
from market_data import get_static_info, get_tasi_data
from database import execute_query, fetch_table, get_db
from config import BACKUP_DIR

def view_dashboard(fin):
    # --- 1. مصدر الأموال ---
    st.markdown("### 🏦 مصدر الأموال")
    c1, c2, c3, c4 = st.columns(4)
    
    total_invested_pocket = fin['total_deposited'] - fin['total_withdrawn']
    
    # تنسيق الأرقام لتبدو مثل الصورة
    with c1: render_kpi("النقد المتوفر", f"SAR {fin['cash']:,.2f}")
    with c2: render_kpi("اجمالي المستثمر (من حسابي)", f"SAR {total_invested_pocket:,.2f}")
    with c3: render_kpi("ما تم سحبه", f"SAR {fin['total_withdrawn']:,.2f}", -1) # لون أحمر
    with c4: render_kpi("ما تم إيداعه", f"SAR {fin['total_deposited']:,.2f}", "blue")

    st.markdown("---")

    # --- 2. العمليات المنفذة & الأهداف ---
    st.markdown(f"### ✅ العمليات المنفذة (الهدف الاستثماري حتى {date.today().year}-12-31)")
    
    # حسابات الهدف (افتراض 10% كما في طلبك)
    target_pct = 10.0
    target_amount = total_invested_pocket * (target_pct / 100)
    # الأرباح المحققة تشمل (الربح الرأسمالي + العوائد)
    total_realized_gains = fin['realized_pl'] + fin['total_returns']
    remaining_to_target = target_amount - total_realized_gains
    pct_achieved = (total_realized_gains / target_amount * 100) if target_amount != 0 else 0
    
    col_exec1, col_exec2, col_exec3, col_exec4 = st.columns(4)
    with col_exec1:
        st.metric("التكلفة/المبلغ الأساسي", f"SAR {fin['cost_closed']:,.2f}")
        st.metric("نسبة الهدف الاستثماري", f"{target_pct}%")
    with col_exec2:
        st.metric("الخسائر/الأرباح المحققة", f"SAR {fin['realized_pl']:,.2f}", delta=f"{fin['realized_pl']:,.2f}")
        st.metric("قيمة الهدف الاستثماري", f"SAR {target_amount:,.2f}")
    with col_exec3:
        st.metric("المبلغ بعد البيع", f"SAR {fin['sales_closed']:,.2f}")
        st.metric("المتبقي للوصول للهدف", f"SAR {remaining_to_target:,.2f}")
    with col_exec4:
        st.metric("اجمالي العوائد", f"SAR {fin['total_returns']:,.2f}")
        st.metric("نسبة المحقق من الهدف", f"{pct_achieved:.2f}%")

    st.markdown("---")

    # --- 3. العمليات القائمة ---
    st.markdown("### ⏳ العمليات القائمة (المفتوحة)")
    
    col_op1, col_op2, col_op3, col_op4 = st.columns(4)
    
    with col_op1: st.metric("التكلفة الحالية", f"SAR {fin['cost_open']:,.2f}")
    with col_op2: st.metric("القيمة السوقية (سعر السوق)", f"SAR {fin['market_val_open']:,.2f}")
    with col_op3: st.metric("الربح/الخسارة", f"SAR {fin['unrealized_pl']:,.2f}", delta=f"{fin['unrealized_pl']:,.2f}")
    
    unrealized_pct = (fin['unrealized_pl'] / fin['cost_open'] * 100) if fin['cost_open'] > 0 else 0
    with col_op4: st.metric("نسبة الربح/الخسارة %", f"{unrealized_pct:.2f}%", delta=f"{unrealized_pct:.2f}%")

    st.markdown("---")

    # --- 4. توزيع القطاعات (تم استعادته) ---
    st.markdown("### 📊 توزيع القطاعات")
    trades = fin['all_trades']
    if not trades.empty:
        open_trades = trades[trades['status'] != 'Close']
        if not open_trades.empty:
            # تجميع حسب القطاع
            sector_data = open_trades.groupby('sector')['market_value'].sum().reset_index()
            
            fig = px.pie(sector_data, values='market_value', names='sector', 
                         title='توزيع المحفظة حسب القطاع', hole=0.4)
            fig.update_layout(font=dict(family="Cairo"))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("لا توجد صفقات مفتوحة لعرض توزيع القطاعات")

def view_portfolio(fin, strategy):
    st.header(f"💼 محفظة {strategy}")
    
    # تنظيف مفتاح الاستراتيجية
    strat_key = "مضاربة" if strategy=="مضاربة" else "استثمار"
    
    # فلترة صارمة جداً
    all_trades = fin['all_trades']
    if all_trades.empty:
        st.info("لا توجد بيانات صفقات.")
        return

    # التأكد من أن العمود نصي ونظيف
    all_trades['strategy'] = all_trades['strategy'].astype(str).str.strip()
    
    # الفلترة
    df = all_trades[all_trades['strategy'] == strat_key].copy()
    
    if not df.empty:
        # ترتيب
        df = df.sort_values(by='date', ascending=False)
        
        # حساب الوزن النسبي داخل هذه المحفظة فقط (كما طلبت)
        # نحسب الوزن فقط للصفقات المفتوحة، المغلقة وزنها 0
        is_open = df['status'] != 'Close'
        total_market_val_strat = df.loc[is_open, 'market_value'].sum()
        
        df['local_weight'] = 0.0
        if total_market_val_strat > 0:
            df.loc[is_open, 'local_weight'] = (df.loc[is_open, 'market_value'] / total_market_val_strat) * 100
        
        # تعريف الأعمدة بالضبط كما طلبت
        # الاسم، الرمز، القطاع، الحالة، تاريخ الشراء، تاريخ البيع، الكمية، سعر الشراء، التكلفة، 
        # اعلى سنوي، السعر الحالي، ادنى سنوي، سعر السوق، الربح والخسارة، نسبة الربح، الوزن، التغير اليومي
        
        cols = [
            ('company_name', 'اسم الشركة'),
            ('symbol', 'الرمز'),
            ('sector', 'القطاع'),
            ('status', 'الحالة'),
            ('date', 'تاريخ الشراء'),
            ('exit_date', 'تاريخ البيع'), # يظهر فقط للمغلقة
            ('quantity', 'الكمية'),
            ('entry_price', 'سعر الشراء'),
            ('total_cost', 'التكلفة'),
            ('year_high', 'أعلى سنوي'),
            ('current_price', 'السعر الحالي'),
            ('year_low', 'أدنى سنوي'),
            ('market_value', 'القيمة السوقية'),
            ('gain', 'الربح/الخسارة'),
            ('gain_pct', '% الربح'),
            ('local_weight', 'الوزن %'),
            ('daily_change', 'يومي %')
        ]
        
        # عرض إجمالي هذه المحفظة فقط
        total_g = df['gain'].sum()
        total_v = df['market_value'].sum()
        c1, c2 = st.columns(2)
        with c1: st.metric("قيمة المحفظة", f"{total_v:,.2f}")
        with c2: st.metric("إجمالي الربح/الخسارة", f"{total_g:,.2f}", delta=f"{total_g:,.2f}")
        
        render_table(df, cols)
    else: 
        st.warning(f"لا توجد صفقات مسجلة تحت تصنيف '{strat_key}'. تأكد من اختيار التصنيف الصحيح عند إضافة الصفقة.")

def view_liquidity():
    st.header("💵 سجلات السيولة")
    fin = calculate_portfolio_metrics()
    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "العوائد"])
    with t1:
        st.markdown(f"**الإجمالي:** {fin['total_deposited']:,.2f}")
        render_table(fin['deposits'], [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظات')])
    with t2:
        st.markdown(f"**الإجمالي:** {fin['total_withdrawn']:,.2f}")
        render_table(fin['withdrawals'], [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظات')])
    with t3:
        st.markdown(f"**الإجمالي:** {fin['total_returns']:,.2f}")
        render_table(fin['returns'], [('date', 'التاريخ'), ('symbol', 'الرمز'), ('company_name', 'الشركة'), ('amount', 'المبلغ')])

def view_add_trade():
    st.header("📝 تسجيل عملية جديدة")
    with st.form("add_trade_form"):
        c1, c2 = st.columns(2)
        sym = c1.text_input("رمز السهم")
        qty = c2.number_input("الكمية", min_value=1.0)
        c3, c4 = st.columns(2)
        price = c3.number_input("سعر الشراء", min_value=0.0)
        strat = c4.selectbox("نوع المحفظة", ["استثمار", "مضاربة"])
        date_t = st.date_input("تاريخ الشراء", date.today())
        
        if st.form_submit_button("حفظ", type="primary"):
            if sym and qty > 0:
                n, s = get_static_info(sym)
                # حفظ الاستراتيجية نظيفة
                execute_query("INSERT INTO Trades (symbol, company_name, sector, date, quantity, entry_price, strategy, status, current_price) VALUES (?,?,?,?,?,?,?,?,?)", 
                    (sym, n, s, str(date_t), qty, price, strat.strip(), 'Open', price))
                st.success("تم الحفظ"); st.cache_data.clear()
            else: st.error("بيانات ناقصة")

def view_settings():
    st.header("⚙️ الإعدادات")
    with st.expander("النسخ الاحتياطي", expanded=True):
        if st.button("نسخ الآن"): create_smart_backup(); st.success("تم")
        bk = BACKUP_DIR / "backup_latest.xlsx"
        if bk.exists():
            with open(bk, "rb") as f: st.download_button("تحميل Excel", f, "backup.xlsx")
    with st.expander("استيراد"):
        up = st.file_uploader("ملف Excel", type=['xlsx'])
        if up and st.button("استيراد"):
            try:
                xl = pd.ExcelFile(up)
                with get_db() as conn:
                    for t in ['Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants']:
                        conn.execute(f"DELETE FROM {t}")
                        if t in xl.sheet_names:
                            df = pd.read_excel(xl, t)
                            if 'id' in df.columns: df = df.drop(columns=['id'])
                            if 'source' in df.columns: df.rename(columns={'source':'note'}, inplace=True)
                            # تنظيف الاستراتيجية عند الاستيراد أيضاً
                            if 'strategy' in df.columns and t == 'Trades':
                                df['strategy'] = df['strategy'].astype(str).str.strip()
                            df.to_sql(t, conn, if_exists='append', index=False)
                    conn.commit()
                st.success("تم"); st.cache_data.clear()
            except Exception as e: st.error(str(e))

def router():
    render_navbar()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    if pg == 'home': view_dashboard(fin)
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'cash': view_liquidity()
    elif pg == 'analysis': view_advanced_chart(fin)
    elif pg == 'add': view_add_trade()
    elif pg == 'settings': view_settings()
    elif pg == 'update':
        with st.spinner("تحديث الأسعار..."): update_prices()
        st.session_state.page = 'home'; st.rerun()
