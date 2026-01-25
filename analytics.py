import pandas as pd
import numpy as np
from database import fetch_table
import streamlit as st

@st.cache_data(ttl=60)
def calculate_portfolio_metrics():
    default = {"cash": 0, "market_val_open": 0, "unrealized_pl": 0, "realized_pl": 0, "all_trades": pd.DataFrame()}
    try:
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")

        # تنظيف المبالغ
        for df in [dep, wit, ret]:
            if not df.empty: df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)

        total_in = dep['amount'].sum() if not dep.empty else 0
        total_out = wit['amount'].sum() if not wit.empty else 0
        total_div = ret['amount'].sum() if not ret.empty else 0

        if trades.empty:
            return {**default, "cash": total_in + total_div - total_out, "deposits": dep, "withdrawals": wit, "returns": ret, "total_deposited": total_in, "total_withdrawn": total_out, "total_returns": total_div}

        # حسابات الصفقات
        num_cols = ['quantity', 'entry_price', 'exit_price', 'current_price']
        for c in num_cols: trades[c] = pd.to_numeric(trades[c], errors='coerce').fillna(0)

        # منطق الحالة
        is_closed = (trades['exit_price'] > 0) | (trades['status'].str.lower().isin(['close', 'مغلقة']))
        trades['status'] = np.where(is_closed, 'Close', 'Open')
        trades.loc[is_closed, 'current_price'] = trades['exit_price']

        trades['total_cost'] = trades['quantity'] * trades['entry_price']
        trades['market_value'] = trades['quantity'] * trades['current_price']
        trades['gain'] = trades['market_value'] - trades['total_cost']

        cost_open = trades[trades['status']=='Open']['total_cost'].sum()
        val_open = trades[trades['status']=='Open']['market_value'].sum()
        realized = trades[trades['status']=='Close']['gain'].sum()
        
        # الكاش = (إيداع + عوائد + مبيعات) - (سحب + مشتريات كلية)
        total_sales = trades[trades['status']=='Close']['market_value'].sum()
        total_buys = trades['total_cost'].sum()
        cash = (total_in + total_div + total_sales) - (total_out + total_buys)

        return {
            "cash": cash, "market_val_open": val_open, "unrealized_pl": val_open - cost_open, "realized_pl": realized,
            "total_deposited": total_in, "total_withdrawn": total_out, "total_returns": total_div,
            "all_trades": trades, "deposits": dep, "withdrawals": wit, "returns": ret
        }
    except: return default

def generate_equity_curve(df):
    if df.empty: return pd.DataFrame()
    return df[['date', 'total_cost']].sort_values('date').assign(cumulative_invested=lambda x: x['total_cost'].cumsum())

def run_backtest(df, strat, cap):
    # منطق مختصر للمختبر لضمان الاستقرار
    df = df.copy()
    df['SMA20'] = df['Close'].rolling(20).mean()
    df['Signal'] = np.where(df['Close'] > df['SMA20'], 1, -1)
    df['Portfolio_Value'] = cap * (1 + (df['Close'].pct_change() * df['Signal'].shift(1)).fillna(0).cumsum())
    return {'final_value': df['Portfolio_Value'].iloc[-1], 'return_pct': ((df['Portfolio_Value'].iloc[-1]/cap)-1)*100, 'df': df}
