import pandas as pd
import numpy as np
from database import fetch_table, execute_query
from market_data import fetch_batch_data
import streamlit as st

@st.cache_data(ttl=60)
def calculate_portfolio_metrics():
    default_res = {
        "cost_open": 0.0,
        "market_val_open": 0.0,
        "cash": 0.0,
        "unrealized_pl": 0.0,
        "realized_pl": 0.0,
        "total_deposited": 0.0,
        "total_withdrawn": 0.0,
        "total_returns": 0.0,
        "deposits": pd.DataFrame(),
        "withdrawals": pd.DataFrame(),
        "returns": pd.DataFrame(),
        "all_trades": pd.DataFrame()
    }
    
    try:
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")
        
        # تحويل المبالغ المالية بأمان
        for df in [dep, wit, ret]:
            if 'amount' not in df.columns:
                df['amount'] = 0.0
            else:
                df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0)
                
        total_dep = dep['amount'].sum()
        total_wit = wit['amount'].sum()
        total_ret = ret['amount'].sum()
        
        if trades.empty:
            default_res.update({
                "total_deposited": total_dep,
                "total_withdrawn": total_wit,
                "total_returns": total_ret,
                "cash": (total_dep + total_ret) - total_wit,
                "deposits": dep,
                "withdrawals": wit,
                "returns": ret
            })
            return default_res

        cols_needed = ['quantity', 'entry_price', 'exit_price', 'current_price']
        for c in cols_needed:
            trades[c] = pd.to_numeric(trades[c], errors='coerce').fillna(0.0)

        # ---------------------------------------------------------
        # 🔧 التصحيح هنا: التعامل مع الصفقة المغلقة بصفر
        # ---------------------------------------------------------
        if 'status' not in trades.columns:
            trades['status'] = 'Open'
            
        # التأكد من وجود عمود التاريخ لتجنب الأخطاء
        if 'exit_date' not in trades.columns:
            trades['exit_date'] = None

        # الصفقة مغلقة إذا: (سعر البيع > 0) أو (الحالة نصياً Close) أو (يوجد تاريخ خروج)
        has_exit_date = trades['exit_date'].notna() & (trades['exit_date'].astype(str) != 'None') & (trades['exit_date'].astype(str) != '')
        
        is_closed = (
            (trades['exit_price'] > 0) | 
            (trades['status'].astype(str).str.lower().isin(['close', 'sold', 'مغلقة'])) |
            has_exit_date  # ✅ تمت إضافة هذا الشرط ليقبل البيع بصفر طالما يوجد تاريخ
        )
        
        trades['status'] = np.where(is_closed, 'Close', 'Open')
        # ---------------------------------------------------------

        # في حال الإغلاق، السعر الحالي هو سعر الخروج
        trades.loc[is_closed, 'current_price'] = trades['exit_price']
        
        trades['total_cost'] = trades['quantity'] * trades['entry_price']
        trades['market_value'] = trades['quantity'] * trades['current_price']
        trades['gain'] = trades['market_value'] - trades['total_cost']
        
        mask = trades['total_cost'] != 0
        trades['gain_pct'] = 0.0
        trades.loc[mask, 'gain_pct'] = (trades.loc[mask, 'gain'] / trades.loc[mask, 'total_cost']) * 100
        
        open_trades = trades[trades['status'] == 'Open']
        closed_trades = trades[trades['status'] == 'Close']
        
        cost_open = open_trades['total_cost'].sum()
        market_val_open = open_trades['market_value'].sum()
        
        # الربح المحقق = قيمة البيع - التكلفة
        realized_pl = closed_trades['market_value'].sum() - closed_trades['total_cost'].sum()
        
        total_sales = closed_trades['market_value'].sum()
        total_purchases = trades['total_cost'].sum()
        
        # معادلة الكاش فلو
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
        st.error(f"خطأ في التحليل: {e}")
        return default_res

def update_prices():
    try:
        df = fetch_table("Trades")
        if df.empty: return False
        
        # نأخذ فقط المفتوحة حسب الداتا بيس لتحديث أسعارها
        # نعتمد هنا على الحالة المسجلة لتجنب تحديث صفقة مغلقة بصفر
        open_symbols = df[df['status'] == 'Open']['symbol'].unique().tolist()
        
        if not open_symbols: return True
        
        live_data = fetch_batch_data(open_symbols)
        
        for sym, data in live_data.items():
            price = float(data.get('price', 0))
            if price > 0:
                execute_query(
                    "UPDATE Trades SET current_price = %s WHERE symbol = %s AND status = 'Open'",
                    (price, sym)
                )
        return True
    except Exception as e:
        st.error(f"فشل التحديث: {e}")
        return False

def generate_equity_curve(df):
    if df.empty: return pd.DataFrame()
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df['cumulative_invested'] = df['total_cost'].cumsum()
    return df

def create_smart_backup():
    pass

def calculate_historical_drawdown(df):
    return pd.DataFrame()
