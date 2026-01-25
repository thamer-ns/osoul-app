import pandas as pd
import numpy as np
import yfinance as yf
from database import fetch_table, get_db

# 1. SQL سريع
def get_portfolio_summary_sql():
    query = """
    SELECT 
        COALESCE((SELECT SUM(amount) FROM Deposits), 0),
        COALESCE((SELECT SUM(amount) FROM Withdrawals), 0),
        COALESCE((SELECT SUM(amount) FROM ReturnsGrants), 0),
        COALESCE((SELECT SUM((exit_price - entry_price) * quantity) FROM Trades WHERE status = 'Close'), 0),
        COALESCE((SELECT SUM(quantity * entry_price) FROM Trades WHERE status = 'Open'), 0)
    """
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(query)
                    row = cur.fetchone()
                    if row: return {"total_deposited": float(row[0]), "total_withdrawn": float(row[1]), "total_returns": float(row[2]), "realized_pl": float(row[3]), "cost_open": float(row[4])}
                except: pass
    return {"total_deposited": 0, "total_withdrawn": 0, "total_returns": 0, "realized_pl": 0, "cost_open": 0}

# 2. حسابات المحفظة
def calculate_portfolio_metrics():
    sql = get_portfolio_summary_sql()
    trades = fetch_table("Trades")
    dep = fetch_table("Deposits")
    wit = fetch_table("Withdrawals")
    ret = fetch_table("ReturnsGrants")
    
    # حماية من البيانات الفارغة
    for df in [dep, wit, ret]:
        if 'amount' not in df.columns: df['amount'] = 0.0

    if trades.empty:
        return {**sql, "market_val_open": 0, "unrealized_pl": 0, "cash": 0, "equity": 0, 
                "all_trades": pd.DataFrame(), "deposits": dep, "withdrawals": wit, "returns": ret,
                "projected_dividend_income": 0, "cost_closed": 0, "sales_closed": 0}

    # تحويل الأرقام
    for c in ['quantity', 'entry_price', 'current_price', 'exit_price', 'dividend_yield']:
        if c in trades.columns: trades[c] = pd.to_numeric(trades[c], errors='coerce').fillna(0.0)

    # معالجة الحالة (Open/Close)
    condition_closed = (trades['exit_price'] > 0) | (trades['status'].astype(str).str.lower().isin(['close', 'sold', 'مغلقة', 'مباعة']))
    trades['status'] = np.where(condition_closed, 'Close', 'Open')

    open_trades = trades[trades['status'] == 'Open']
    closed_trades = trades[trades['status'] == 'Close']

    mkt_val = (open_trades['quantity'] * open_trades['current_price']).sum()
    unrealized = mkt_val - sql['cost_open']
    
    # التوزيعات المتوقعة
    trades['projected_annual_income'] = trades['quantity'] * trades['current_price'] * trades['dividend_yield']
    projected_div = open_trades['projected_annual_income'].sum()

    # الكاش
    sales = closed_trades.apply(lambda x: x['quantity'] * x['exit_price'], axis=1).sum()
    buys = (trades['quantity'] * trades['entry_price']).sum()
    cash = (sql['total_deposited'] + sql['total_returns'] + sales) - (sql['total_withdrawn'] + buys)
    
    # أعمدة العرض
    trades['market_value'] = trades['quantity'] * trades['current_price']
    trades['total_cost'] = trades['quantity'] * trades['entry_price']
    trades['gain'] = trades['market_value'] - trades['total_cost']
    
    # إغلاق العمليات في الجدول
    trades.loc[condition_closed, 'current_price'] = trades.loc[condition_closed, 'exit_price']
    trades.loc[condition_closed, 'market_value'] = trades.loc[condition_closed, 'quantity'] * trades.loc[condition_closed, 'exit_price']

    return {**sql, "market_val_open": mkt_val, "unrealized_pl": unrealized, "cash": cash, "equity": cash+mkt_val,
            "projected_dividend_income": projected_div, "cost_closed": closed_trades['total_cost'].sum(), 
            "sales_closed": sales, "all_trades": trades, "deposits": dep, "withdrawals": wit, "returns": ret}

# 3. المختبر (Backtest Logic)
def run_backtest(df, strategy, capital=100000):
    if df is None or df.empty: return None
    df = df.copy()
    df['Signal'] = 0
    df['SMA20'] = df['Close'].rolling(20).mean()
    df['SMA50'] = df['Close'].rolling(50).mean()
    
    if strategy == "Trend Follower":
        df.loc[df['SMA20'] > df['SMA50'], 'Signal'] = 1
        df.loc[df['SMA20'] < df['SMA50'], 'Signal'] = -1
    else: # Sniper
        df.loc[df['Close'] > df['SMA20'], 'Signal'] = 1
        df.loc[df['Close'] < df['SMA20'], 'Signal'] = -1
        
    cash = capital
    pos = 0
    vals = []
    for i in range(len(df)):
        p = df['Close'].iloc[i]
        sig = df['Signal'].iloc[i]
        if sig == 1 and cash > p:
            buy = cash // p
            pos += buy
            cash -= buy * p
        elif sig == -1 and pos > 0:
            cash += pos * p
            pos = 0
        vals.append(cash + (pos * p))
    
    df['Portfolio_Value'] = vals
    return {'final_value': vals[-1], 'return_pct': ((vals[-1]-capital)/capital)*100, 'df': df}

def update_prices():
    from market_data import fetch_batch_data
    trades = fetch_table("Trades")
    wl = fetch_table("Watchlist")
    syms = list(set(trades[trades['status']=='Open']['symbol'].tolist() + wl['symbol'].tolist()))
    if not syms: return
    d = fetch_batch_data(syms)
    with get_db() as conn:
        with conn.cursor() as cur:
            for s, data in d.items():
                if data['price'] > 0:
                    cur.execute("UPDATE Trades SET current_price=%s, prev_close=%s, year_high=%s, year_low=%s, dividend_yield=%s WHERE symbol=%s AND status='Open'", 
                                (data['price'], data['prev_close'], data['year_high'], data['year_low'], data.get('dividend_yield',0), s))
            conn.commit()

def generate_equity_curve(df): 
    if df.empty: return pd.DataFrame()
    return df[['date', 'total_cost']].sort_values('date').assign(cumulative_invested=lambda x: x['total_cost'].cumsum())
