import pandas as pd
import numpy as np
from database import fetch_table, execute_query
from market_data import fetch_batch_data
import streamlit as st
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

@st.cache_data(ttl=60)
def calculate_portfolio_metrics():
    try:
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")

        expected_cols = [
            'symbol', 'strategy', 'status', 'market_value', 'total_cost', 
            'gain', 'gain_pct', 'sector', 'company_name', 'date', 'exit_date', 
            'quantity', 'entry_price', 'exit_price', 'current_price', 
            'prev_close', 'daily_change', 'dividend_yield', 'asset_type',
            'year_high', 'year_low', 'weight', 'projected_annual_income'
        ]

        if trades.empty:
            return {
                "cost_open": 0, "market_val_open": 0, "cash": 0, 
                "all_trades": pd.DataFrame(columns=expected_cols), 
                "unrealized_pl": 0, "realized_pl": 0, 
                "total_deposited": 0, "total_withdrawn": 0, "total_returns": 0,
                "deposits": dep, "withdrawals": wit, "returns": ret
            }

        for col in expected_cols:
            if col not in trades.columns:
                trades[col] = 0.0 if col not in ['symbol', 'strategy', 'status', 'sector', 'company_name', 'date', 'exit_date', 'asset_type'] else None

        trades['exit_price'] = pd.to_numeric(trades['exit_price'], errors='coerce').fillna(0.0)
        condition_closed = (trades['exit_price'] > 0) | (trades['status'].astype(str).str.lower().isin(['close', 'sold', 'مغلقة', 'مباعة']))
        trades['status'] = np.where(condition_closed, 'Close', 'Open')

        num_cols = ['quantity', 'entry_price', 'current_price', 'prev_close']
        for c in num_cols:
            trades[c] = pd.to_numeric(trades[c], errors='coerce').fillna(0.0)

        trades['total_cost'] = (trades['quantity'] * trades['entry_price'])
        is_closed = trades['status'] == 'Close'
        trades.loc[is_closed, 'current_price'] = trades.loc[is_closed, 'exit_price']
        
        trades['market_value'] = (trades['quantity'] * trades['current_price'])
        trades['gain'] = trades['market_value'] - trades['total_cost']
        
        trades['gain_pct'] = 0.0
        mask_nonzero = trades['total_cost'] != 0
        trades.loc[mask_nonzero, 'gain_pct'] = (trades.loc[mask_nonzero, 'gain'] / trades.loc[mask_nonzero, 'total_cost']) * 100

        open_trades = trades[~is_closed]
        closed_trades = trades[is_closed]

        cost_open = open_trades['total_cost'].sum()
        market_val_open = open_trades['market_value'].sum()
        
        sales_closed = closed_trades['market_value'].sum()
        cost_closed = closed_trades['total_cost'].sum()
        realized_pl = sales_closed - cost_closed

        total_dep = dep['amount'].sum() if not dep.empty else 0
        total_wit = wit['amount'].sum() if not wit.empty else 0
        total_ret = ret['amount'].sum() if not ret.empty else 0
        
        total_buy_cost = trades['total_cost'].sum()
        cash_available = (total_dep + total_ret + sales_closed) - (total_wit + total_buy_cost)

        return {
            "cost_open": cost_open,
            "market_val_open": market_val_open,
            "unrealized_pl": market_val_open - cost_open,
            "realized_pl": realized_pl,
            "cash": cash_available,
            "total_deposited": total_dep,
            "total_withdrawn": total_wit,
            "total_returns": total_ret,
            "all_trades": trades,
            "deposits": dep,
            "withdrawals": wit,
            "returns": ret
        }

    except Exception as e:
        logger.error(f"Error in metrics: {str(e)}")
        return {
            "cost_open": 0, "market_val_open": 0, "cash": 0, 
            "all_trades": pd.DataFrame(columns=expected_cols), 
            "unrealized_pl": 0, "realized_pl": 0, 
            "total_deposited": 0, "total_withdrawn": 0, "total_returns": 0,
            "deposits": dep, "withdrawals": wit, "returns": ret
        }

def update_prices():
    try:
        trades = fetch_table("Trades")
        wl = fetch_table("Watchlist")
        if trades.empty and wl.empty: return False
        
        symbols = set()
        if not trades.empty:
            symbols.update(trades.loc[trades['status'] != 'Close', 'symbol'].dropna().unique())
        if not wl.empty:
            symbols.update(wl['symbol'].dropna().unique())
            
        if not symbols: return False
        
        data = fetch_batch_data(list(symbols))
        if not data: return False
        
        from database import get_db
        with get_db() as conn:
            with conn.cursor() as cur:
                for s, d in data.items():
                    if d['price'] > 0:
                        cur.execute("""
                            UPDATE Trades 
                            SET current_price=%s, prev_close=%s, year_high=%s, year_low=%s, dividend_yield=%s 
                            WHERE symbol=%s AND status != 'Close'
                        """, (d['price'], d['prev_close'], d['year_high'], d['year_low'], d['dividend_yield'], s))
                conn.commit()
        
        st.cache_data.clear()
        return True
    except Exception as e:
        logger.error(f"Update prices error: {e}")
        return False

def create_smart_backup(): return True
def generate_equity_curve(trades_df):
    if trades_df.empty: return pd.DataFrame()
    df = trades_df[['date', 'total_cost']].copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df['cumulative_invested'] = df['total_cost'].cumsum()
    return df
def calculate_historical_drawdown(df): return pd.DataFrame()
