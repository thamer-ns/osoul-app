import pandas as pd
import numpy as np
import shutil
from database import fetch_table, get_db
from market_data import get_static_info, fetch_batch_data, get_chart_history
# --- التعديل هنا: حذفنا SECTOR_TARGETS ---
from config import BACKUP_DIR 
import streamlit as st
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# تعريف المتغير هنا كقيمة افتراضية لتجنب خطأ الاستيراد
SECTOR_TARGETS = {}

def calculate_portfolio_metrics():
    try:
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")

        if trades.empty:
            trades = pd.DataFrame(columns=['symbol', 'strategy', 'status', 'market_value', 'total_cost', 'gain', 'sector', 'company_name', 'date', 'exit_date', 'quantity', 'entry_price', 'exit_price'])

        if not trades.empty:
            if 'status' not in trades.columns: trades['status'] = 'Open'
            trades['status'] = trades['status'].str.strip()
            close_keywords = ['close', 'sold', 'مغلقة', 'مباعة']
            trades.loc[trades['status'].str.lower().isin(close_keywords), 'status'] = 'Close'
            
            num_cols = ['quantity', 'entry_price', 'exit_price', 'current_price', 'prev_close']
            for c in num_cols:
                if c not in trades.columns: trades[c] = 0.0
                trades[c] = pd.to_numeric(trades[c], errors='coerce').fillna(0.0)

            trades['total_cost'] = (trades['quantity'] * trades['entry_price']).round(2)
            
            is_closed = trades['status'] == 'Close'
            trades.loc[is_closed, 'current_price'] = trades.loc[is_closed, 'exit_price']
            trades['market_value'] = (trades['quantity'] * trades['current_price']).round(2)
            trades['gain'] = (trades['market_value'] - trades['total_cost']).round(2)
            trades['daily_change'] = (((trades['current_price'] - trades['prev_close']) / trades['prev_close'].replace(0, 1)) * 100).round(2)
            trades.loc[is_closed, 'daily_change'] = 0.0

        total_dep = dep['amount'].sum() if not dep.empty else 0.0
        total_wit = wit['amount'].sum() if not wit.empty else 0.0
        total_ret = ret['amount'].sum() if not ret.empty else 0.0
        
        open_trades = trades[trades['status'] != 'Close'] if not trades.empty else pd.DataFrame()
        closed_trades = trades[trades['status'] == 'Close'] if not trades.empty else pd.DataFrame()
        
        cost_open = open_trades['total_cost'].sum() if not open_trades.empty else 0.0
        cost_closed = closed_trades['total_cost'].sum() if not closed_trades.empty else 0.0
        sales_closed = closed_trades['market_value'].sum() if not closed_trades.empty else 0.0
        market_val_open = open_trades['market_value'].sum() if not open_trades.empty else 0.0

        total_in = total_dep + total_ret + sales_closed
        total_out = total_wit + cost_open + cost_closed
        cash_available = round(total_in - total_out, 2)

        vals = {
            "cost_open": cost_open, "market_val_open": market_val_open, "cost_closed": cost_closed, "sales_closed": sales_closed,
            "total_deposited": total_dep, "total_withdrawn": total_wit, "total_returns": total_ret, "cash": cash_available,
            "all_trades": trades, "deposits": dep, "withdrawals": wit, "returns": ret
        }
        vals['unrealized_pl'] = round(vals['market_val_open'] - vals['cost_open'], 2)
        vals['realized_pl'] = round(vals['sales_closed'] - vals['cost_closed'], 2)
        vals['equity'] = round(vals['cash'] + vals['market_val_open'], 2)
        return vals
    except Exception as e:
        logger.error(f"Error in metrics: {str(e)}")
        return {"cost_open": 0, "market_val_open": 0, "cash": 0, "all_trades": pd.DataFrame(), "unrealized_pl":0, "realized_pl":0, "total_deposited":0, "total_withdrawn":0, "total_returns":0, "deposits":pd.DataFrame(), "withdrawals":pd.DataFrame(), "returns":pd.DataFrame()}

