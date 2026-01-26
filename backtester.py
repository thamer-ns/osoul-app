import pandas as pd
import numpy as np

def calculate_indicators(df):
    df = df.copy().sort_index()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['SMA_50'] = df['Close'].rolling(50).mean()
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def run_backtest(df, strategy, capital=100000):
    if df is None or len(df) < 55: return None
    df = calculate_indicators(df)
    df['Signal'] = 0
    
    # الاستراتيجيات
    if 'Trend' in strategy: # Trend Follower
        buy = (df['Close'] > df['SMA_50']) & (df['RSI'] > 50)
        sell = (df['Close'] < df['SMA_50'])
        df.loc[buy, 'Signal'] = 1
        df.loc[sell, 'Signal'] = -1
    else: # Sniper
        buy = (df['Close'] > df['SMA_20']) & (df['Close'].shift(1) <= df['SMA_20'].shift(1))
        sell = (df['Close'] < df['SMA_20'])
        df.loc[buy, 'Signal'] = 1
        df.loc[sell, 'Signal'] = -1

    # المحاكاة
    cash = capital
    position = 0
    history = []
    log = []
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        sig = df['Signal'].iloc[i]
        
        if sig == 1 and position == 0: # شراء
            cost = cash * 0.98 # عمولة واحتياط
            position = cost / price
            cash -= cost
            log.append({'التاريخ': date.date(), 'العملية': 'شراء 🟢', 'السعر': round(price,2), 'الرصيد': round(cash + position*price, 2)})
        
        elif sig == -1 and position > 0: # بيع
            cash += position * price
            log.append({'التاريخ': date.date(), 'العملية': 'بيع 🔴', 'السعر': round(price,2), 'الرصيد': round(cash, 2)})
            position = 0
            
        history.append(cash + (position * price))
        
    df['Portfolio_Value'] = history
    final_val = history[-1]
    
    return {
        'return_pct': ((final_val - capital)/capital)*100,
        'final_value': final_val,
        'df': df,
        'trades_log': pd.DataFrame(log)
    }
