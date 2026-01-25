# استبدل دالة view_portfolio القديمة بهذه الجديدة
def view_portfolio(fin, page_key):
    ts = "مضاربة" if page_key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    all_d = fin['all_trades']
    df = pd.DataFrame()
    if not all_d.empty:
        df = all_d[all_d['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    # حساب الإجماليات
    if not df.empty:
        total_market = df[df['status']=='Open']['market_value'].sum()
        df['weight'] = df.apply(lambda x: (x['market_value'] / total_market * 100) if x['status']=='Open' and total_market > 0 else 0, axis=1)
        df['daily_change'] = df.apply(lambda x: ((x['current_price'] - x['prev_close']) / x['prev_close'] * 100) if pd.notna(x['prev_close']) and x['prev_close'] > 0 else 0, axis=1)

    COLS_FULL = [
        ('company_name', 'اسم الشركة'), ('sector', 'القطاع'), ('status', 'الحالة'),
        ('symbol', 'رمز الشركة'), ('date', 'تاريخ الشراء'), ('exit_date', 'تاريخ البيع'),
        ('quantity', 'الكمية'), ('entry_price', 'سعر الشراء'), ('total_cost', 'التكلفة'),
        ('year_high', 'اعلى سنوي'), ('current_price', 'السعر الحالي'), ('year_low', 'ادنى سنوي'),
        ('market_value', 'سعر السوق'), ('gain', 'الربح والخسارة'), ('gain_pct', 'نسبة الربح والخسارة'),
        ('weight', 'وزن السهم'), ('daily_change', 'نسبة التغير اليومي'), ('prev_close', 'اغلاق الامس')
    ]

    # عرض البطاقات العلوية
    if not df.empty:
        op = df[df['status']=='Open'].copy()
        market_val = op['quantity'].mul(op['current_price']).sum() if not op.empty else 0
        total_cost = op['quantity'].mul(op['entry_price']).sum() if not op.empty else 0
        unrealized = market_val - total_cost
        cl = df[df['status']=='Close'].copy()
        realized_profit = ((cl['exit_price'] - cl['entry_price']) * cl['quantity']).sum() if not cl.empty else 0

        c1, c2, c3, c4 = st.columns(4)
        with c1: render_kpi("القيمة السوقية", safe_fmt(market_val), "blue")
        with c2: render_kpi("التكلفة", safe_fmt(total_cost))
        with c3: render_kpi("الربح العائم", safe_fmt(unrealized), unrealized)
        with c4: render_kpi("الربح المحقق", safe_fmt(realized_profit), realized_profit)
        st.markdown("---")

    if df.empty: st.info("المحفظة فارغة"); return

    open_df = df[df['status']=='Open'].copy()
    closed_df = df[df['status']=='Close'].copy()

    t1, t2, t3 = st.tabs(["الأسهم الحالية", "تحليل الأداء", "الأرشيف"])
    
    # --- التبويب الأول: الأسهم الحالية (تم حذف الفرز والبيع) ---
    with t1:
        if not open_df.empty:
            # ترتيب تلقائي بالأحدث فقط
            open_df = open_df.sort_values(by="date", ascending=False)
            render_table(open_df, COLS_FULL)
        else: st.info("لا توجد أسهم حالية")
    
    # --- التبويب الثاني: تحليل ---
    with t2:
        if not open_df.empty and page_key == 'invest':
            fig = px.pie(open_df, values='market_value', names='sector', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            
    # --- التبويب الثالث: الأرشيف ---
    with t3:
        if not closed_df.empty: 
            closed_df['net_sales'] = closed_df['quantity'] * closed_df['exit_price']
            closed_df['realized_gain'] = closed_df['net_sales'] - closed_df['total_cost']
            c1, c2 = st.columns(2)
            with c1: render_kpi("صافي البيع", safe_fmt(closed_df['net_sales'].sum()), "blue")
            with c2: render_kpi("الربح المحقق", safe_fmt(closed_df['realized_gain'].sum()))
            render_table(closed_df, COLS_FULL)
        else: st.info("الأرشيف فارغ")
