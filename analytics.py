import pandas as pd
import numpy as np
import shutil
from database import fetch_table, get_db, execute_query
from market_data import get_static_info, fetch_batch_data
from config import BACKUP_DIR, SECTOR_TARGETS
import streamlit as st

def calculate_portfolio_metrics():
    # 1. جلب البيانات الخام
    trades = fetch_table("Trades")
    dep = fetch_table("Deposits")
    wit = fetch_table("Withdrawals")
    ret = fetch_table("ReturnsGrants")

    # 2. معالجة الصفقات (القلب النابض للبيانات)
    if not trades.empty:
        # توحيد صيغة التاريخ
        trades['date'] = pd.to_datetime(trades['date'], errors='coerce')
        
        # التأكد من أن جميع الأعمدة الرقمية موجودة ولها قيم
        cols_to_fix = ['quantity', 'entry_price', 'exit_price', 'current_price', 'prev_close', 'dividend_yield']
        for col in cols_to_fix:
            if col not in trades.columns: trades[col] = 0.0
            trades[col] = pd.to_numeric(trades[col], errors='coerce').fillna(0.0)

        # حساب التكلفة
        trades['total_cost'] = trades['quantity'] * trades['entry_price']
        
        # تحديد الحالة بدقة
        trades['status'] = trades['status'].astype(str).str.strip()
        is_closed = trades['status'].str.lower().isin(['close', 'sold', 'مغلقة', 'مباعة'])
        
        # منطق السعر الحالي: إذا مغلقة نستخدم سعر البيع، إذا مفتوحة نستخدم سعر السوق
        trades.loc[is_closed, 'current_price'] = trades.loc[is_closed, 'exit_price']
        
        # حساب القيمة السوقية
        trades['market_value'] = trades['quantity'] * trades['current_price']
        
        # حساب الأرباح
        trades['gain'] = trades['market_value'] - trades['total_cost']
        trades['gain_pct'] = (trades['gain'] / trades['total_cost'].replace(0, 1)) * 100
        
        # حساب التغير اليومي (فقط للصفقات المفتوحة)
        trades['daily_change'] = ((trades['current_price'] - trades['prev_close']) / trades['prev_close'].replace(0, 1)) * 100
        trades.loc[is_closed, 'daily_change'] = 0.0
        
        # تعبئة البيانات المفقودة (الاسم والقطاع) من القاموس الثابت
        for idx, row in trades.iterrows():
            sym = str(row['symbol'])
            n, s = get_static_info(sym)
            # نملأ البيانات فقط إذا كانت فارغة في قاعدة البيانات
            if pd.isna(row['company_name']) or str(row['company_name']).strip() == "":
                trades.at[idx, 'company_name'] = n
            if pd.isna(row['sector']) or str(row['sector']).strip() == "":
                trades.at[idx, 'sector'] = s

        # حساب الوزن النسبي للصفقات المفتوحة
        total_open_val = trades.loc[~is_closed, 'market_value'].sum()
        trades['weight'] = 0.0
        if total_open_val > 0:
            trades.loc[~is_closed, 'weight'] = (trades.loc[~is_closed, 'market_value'] / total_open_val) * 100

    # 3. تجميع المبالغ المالية
    total_dep = dep['amount'].sum() if not dep.empty else 0
    total_wit = wit['amount'].sum() if not wit.empty else 0
    total_ret = ret['amount'].sum() if not ret.empty else 0
    
    # 4. فصل المحفظة
    open_trades = trades[~trades['status'].str.lower().isin(['close', 'مغلقة'])] if not trades.empty else pd.DataFrame()
    closed_trades = trades[trades['status'].str.lower().isin(['close', 'مغلقة'])] if not trades.empty else pd.DataFrame()
    
    # 5. التجميع النهائي
    vals = {
        "cost_open": open_trades['total_cost'].sum() if not open_trades.empty else 0,
        "market_val_open": open_trades['market_value'].sum() if not open_trades.empty else 0,
        "cost_closed": closed_trades['total_cost'].sum() if not closed_trades.empty else 0,
        "sales_closed": closed_trades['market_value'].sum() if not closed_trades.empty else 0,
        "total_deposited": total_dep,
        "total_withdrawn": total_wit,
        "total_returns": total_ret,
        "all_trades": trades, "deposits": dep, "withdrawals": wit, "returns": ret
    }
    
    vals['unrealized_pl'] = vals['market_val_open'] - vals['cost_open']
    vals['realized_pl'] = vals['sales_closed'] - vals['cost_closed']
    
    # معادلة الكاش الدقيقة: (إيداع - سحب + عوائد + مبيعات) - (شراء مفتوح + شراء مغلق)
    vals['cash'] = (total_dep - total_wit + total_ret + vals['sales_closed']) - (vals['cost_open'] + vals['cost_closed'])
    vals['equity'] = vals['cash'] + vals['market_val_open']
    
    # الدخل المتوقع
    vals['projected_income'] = 0.0
    if not open_trades.empty and 'dividend_yield' in open_trades.columns:
        vals['projected_income'] = (open_trades['market_value'] * open_trades['dividend_yield']).sum()
    
    return vals

def update_prices():
    try:
        trades = fetch_table("Trades")
        wl = fetch_table("Watchlist")
        if trades.empty and wl.empty: return False
        
        # نجمع الرموز من الصفقات المفتوحة ومن قائمة المتابعة
        symbols = list(set(trades[trades['status'] != 'Close']['symbol'].tolist() + wl['symbol'].tolist()))
        
        data = fetch_batch_data(symbols)
        if not data: return False
        
        with get_db() as conn:
            for s, d in data.items():
                if d['price'] > 0:
                    conn.execute("""UPDATE Trades SET 
                        current_price=?, prev_close=?, year_high=?, year_low=?, dividend_yield=? 
                        WHERE symbol=? AND status != 'Close'""", 
                        (d['price'], d['prev_close'], d['year_high'], d['year_low'], d['dividend_yield'], s))
            conn.commit()
        create_smart_backup()
        st.cache_data.clear()
        return True
    except: return False

def create_smart_backup():
    try:
        latest = BACKUP_DIR / "backup_latest.xlsx"
        if latest.exists(): shutil.copy(latest, BACKUP_DIR / "backup_previous.xlsx")
        with pd.ExcelWriter(latest, engine='xlsxwriter') as writer:
            for t in ['Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants', 'Watchlist', 'Users']:
                df = fetch_table(t)
                # حفظ التواريخ كنص لمنع مشاكل الاكسل
                for col in df.columns:
                    if 'date' in col: df[col] = df[col].astype(str)
                df.to_excel(writer, sheet_name=t, index=False)
        return True
    except: return False

def calculate_rsi(data, window=14):
    if 'Close' not in data.columns: return None
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))
