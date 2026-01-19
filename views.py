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
            <div style="font-size:1rem; color:#6B7280; margin-bottom:5px;">المؤشر العام (TASI)</div>
            <div style="font-size:2.2rem; font-weight:900; color:#1F2937;">{t_price:,.2f}</div>
        </div>
        <div style="text-align:left;">
            <div style="background:{color}15; color:{color}; padding:8px 20px; border-radius:10px; font-size:1.2rem; font-weight:bold; direction:ltr;">
                {arrow} {t_change:+.2f}%
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # الملخص المالي
    st.markdown("### 🏦 الملخص المالي")
    c1, c2, c3, c4 = st.columns(4)
    net_deposit = fin['total_deposited'] - fin['total_withdrawn']
    with c1: render_kpi("الكاش المتوفر", f"{fin['cash']:,.2f}")
    with c2: render_kpi("رأس المال (الصافي)", f"{net_deposit:,.2f}")
    with c3: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}", "blue")
    total_pl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("صافي الربح/الخسارة", f"{total_pl:,.2f}", total_pl)
    
    # تمت إزالة رسم توزيع القطاعات من هنا بناءً على طلبك

def view_portfolio(fin, page_key):
    if page_key == 'spec':
        target_strategy = "مضاربة"
        page_title = "⚡ محفظة المضاربة"
    else:
        target_strategy = "استثمار"
        page_title = "💎 محفظة الاستثمار"

    st.header(page_title)
    all_trades = fin['all_trades']
    
    if all_trades.empty:
        st.info("لا توجد بيانات.")
        return

    df_strategy = all_trades[all_trades['strategy'] == target_strategy].copy()
    
    if df_strategy.empty:
        st.warning(f"لا توجد أسهم في {target_strategy}.")
        return

    df_open = df_strategy[df_strategy['status'] == 'Open'].copy()
    df_closed = df_strategy[df_strategy['status'] == 'Close'].copy()

    tab1, tab2 = st.tabs([f"الصفقات القائمة ({len(df_open)})", f"الأرشيف ({len(df_closed)})"])

    with tab1:
        if not df_open.empty:
            # ==========================================
            # 1. جدول توزيع القطاعات (الجديد مثل الصورة)
            # ==========================================
            st.markdown("#### 📊 ملخص القطاعات")
            
            # تجميع البيانات حسب القطاع
            sector_summary = df_open.groupby('sector').agg({
                'symbol': 'count',          # عدد الشركات
                'total_cost': 'sum',        # التكلفة
                'market_value': 'sum'       # القيمة السوقية (لحساب الوزن)
            }).reset_index()
            
            # الحسابات
            total_mv = sector_summary['market_value'].sum()
            sector_summary['current_weight'] = (sector_summary['market_value'] / total_mv * 100).fillna(0)
            
            # الوزن المستهدف (قيمة افتراضية 0 لأنها غير موجودة في قاعدة البيانات حالياً)
            sector_summary['target_weight'] = 0.0 
            
            # المتبقي للهدف = (القيمة الاجمالية * الهدف%) - القيمة الحالية للقطاع
            # بما أن الهدف 0، المتبقي سيكون بالسالب (أي أننا تجاوزنا الهدف) وسيظهر بالأحمر
            sector_summary['remaining'] = (total_mv * sector_summary['target_weight'] / 100) - sector_summary['market_value']

            # ترتيب الأعمدة للعرض (مطابق للصورة تماماً)
            # القطاع | عدد الشركات | التكلفة | الوزن الحالي | الوزن المستهدف | المتبقي
            cols_sector = [
                ('sector', 'القطاع'),
                ('symbol', 'عدد الشركات'),
                ('total_cost', 'التكلفة'),
                ('current_weight', 'الوزن الحالي %'),
                ('target_weight', 'الوزن المستهدف %'),
                ('remaining', 'المتبقي للهدف')
            ]
            render_table(sector_summary, cols_sector)
            st.markdown("---")

            # ==========================================
            # 2. جدول تفاصيل الصفقات (القديم)
            # ==========================================
            st.markdown("#### 📋 تفاصيل الصفقات")
            
            total_val = df_open['market_value'].sum()
            df_open['local_weight'] = (df_open['market_value'] / total_val * 100) if total_val > 0 else 0
            
            # ملخص سريع
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("القيمة السوقية", f"{total_val:,.2f}")
            with c2: st.metric("الربح/الخسارة", f"{df_open['gain'].sum():,.2f}")
            with c3: st.metric("عدد الشركات", len(df_open))

            cols_open = [
                ('company_name', 'الشركة'),
                ('symbol', 'الرمز'),
                ('sector', 'القطاع'),
                ('status', 'الحالة'),
                ('quantity', 'الكمية'),
                ('entry_price', 'شراء'),
                ('total_cost', 'التكلفة'),
                ('current_price', 'سعر السوق/البيع'),
                ('market_value', 'القيمة'),
                ('gain', 'الربح/الخسارة'),
                ('gain_pct', 'النسبة %'),
                ('local_weight', 'الوزن'),
                ('daily_change', 'تغيير يومي'),
                ('date', 'التاريخ'),
            ]
            render_table(df_open.sort_values(by='date', ascending=False), cols_open)
        else:
            st.info("المحفظة فارغة حالياً.")

    with tab2:
        if not df_closed.empty:
            st.markdown("### 📜 سجل الصفقات المغلقة")
            cols_closed = [
                ('company_name', 'الشركة'), ('symbol', 'الرمز'), 
                ('sector', 'القطاع'), ('status', 'الحالة'),
                ('quantity', 'الكمية'), ('entry_price', 'شراء'), ('exit_price', 'بيع'),
                ('market_value', 'قيمة البيع'), ('gain', 'الربح المحقق'), ('gain_pct', 'العائد %'),
                ('exit_date', 'تاريخ البيع')
            ]
            render_table(df_closed.sort_values(by='exit_date', ascending=False), cols_closed)
        else:
            st.info("لا توجد صفقات مغلقة.")

