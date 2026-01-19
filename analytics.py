import pandas as pd
import numpy as np
import shutil
from database import fetch_table, get_db
from market_data import get_static_info, fetch_batch_data
from config import BACKUP_DIR
import streamlit as st
import logging

logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app_errors.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def calculate_portfolio_metrics():
    try:
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")

        if trades.empty:
            trades = pd.DataFrame(columns=[
                'symbol', 'strategy', 'status', 'market_value', 'total_cost', 
                'gain', 'sector', 'company_name', 'date', 'exit_date', 
                'quantity', 'entry_price', 'exit_price'
            ])

        if not trades.empty:
            unique_symbols = trades['symbol'].unique()
            info_map = {sym: get_static_info(sym) for sym in unique_symbols}
            
            trades['company_name'] = trades['symbol'].map(lambda x: info_map.get(x, (x, ''))[0])
            trades['sector'] = trades['symbol'].map(lambda x: info_map.get(x, ('', ''))[1])

            if 'strategy' in trades.columns:
                trades['strategy'] = trades['strategy'].astype(str).str.strip()
            
            if 'status' in trades.columns:
                trades['status'] = trades['status'].astype(str).str.strip()
                close_keywords = ['close', 'sold', 'مغلقة', 'مباعة']
                trades.loc[trades['status'].str.lower().isin(close_keywords), 'status'] = 'Close'
                trades.loc[trades['status'] != 'Close', 'status'] = 'Open'

            trades['date'] = pd.to_datetime(trades['date'], errors='coerce')
            if 'exit_date' in trades.columns:
                trades['exit_date'] = pd.to_datetime(trades['exit_date'], errors='coerce')
            
            num_cols = ['quantity', 'entry_price', 'exit_price', 'current_price', 'prev_close', 'dividend_yield', 'year_high', 'year_low']
            for c in num_cols:
                if c not in trades.columns: trades[c] = 0.0
                trades[c] = pd.to_numeric(trades[c], errors='coerce').fillna(0.0)

            # --- الحسابات الأساسية للصفقات ---
            trades['total_cost'] = trades['quantity'] * trades['entry_price']
            is_closed = trades['status'] == 'Close'
            trades.loc[is_closed, 'current_price'] = trades.loc[is_closed, 'exit_price']
            trades['market_value'] = trades['quantity'] * trades['current_price']
            
            # الربح الرأسمالي (Capital Gain) فقط
            trades['gain'] = trades['market_value'] - trades['total_cost']
            trades['gain_pct'] = (trades['gain'] / trades['total_cost'].replace(0, 1)) * 100
            
            trades['daily_change'] = ((trades['current_price'] - trades['prev_close']) / trades['prev_close'].replace(0, 1)) * 100
            trades.loc[is_closed, 'daily_change'] = 0.0

        total_dep = dep['amount'].sum() if not dep.empty else 0.0
        total_wit = wit['amount'].sum() if not wit.empty else 0.0
        total_ret = ret['amount'].sum() if not ret.empty else 0.0
        
        open_trades = trades[trades['status'] == 'Open'] if not trades.empty else pd.DataFrame()
        closed_trades = trades[trades['status'] == 'Close'] if not trades.empty else pd.DataFrame()
        
        cost_open = open_trades['total_cost'].sum() if not open_trades.empty else 0.0
        cost_closed = closed_trades['total_cost'].sum() if not closed_trades.empty else 0.0
        sales_closed = closed_trades['market_value'].sum() if not closed_trades.empty else 0.0
        market_val_open = open_trades['market_value'].sum() if not open_trades.empty else 0.0

        total_in = total_dep + total_ret + sales_closed
        total_out = total_wit + cost_open + cost_closed
        cash_available = total_in - total_out

        vals = {
            "cost_open": cost_open,
            "market_val_open": market_val_open,
            "cost_closed": cost_closed,
            "sales_closed": sales_closed,
            "total_deposited": total_dep,
            "total_withdrawn": total_wit,
            "total_returns": total_ret,
            "cash": cash_available,
            "all_trades": trades, "deposits": dep, "withdrawals": wit, "returns": ret
        }
        
        vals['unrealized_pl'] = vals['market_val_open'] - vals['cost_open']
        vals['realized_pl'] = vals['sales_closed'] - vals['cost_closed']
        vals['equity'] = vals['cash'] + vals['market_val_open']
        
        return vals

    except Exception as e:
        logger.error(f"Error in calculate_portfolio_metrics: {str(e)}")
        return {
            "cost_open": 0, "market_val_open": 0, "cost_closed": 0, "sales_closed": 0,
            "total_deposited": 0, "total_withdrawn": 0, "total_returns": 0, "cash": 0,
            "unrealized_pl": 0, "realized_pl": 0, "equity": 0,
            "all_trades": pd.DataFrame(), "deposits": pd.DataFrame(), 
            "withdrawals": pd.DataFrame(), "returns": pd.DataFrame()
        }

