import pandas as pd
import numpy as np
from database import fetch_table
import streamlit as st

@st.cache_data(ttl=60)
def calculate_portfolio_metrics():
    # الهيكل الافتراضي (الذي يمنع KeyError)
    empty_df = pd.DataFrame()
    default_res = {
        "cost_open": 0.0, "market_val_open": 0.0, "cash": 0.0, 
        "unrealized_pl": 0.0, "realized_pl": 0.0, 
        "total_deposited": 0.0, "total_withdrawn": 0.0, "total_returns": 0.0,
        "deposits": pd.DataFrame(columns=['date', 'amount', 'note']),
        "withdrawals": pd.DataFrame(columns=['date', 'amount', 'note']),
        "returns": pd.DataFrame(columns=['date', 'amount', 'symbol', 'note']),
        "all_trades": pd.DataFrame(columns=['symbol', 'company_name', 'sector', 'status', 'strategy', 'asset_type', 'date', 'quantity', 'entry_price', 'exit_price', 'current_price', 'total_cost', 'market_value', 'gain', 'gain_pct'])
    }

    try:
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")

        # تنظيف الجداول المالية
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

        # التأكد من الأعمدة
        cols = ['quantity', 'entry_price', 'exit_price', 'current_price', 'status', 'asset_type']
        for c in cols:
            if c not in trades.columns:
                trades[c] = 0.0 if c not in ['status', 'asset_type'] else ('Open' if c=='status' else 'Stock')
        
        trades['asset_type'] = trades['asset_type'].fillna('Stock')
        
        for c in ['quantity', 'entry_price', 'exit_price', 'current_price']:
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

        open_trades = trades[trades['status'] == 'Open']
        closed_trades = trades[trades['status'] == 'Close']

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

def update_prices(): return True
def create_smart_backup(): return True
def generate_equity_curve(df):
    if df.empty: return pd.DataFrame()
    return df[['date', 'total_cost']].sort_values('date').assign(cumulative_invested=lambda x: x['total_cost'].cumsum())
def calculate_historical_drawdown(df): return pd.DataFrame()