def get_comprehensive_performance(trades_df, returns_df):
    if trades_df.empty: return pd.DataFrame(), pd.DataFrame()
    sector_trades = trades_df.groupby('sector').agg({'total_cost': 'sum', 'gain': 'sum', 'market_value': 'sum'}).reset_index()
    sector_trades['net_profit'] = sector_trades['gain']
    sector_trades['roi_pct'] = ((sector_trades['net_profit'] / sector_trades['total_cost'].replace(0, 1)) * 100).round(2)
    return sector_trades, pd.DataFrame()

def get_rebalancing_advice(df_open, targets_df, total_portfolio_value):
    return pd.DataFrame()

def get_dividends_calendar(returns_df):
    if returns_df.empty: return pd.DataFrame()
    df = returns_df.copy()
    df['date'] = pd.to_datetime(df['date'])
    df['year_month'] = df['date'].dt.strftime('%Y-%m')
    return df.groupby('year_month').agg({'amount': 'sum', 'symbol': lambda x: ', '.join(x.unique())}).reset_index().sort_values('year_month', ascending=False)

def generate_equity_curve(trades_df):
    if trades_df.empty: return pd.DataFrame()
    df = trades_df[['date', 'total_cost']].copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df['cumulative_invested'] = df['total_cost'].cumsum()
    return df

@st.cache_data(ttl=3600)
def calculate_historical_drawdown(open_trades_df):
    if open_trades_df.empty: return pd.DataFrame()
    symbols = open_trades_df['symbol'].unique().tolist()
    data = {}
    try:
        for sym in symbols:
            hist = get_chart_history(sym, "1y", "1d")
            if hist is not None and not hist.empty: data[sym] = hist['Close']
    except: return pd.DataFrame()
    if not data: return pd.DataFrame()
    prices_df = pd.DataFrame(data).ffill().dropna()
    if prices_df.empty: return pd.DataFrame()
    portfolio_history = pd.Series(0, index=prices_df.index)
    for _, row in open_trades_df.iterrows():
        sym = row['symbol']
        qty = row['quantity']
        if sym in prices_df.columns: portfolio_history += prices_df[sym] * qty
    rolling_max = portfolio_history.cummax()
    drawdown = (portfolio_history - rolling_max) / rolling_max * 100
    return pd.DataFrame({'date': drawdown.index, 'drawdown': drawdown.values})

def update_prices():
    try:
        trades = fetch_table("Trades")
        wl = fetch_table("Watchlist")
        if trades.empty and wl.empty: return False
        
        trade_symbols = trades.loc[trades['status'] != 'Close', 'symbol'].dropna().unique().tolist() if not trades.empty else []
        wl_symbols = wl['symbol'].dropna().unique().tolist() if not wl.empty else []
        symbols = list(set(trade_symbols + wl_symbols))
        
        data = fetch_batch_data(symbols) 
        if not data: return False
        
        with get_db() as conn:
            for s, d in data.items():
                if d['price'] > 0:
                    conn.execute("UPDATE Trades SET current_price=?, prev_close=?, year_high=?, year_low=?, dividend_yield=? WHERE symbol=? AND status!='Close'", 
                                 (d['price'], d['prev_close'], d['year_high'], d['year_low'], d['dividend_yield'], s))
            conn.commit()
        create_smart_backup()
        st.cache_data.clear()
        return True
    except Exception as e:
        logger.error(f"Error in update_prices: {str(e)}")
        return False

def create_smart_backup():
    try:
        latest = BACKUP_DIR / "backup_latest.xlsx"
        if latest.exists(): shutil.copy(latest, BACKUP_DIR / "backup_previous.xlsx")
        with pd.ExcelWriter(latest, engine='xlsxwriter') as writer:
            for t in ['Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants', 'Watchlist', 'Users', 'SectorTargets', 'InvestmentThesis']:
                df = fetch_table(t)
                for c in df.columns:
                    if 'date' in c: df[c] = df[c].astype(str)
                df.to_excel(writer, sheet_name=t, index=False)
        return True
    except: return False
