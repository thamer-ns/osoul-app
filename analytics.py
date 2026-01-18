import pandas as pd
import numpy as np
import shutil
from database import fetch_table, get_db, execute_query
from market_data import get_static_info, fetch_batch_data
from config import BACKUP_DIR, SECTOR_TARGETS
import streamlit as st

def calculate_portfolio_metrics():
    trades = fetch_table("Trades")
    dep = fetch_table("Deposits")
    wit = fetch_table("Withdrawals")
    ret = fetch_table("ReturnsGrants")

    if not trades.empty:
        trades['date'] = pd.to_datetime(trades['date'], errors='coerce')
        trades['total_cost'] = trades['quantity'] * trades['entry_price']
        
        is_closed = trades['status'].astype(str).str.lower().isin(['close', 'مغلقة'])
        trades.loc[is_closed, 'current_price'] = trades.loc[is_closed, 'exit_price']
        
        trades['market_value'] = trades['quantity'] * trades['current_price']
        trades['gain'] = trades['market_value'] - trades['total_cost']
        trades['gain_pct'] = (trades['gain'] / trades['total_cost'].replace(0, 1)) * 100
        
        for idx, row in trades.iterrows():
            n, s = get_static_info(row['symbol'])
            if not row['company_name']: trades.at[idx, 'company_name'] = n
            if not row['sector']: trades.at[idx, 'sector'] = s

    total_dep = dep['amount'].sum() if not dep.empty else 0
    total_wit = wit['amount'].sum() if not wit.empty else 0
    total_ret = ret['amount'].sum() if not ret.empty else 0
    
    open_trades = trades[~trades['status'].isin(['Close', 'مغلقة'])] if not trades.empty else pd.DataFrame()
    closed_trades = trades[trades['status'].isin(['Close', 'مغلقة'])] if not trades.empty else pd.DataFrame()
    
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
    vals['cash'] = (total_dep - total_wit + total_ret + vals['sales_closed']) - (vals['cost_open'] + vals['cost_closed'])
    vals['equity'] = vals['cash'] + vals['market_val_open']
    vals['projected_income'] = (open_trades['market_value'] * open_trades['dividend_yield']).sum() if not open_trades.empty and 'dividend_yield' in open_trades else 0
    
    return vals

def update_prices():
    try:
        trades = fetch_table("Trades")
        wl = fetch_table("Watchlist")
        if trades.empty and wl.empty: return False
        
        symbols = list(set(trades[trades['status'] != 'Close']['symbol'].tolist() + wl['symbol'].tolist()))
        data = fetch_batch_data(symbols)
        
        with get_db() as conn:
            for s, d in data.items():
                conn.execute("UPDATE Trades SET current_price=?, prev_close=?, year_high=?, year_low=?, dividend_yield=? WHERE symbol=? AND status != 'Close'", 
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
                fetch_table(t).to_excel(writer, sheet_name=t, index=False)
        return True
    except: return False

def calculate_rsi(data, window=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_sector_recommendations(fin):
    if fin['all_trades'].empty: return []
    open_t = fin['all_trades'][fin['all_trades']['status'] != 'Close']
    if open_t.empty: return []
    
    total = open_t['market_value'].sum()
    current = open_t.groupby('sector')['market_value'].sum() / total * 100
    recs = []
    
    for sec, target in SECTOR_TARGETS.items():
        curr_val = current.get(sec, 0)
        if curr_val < target - 5: # إذا كان أقل من الهدف بـ 5%
            recs.append({'sector': sec, 'diff': target - curr_val})
    return recs
