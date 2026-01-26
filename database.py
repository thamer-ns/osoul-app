def fetch_table(table_name):
    # القوائم الافتراضية
    SCHEMAS = {
        'Trades': ['id', 'symbol', 'company_name', 'sector', 'asset_type', 'date', 'quantity', 'entry_price', 'exit_price', 'current_price', 'strategy', 'status'],
        'Deposits': ['id', 'date', 'amount', 'note'],
        'Withdrawals': ['id', 'date', 'amount', 'note'],
        'ReturnsGrants': ['id', 'date', 'symbol', 'company_name', 'amount', 'note']
    }
    
    with get_db() as conn:
        if conn:
            try:
                # محاولة قراءة البيانات
                df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
                df.columns = df.columns.str.lower()
                
                # إصلاح الأعمدة المفقودة
                if table_name == 'Trades' and 'asset_type' not in df.columns: 
                    df['asset_type'] = 'Stock'
                
                return df
                
            except Exception as e:
                # === هنا التغيير المهم: إظهار الخطأ ===
                st.error(f"خطأ في جلب جدول {table_name}: {e}")
                # طباعة الخطأ في التيرمينال أيضاً
                print(f"DB ERROR ({table_name}): {e}")
                
        else:
            st.error("لا يوجد اتصال بقاعدة البيانات!")

    # إرجاع جدول فارغ مهيكل حتى لا ينهار البرنامج بالكامل
    return pd.DataFrame(columns=[c.lower() for c in SCHEMAS.get(table_name, [])])
