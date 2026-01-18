import streamlit as st
import pandas as pd
from datetime import date
from analytics import calculate_portfolio_metrics, update_prices, create_smart_backup
from components import render_kpi, render_table, render_navbar
from charts import view_advanced_chart
from market_data import get_static_info, get_tasi_data
from database import execute_query, fetch_table, get_db
from config import BACKUP_DIR

def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    
    # مؤشر السوق
    clr = "#10B981" if t_change >= 0 else "#EF4444"
    st.markdown(f"""
    <div style="margin-bottom:20px; padding:15px; border-radius:12px; background:rgba(255,255,255,0.5); border:1px solid #eee;">
        <span style="font-size:1.1rem; font-weight:bold;">المؤشر العام (TASI):</span> 
        <span style="font-size:1.3rem; font-weight:900; margin-right:10px;">{t_price:,.2f}</span>
        <span style="color:{clr}; direction:ltr; font-weight:bold; margin-right:10px;">({t_change:+.2f}%)</span>
    </div>
    """, unsafe_allow_html=True)
    
    # البطاقات الرئيسية
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi("صافي الأصول (Equity)", f"{fin['equity']:,.2f}", "blue")
    with c2: render_kpi("الكاش المتوفر", f"{fin['cash']:,.2f}")
    with c3: render_kpi("الربح العائم (Open P&L)", f"{fin['unrealized_pl']:+,.2f}", fin['unrealized_pl'])
    with c4: render_kpi("الربح المحقق (Realized)", f"{fin['realized_pl']:+,.2f}", fin['realized_pl'])
    
    st.markdown("---")
    
    # ملخص التوزيعات
    st.info(f"💰 الدخل السنوي المتوقع من التوزيعات: **{fin.get('projected_income', 0):,.2f}** ريال")

def view_portfolio(fin, strategy):
    st.header(f"💼 محفظة {strategy}")
    
    # تصفية البيانات حسب الاستراتيجية
    strat_filter = "مضاربة" if strategy=="مضاربة" else "استثمار"
    df = fin['all_trades'][fin['all_trades']['strategy'] == strat_filter]
    
    if not df.empty:
        # ترتيب حسب التاريخ الأحدث
        df = df.sort_values(by='date', ascending=False)
        
        # تعريف الأعمدة بدقة - هنا كانت المشكلة سابقاً
        cols = [
            ('symbol', 'الرمز'), 
            ('company_name', 'الشركة'), 
            ('quantity', 'الكمية'), 
            ('entry_price', 'ت.الشراء'), 
            ('current_price', 'السعر'), # سواء كان سعر سوق أو سعر بيع
            ('gain', 'الربح'), 
            ('gain_pct', '%'), 
            ('daily_change', 'يومي %'),
            ('weight', 'الوزن'),
            ('status', 'الحالة'),
            ('date', 'التاريخ')
        ]
        render_table(df, cols)
    else: 
        st.warning(f"لا توجد صفقات مسجلة في محفظة {strategy}")

