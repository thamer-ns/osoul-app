import pandas as pd
import numpy as np

def calculate_indicators(df):
    df = df.copy()
    df = df.sort_index(ascending=True)
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def run_backtest(df, strategy_type, initial_capital=100000):
    if df is None or df.empty or len(df) < 55: return None
    df = calculate_indicators(df)
    df['Signal'] = 0
    
    if strategy_type == 'Trend Follower (جون ميرفي)':
        buy_cond = (df['Close'] > df['SMA_50']) & (df['RSI'] > 50)
        sell_cond = (df['Close'] < df['SMA_50'])
        df.loc[buy_cond, 'Signal'] = 1
        df.loc[sell_cond, 'Signal'] = -1

    elif strategy_type == 'Sniper (هجين)':
        buy_cond = (df['Close'] > df['SMA_20']) & (df['Close'].shift(1) <= df['SMA_20'].shift(1))
        sell_cond = (df['Close'] < df['SMA_20'])
        df.loc[buy_cond, 'Signal'] = 1
        df.loc[sell_cond, 'Signal'] = -1

    cash = initial_capital
    position = 0
    portfolio_values = []
    trades = []
    in_position = False
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        signal = df['Signal'].iloc[i]
        
        if pd.isna(price): portfolio_values.append(cash); continue

        if signal == 1 and not in_position:
            cost = cash * 0.95
            position = cost / price
            cash -= cost
            in_position = True
            trades.append({'التاريخ': date.strftime('%Y-%m-%d'), 'العملية': 'شراء 🟢', 'السعر': round(price, 2), 'الرصيد': round(cash + (position*price), 2)})
            
        elif signal == -1 and in_position:
            cash += position * price
            trades.append({'التاريخ': date.strftime('%Y-%m-%d'), 'العملية': 'بيع 🔴', 'السعر': round(price, 2), 'الرصيد': round(cash, 2)})
            position = 0
            in_position = False
            
        portfolio_values.append(cash + (position * price))
        
    df['Portfolio_Value'] = portfolio_values
    return {'df': df, 'final_value': portfolio_values[-1], 'return_pct': ((portfolio_values[-1] - initial_capital) / initial_capital) * 100, 'trades_count': len(trades), 'trades_log': pd.DataFrame(trades)}
