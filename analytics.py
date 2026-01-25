import pandas as pd
import numpy as np
import yfinance as yf
from database import fetch_table, get_db
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# --- 1. التحليل المالي السريع (SQL Optimization) ---
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
                    if row:
                        return {
                            "total_deposited": float(row[0]), "total_withdrawn": float(row[1]),
                            "total_returns": float(row[2]), "realized_pl": float(row[3]), "cost_open": float(row[4])
                        }
                except: pass
    return {"total_deposited": 0.0, "total_withdrawn": 0.0, "total_returns": 0.0, "realized_pl": 0.0, "cost_open": 0.0}

# --- 2. المحرك الأساسي ---
def calculate_portfolio_metrics():
    sql_sums = get_portfolio_summary_sql()
    
    # جلب البيانات
    trades = fetch_table("Trades")
    dep = fetch_table("Deposits")
    wit = fetch_table("Withdrawals")
    ret = fetch_table("ReturnsGrants")
    
    # ضمان وجود الأعمدة الأساسية
    if 'amount' not in dep.columns: dep['amount'] = 0.0
    if 'amount' not in wit.columns: wit['amount'] = 0.0
    if 'amount' not in ret.columns: ret['amount'] = 0.0

    if trades.empty:
        return {
            **sql_sums, "market_val_open": 0, "unrealized_pl": 0, "cash": 0, "equity": 0,
            "all_trades": pd.DataFrame(columns=['symbol', 'company_name', 'sector', 'status', 'strategy', 'date', 'quantity', 'entry_price', 'exit_price', 'current_price', 'market_value', 'total_cost', 'gain', 'dividend_yield']), 
            "deposits": dep, "withdrawals": wit, "returns": ret,
            "cost_closed": 0, "sales_closed": 0, "projected_dividend_income": 0
        }

    # تحويل الأرقام لضمان عدم حدوث خطأ
    cols_to_numeric = ['quantity', 'entry_price', 'current_price', 'exit_price', 'dividend_yield']
    for col in cols_to_numeric:
        if col in trades.columns:
            trades[col] = pd.to_numeric(trades[col], errors='coerce').fillna(0.0)
        else:
            trades[col] = 0.0
    
    # معالجة الحالة
    condition_closed = (trades['exit_price'] > 0) | (trades['status'].astype(str).str.lower().isin(['close', 'sold', 'مغلقة', 'مباعة']))
    trades['status'] = np.where(condition_closed, 'Close', 'Open')

    # الحسابات
    open_trades = trades[trades['status'] == 'Open'].copy()
    market_val_open = (open_trades['quantity'] * open_trades['current_price']).sum()
    unrealized_pl = market_val_open - sql_sums['cost_open']
    
    # التوزيعات المتوقعة (الميزة الجديدة من logic.py)
    trades['projected_annual_income'] = trades['quantity'] * trades['current_price'] * trades['dividend_yield']
    projected_dividend_income = open_trades['projected_annual_income'].sum()

    # الكاش
    total_sales = trades[trades['status'] == 'Close'].apply(lambda x: x['quantity'] * x['exit_price'], axis=1).sum()
    total_purchases = (trades['quantity'] * trades['entry_price']).sum()
    cash = (sql_sums['total_deposited'] + sql_sums['total_ret'] + total_sales) - (sql_sums['total_withdrawn'] + total_purchases)
    
    # أعمدة العرض للجدول
    trades['total_cost'] = trades['quantity'] * trades['entry_price']
    
    # للصفقات المغلقة، القيمة الحالية هي سعر البيع
    is_closed = trades['status'] == 'Close'
    trades.loc[is_closed, 'current_price'] = trades.loc[is_closed, 'exit_price']
    
    trades['market_value'] = trades['quantity'] * trades['current_price']
    trades['gain'] = trades['market_value'] - trades['total_cost']
    
    # نسب الربح
    trades['gain_pct'] = 0.0
    mask_cost = trades['total_cost'] != 0
    trades.loc[mask_cost, 'gain_pct'] = (trades.loc[mask_cost, 'gain'] / trades.loc[mask_cost, 'total_cost']) * 100

    cost_closed = trades.loc[is_closed, 'total_cost'].sum()
    
    return {
        **sql_sums,
        "market_val_open": market_val_open,
        "unrealized_pl": unrealized_pl,
        "cash": cash,
        "equity": cash + market_val_open,
        "cost_closed": cost_closed,
        "sales_closed": total_sales,
        "projected_dividend_income": projected_dividend_income,
        "all_trades": trades,
        "deposits": dep,
        "withdrawals": wit,
        "returns": ret
    }

# --- 3. دالة المختبر (تمت إضافتها لإصلاح الخطأ) ---
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
                    # تحديث التوزيعات أيضاً إذا توفرت
                    cur.execute("UPDATE Trades SET current_price=%s, prev_close=%s, year_high=%s, year_low=%s, dividend_yield=%s WHERE symbol=%s AND status='Open'", 
                                (d['price'], d['prev_close'], d['year_high'], d['year_low'], d.get('dividend_yield',0), s))
            conn.commit()
def generate_equity_curve(df): return pd.DataFrame()
