import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from analytics import calculate_portfolio_metrics, update_prices, create_smart_backup, get_comprehensive_performance, get_rebalancing_advice, get_dividends_calendar, generate_equity_curve
from components import render_kpi, render_table, render_navbar
from charts import view_advanced_chart
from market_data import get_static_info, get_tasi_data
from database import execute_query, fetch_table, get_db
from config import BACKUP_DIR

def apply_sorting(df, cols_definition, key_suffix):
    if df.empty: return df
    
    with st.expander("أدوات الفرز والترتيب", expanded=False):
        label_to_col = {label: col for col, label in cols_definition}
        sort_options = list(label_to_col.keys())
        
        c1, c2 = st.columns([2, 1])
        with c1:
            selected_label = st.selectbox(
                "فرز حسب العمود:", 
                sort_options, 
                index=0, 
                key=f"sort_col_{key_suffix}"
            )
        with c2:
            sort_order = st.radio(
                "اتجاه الترتيب:", 
                ["تنازلي", "تصاعدي"], 
                horizontal=True, 
                key=f"sort_ord_{key_suffix}"
            )
    
    target_col = label_to_col[selected_label]
    is_ascending = (sort_order == "تصاعدي")
    
    try:
        return df.sort_values(by=target_col, ascending=is_ascending)
    except:
        return df

def view_dashboard(fin):
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

    st.markdown("### الملخص المالي")
    c1, c2, c3, c4 = st.columns(4)
    net_deposit = fin['total_deposited'] - fin['total_withdrawn']
    
    with c1: render_kpi("الكاش المتوفر", f"{fin['cash']:,.2f}", help_text="النقد المتاح حالياً في المحفظة للشراء")
    with c2: render_kpi("رأس المال (الصافي)", f"{net_deposit:,.2f}", help_text="إجمالي الإيداعات - إجمالي السحوبات")
    with c3: render_kpi("القيمة السوقية", f"{fin['market_val_open']:,.2f}", "blue", help_text="قيمة الأسهم الحالية في السوق")
    total_pl = fin['unrealized_pl'] + fin['realized_pl'] + fin['total_returns']
    with c4: render_kpi("صافي الربح/الخسارة", f"{total_pl:,.2f}", total_pl, help_text="الأرباح المحققة + العائمة + التوزيعات")
    
    # --- الجديد: منحنى النمو ---
    st.markdown("---")
    st.markdown("### 📈 منحنى نمو الاستثمار")
    curve_df = generate_equity_curve(fin['all_trades'])
    if not curve_df.empty:
        fig = px.line(curve_df, x='date', y='cumulative_invested', title='تطور حجم الاستثمار (التكلفة التراكمية)', markers=True)
        fig.update_layout(font=dict(family="Cairo"), yaxis_title="القيمة (SAR)", xaxis_title="التاريخ")
        st.plotly_chart(fig, use_container_width=True)

