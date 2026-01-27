# --- 3. Portfolio View (معدلة بالتصميم الجديد) ---
def view_portfolio(fin, key):
    ts = "مضاربة" if key == 'spec' else "استثمار"
    st.header(f"💼 محفظة {ts}")
    
    # 1. CSS مستوحى من تصميم finance-table الذي طلبته
    st.markdown("""
        <style>
        /* حاوية الجدول كاملة */
        .finance-container {
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(0,0,0,0.03);
            background-color: white;
            margin-bottom: 25px;
        }
        
        /* رأس الجدول */
        .finance-header {
            background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
            padding: 15px 10px;
            border-bottom: 2px solid #e5e7eb;
            font-weight: 800;
            color: #1e293b; /* Primary Dark */
            font-size: 0.95rem;
            display: flex;
            align-items: center;
        }
        
        /* صفوف البيانات */
        .finance-row {
            padding: 12px 10px;
            border-bottom: 1px solid #f1f5f9;
            transition: all 0.2s ease;
            background-color: white;
            color: #334155;
            display: flex;
            align-items: center;
            font-size: 0.95rem;
        }
        
        /* تأثير التمرير (Hover) */
        .finance-row:hover {
            background-color: #f0f9ff !important;
        }
        
        /* تنسيق الأرقام والألوان */
        .val-success { color: #10b981; font-weight: bold; }
        .val-danger { color: #ef4444; font-weight: bold; }
        .val-neutral { color: #64748b; }
        
        /* تنسيق حالة الصفقة (Badge) */
        .status-badge {
            background-color: #E3FCEF;
            color: #006644;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: bold;
        }
        
        /* ضبط المحاذاة داخل الأعمدة */
        div[data-testid="stVerticalBlock"] > div > div[data-testid="stHorizontalBlock"] {
            align-items: center;
        }
        </style>
    """, unsafe_allow_html=True)
    
    df = fin['all_trades']
    if df.empty: sub = pd.DataFrame()
    else: sub = df[df['strategy'].astype(str).str.contains(ts, na=False)].copy()
    
    op = sub[sub['status'] == 'Open'].copy()
    cl = sub[sub['status'] == 'Close'].copy()
    
    t1, t2 = st.tabs(["الصفقات القائمة", "الأرشيف"])
    
    with t1:
        # الملخص (KPIs) - كما هو
        total_cost = op['total_cost'].sum() if not op.empty else 0
        total_market = op['market_value'].sum() if not op.empty else 0
        total_gain = op['gain'].sum() if not op.empty else 0
        total_pct = (total_gain / total_cost * 100) if total_cost != 0 else 0.0
        
        k1, k2, k3, k4 = st.columns(4)
        with k1: render_kpi("التكلفة", safe_fmt(total_cost), "neutral", "💰")
        with k2: render_kpi("السوق", safe_fmt(total_market), "blue", "📊")
        with k3: render_kpi("الربح", safe_fmt(total_gain), "success" if total_gain >= 0 else "danger", "📈")
        with k4: render_kpi("النسبة", f"{total_pct:.2f}%", "success" if total_pct >= 0 else "danger", "٪")
        
        st.markdown("---")
        
        # شريط الأدوات والفرز
        c_add, c_sort = st.columns([1, 3])
        with c_add:
            if st.button("➕ إضافة / شراء", type="primary", use_container_width=True):
                st.session_state.page = 'add'; st.rerun()
        
        if not op.empty:
            from market_data import fetch_batch_data
            from data_source import get_company_details
            
            # تحضير البيانات
            live_data = fetch_batch_data(op['symbol'].unique().tolist())
            op['sector'] = op['symbol'].apply(lambda x: get_company_details(x)[1])
            op['prev_close'] = op['symbol'].apply(lambda x: live_data.get(x, {}).get('prev_close', 0))
            op['day_change'] = ((op['current_price'] - op['prev_close']) / op['prev_close'] * 100).fillna(0)
            op['weight'] = (op['market_value'] / total_market * 100).fillna(0)

            # منطق الفرز
            with c_sort:
                sort_options = {
                    "الربح والخسارة": "gain", "القيمة السوقية": "market_value",
                    "نسبة الربح %": "gain_pct", "التغير اليومي": "day_change",
                    "تاريخ الشراء": "date", "الاسم": "company_name"
                }
                sort_sel = st.selectbox("فرز حسب:", list(sort_options.keys()), label_visibility="collapsed")
                sort_col = sort_options[sort_sel]
                ascending = True if sort_col in ["company_name", "date"] else False
                op = op.sort_values(by=sort_col, ascending=ascending)

            # === بناء الجدول بتصميم Finance Table ===
            
            # 1. بداية حاوية الجدول
            st.markdown('<div class="finance-container">', unsafe_allow_html=True)
            
            # 2. رأس الجدول (Header)
            st.markdown('<div class="finance-header">', unsafe_allow_html=True)
            h1, h2, h3, h4, h5, h6, h7 = st.columns([2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.5])
            h1.markdown("الشركة / الرمز")
            h2.markdown("الكمية")
            h3.markdown("التكلفة")
            h4.markdown("آخر سعر (يومي)")
            h5.markdown("القيمة (الوزن)")
            h6.markdown("الربح الصافي")
            h7.markdown("إجراءات")
            st.markdown('</div>', unsafe_allow_html=True) # إغلاق الرأس

            # 3. صفوف البيانات (Rows)
            for idx, row in op.iterrows():
                # حاوية الصف مع كلاس finance-row
                with st.container():
                    st.markdown('<div class="finance-row">', unsafe_allow_html=True)
                    c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.5])
                    
                    name, _ = get_company_details(row['symbol'])
                    
                    # العمود 1: الاسم والرمز والحالة
                    with c1: 
                        st.markdown(f"**{name}** <span class='status-badge'>مفتوحة</span><br><span style='color:#64748b; font-size:0.8em'>{row['symbol']}</span>", unsafe_allow_html=True)
                    
                    # العمود 2: الكمية
                    with c2: st.markdown(f"**{row['quantity']:,.0f}**")
                    
                    # العمود 3: التكلفة
                    with c3: st.markdown(f"{row['entry_price']:,.2f}")
                    
                    # العمود 4: السعر والتغير اليومي
                    with c4: 
                        dc = row['day_change']
                        clr_dc = "#10b981" if dc >= 0 else "#ef4444"
                        st.markdown(f"**{row['current_price']:,.2f}**<br><span style='color:{clr_dc}; direction:ltr; font-size:0.85em'>{dc:+.2f}%</span>", unsafe_allow_html=True)
                        
                    # العمود 5: القيمة والوزن
                    with c5: 
                        st.markdown(f"**{row['market_value']:,.0f}**<br><span style='color:#64748b; font-size:0.8em'>{row['weight']:.1f}%</span>", unsafe_allow_html=True)
                        
                    # العمود 6: الربح
                    with c6:
                        color_cls = "val-success" if row['gain'] >= 0 else "val-danger"
                        st.markdown(f"<span class='{color_cls}'>{row['gain']:+,.0f}</span><br><span class='{color_cls}' style='font-size:0.85em'>{row['gain_pct']:.1f}%</span>", unsafe_allow_html=True)
                    
                    # العمود 7: الأزرار التفاعلية (حافظنا عليها)
                    with c7:
                        b_col1, b_col2 = st.columns(2)
                        with b_col1:
                            pop_buy = st.popover("➕", help="شراء")
                            with pop_buy:
                                st.markdown(f"**شراء: {name}**")
                                with st.form(f"buy_{row['symbol']}_{idx}"):
                                    q = st.number_input("الكمية", 1); p = st.number_input("السعر", value=float(row['current_price']))
                                    d = st.date_input("التاريخ", date.today())
                                    if st.form_submit_button("شراء"):
                                        at = "Sukuk" if "Sukuk" in str(row.get('asset_type','')) else "Stock"
                                        execute_query("INSERT INTO Trades (symbol, asset_type, date, quantity, entry_price, strategy, status) VALUES (%s,%s,%s,%s,%s,%s,'Open')", (row['symbol'], at, str(d), q, p, ts))
                                        st.success("تم"); st.rerun()
                        with b_col2:
                            pop_sell = st.popover("➖", help="بيع")
                            with pop_sell:
                                st.markdown(f"**بيع: {name}**")
                                with st.form(f"sell_{row['symbol']}_{idx}"):
                                    st.caption(f"الكمية: {row['quantity']}")
                                    p = st.number_input("سعر البيع", value=float(row['current_price']))
                                    d = st.date_input("تاريخ", date.today())
                                    if st.form_submit_button("بيع"):
                                        execute_query("UPDATE Trades SET status='Close', exit_price=%s, exit_date=%s WHERE symbol=%s AND strategy=%s AND status='Open'", (p, str(d), row['symbol'], ts))
                                        st.success("تم"); st.rerun()
                    
                    st.markdown('</div>', unsafe_allow_html=True) # إغلاق div الصف
            
            st.markdown('</div>', unsafe_allow_html=True) # إغلاق حاوية الجدول
        else:
            st.info("لا توجد صفقات قائمة")

    with t2:
        if not cl.empty:
            render_custom_table(cl, [('company_name', 'الشركة', 'text'), ('symbol', 'الرمز', 'text'), ('gain', 'الربح', 'colorful'), ('gain_pct', '%', 'percent'), ('exit_date', 'تاريخ البيع', 'date')])
        else:
            st.info("الأرشيف فارغ")
