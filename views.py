import streamlit as st
import pandas as pd
from datetime import date
from analytics import calculate_portfolio_metrics, update_prices, create_smart_backup
from components import render_kpi, render_table, render_navbar
from charts import view_advanced_chart
from market_data import get_static_info, get_tasi_data
from database import execute_query, fetch_table
from config import BACKUP_DIR

def view_dashboard(fin):
    try: t_price, t_change = get_tasi_data()
    except: t_price, t_change = 0, 0
    
    st.markdown(f"### 📊 مؤشر السوق: {t_price:,.2f} ({t_change:+.2f}%)")
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi("صافي الأصول (Equity)", f"{fin['equity']:,.2f}", "blue")
    with c2: render_kpi("الكاش المتوفر", f"{fin['cash']:,.2f}")
    with c3: render_kpi("الربح العائم", f"{fin['unrealized_pl']:+,.2f}", fin['unrealized_pl'])
    with c4: render_kpi("الربح المحقق", f"{fin['realized_pl']:+,.2f}", fin['realized_pl'])
    
    st.markdown("---")
    st.subheader("توزيع الأصول")
    if not fin['all_trades'].empty:
        open_t = fin['all_trades'][fin['all_trades']['status']!='Close']
        if not open_t.empty:
            data = open_t.groupby('sector')['market_value'].sum().reset_index()
            st.bar_chart(data, x='sector', y='market_value')

def view_portfolio(fin, strategy):
    st.header(f"محفظة {strategy}")
    df = fin['all_trades'][fin['all_trades']['strategy'] == ("مضاربة" if strategy=="مضاربة" else "استثمار")]
    
    if not df.empty:
        cols = [('symbol', 'الرمز'), ('company_name', 'الشركة'), ('quantity', 'الكمية'), ('entry_price', 'ت.الشراء'), 
                ('current_price', 'السعر الحالي'), ('gain', 'الربح'), ('gain_pct', '%'), ('status', 'الحالة')]
        render_table(df, cols)
    else: st.info("المحفظة فارغة")

def view_add_trade():
    st.header("إضافة عملية جديدة")
    with st.form("add_t"):
        c1, c2 = st.columns(2)
        sym = c1.text_input("الرمز")
        qty = c2.number_input("الكمية", min_value=1.0)
        c3, c4 = st.columns(2)
        price = c3.number_input("السعر", min_value=0.0)
        strat = c4.selectbox("النوع", ["استثمار", "مضاربة"])
        
        if st.form_submit_button("حفظ", type="primary"):
            if sym and qty and price:
                n, s = get_static_info(sym)
                execute_query("INSERT INTO Trades (symbol, company_name, sector, date, quantity, entry_price, strategy, status, current_price) VALUES (?,?,?,?,?,?,?,?,?)", 
                              (sym, n, s, str(date.today()), qty, price, strat, 'Open', price))
                st.success("تم الحفظ")
                st.cache_data.clear()
            else: st.error("البيانات ناقصة")

def view_settings():
    st.header("الإعدادات")
    
    with st.expander("النسخ الاحتياطي", expanded=True):
        if st.button("نسخ الآن"): 
            create_smart_backup()
            st.success("تم")
            
        bk_file = BACKUP_DIR / "backup_latest.xlsx"
        if bk_file.exists():
            with open(bk_file, "rb") as f:
                st.download_button("تحميل Excel", f, file_name="backup.xlsx")
                
    with st.expander("تخصيص الألوان"):
        c = st.color_picker("اللون الرئيسي", st.session_state.custom_colors['primary'])
        if st.button("تطبيق"):
            st.session_state.custom_colors['primary'] = c
            st.rerun()

def router():
    render_navbar()
    pg = st.session_state.page
    fin = calculate_portfolio_metrics()
    
    if pg == 'home': view_dashboard(fin)
    elif pg in ['spec', 'invest']: view_portfolio(fin, pg)
    elif pg == 'analysis': view_advanced_chart(fin)
    elif pg == 'add': view_add_trade()
    elif pg == 'settings': view_settings()
    elif pg == 'update':
        with st.spinner("تحديث الأسعار..."):
            update_prices()
        st.session_state.page = 'home'
        st.rerun()
