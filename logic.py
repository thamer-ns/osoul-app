import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st
from config import TADAWUL_DB, SECTOR_TARGETS
from database import get_db, create_smart_backup
import logging
import time

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

HAS_YF = True

def get_ticker_symbol(symbol):
    s = str(symbol).strip().upper()
    if s.isdigit(): return f"{s}.SR"
    return s

def get_static_info(symbol):
    s = str(symbol).strip().replace('.SR', '').replace('.sr', '')
    return TADAWUL_DB.get(s, {}).get('name', ''), TADAWUL_DB.get(s, {}).get('sector', '')

def fetch_with_retry(tickers_str, retries=3):
    for attempt in range(retries):
        try: return yf.Tickers(tickers_str)
        except: time.sleep(1)
    return None

@st.cache_data(ttl=300, show_spinner=False)
def fetch_batch_data(symbols_list):
    if not HAS_YF or not symbols_list: return {}
    tickers_map = {s: get_ticker_symbol(s) for s in symbols_list}
    unique = list(set(tickers_map.values()))
    results = {}
    batch_size = 10 
    
    for i in range(0, len(unique), batch_size):
        batch = unique[i:i+batch_size]
        tickers = fetch_with_retry(' '.join(batch))
        if tickers:
            for orig, yahoo_sym in tickers_map.items():
                if yahoo_sym not in batch: continue
                try:
                    t = tickers.tickers[yahoo_sym]
                    info = t.info 
                    price = info.get('currentPrice') or t.fast_info.last_price
                    
                    results[orig] = {
                        'price': float(price) if price else 0.0,
                        'prev_close': float(info.get('previousClose', 0.0)),
                        'year_high': float(info.get('fiftyTwoWeekHigh', 0.0)),
                        'year_low': float(info.get('fiftyTwoWeekLow', 0.0)),
                        'dividend_yield': float(info.get('dividendYield', 0.0)) if info.get('dividendYield') else 0.0
                    }
                except: pass
    return results

@st.cache_data(ttl=300, show_spinner=False)
def get_tasi_data():
    if not HAS_YF: return None, 0.0
    try:
        t = yf.Ticker("^TASI.SR").fast_info
        p = t.last_price
        prev = t.previous_close
        if p and prev: return p, ((p - prev) / prev) * 100
        return None, 0.0
    except: return None, 0.0

@st.cache_data(ttl=300, show_spinner=False)
def get_chart_data(symbol, period, interval):
    if not HAS_YF: return None
    try:
        t = yf.Ticker(get_ticker_symbol(symbol))
        return t.history(period=period, interval=interval)
    except: return None

def enrich_data_frame(df):
    if df.empty: return df
    if 'company_name' not in df.columns: df['company_name'] = ""
    if 'sector' not in df.columns: df['sector'] = ""
    for idx, row in df.iterrows():
        sym = row.get('symbol')
        if sym:
            n, s = get_static_info(sym)
            if not row.get('company_name'): df.at[idx, 'company_name'] = n
            if not row.get('sector'): df.at[idx, 'sector'] = s
    return df

def process_trade_logic(df):
    if df.empty: return df
    if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'], errors='coerce')
    cols = ['quantity', 'entry_price', 'current_price', 'exit_price', 'prev_close', 'year_high', 'year_low', 'dividend_yield']
    for c in cols:
        if c not in df.columns: df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
    
    if 'status' not in df.columns: df['status'] = 'Open'
    
    status_clean = df['status'].astype(str).str.strip().str.lower()
    is_db_closed = status_clean.isin(['close', 'sold', 'مغلقة', 'مباعة'])
    has_exit_price = (df['exit_price'] > 0)
    
    df['status'] = np.where(is_db_closed | has_exit_price, 'Close', 'Open')
    
    mask_close = df['status'] == 'Close'
    df.loc[mask_close, 'current_price'] = df.loc[mask_close, 'exit_price']
    
    df['total_cost'] = df['quantity'] * df['entry_price']
    df['market_value'] = df['quantity'] * df['current_price']
    df['gain'] = df['market_value'] - df['total_cost']
    df['gain_pct'] = (df['gain'] / df['total_cost'].replace(0, 1)) * 100
    
    df['daily_change'] = ((df['current_price'] - df['prev_close']) / df['prev_close'].replace(0, 1)) * 100
    df.loc[mask_close, 'daily_change'] = 0.0 
    
    df['projected_annual_income'] = df['market_value'] * df['dividend_yield']
    
    total_val = df[df['status'] == 'Open']['market_value'].sum()
    df['weight'] = 0.0
    mask_open = df['status'] == 'Open'
    if total_val > 0:
        df.loc[mask_open, 'weight'] = (df.loc[mask_open, 'market_value'] / total_val) * 100
        
    return df

