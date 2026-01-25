import pandas as pd
import numpy as np
import yfinance as yf
from database import fetch_table, get_db
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# --- 1. التحليل المالي السريع (SQL Optimization) ---
def get_portfolio_summary_sql():
    """حساب الإجماليات مباشرة من قاعدة البيانات لتسريع الأداء"""
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
                        "total_deposited": row[0],
                        "total_withdrawn": row[1],
                        "total_returns": row[2],
                        "realized_pl": row[3],
                        "cost_open": row[4]
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
            "all_trades": pd.DataFrame(), "deposits": dep, "withdrawals": wit, "returns": ret
        }

    # تنظيف البيانات
    trades['current_price'] = pd.to_numeric(trades['current_price'], errors='coerce').fillna(0.0)
    trades['entry_price'] = pd.to_numeric(trades['entry_price'], errors='coerce').fillna(0.0)
    
    open_trades = trades[trades['status'] == 'Open'].copy()
    market_val_open = (open_trades['quantity'] * open_trades['current_price']).sum()
    unrealized_pl = market_val_open - sql_sums['cost_open']
    
    # حساب الكاش
    total_sales_value = trades[trades['status'] == 'Close'].apply(lambda x: x['quantity'] * x['exit_price'], axis=1).sum()
    total_buy_cost_all = (trades['quantity'] * trades['entry_price']).sum()
    cash = (sql_sums['total_deposited'] + sql_sums['total_ret'] + total_sales_value) - (sql_sums['total_withdrawn'] + total_buy_cost_all)

    return {
        **sql_sums,
        "market_val_open": market_val_open,
        "unrealized_pl": unrealized_pl,
        "cash": cash,
        "all_trades": trades,
        "deposits": dep,
        "withdrawals": wit,
        "returns": ret
    }

# --- 3. دالة المختبر (BACKTESTING) - كانت مفقودة ---
def run_backtest(df, strategy_name, initial_capital=100000):
    """تشغيل اختبار استراتيجية على بيانات تاريخية"""
    if df is None or df.empty: return None
    
    df = df.copy()
    df['Signal'] = 0
    
    # إعداد المؤشرات البسيطة للاختبار
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    
    # منطق الاستراتيجية
    if strategy_name == "Trend Follower":
        # تقاطع ذهبي: شراء لما متوسط 20 يقطع 50 لأعلى
        df.loc[df['SMA_20'] > df['SMA_50'], 'Signal'] = 1
        df.loc[df['SMA_20'] < df['SMA_50'], 'Signal'] = -1
    else: # Sniper
        # استراتيجية بسيطة: شراء إذا السعر فوق متوسط 20
        df.loc[df['Close'] > df['SMA_20'], 'Signal'] = 1
        df.loc[df['Close'] < df['SMA_20'], 'Signal'] = -1

    # محاكاة المحفظة
    cash = initial_capital
    position = 0
    portfolio_values = []
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        signal = df['Signal'].iloc[i]
        
        if signal == 1 and cash > price: # شراء
            shares_to_buy = cash // price
            position += shares_to_buy
            cash -= shares_to_buy * price
        elif signal == -1 and position > 0: # بيع
            cash += position * price
            position = 0
            
        current_val = cash + (position * price)
        portfolio_values.append(current_val)
        
    df['Portfolio_Value'] = portfolio_values
    final_val = portfolio_values[-1]
    return {
        'final_value': final_val,
        'return_pct': ((final_val - initial_capital) / initial_capital) * 100,
        'df': df
    }

# --- 4. دوال مساعدة ---
def generate_equity_curve(trades_df):
    if trades_df.empty: return pd.DataFrame()
    df = trades_df[['date', 'total_cost']].copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df['cumulative_invested'] = df['total_cost'].cumsum()
    return df

def update_prices():
    from market_data import fetch_batch_data
    trades = fetch_table("Trades")
    wl = fetch_table("Watchlist")
    
    symbols = set()
    if not trades.empty: symbols.update(trades[trades['status']=='Open']['symbol'].unique())
    if not wl.empty: symbols.update(wl['symbol'].unique())
    
    if not symbols: return
    
    data = fetch_batch_data(list(symbols))
    if not data: return
    
    with get_db() as conn:
        with conn.cursor() as cur:
            for s, d in data.items():
                if d['price'] > 0:
                    cur.execute("""
                        UPDATE Trades SET current_price=%s, prev_close=%s 
                        WHERE symbol=%s AND status='Open'
                    """, (d['price'], d['prev_close'], s))
            conn.commit()