def view_liquidity():
    st.header("💵 السيولة النقدية")
    fin = calculate_portfolio_metrics()
    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "العوائد"])
    with t1: render_table(fin['deposits'], [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظات')])
    with t2: render_table(fin['withdrawals'], [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظات')])
    with t3: render_table(fin['returns'], [('date', 'التاريخ'), ('symbol', 'الرمز'), ('company_name', 'الشركة'), ('amount', 'المبلغ')])

def view_add_trade():
    st.header("📝 إضافة صفقة")
    with st.form("add"):
        c1, c2 = st.columns(2)
        sym = c1.text_input("رمز السهم")
        qty = c2.number_input("الكمية", min_value=1.0, step=1.0)
        c3, c4 = st.columns(2)
        price = c3.number_input("سعر الشراء", step=0.01)
        strat = c4.selectbox("المحفظة", ["استثمار", "مضاربة"])
        d = st.date_input("التاريخ", date.today())
        if st.form_submit_button("حفظ", type="primary"):
            if sym and qty:
                n, s = get_static_info(sym)
                execute_query("INSERT INTO Trades (symbol, company_name, sector, date, quantity, entry_price, strategy, status, current_price) VALUES (?,?,?,?,?,?,?,?,?)",
                    (sym, n, s, str(d), qty, price, strat.strip(), 'Open', price))
                st.success("تم"); st.cache_data.clear()

def view_settings():
    st.header("⚙️ الإعدادات")
    with st.expander("النسخ الاحتياطي"):
        if st.button("نسخ"): create_smart_backup(); st.success("تم")
        p = BACKUP_DIR / "backup_latest.xlsx"
        if p.exists():
            with open(p, "rb") as f: st.download_button("تحميل", f, "backup.xlsx")
    with st.expander("استيراد"):
        f = st.file_uploader("ملف Excel", type="xlsx")
        if f and st.button("استيراد"):
            try:
                xl = pd.ExcelFile(f)
                with get_db() as conn:
                    for t in ['Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants']:
                        conn.execute(f"DELETE FROM {t}")
                        if t in xl.sheet_names:
                            df = pd.read_excel(xl, t)
                            if 'strategy' in df.columns: df['strategy'] = df['strategy'].astype(str).str.strip()
                            df.to_sql(t, conn, if_exists='append', index=False)
                    conn.commit()
                st.success("تم الاستيراد"); st.cache_data.clear()
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
        with st.spinner("جاري التحديث..."): update_prices()
        st.session_state.page = 'home'; st.rerun()
