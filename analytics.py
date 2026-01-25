import pandas as pd
import numpy as np
import yfinance as yf
from database import fetch_table, get_db
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# --- 1. التحليل المالي السريع ---
def get_portfolio_summary_sql():
    query = """
    SELECT 
        (SELECT COALESCE(SUM(amount), 0) FROM Deposits) as total_dep,
        (SELECT COALESCE(SUM(amount), 0) FROM Withdrawals) as total_wit,
        (SELECT COALESCE(SUM(amount), 0) FROM ReturnsGrants) as total_ret,
        (SELECT COALESCE(SUM((exit_price - entry_price) * quantity), 0) FROM Trades WHERE status = 'Close') as realized_pl,
        (SELECT COALESCE(SUM(quantity * entry_price), 0) FROM Trades WHERE status = 'Open') as cost_open
    """
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()
                if row:
                    return {
                        "total_deposited": row[0], "total_withdrawn": row[1],
                        "total_returns": row[2], "realized_pl": row[3], "cost_open": row[4]
                    }
    return {"total_deposited": 0, "total_withdrawn": 0, "total_returns": 0, "realized_pl": 0, "cost_open": 0}

# --- 2. المحرك الأساسي ---
def calculate_portfolio_metrics():
    sql_sums = get_portfolio_summary_sql()
    trades = fetch_table("Trades")
    dep = fetch_table("Deposits")
    wit = fetch_table("Withdrawals")
    ret = fetch_table("ReturnsGrants")
    
    if trades.empty:
        return {
            **sql_sums, "market_val_open": 0, "unrealized_pl": 0, "cash": 0,
            "all_trades": pd.DataFrame(), "deposits": dep, "withdrawals": wit, "returns": ret, "equity": 0
        }

    trades['current_price'] = pd.to_numeric(trades['current_price'], errors='coerce').fillna(0.0)
    trades['entry_price'] = pd.to_numeric(trades['entry_price'], errors='coerce').fillna(0.0)
    trades['quantity'] = pd.to_numeric(trades['quantity'], errors='coerce').fillna(0.0)
    trades['dividend_yield'] = pd.to_numeric(trades.get('dividend_yield', 0), errors='coerce').fillna(0.0)

    open_trades = trades[trades['status'] == 'Open'].copy()
    market_val_open = (open_trades['quantity'] * open_trades['current_price']).sum()
    unrealized_pl = market_val_open - sql_sums['cost_open']
    
    # حساب الدخل المتوقع
    trades['projected_annual_income'] = trades['market_value'] * trades['dividend_yield'] if 'market_value' in trades else 0
    projected_dividend_income = open_trades['quantity'].mul(open_trades['current_price']).mul(open_trades['dividend_yield']).sum()

    # حساب الكاش
    total_sales_value = trades[trades['status'] == 'Close'].apply(lambda x: x['quantity'] * x['exit_price'], axis=1).sum()
    total_buy_cost_all = (trades['quantity'] * trades['entry_price']).sum()
    cash = (sql_sums['total_deposited'] + sql_sums['total_ret'] + total_sales_value) - (sql_sums['total_withdrawn'] + total_buy_cost_all)
    
    # تحسينات التوافق مع views.py
    # نضيف الأعمدة المطلوبة
    trades['market_value'] = trades['quantity'] * trades['current_price']
    trades['total_cost'] = trades['quantity'] * trades['entry_price']
    trades['gain'] = trades['market_value'] - trades['total_cost']
    
    # إغلاق العمليات
    closed_mask = trades['status'] == 'Close'
    trades.loc[closed_mask, 'current_price'] = trades.loc[closed_mask, 'exit_price']
    trades.loc[closed_mask, 'market_value'] = trades.loc[closed_mask, 'quantity'] * trades.loc[closed_mask, 'exit_price']

    return {
        **sql_sums,
        "market_val_open": market_val_open,
        "unrealized_pl": unrealized_pl,
        "cash": cash,
        "equity": cash + market_val_open,
        "cost_closed": trades[closed_mask]['total_cost'].sum(),
        "sales_closed": trades[closed_mask]['market_value'].sum(),
        "projected_dividend_income": projected_dividend_income,
        "all_trades": trades,
        "deposits": dep,
        "withdrawals": wit,
        "returns": ret
    }

# --- 3. دالة المختبر (هذه هي الدالة المفقودة التي تسبب الخطأ) ---
def run_backtest(df, strategy_name, initial_capital=100000):
    if df is None or df.empty: return None
    df = df.copy()
    df['Signal'] = 0
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    
    if strategy_name == "Trend Follower":
        df.loc[df['SMA_20'] > df['SMA_50'], 'Signal'] = 1
        df.loc[df['SMA_20'] < df['SMA_50'], 'Signal'] = -1
    else: 
        df.loc[df['Close'] > df['SMA_20'], 'Signal'] = 1
        df.loc[df['Close'] < df['SMA_20'], 'Signal'] = -1

    cash = initial_capital
    position = 0
    portfolio_values = []
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        signal = df['Signal'].iloc[i]
        if signal == 1 and cash > price:
            shares = cash // price
            position += shares
            cash -= shares * price
        elif signal == -1 and position > 0:
            cash += position * price
            position = 0
        portfolio_values.append(cash + (position * price))
        
    df['Portfolio_Value'] = portfolio_values
    final = portfolio_values[-1]
    return {'final_value': final, 'return_pct': ((final - initial_capital)/initial_capital)*100, 'df': df}

def update_prices():
    from market_data import fetch_batch_data
    trades = fetch_table("Trades")
    wl = fetch_table("Watchlist")
    symbols = list(set(trades[trades['status']=='Open']['symbol'].tolist() + wl['symbol'].tolist()))
    if not symbols: return
    data = fetch_batch_data(symbols)
    with get_db() as conn:
        with conn.cursor() as cur:
            for s, d in data.items():
                if d['price'] > 0:
                    cur.execute("UPDATE Trades SET current_price=%s, prev_close=%s, year_high=%s, year_low=%s, dividend_yield=%s WHERE symbol=%s AND status='Open'", 
                                (d['price'], d['prev_close'], d['year_high'], d['year_low'], d.get('dividend_yield',0), s))
            conn.commit()
def generate_equity_curve(df): return pd.DataFrame() # Placeholder