def view_portfolio(fin, page_key):
    if page_key == 'spec':
        target_strategy = "مضاربة"
        page_title = "محفظة المضاربة"
    else:
        target_strategy = "استثمار"
        page_title = "محفظة الاستثمار"

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

    tab1, tab2, tab3 = st.tabs([f"الصفقات القائمة ({len(df_open)})", "التحليل و إعادة التوازن", f"الصفقات المغلقة ({len(df_closed)})"])

    with tab1:
        if not df_open.empty:
            st.markdown("#### ملخص توزيع القطاعات")
            sector_summary = df_open.groupby('sector').agg({
                'symbol': 'count',
                'total_cost': 'sum',
                'market_value': 'sum'
            }).reset_index()
            
            total_mv = sector_summary['market_value'].sum()
            sector_summary['current_weight'] = (sector_summary['market_value'] / total_mv * 100).fillna(0)
            
            targets_df = fetch_table("SectorTargets")
            if not targets_df.empty:
                sector_summary = pd.merge(sector_summary, targets_df, on='sector', how='left')
                sector_summary['target_percentage'] = sector_summary['target_percentage'].fillna(0.0)
            else:
                sector_summary['target_percentage'] = 0.0

            target_amount = total_mv * (sector_summary['target_percentage'] / 100)
            sector_summary['remaining'] = target_amount - sector_summary['market_value']

            cols_sector = [
                ('sector', 'القطاع'),
                ('symbol', 'عدد الشركات'),
                ('total_cost', 'التكلفة'),
                ('current_weight', 'الوزن الحالي'),
                ('target_percentage', 'الوزن المستهدف'),
                ('remaining', 'المتبقي للهدف')
            ]
            
            sorted_sectors = apply_sorting(sector_summary, cols_sector, f"{page_key}_sec")
            render_table(sorted_sectors, cols_sector)
            
            st.markdown("---")
            st.markdown("#### تفاصيل الصفقات")
            
            total_val = df_open['market_value'].sum()
            df_open['local_weight'] = (df_open['market_value'] / total_val * 100) if total_val > 0 else 0
            
            cols_open = [
                ('company_name', 'الشركة'),
                ('symbol', 'الرمز'),
                ('sector', 'القطاع'),
                ('status', 'الحالة'),
                ('quantity', 'الكمية'),
                ('entry_price', 'شراء'),
                ('total_cost', 'التكلفة'),
                ('current_price', 'سعر السوق'),
                ('market_value', 'القيمة'),
                ('gain', 'الربح/الخسارة'),
                ('gain_pct', 'النسبة %'),
                ('local_weight', 'الوزن'),
                ('daily_change', 'تغيير يومي'),
                ('date', 'التاريخ'),
            ]
            
            sorted_open = apply_sorting(df_open, cols_open, f"{page_key}_open")
            render_table(sorted_open, cols_open)
        else:
            st.info("المحفظة فارغة حالياً.")
    
    with tab2:
        # --- التحليل الشامل ---
        st.markdown("### التحليل المالي الشامل")
        sec_perf, stock_perf = get_comprehensive_performance(df_strategy, fin['returns'])
        
        if not sec_perf.empty:
            st.markdown("**أداء القطاعات (الربح + العوائد)**")
            cols_sec_perf = [
                ('sector', 'القطاع'),
                ('total_cost', 'حجم الاستثمار'),
                ('gain', 'أرباح رأسمالية'),
                ('total_dividends', 'توزيعات نقدية'),
                ('net_profit', 'الربح الصافي'),
                ('roi_pct', 'العائد الكلي %')
            ]
            render_table(sec_perf.sort_values(by='net_profit', ascending=False), cols_sec_perf)
        
        st.markdown("---")
        
        # --- إعادة التوازن الذكي ---
        st.markdown("### ⚖️ مقترح إعادة التوازن")
        targets_df = fetch_table("SectorTargets")
        if not targets_df.empty and not df_open.empty:
            total_mv_strat = df_open['market_value'].sum()
            advice = get_rebalancing_advice(df_open, targets_df, total_mv_strat)
            
            if not advice.empty:
                st.info(f"لضبط المحفظة لتطابق الأوزان المستهدفة بناءً على القيمة الحالية ({total_mv_strat:,.2f})، يقترح النظام التالي:")
                cols_advice = [
                    ('sector', 'القطاع'),
                    ('target_percentage', 'الهدف %'),
                    ('action', 'الإجراء المقترح'),
                    ('suggested_amount', 'القيمة التقديرية (ريال)')
                ]
                render_table(advice, cols_advice)
            else:
                st.success("🎉 محفظتك متوازنة تماماً مع أهدافك!")
        else:
            st.warning("الرجاء تحديد الأوزان المستهدفة في الإعدادات أولاً.")

    with tab3:
        if not df_closed.empty:
            st.markdown("### سجل الصفقات المغلقة")
            cols_closed = [
                ('company_name', 'الشركة'), ('symbol', 'الرمز'), 
                ('sector', 'القطاع'), ('status', 'الحالة'),
                ('quantity', 'الكمية'), ('entry_price', 'شراء'), ('exit_price', 'بيع'),
                ('market_value', 'قيمة البيع'), ('gain', 'الربح المحقق'), ('gain_pct', 'العائد %'),
                ('exit_date', 'تاريخ البيع')
            ]
            
            sorted_closed = apply_sorting(df_closed, cols_closed, f"{page_key}_closed")
            render_table(sorted_closed, cols_closed)
        else:
            st.info("لا توجد صفقات مغلقة.")