def calculate_sector_distribution(df, total_portfolio_cost):
    if df.empty or total_portfolio_cost == 0: return pd.DataFrame()
    open_df = df[df['status'] == 'Open']
    if open_df.empty: return pd.DataFrame()

    sector_grp = open_df.groupby('sector').agg(
        companies_count=('symbol', 'nunique'),
        sector_cost=('total_cost', 'sum')
    ).reset_index()
    
    sector_grp['current_weight'] = (sector_grp['sector_cost'] / total_portfolio_cost) * 100
    sector_grp['target_weight'] = sector_grp['sector'].map(SECTOR_TARGETS).fillna(0.0)
    sector_grp['remaining_to_target'] = ((sector_grp['target_weight'] - sector_grp['current_weight']) / 100) * total_portfolio_cost
    
    return sector_grp

def get_financial_summary():
    with get_db() as conn:
        try: dep = pd.read_sql("SELECT * FROM Deposits", conn)
        except: dep = pd.DataFrame()
        try: wit = pd.read_sql("SELECT * FROM Withdrawals", conn)
        except: wit = pd.DataFrame()
        try: ret = pd.read_sql("SELECT * FROM ReturnsGrants", conn)
        except: ret = pd.DataFrame()
        try: trades = pd.read_sql("SELECT * FROM Trades", conn)
        except: trades = pd.DataFrame()
        
        trades = enrich_data_frame(trades)
        trades = process_trade_logic(trades)
        
        for d in [dep, wit, ret]:
            if 'date' in d.columns: d['date'] = pd.to_datetime(d['date'], errors='coerce')

        total_deposited = dep['amount'].sum() if not dep.empty else 0
        total_withdrawn = wit['amount'].sum() if not wit.empty else 0
        net_invested_cash = total_deposited - total_withdrawn
        total_returns = ret['amount'].sum() if not ret.empty else 0
        
        open_trades = trades[trades['status']=='Open']
        closed_trades = trades[trades['status']=='Close']
        
        cost_open = open_trades['total_cost'].sum() if not open_trades.empty else 0
        market_val_open = open_trades['market_value'].sum() if not open_trades.empty else 0
        unrealized_pl = market_val_open - cost_open
        
        projected_dividend_income = open_trades['projected_annual_income'].sum() if not open_trades.empty else 0
        
        cost_closed = closed_trades['total_cost'].sum() if not closed_trades.empty else 0
        sales_closed = closed_trades['market_value'].sum() if not closed_trades.empty else 0
        realized_pl = sales_closed - cost_closed
        
        cash = net_invested_cash + total_returns + sales_closed - (cost_open + cost_closed)
        equity = cash + market_val_open
        
        return {
            "equity": equity, 
            "cash": cash, 
            "market_val_open": market_val_open, 
            "unrealized_pl": unrealized_pl, 
            "realized_pl": realized_pl, 
            "cost_open": cost_open,
            "cost_closed": cost_closed,
            "sales_closed": sales_closed,
            "total_deposited": total_deposited,
            "total_withdrawn": total_withdrawn,
            "total_returns": total_returns,
            "projected_dividend_income": projected_dividend_income,
            "all_trades": trades, 
            "deposits": dep, 
            "withdrawals": wit, 
            "returns": ret
        }

def update_market_data_batch():
    if not HAS_YF: return False
    try:
        with get_db() as conn:
            trades = pd.read_sql("SELECT id, symbol FROM Trades WHERE status = 'Open'", conn)
            try: watchlist = pd.read_sql("SELECT symbol FROM Watchlist", conn)
            except: watchlist = pd.DataFrame(columns=['symbol'])
            all_symbols = list(set(trades['symbol'].tolist() + watchlist['symbol'].tolist()))
            if not all_symbols: return False
            market_data = fetch_batch_data(all_symbols)
            for i, row in trades.iterrows():
                if row['symbol'] in market_data:
                    d = market_data[row['symbol']]
                    if d['price'] > 0:
                        conn.execute("""UPDATE Trades SET current_price = ?, prev_close = ?, year_high = ?, year_low = ?, dividend_yield = ? WHERE id = ?""", 
                                     (d['price'], d['prev_close'], d['year_high'], d['year_low'], d['dividend_yield'], row['id']))
            conn.commit()
        create_smart_backup()
        st.cache_data.clear()
        return True
    except: return False

def get_sector_recommendations(fin):
    trades = fin['all_trades']
    if trades.empty: return []
    open_trades = trades[trades['status'] == 'Open']
    total_value = open_trades['market_value'].sum()
    if total_value == 0: return []
    sector_weights = open_trades.groupby('sector')['market_value'].sum() / total_value
    all_sectors = set(info['sector'] for info in TADAWUL_DB.values())
    owned_sectors = set(sector_weights.index)
    missing_sectors = list(all_sectors - owned_sectors)
    recommendations = []
    for sector in missing_sectors:
        suggestions = [info['name'] for code, info in TADAWUL_DB.items() if info['sector'] == sector][:3]
        recommendations.append({'sector': sector, 'suggestions': "، ".join(suggestions), 'reason': "قطاع غير ممثل في محفظتك"})
    return recommendations
