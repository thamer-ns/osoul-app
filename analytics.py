import pandas as pd
import numpy as np
from database import fetch_table, execute_query
from market_data import fetch_batch_data
import streamlit as st

# نسبة العمولة
COMMISSION_RATE = 0.00155 

@st.cache_data(ttl=60)
def calculate_portfolio_metrics():
    # الهيكل الافتراضي الآمن
    default_res = {
        "cost_open": 0.0, "market_val_open": 0.0, "cash": 0.0, 
        "unrealized_pl": 0.0, "realized_pl": 0.0, 
        "total_deposited": 0.0, "total_withdrawn": 0.0, "total_returns": 0.0,
        "deposits": pd.DataFrame(columns=['date', 'amount', 'note']),
        "withdrawals": pd.DataFrame(columns=['date', 'amount', 'note']),
        "returns": pd.DataFrame(columns=['date', 'amount', 'symbol', 'note']),
        "all_trades": pd.DataFrame()
    }

    try:
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")

        # 1. تنظيف بيانات السيولة (ضمان وجود amount)
        for df in [dep, wit, ret]:
            if 'amount' not in df.columns:
                df['amount'] = 0.0
            else:
                df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0)

        # 2. حسابات السيولة
        total_dep = dep['amount'].sum()
        total_wit = wit['amount'].sum()
        total_ret = ret['amount'].sum()

        # 3. معالجة الصفقات
        if trades.empty:
            default_res.update({
                "total_deposited": total_dep, "total_withdrawn": total_wit, "total_returns": total_ret,
                "cash": (total_dep + total_ret) - total_wit,
                "deposits": dep, "withdrawals": wit, "returns": ret
            })
            return default_res

        # التأكد من الأعمدة
        req_cols = ['quantity', 'entry_price', 'exit_price', 'current_price', 'status', 'asset_type']
        for c in req_cols:
            if c not in trades.columns:
                trades[c] = 0.0 if c != 'status' and c != 'asset_type' else ('Open' if c=='status' else 'Stock')

        # تحويل الأرقام
        for c in ['quantity', 'entry_price', 'exit_price', 'current_price']:
            trades[c] = pd.to_numeric(trades[c], errors='coerce').fillna(0.0)

        # منطق الحالة
        condition_closed = (trades['exit_price'] > 0) | (trades['status'].astype(str).str.lower().isin(['close', 'sold', 'مغلقة', 'مباعة']))
        trades['status'] = np.where(condition_closed, 'Close', 'Open')

        # الحسابات المالية
        trades['total_cost'] = trades['quantity'] * trades['entry_price']
        
        # للمغلق: السعر الحالي = سعر البيع
        trades.loc[trades['status'] == 'Close', 'current_price'] = trades['exit_price']
        
        trades['market_value'] = trades['quantity'] * trades['current_price']
        trades['gain'] = trades['market_value'] - trades['total_cost']

        # فصل المفتوح والمغلق
        open_trades = trades[trades['status'] == 'Open']
        closed_trades = trades[trades['status'] == 'Close']

        cost_open = open_trades['total_cost'].sum()
        market_val_open = open_trades['market_value'].sum()
        
        sales_closed = closed_trades['market_value'].sum()
        cost_closed = closed_trades['total_cost'].sum()
        realized_pl = sales_closed - cost_closed

        # حساب الكاش الدقيق
        # الكاش = (إيداع + عوائد + مبيعات الأسهم) - (سحوبات + تكلفة شراء الأسهم الكلية)
        total_buy_cost = trades['total_cost'].sum()
        cash = (total_dep + total_ret + sales_closed) - (total_wit + total_buy_cost)

        return {
            "cost_open": cost_open,
            "market_val_open": market_val_open,
            "unrealized_pl": market_val_open - cost_open,
            "realized_pl": realized_pl,
            "cash": cash,
            "total_deposited": total_dep,
            "total_withdrawn": total_wit,
            "total_returns": total_ret,
            "all_trades": trades,
            "deposits": dep,
            "withdrawals": wit,
            "returns": ret
        }

    except Exception as e:
        print(f"Error: {e}")
        return default_res

def update_prices():
    try:
        trades = fetch_table("Trades")
        wl = fetch_table("Watchlist")
        syms = set()
        if not trades.empty: syms.update(trades.loc[trades['status']!='Close', 'symbol'].dropna().unique())
        if not wl.empty: syms.update(wl['symbol'].dropna().unique())
        
        if not syms: return False
        data = fetch_batch_data(list(syms))
        
        from database import get_db
        with get_db() as conn:
            with conn.cursor() as cur:
                for s, d in data.items():
                    if d['price'] > 0:
                        cur.execute("UPDATE Trades SET current_price=%s, prev_close=%s WHERE symbol=%s AND status!='Close'", 
                                    (d['price'], d['prev_close'], s))
                conn.commit()
        st.cache_data.clear()
        return True
    except: return False

def create_smart_backup(): return True
def generate_equity_curve(df): return pd.DataFrame()
def run_backtest(df, s, c): return None