def view_liquidity():
    st.header("💵 سجلات السيولة")
    fin = calculate_portfolio_metrics() # إعادة حساب لضمان دقة البيانات
    
    tab1, tab2, tab3 = st.tabs(["الإيداعات", "السحوبات", "العوائد"])
    
    with tab1:
        st.markdown(f"**الإجمالي:** {fin['total_deposited']:,.2f}")
        render_table(fin['deposits'], [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظات')])
        
    with tab2:
        st.markdown(f"**الإجمالي:** {fin['total_withdrawn']:,.2f}")
        render_table(fin['withdrawals'], [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظات')])
        
    with tab3:
        st.markdown(f"**الإجمالي:** {fin['total_returns']:,.2f}")
        render_table(fin['returns'], [('date', 'التاريخ'), ('symbol', 'الرمز'), ('company_name', 'الشركة'), ('amount', 'المبلغ')])

def view_add_trade():
    st.header("📝 تسجيل عملية جديدة")
    
    with st.form("add_trade_form"):
        c1, c2 = st.columns(2)
        sym = c1.text_input("رمز السهم (مثال: 1120)")
        qty = c2.number_input("الكمية", min_value=1.0, step=1.0)
        
        c3, c4 = st.columns(2)
        price = c3.number_input("سعر الشراء", min_value=0.0, step=0.01)
        strat = c4.selectbox("نوع المحفظة", ["استثمار", "مضاربة"])
        
        date_t = st.date_input("تاريخ الشراء", date.today())
        
        if st.form_submit_button("حفظ العملية", type="primary"):
            if sym and qty > 0 and price > 0:
                n, s = get_static_info(sym)
                execute_query(
                    "INSERT INTO Trades (symbol, company_name, sector, date, quantity, entry_price, strategy, status, current_price) VALUES (?,?,?,?,?,?,?,?,?)", 
                    (sym, n, s, str(date_t), qty, price, strat, 'Open', price)
                )
                st.success("تمت الإضافة بنجاح")
                st.cache_data.clear()
            else: st.error("الرجاء التأكد من إدخال الرمز والكمية والسعر")
            
    st.markdown("---")
    # إضافة سريعة للإيداع/السحب
    with st.expander("تسجيل حركة نقدية (إيداع/سحب)"):
        op_type = st.radio("العملية", ["إيداع", "سحب"], horizontal=True)
        amount = st.number_input("المبلغ", min_value=0.0)
        note = st.text_input("ملاحظات")
        if st.button("تسجيل النقد"):
            tbl = "Deposits" if op_type == "إيداع" else "Withdrawals"
            execute_query(f"INSERT INTO {tbl} (date, amount, note) VALUES (?,?,?)", (str(date.today()), amount, note))
            st.success("تم التسجيل")
            st.cache_data.clear()

def view_settings():
    st.header("⚙️ الإعدادات")
    
    with st.expander("النسخ الاحتياطي واستعادة البيانات", expanded=True):
        c1, c2 = st.columns(2)
        if c1.button("إنشاء نسخة احتياطية الآن", use_container_width=True): 
            create_smart_backup()
            st.success("تم إنشاء النسخة في مجلد backups")
            
        bk_file = BACKUP_DIR / "backup_latest.xlsx"
        if bk_file.exists():
            with open(bk_file, "rb") as f:
                c2.download_button("📥 تحميل ملف البيانات (Excel)", f, file_name="osouli_backup.xlsx", use_container_width=True)
    
    # قسم الاستيراد - مهم لاستعادة البيانات القديمة
    with st.expander("استيراد بيانات من Excel"):
        up_file = st.file_uploader("ملف النسخة الاحتياطية", type=['xlsx'])
        if up_file and st.button("بدء الاستيراد"):
            try:
                xl = pd.ExcelFile(up_file)
                with get_db() as conn:
                    # تنظيف الجداول
                    for t in ['Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants']:
                        conn.execute(f"DELETE FROM {t}")
                        if t in xl.sheet_names:
                            df = pd.read_excel(xl, t)
                            if 'id' in df.columns: df = df.drop(columns=['id'])
                            # معالجة اختلاف الأسماء
                            if 'source' in df.columns: df.rename(columns={'source':'note'}, inplace=True)
                            if 'reason' in df.columns: df.rename(columns={'reason':'note'}, inplace=True)
                            df.to_sql(t, conn, if_exists='append', index=False)
                    conn.commit()
                st.success("تم استيراد البيانات! الرجاء تحديث الصفحة.")
                st.cache_data.clear()
            except Exception as e: st.error(f"خطأ: {e}")

def router():
    render_navbar()
    pg = st.session_state.page
    
    # حساب البيانات مرة واحدة وتمريرها للصفحات
    fin = calculate_portfolio_metrics()
    
    if pg == 'home': view_dashboard(fin)
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'cash': view_liquidity() # إضافة صفحة السيولة
    elif pg == 'analysis': view_advanced_chart(fin)
    elif pg == 'add': view_add_trade()
    elif pg == 'settings': view_settings()
    elif pg == 'update':
        with st.spinner("جاري جلب الأسعار من السوق..."):
            update_prices()
        st.session_state.page = 'home'
        st.rerun()
