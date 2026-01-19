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
    # المؤشر
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    C = st.session_state.custom_colors
    arrow = "🔼" if t_change >= 0 else "🔽"
    color = "#10B981" if t_change >= 0 else "#EF4444"
    st.markdown(f"""
    <div class="tasi-box">
        <div>
            <div style="font-size:1.2rem; color:{C['sub_text']}; margin-bottom:5px;">المؤشر العام (TASI)</div>
            <div style="font-size:2.5rem; font-weight:900; color:{C['main_text']};">{t_price:,.2f}</div>
        </div>
        <div style="text-align:left;">
            <div style="background:{color}20; color:{color}; padding:10px 25px; border-radius:12px; font-size:1.4rem; font-weight:bold; direction:ltr; border:1px solid {color}50;">
                {arrow} {t_change:+.2f}%
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # مصدر الأموال
    st.markdown("### 🏦 الملخص المالي")
    c1, c2, c3, c4 = st.columns(4)
    total_invested_pocket = fin['total_deposited'] - fin['total_withdrawn']
    with c1: render_kpi("النقد المتوفر (الكاش)", f"SAR {fin['cash']:,.2f}")
    with c2: render_kpi("صافي الإيداعات", f"SAR {total_invested_pocket:,.2f}")
    with c3: render_kpi("القيمة السوقية الحالية", f"SAR {fin['market_val_open']:,.2f}", "blue")
    
    total_pl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("إجمالي الأرباح/الخسائر", f"SAR {total_pl:,.2f}", total_pl)
    st.markdown("---")

    # العمليات القائمة
    st.markdown("### ⏳ الصفقات المفتوحة (القائمة)")
    col_op1, col_op2, col_op3, col_op4 = st.columns(4)
    with col_op1: st.metric("التكلفة الحالية", f"SAR {fin['cost_open']:,.2f}")
    with col_op2: st.metric("القيمة السوقية", f"SAR {fin['market_val_open']:,.2f}")
    with col_op3: st.metric("الربح/الخسارة العائم", f"SAR {fin['unrealized_pl']:,.2f}", delta=f"{fin['unrealized_pl']:,.2f}")
    unrealized_pct = (fin['unrealized_pl'] / fin['cost_open'] * 100) if fin['cost_open'] > 0 else 0
    with col_op4: st.metric("نسبة النمو %", f"{unrealized_pct:.2f}%", delta=f"{unrealized_pct:.2f}%")
    st.markdown("---")

    # توزيع القطاعات
    st.markdown("### 📊 توزيع السيولة والقطاعات")
    trades = fin['all_trades']
    if not trades.empty:
        open_trades = trades[trades['status'] == 'Open']
        if not open_trades.empty:
            sector_data = open_trades.groupby('sector')['market_value'].sum().reset_index()
            fig = px.pie(sector_data, values='market_value', names='sector', title='توزيع المحفظة الحالية حسب القطاع', hole=0.4)
            fig.update_layout(font=dict(family="Cairo"))
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("لا توجد صفقات مفتوحة حالياً لعرض الرسم البياني.")

def view_portfolio(fin, page_key):
    # --- إصلاح المشكلة هنا: الربط الصحيح بين مفتاح الصفحة واسم الاستراتيجية في قاعدة البيانات ---
    if page_key == 'spec':
        target_strategy = "مضاربة"
        page_title = "⚡ محفظة المضاربة"
    else:
        target_strategy = "استثمار"
        page_title = "💎 محفظة الاستثمار"

    st.header(page_title)
    all_trades = fin['all_trades']
    
    if all_trades.empty:
        st.info("لا توجد بيانات مسجلة في النظام.")
        return

    # الفلترة الصارمة بناءً على الاستراتيجية
    # نستخدم strip() لضمان عدم وجود مسافات خفية
    df_strategy = all_trades[all_trades['strategy'] == target_strategy].copy()
    
    if df_strategy.empty:
        st.warning(f"لا توجد صفقات مسجلة تحت تصنيف '{target_strategy}'. تأكد من اختيار التصنيف الصحيح عند إضافة الصفقة.")
        return

    # فصل البيانات (مفتوحة / مغلقة)
    df_open = df_strategy[df_strategy['status'] == 'Open'].copy()
    df_closed = df_strategy[df_strategy['status'] == 'Close'].copy()

    # تبويبات للفصل بين المفتوح والمغلق
    tab1, tab2 = st.tabs([f"الصفقات القائمة (عدد: {len(df_open)})", f"أرشيف العمليات المغلقة (عدد: {len(df_closed)})"])

    # --- تبويب الصفقات المفتوحة ---
    with tab1:
        if not df_open.empty:
            # حساب الأوزان محلياً لهذه المحفظة
            total_val = df_open['market_value'].sum()
            df_open['local_weight'] = (df_open['market_value'] / total_val * 100) if total_val > 0 else 0
            
            # مؤشرات سريعة لهذه المحفظة
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("القيمة السوقية", f"{total_val:,.2f}")
            gain_val = df_open['gain'].sum()
            with c2: st.metric("الربح/الخسارة", f"{gain_val:,.2f}", delta=f"{gain_val:,.2f}")
            with c3: st.metric("عدد الشركات", len(df_open))

            cols_open = [
                ('company_name', 'الشركة'), ('symbol', 'الرمز'), ('date', 'تاريخ الشراء'),
                ('quantity', 'الكمية'), ('entry_price', 'سعر الشراء'), 
                ('current_price', 'السعر الحالي'), ('market_value', 'القيمة السوقية'), 
                ('gain', 'الربح/الخسارة'), ('gain_pct', '% النمو'),
                ('local_weight', 'الوزن %'), ('daily_change', 'يومي %')
            ]
            render_table(df_open.sort_values(by='date', ascending=False), cols_open)
        else:
            st.info("لا توجد أسهم تمتلكها حالياً في هذه المحفظة.")

    # --- تبويب الصفقات المغلقة ---
    with tab2:
        if not df_closed.empty:
            realized = df_closed['gain'].sum()
            sales = df_closed['market_value'].sum()
            
            c1, c2 = st.columns(2)
            with c1: st.metric("إجمالي المبيعات", f"{sales:,.2f}")
            with c2: st.metric("الأرباح المحققة", f"{realized:,.2f}", delta=f"{realized:,.2f}")

            cols_closed = [
                ('company_name', 'الشركة'), ('symbol', 'الرمز'), 
                ('date', 'تاريخ الشراء'), ('exit_date', 'تاريخ البيع'),
                ('quantity', 'الكمية'), ('entry_price', 'شراء'), ('exit_price', 'بيع'),
                ('market_value', 'قيمة البيع'), ('gain', 'الربح المحقق'), ('gain_pct', '% العائد')
            ]
            render_table(df_closed.sort_values(by='exit_date', ascending=False), cols_closed)
        else:
            st.info("لا توجد صفقات مغلقة سابقة.")

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
        # تأكدنا هنا أن القيم المدخلة تطابق ما نبحث عنه في view_portfolio
        strat = c4.selectbox("نوع المحفظة", ["استثمار", "مضاربة"])
        date_t = st.date_input("تاريخ الشراء", date.today())
        
        if st.form_submit_button("حفظ", type="primary"):
            if sym and qty > 0:
                n, s = get_static_info(sym)
                # الحالة الافتراضية Open
                execute_query("INSERT INTO Trades (symbol, company_name, sector, date, quantity, entry_price, strategy, status, current_price) VALUES (?,?,?,?,?,?,?,?,?)", 
                    (sym, n, s, str(date_t), qty, price, strat.strip(), 'Open', price))
                st.success("تم الحفظ بنجاح"); st.cache_data.clear()
            else: st.error("الرجاء إدخال الرمز والكمية بشكل صحيح")

def view_settings():
    st.header("⚙️ الإعدادات")
    with st.expander("النسخ الاحتياطي", expanded=True):
        if st.button("نسخ الآن"): create_smart_backup(); st.success("تم إنشاء نسخة احتياطية")
        bk = BACKUP_DIR / "backup_latest.xlsx"
        if bk.exists():
            with open(bk, "rb") as f: st.download_button("تحميل ملف Excel", f, "backup.xlsx")
    with st.expander("استيراد بيانات سابقة"):
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
                            if 'strategy' in df.columns and t == 'Trades':
                                df['strategy'] = df['strategy'].astype(str).str.strip()
                            df.to_sql(t, conn, if_exists='append', index=False)
                    conn.commit()
                st.success("تم الاستيراد بنجاح"); st.cache_data.clear()
            except Exception as e: st.error(f"خطأ: {str(e)}")

def router():
    render_navbar()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    
    # التوجيه الصحيح
    if pg == 'home': view_dashboard(fin)
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg) # هنا نرسل المفتاح spec أو invest
    elif pg == 'cash': view_liquidity()
    elif pg == 'analysis': view_advanced_chart(fin)
    elif pg == 'add': view_add_trade()
    elif pg == 'settings': view_settings()
    elif pg == 'update':
        with st.spinner("جاري تحديث الأسعار من السوق..."): update_prices()
        st.session_state.page = 'home'; st.rerun()
