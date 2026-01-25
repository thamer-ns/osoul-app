import streamlit as st
import pandas as pd
import plotly.express as px
from market_data import fetch_batch_data
from database import fetch_table

def render_pulse_dashboard():
    st.markdown("## 💓 نبض السوق (Market Pulse)")
    
    # 1. جلب جميع الرموز (من المحفظة + قائمة المراقبة)
    trades = fetch_table("Trades")
    watchlist = fetch_table("Watchlist")
    
    symbols = set()
    if not trades.empty:
        # نأخذ الرموز المفتوحة فقط
        active_symbols = trades[trades['status'] == 'Open']['symbol'].unique().tolist()
        symbols.update(active_symbols)
    
    if not watchlist.empty:
        wl_symbols = watchlist['symbol'].unique().tolist()
        symbols.update(wl_symbols)
        
    if not symbols:
        st.warning("لا توجد أسهم لعرضها. أضف أسهم للمحفظة أو قائمة المراقبة.")
        return

    # 2. جلب الأسعار اللحظية (Google Finance)
    with st.spinner("جاري جس نبض السوق..."):
        # نستخدم الدالة التي برمجناها سابقاً في market_data
        market_data = fetch_batch_data(list(symbols))

    # 3. تجهيز البيانات للعرض
    pulse_data = []
    for sym, data in market_data.items():
        # محاولة معرفة اسم الشركة
        name = sym
        if not trades.empty:
            name_row = trades[trades['symbol'] == sym]
            if not name_row.empty:
                name = name_row.iloc[0]['company_name']
        
        # حساب التغير (بما أن جوجل أحياناً لا يعطي التغير، سنحسبه بناءً على الإغلاق السابق التقريبي)
        # أو نعتمد على اللون فقط
        price = data.get('price', 0)
        
        # تصنيف الحالة
        status = "Unknown"
        color = "grey"
        # هنا يمكنك إضافة منطقك الخاص (مثلاً مقارنة بسعر شرائك)
        
        pulse_data.append({
            'الرمز': sym,
            'الشركة': name,
            'السعر': price,
        })

    if not pulse_data:
        st.error("فشل الاتصال بمصدر الأسعار.")
        return

    df = pd.DataFrame(pulse_data)

    # 4. عرض لوحة "بطاقات" الأسعار (Ticker Grid)
    st.markdown("### 📺 شاشة الأسعار اللحظية")
    
    # تقسيم الشاشة إلى أعمدة (Cards)
    cols = st.columns(4)
    for i, row in df.iterrows():
        col = cols[i % 4]
        with col:
            # تصميم بطاقة السعر
            price_val = row['السعر']
            
            # محاولة جلب متوسط التكلفة من المحفظة لمقارنته
            avg_cost = 0
            if not trades.empty:
                my_trade = trades[(trades['symbol'] == row['الرمز']) & (trades['status'] == 'Open')]
                if not my_trade.empty:
                    # حساب متوسط التكلفة المرجح
                    total_qty = my_trade['quantity'].sum()
                    total_cost = my_trade['total_cost'].sum()
                    if total_qty > 0:
                        avg_cost = total_cost / total_qty

            delta_color = "off"
            delta_val = None
            
            if avg_cost > 0:
                diff = price_val - avg_cost
                pct = (diff / avg_cost) * 100
                delta_val = f"{pct:.2f}%"
                delta_color = "normal" # أخضر للربح، أحمر للخسارة تلقائياً من ستريم ليت
            
            st.metric(
                label=f"{row['الشركة']} ({row['الرمز']})",
                value=f"{price_val:.2f}",
                delta=delta_val,
                delta_color=delta_color
            )

    st.markdown("---")

    # 5. أدوات التحليل السريع (مستوحاة من برامج التداول)
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown("### 🧮 حاسبة نقاط الارتكاز (Pivot Points)")
        # أداة مهمة للمضاربين
        with st.form("pivot_calc"):
            p_high = st.number_input("القمة (High)", min_value=0.0)
            p_low = st.number_input("القاع (Low)", min_value=0.0)
            p_close = st.number_input("الإغلاق (Close)", min_value=0.0)
            if st.form_submit_button("احسب المستويات"):
                pp = (p_high + p_low + p_close) / 3
                r1 = (2 * pp) - p_low
                s1 = (2 * pp) - p_high
                r2 = pp + (p_high - p_low)
                s2 = pp - (p_high - p_low)
                
                st.success(f"الارتكاز (PP): {pp:.2f}")
                col_r, col_s = st.columns(2)
                col_r.warning(f"مقاومة 1: {r1:.2f}\n\nمقاومة 2: {r2:.2f}")
                col_s.error(f"دعم 1: {s1:.2f}\n\nدعم 2: {s2:.2f}")

    with c2:
        st.markdown("### ⚖️ حاسبة إدارة المخاطر")
        # أداة لتحديد الكمية المناسبة
        with st.form("risk_calc"):
            capital = st.number_input("رأس المال للمحفظة", value=100000.0)
            risk_pct = st.number_input("نسبة المخاطرة بالصفقة %", value=1.0)
            entry = st.number_input("سعر الدخول", min_value=0.0)
            stop_loss = st.number_input("سعر وقف الخسارة", min_value=0.0)
            
            if st.form_submit_button("احسب الكمية"):
                if entry > stop_loss and entry > 0:
                    risk_amount = capital * (risk_pct / 100)
                    risk_per_share = entry - stop_loss
                    shares = risk_amount / risk_per_share
                    position_size = shares * entry
                    
                    st.info(f"المبلغ المعرض للخطر: {risk_amount:.2f}")
                    st.success(f"عدد الأسهم المقترح: {int(shares)}")
                    st.warning(f"قيمة الصفقة الإجمالية: {position_size:.2f}")
                else:
                    st.error("سعر الوقف يجب أن يكون أقل من الدخول (للشراء)")
