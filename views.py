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
    # 1. قسم المؤشر العام (استعادة التصميم الجميل)
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    
    C = st.session_state.custom_colors
    arrow = "🔼" if t_change >= 0 else "🔽"
    color = "#10B981" if t_change >= 0 else "#EF4444"
    
    # HTML مخصص للمؤشر ليكون بارزاً
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
    
    # 2. تقسيم البطاقات (أربعة أعمدة كما كان)
    st.markdown("#### 📊 الملخص المالي")
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi("صافي الأصول (Equity)", f"{fin['equity']:,.2f}", "blue")
    with c2: render_kpi("النقد المتوفر (Cash)", f"{fin['cash']:,.2f}")
    with c3: render_kpi("الربح العائم (Open P&L)", f"{fin['unrealized_pl']:+,.2f}", fin['unrealized_pl'])
    with c4: render_kpi("الربح المحقق (Realized)", f"{fin['realized_pl']:+,.2f}", fin['realized_pl'])
    
    st.markdown("---")

    # 3. تفاصيل مصدر الأموال (استعادة الأيقونات والترتيب)
    col_funds, col_perf = st.columns(2)
    
    with col_funds:
        st.markdown("##### 🏦 حركة الأموال")
        cf1, cf2 = st.columns(2)
        with cf1: render_kpi("إجمالي الإيداعات", f"{fin['total_deposited']:,.2f}")
        with cf2: render_kpi("إجمالي السحوبات", f"{fin['total_withdrawn']:,.2f}")
        
        st.info(f"صافي المستثمر من الجيب: **{(fin['total_deposited'] - fin['total_withdrawn']):,.2f}** ريال")

    with col_perf:
        st.markdown("##### 📈 الأداء والصفقات")
        cp1, cp2 = st.columns(2)
        with cp1: render_kpi("قيمة الأسهم الحالية", f"{fin['market_val_open']:,.2f}")
        with cp2: render_kpi("التوزيعات المقبوضة", f"{fin['total_returns']:,.2f}", "blue")
        
        st.success(f"الدخل السنوي المتوقع (توزيعات): **{fin['projected_income']:,.2f}** ريال")

def view_portfolio(fin, strategy):
    st.header(f"💼 محفظة {strategy}")
    
    # [هام] التأكد من الفلترة الصحيحة للنص (إزالة المسافات)
    strat_key = "مضاربة" if strategy=="مضاربة" else "استثمار"
    
    # الفلترة بدقة
    df = fin['all_trades'][fin['all_trades']['strategy'].astype(str).str.strip() == strat_key]
    
    if not df.empty:
        # ترتيب
        df = df.sort_values(by='date', ascending=False)
        
        # عرض البيانات بالأعمدة الصحيحة
        cols = [
            ('symbol', 'الرمز'), 
            ('company_name', 'الشركة'), 
            ('quantity', 'الكمية'), 
            ('entry_price', 'شراء'), 
            ('current_price', 'سوق/بيع'), 
            ('gain', 'الربح'), 
            ('gain_pct', '%'), 
            ('daily_change', 'يومي %'),
            ('weight', 'الوزن'),
            ('status', 'الحالة'),
            ('date', 'التاريخ')
        ]
        
        # عرض إجمالي هذه المحفظة فقط
        total_g = df['gain'].sum()
        total_v = df['market_value'].sum()
        c1, c2 = st.columns(2)
        with c1: st.metric("قيمة المحفظة", f"{total_v:,.2f}")
        with c2: st.metric("إجمالي الربح/الخسارة", f"{total_g:,.2f}", delta=f"{total_g:,.2f}")
        
        render_table(df, cols)
    else: 
        st.info(f"لا توجد صفقات مسجلة تحت تصنيف '{strat_key}'")

# باقي الدوال (view_liquidity, view_add_trade, settings) تبقى كما هي من الكود السابق المصحح
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
                # التأكد من حفظ النوع بدون مسافات
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
