import pandas as pd
import numpy as np
from database import fetch_table, execute_query
from market_data import fetch_batch_data
import streamlit as st

@st.cache_data(ttl=60)
def calculate_portfolio_metrics():
    # الهيكل الافتراضي
    default_res = {
        "cost_open": 0.0, "market_val_open": 0.0, "cash": 0.0, 
        "unrealized_pl": 0.0, "realized_pl": 0.0, 
        "total_deposited": 0.0, "total_withdrawn": 0.0, "total_returns": 0.0,
        "deposits": pd.DataFrame(), "withdrawals": pd.DataFrame(),
        "returns": pd.DataFrame(), "all_trades": pd.DataFrame()
    }

    try:
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")

        # تنظيف البيانات المالية
        for df in [dep, wit, ret]:
            if 'amount' not in df.columns: df['amount'] = 0.0
            else: df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0)

        total_dep = dep['amount'].sum()
        total_wit = wit['amount'].sum()
        total_ret = ret['amount'].sum()

        if trades.empty:
            default_res.update({
                "total_deposited": total_dep, "total_withdrawn": total_wit, 
                "total_returns": total_ret, "cash": (total_dep + total_ret) - total_wit,
                "deposits": dep, "withdrawals": wit, "returns": ret
            })
            return default_res

        # معالجة الصفقات
        cols_needed = ['quantity', 'entry_price', 'exit_price', 'current_price']
        for c in cols_needed:
            trades[c] = pd.to_numeric(trades[c], errors='coerce').fillna(0.0)
            
        if 'status' not in trades.columns: trades['status'] = 'Open'
        
        # تحديد حالة الصفقة (مغلقة/مفتوحة)
        is_closed = (trades['exit_price'] > 0) | (trades['status'].astype(str).str.lower().isin(['close', 'sold', 'مغلقة']))
        trades['status'] = np.where(is_closed, 'Close', 'Open')
        
        # السعر الحالي للمغلقة هو سعر البيع
        trades.loc[is_closed, 'current_price'] = trades['exit_price']

        # الحسابات
        trades['total_cost'] = trades['quantity'] * trades['entry_price']
        trades['market_value'] = trades['quantity'] * trades['current_price']
        trades['gain'] = trades['market_value'] - trades['total_cost']
        
        mask_cost = trades['total_cost'] != 0
        trades['gain_pct'] = 0.0
        trades.loc[mask_cost, 'gain_pct'] = (trades.loc[mask_cost, 'gain'] / trades.loc[mask_cost, 'total_cost']) * 100

        # المجاميع
        open_trades = trades[trades['status'] == 'Open']
        closed_trades = trades[trades['status'] == 'Close']

        cost_open = open_trades['total_cost'].sum()
        market_val_open = open_trades['market_value'].sum()
        
        # الربح المحقق = (قيمة البيع - تكلفة الشراء) للصفقات المغلقة
        realized_pl = closed_trades['market_value'].sum() - closed_trades['total_cost'].sum()
        
        # الكاش = (إيداع + عوائد + مبيعات) - (سحب + مشتريات)
        total_sales = closed_trades['market_value'].sum()
        total_purchases = trades['total_cost'].sum() # كل الشراء (مفتوح ومغلق)
        
        cash_simple = (total_dep + total_ret - total_wit) + total_sales - total_purchases

        return {
            "cost_open": cost_open, 
            "market_val_open": market_val_open,
            "unrealized_pl": market_val_open - cost_open,
            "realized_pl": realized_pl,
            "cash": cash_simple,
            "total_deposited": total_dep, 
            "total_withdrawn": total_wit, 
            "total_returns": total_ret,
            "all_trades": trades, 
            "deposits": dep, 
            "withdrawals": wit, 
            "returns": ret
        }
    except Exception as e:
        print(f"Error in analytics: {e}")
        return default_res

# analytics.py

def update_prices():
    """تحديث أسعار السوق للأسهم المفتوحة"""
    try:
        df = fetch_table("Trades")
        if df.empty: return False
        
        # الرموز المفتوحة فقط
        open_symbols = df[df['status'] == 'Open']['symbol'].unique().tolist()
        if not open_symbols: return True
        
        # جلب الأسعار
        live_data = fetch_batch_data(open_symbols)
        
        count = 0
        for sym, data in live_data.items():
            # ---------------------------------------------------------
            # 🛠️ التعديل هنا: استخدام float() لتحويل رقم numpy
            # ---------------------------------------------------------
            raw_price = data.get('price', 0)
            price = float(raw_price) 
            
            if price > 0:
                # تحديث السعر في قاعدة البيانات
                query = "UPDATE Trades SET current_price = %s WHERE symbol = %s AND status = 'Open'"
                execute_query(query, (price, sym))
                count += 1
        return True
    except Exception as e: 
        print(f"Update Error: {e}") # طباعة الخطأ للمتابعة
        return False
def create_smart_backup(): pass # يمكن تنفيذها لاحقاً

def generate_equity_curve(df):
    if df.empty: return pd.DataFrame()
    # ترتيب حسب التاريخ وحساب التراكمي
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df['cumulative_invested'] = df['total_cost'].cumsum()
    return df

def calculate_historical_drawdown(df): return pd.DataFrame()