def get_comprehensive_performance(trades_df, returns_df):
    """
    تحليل مالي شامل يدمج أرباح الصفقات + التوزيعات النقدية
    """
    if trades_df.empty: return pd.DataFrame(), pd.DataFrame()

    # 1. تجميع أداء الصفقات (مفتوحة + مغلقة) حسب السهم والقطاع
    # نستخدم groupby مرتين: مرة للسهم ومرة للقطاع
    
    # --- أ. تحليل القطاعات ---
    # تجميع الصفقات حسب القطاع
    sector_trades = trades_df.groupby('sector').agg({
        'total_cost': 'sum',
        'gain': 'sum',         # ربح رأسمالي (فرق سعر)
        'market_value': 'sum',
        'symbol': 'count'
    }).reset_index()
    
    # تجهيز التوزيعات وربطها بالقطاع
    sector_dividends = pd.DataFrame()
    if not returns_df.empty:
        # نحتاج معرفة قطاع كل سهم في جدول العوائد
        unique_ret_syms = returns_df['symbol'].unique()
        info_map = {sym: get_static_info(sym)[1] for sym in unique_ret_syms} # [1] هو القطاع
        
        returns_df['sector'] = returns_df['symbol'].map(info_map)
        sector_dividends = returns_df.groupby('sector')['amount'].sum().reset_index()
        sector_dividends.rename(columns={'amount': 'total_dividends'}, inplace=True)
    
    # دمج أرباح الصفقات مع التوزيعات
    if not sector_dividends.empty:
        sector_perf = pd.merge(sector_trades, sector_dividends, on='sector', how='left')
        sector_perf['total_dividends'] = sector_perf['total_dividends'].fillna(0)
    else:
        sector_perf = sector_trades
        sector_perf['total_dividends'] = 0.0
        
    # الربح الشامل للقطاع = ربح الصفقات + التوزيعات
    sector_perf['net_profit'] = sector_perf['gain'] + sector_perf['total_dividends']
    sector_perf['roi_pct'] = (sector_perf['net_profit'] / sector_perf['total_cost'].replace(0, 1)) * 100

    # --- ب. تحليل الأسهم ---
    stock_trades = trades_df.groupby(['symbol', 'company_name', 'sector']).agg({
        'total_cost': 'sum',
        'gain': 'sum',
        'market_value': 'sum',
        'quantity': 'sum' # مجموع الأسهم المتداولة تاريخياً
    }).reset_index()
    
    stock_dividends = pd.DataFrame()
    if not returns_df.empty:
        stock_dividends = returns_df.groupby('symbol')['amount'].sum().reset_index()
        stock_dividends.rename(columns={'amount': 'total_dividends'}, inplace=True)
        
    if not stock_dividends.empty:
        stock_perf = pd.merge(stock_trades, stock_dividends, on='symbol', how='left')
        stock_perf['total_dividends'] = stock_perf['total_dividends'].fillna(0)
    else:
        stock_perf = stock_trades
        stock_perf['total_dividends'] = 0.0
        
    stock_perf['net_profit'] = stock_perf['gain'] + stock_perf['total_dividends']
    stock_perf['roi_pct'] = (stock_perf['net_profit'] / stock_perf['total_cost'].replace(0, 1)) * 100
    
    return sector_perf, stock_perf

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
                    conn.execute("UPDATE Trades SET current_price=?, prev_close=?, year_high=?, year_low=?, dividend_yield=? WHERE symbol=?", 
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
            for t in ['Trades', 'Deposits', 'Withdrawals', 'ReturnsGrants', 'Watchlist', 'Users', 'SectorTargets']:
                df = fetch_table(t)
                for c in df.columns:
                    if 'date' in c: df[c] = df[c].astype(str)
                df.to_excel(writer, sheet_name=t, index=False)
        return True
    except Exception as e:
        logger.error(f"Error in create_smart_backup: {str(e)}")
        return False

def calculate_rsi(data, window=14):
    try:
        if 'Close' not in data.columns: return None
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    except: return None