def view_liquidity():
    fin = calculate_portfolio_metrics()
    
    c1, c2, c3 = st.columns(3)
    with c1: render_kpi("إجمالي الإيداعات", f"{fin['total_deposited']:,.2f}", "blue")
    with c2: render_kpi("إجمالي السحوبات", f"{fin['total_withdrawn']:,.2f}", -1)
    with c3: render_kpi("إجمالي العوائد", f"{fin['total_returns']:,.2f}", "success")
    
    st.markdown("---")
    
    # --- الجديد: تقويم التوزيعات ---
    st.markdown("### 📅 تقويم التوزيعات النقدية")
    div_cal = get_dividends_calendar(fin['returns'])
    if not div_cal.empty:
        st.dataframe(div_cal, use_container_width=True)
    else:
        st.info("لا توجد توزيعات مسجلة لعرض التقويم.")
        
    st.markdown("---")
    
    cols_dep = [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظات')]
    cols_wit = [('date', 'التاريخ'), ('amount', 'المبلغ'), ('note', 'ملاحظات')]
    cols_ret = [('date', 'التاريخ'), ('symbol', 'الرمز'), ('company_name', 'الشركة'), ('amount', 'المبلغ')]

    t1, t2, t3 = st.tabs(["الإيداعات", "السحوبات", "العوائد"])
    
    with t1: 
        sorted_dep = apply_sorting(fin['deposits'], cols_dep, "liq_dep")
        render_table(sorted_dep, cols_dep)
        
    with t2: 
        sorted_wit = apply_sorting(fin['withdrawals'], cols_wit, "liq_wit")
        render_table(sorted_wit, cols_wit)
        
    with t3: 
        sorted_ret = apply_sorting(fin['returns'], cols_ret, "liq_ret")
        render_table(sorted_ret, cols_ret)

def view_add_trade():
    st.header("إضافة صفقة جديدة")
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
                st.success("تم الحفظ"); st.cache_data.clear()

def view_settings():
    st.header("إعدادات النظام")
    
    st.markdown("### توزيع القطاعات المستهدف")
    st.info("قم بإدخال النسبة المئوية المستهدفة لكل قطاع. المجموع يجب أن يكون 100%.")
    
    trades_df = fetch_table("Trades")
    existing_sectors = trades_df['sector'].unique().tolist() if not trades_df.empty else []
    
    current_targets = fetch_table("SectorTargets")
    
    data_for_edit = []
    
    all_known_sectors = set(existing_sectors)
    if not current_targets.empty:
        all_known_sectors.update(current_targets['sector'].tolist())
    
    for sec in all_known_sectors:
        if not sec: continue
        val = 0.0
        if not current_targets.empty:
            row = current_targets[current_targets['sector'] == sec]
            if not row.empty:
                val = float(row.iloc[0]['target_percentage'])
        data_for_edit.append({'القطاع': sec, 'الوزن المستهدف %': val})
    
    if not data_for_edit:
        data_for_edit = [{'القطاع': 'مثال: البنوك', 'الوزن المستهدف %': 0.0}]

    df_edit = pd.DataFrame(data_for_edit)
    
    edited_df = st.data_editor(
        df_edit, 
        num_rows="dynamic", 
        use_container_width=True,
        column_config={
            "القطاع": st.column_config.TextColumn("اسم القطاع", required=True),
            "الوزن المستهدف %": st.column_config.NumberColumn("النسبة المستهدفة %", min_value=0, max_value=100, step=0.5, format="%.1f%%")
        },
        key="target_editor"
    )

    total_target = edited_df['الوزن المستهدف %'].sum()
    remaining = 100.0 - total_target
    
    col_sum, col_msg = st.columns([1, 2])
    
    if total_target > 100:
        col_sum.metric("المجموع الكلي", f"{total_target:.1f}%", delta=f"{remaining:.1f}% (تجاوز)", delta_color="inverse")
        col_msg.error("⚠️ المجموع تجاوز 100%! لا يمكن الحفظ حتى تقوم بتعديل النسب.")
        btn_disabled = True
    elif total_target < 100:
        col_sum.metric("المجموع الكلي", f"{total_target:.1f}%", delta=f"{remaining:.1f}% متبقي")
        col_msg.warning("المجموع أقل من 100%. يمكنك الحفظ، لكن يفضل توزيع النسبة كاملة.")
        btn_disabled = False
    else:
        col_sum.metric("المجموع الكلي", f"{total_target:.1f}%", delta="مكتمل 100%")
        col_msg.success("توزيع مثالي!")
        btn_disabled = False

    if st.button("حفظ الأوزان المستهدفة", disabled=btn_disabled, type="primary"):
        with get_db() as conn:
            conn.execute("DELETE FROM SectorTargets")
            for _, row in edited_df.iterrows():
                sec = str(row['القطاع']).strip()
                target = float(row['الوزن المستهدف %'])
                if sec and sec != 'مثال: البنوك':
                    conn.execute("INSERT INTO SectorTargets (sector, target_percentage) VALUES (?, ?)", (sec, target))
            conn.commit()
        st.success("تم حفظ توزيع القطاعات بنجاح!")
        st.cache_data.clear()

    st.markdown("---")

    with st.expander("النسخ الاحتياطي والاستعادة"):
        if st.button("إنشاء نسخة احتياطية"): create_smart_backup(); st.success("تم")
        p = BACKUP_DIR / "backup_latest.xlsx"
        if p.exists():
            with open(p, "rb") as f: st.download_button("تحميل ملف النسخة", f, "backup.xlsx")
            
    with st.expander("استيراد بيانات سابقة"):
        f = st.file_uploader("ملف Excel", type="xlsx")
        if f and st.button("بدء الاستيراد"):
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
                st.success("تم الاستيراد بنجاح"); st.cache_data.clear()
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
