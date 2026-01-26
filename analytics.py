import pandas as pd
import numpy as np
from database import fetch_table
import streamlit as st

COMMISSION_RATE = 0.00155 

@st.cache_data(ttl=60)
def calculate_portfolio_metrics():
    empty_df = pd.DataFrame(columns=['date', 'amount', 'note'])
    default_res = {
        "cost_open": 0.0, "market_val_open": 0.0, "cash": 0.0, 
        "unrealized_pl": 0.0, "realized_pl": 0.0, 
        "total_deposited": 0.0, "total_withdrawn": 0.0, "total_returns": 0.0,
        "deposits": empty_df.copy(), "withdrawals": empty_df.copy(), 
        "returns": pd.DataFrame(columns=['date', 'amount', 'symbol', 'note']),
        "all_trades": pd.DataFrame()
    }

    try:
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")

        for df in [dep, wit, ret]:
            if 'amount' not in df.columns: df['amount'] = 0.0
            else: df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0)

        total_dep = dep['amount'].sum()
        total_wit = wit['amount'].sum()
        total_ret = ret['amount'].sum()

        if trades.empty:
            default_res.update({
                "total_deposited": total_dep, "total_withdrawn": total_wit, "total_returns": total_ret,
                "cash": (total_dep + total_ret) - total_wit,
                "deposits": dep, "withdrawals": wit, "returns": ret
            })
            return default_res

        req_cols = ['quantity', 'entry_price', 'exit_price', 'current_price', 'status', 'asset_type', 'prev_close', 'year_high', 'year_low']
        for c in req_cols:
            if c not in trades.columns:
                trades[c] = 0.0 if c not in ['status', 'asset_type'] else ('Open' if c=='status' else 'Stock')
        
        trades['asset_type'] = trades['asset_type'].fillna('Stock')
        for c in ['quantity', 'entry_price', 'exit_price', 'current_price', 'prev_close', 'year_high', 'year_low']:
            trades[c] = pd.to_numeric(trades[c], errors='coerce').fillna(0.0)

        is_closed = (trades['exit_price'] > 0) | (trades['status'].astype(str).str.lower().isin(['close', 'sold', 'مغلقة']))
        trades['status'] = np.where(is_closed, 'Close', 'Open')
        trades.loc[is_closed, 'current_price'] = trades['exit_price']

        trades['total_cost'] = trades['quantity'] * trades['entry_price']
        trades['market_value'] = trades['quantity'] * trades['current_price']
        trades['gain'] = trades['market_value'] - trades['total_cost']
        
        trades['gain_pct'] = 0.0
        mask_cost = trades['total_cost'] != 0
        trades.loc[mask_cost, 'gain_pct'] = (trades.loc[mask_cost, 'gain'] / trades.loc[mask_cost, 'total_cost']) * 100

        trades['daily_change'] = 0.0
        mask_open = trades['status'] == 'Open'
        if trades.loc[mask_open, 'prev_close'].sum() > 0:
             trades.loc[mask_open, 'daily_change'] = ((trades.loc[mask_open, 'current_price'] - trades.loc[mask_open, 'prev_close']) / trades.loc[mask_open, 'prev_close']) * 100

        total_open_val = trades.loc[mask_open, 'market_value'].sum()
        trades['weight'] = 0.0
        if total_open_val > 0:
            trades.loc[mask_open, 'weight'] = (trades.loc[mask_open, 'market_value'] / total_open_val) * 100

        open_trades = trades[mask_open]
        closed_trades = trades[~mask_open]

        cost_open = open_trades['total_cost'].sum()
        market_val_open = open_trades['market_value'].sum()
        sales_closed = closed_trades['market_value'].sum()
        
        total_buy_cost = trades['total_cost'].sum()
        cash = (total_dep + total_ret + sales_closed) - (total_wit + total_buy_cost)

        return {
            "cost_open": cost_open, "market_val_open": market_val_open,
            "unrealized_pl": market_val_open - cost_open,
            "realized_pl": sales_closed - closed_trades['total_cost'].sum(),
            "cash": cash,
            "total_deposited": total_dep, "total_withdrawn": total_wit, "total_returns": total_ret,
            "all_trades": trades, "deposits": dep, "withdrawals": wit, "returns": ret
        }
    except: return default_res

def generate_equity_curve(df):
    if df.empty: return pd.DataFrame()
    return df[['date', 'total_cost']].sort_values('date').assign(cumulative_invested=lambda x: x['total_cost'].cumsum())

def run_backtest(df, s, c):
    if df is None or df.empty: return None
    df = df.copy()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['Signal'] = np.where(df['Close'] > df['MA20'], 1, -1)
    df['Portfolio_Value'] = c * (1 + (df['Close'].pct_change() * df['Signal'].shift(1)).fillna(0).cumsum())
    return {'final_value': df['Portfolio_Value'].iloc[-1], 'return_pct': ((df['Portfolio_Value'].iloc[-1]/c)-1)*100, 'df': df}

def update_prices():
    return True
