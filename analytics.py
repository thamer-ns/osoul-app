import pandas as pd
import numpy as np
import shutil
from database import fetch_table, get_db
from market_data import get_static_info, fetch_batch_data
from config import BACKUP_DIR
import streamlit as st

def calculate_portfolio_metrics():
    trades = fetch_table("Trades")
    dep = fetch_table("Deposits")
    wit = fetch_table("Withdrawals")
    ret = fetch_table("ReturnsGrants")

    # إنشاء هيكل بيانات فارغ إذا لم توجد صفقات لتجنب الأخطاء
    if trades.empty:
        trades = pd.DataFrame(columns=[
            'symbol', 'strategy', 'status', 'market_value', 'total_cost', 
            'gain', 'sector', 'company_name', 'date', 'exit_date', 
            'quantity', 'entry_price', 'exit_price'
        ])

    if not trades.empty:
        # --- 1. تنظيف البيانات (خطوة حاسمة) ---
        # توحيد النصوص وإزالة المسافات لضمان الفلترة الصحيحة
        if 'strategy' in trades.columns:
            trades['strategy'] = trades['strategy'].astype(str).str.strip()
        
        if 'status' in trades.columns:
            trades['status'] = trades['status'].astype(str).str.strip()
            # توحيد صيغ الإغلاق
            close_keywords = ['close', 'sold', 'مغلقة', 'مباعة']
            # تحديد الصفقات المغلقة بدقة
            trades.loc[trades['status'].str.lower().isin(close_keywords), 'status'] = 'Close'
            # ما عدا ذلك يعتبر مفتوح
            trades.loc[trades['status'] != 'Close', 'status'] = 'Open'

        # معالجة التواريخ
        trades['date'] = pd.to_datetime(trades['date'], errors='coerce')
        if 'exit_date' in trades.columns:
            trades['exit_date'] = pd.to_datetime(trades['exit_date'], errors='coerce')
        
        # تحويل الأرقام (معالجة القيم الفارغة)
        num_cols = ['quantity', 'entry_price', 'exit_price', 'current_price', 'prev_close', 'dividend_yield', 'year_high', 'year_low']
        for c in num_cols:
            if c not in trades.columns: trades[c] = 0.0
            trades[c] = pd.to_numeric(trades[c], errors='coerce').fillna(0.0)

        # --- 2. الحسابات المالية للصفقات ---
        trades['total_cost'] = trades['quantity'] * trades['entry_price']
        
        is_closed = trades['status'] == 'Close'
        
        # في حالة الإغلاق: السعر الحالي هو سعر البيع
        trades.loc[is_closed, 'current_price'] = trades.loc[is_closed, 'exit_price']
        
        trades['market_value'] = trades['quantity'] * trades['current_price']
        trades['gain'] = trades['market_value'] - trades['total_cost']
        
        # تجنب القسمة على صفر في النسب المئوية
        trades['gain_pct'] = (trades['gain'] / trades['total_cost'].replace(0, 1)) * 100
        
        # التغير اليومي (للصفقات المفتوحة فقط)
        trades['daily_change'] = ((trades['current_price'] - trades['prev_close']) / trades['prev_close'].replace(0, 1)) * 100
        trades.loc[is_closed, 'daily_change'] = 0.0
        
        # إكمال الأسماء والقطاعات الناقصة
        for idx, row in trades.iterrows():
            n, s = get_static_info(row['symbol'])
            if pd.isna(row['company_name']) or str(row['company_name']).strip() == "":
                trades.at[idx, 'company_name'] = n
            if pd.isna(row['sector']) or str(row['sector']).strip() == "":
                trades.at[idx, 'sector'] = s

    # --- 3. التجميعات النهائية للمحفظة ---
    total_dep = dep['amount'].sum() if not dep.empty else 0.0
    total_wit = wit['amount'].sum() if not wit.empty else 0.0
    total_ret = ret['amount'].sum() if not ret.empty else 0.0
    
    # فصل البيانات
    open_trades = trades[trades['status'] == 'Open'] if not trades.empty else pd.DataFrame()
    closed_trades = trades[trades['status'] == 'Close'] if not trades.empty else pd.DataFrame()
    
    # حساب المجاميع
    cost_open = open_trades['total_cost'].sum() if not open_trades.empty else 0.0
    cost_closed = closed_trades['total_cost'].sum() if not closed_trades.empty else 0.0
    
    sales_closed = closed_trades['market_value'].sum() if not closed_trades.empty else 0.0
    market_val_open = open_trades['market_value'].sum() if not open_trades.empty else 0.0

    # --- 4. معادلة الكاش المصححة ---
    # النقد المتوفر = (كل ما دخل المحفظة) - (كل ما خرج منها)
    # الداخل: إيداعات + عوائد + مبيعات الصفقات المغلقة
    # الخارج: سحوبات + شراء صفقات (سواء كانت مفتوحة الآن أو أغلقت لاحقاً)
    total_in = total_dep + total_ret + sales_closed
    total_out = total_wit + cost_open + cost_closed
    
    cash_available = total_in - total_out

    vals = {
        "cost_open": cost_open,
        "market_val_open": market_val_open,
        "cost_closed": cost_closed,
        "sales_closed": sales_closed,
        "total_deposited": total_dep,
        "total_withdrawn": total_wit,
        "total_returns": total_ret,
        "cash": cash_available,
        "all_trades": trades, "deposits": dep, "withdrawals": wit, "returns": ret
    }
    
    vals['unrealized_pl'] = vals['market_val_open'] - vals['cost_open']
    vals['realized_pl'] = vals['sales_closed'] - vals['cost_closed']
    vals['equity'] = vals['cash'] + vals['market_val_open']
    
    return vals

def update_prices():
    try:
        trades = fetch_table("Trades")
        wl = fetch_table("Watchlist")
        if trades.empty and wl.empty: return False
        
        # تحديث الأسعار فقط للصفقات المفتوحة وقائمة المتابعة
        symbols = list(set(trades[trades['status'] != 'Close']['symbol'].tolist() + wl['symbol'].tolist()))
        data = fetch_batch_data(symbols)
        if not data: return False
        
        with get_db() as conn:
            for s, d in data.items():
                if d['price'] > 0:
                    conn.execute("UPDATE Trades SET current_price=?, prev_close=?, year_high=?, year_low=?, dividend_yield=? WHERE symbol=?", 
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
                # تحويل التواريخ لنصوص لضمان التوافق مع إكسل
                for c in df.columns:
                    if 'date' in c: df[c] = df[c].astype(str)
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
