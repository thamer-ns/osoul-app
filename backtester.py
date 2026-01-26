import pandas as pd
import numpy as np

COMMISSION_RATE = 0.00155  # 0.155%

def calculate_indicators(df):
    df = df.copy().sort_index()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['SMA_50'] = df['Close'].rolling(50).mean()
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def run_backtest(df, strategy, capital=100000):
    if df is None or len(df) < 60: return None
    df = calculate_indicators(df)
    df['Signal'] = 0
    
    if 'Trend' in strategy:
        buy = (df['Close'] > df['SMA_50']) & (df['RSI'] > 50)
        sell = (df['Close'] < df['SMA_50'])
        df.loc[buy, 'Signal'] = 1; df.loc[sell, 'Signal'] = -1
    else: # Sniper
        buy = (df['Close'] > df['SMA_20']) & (df['Close'].shift(1) <= df['SMA_20'].shift(1))
        sell = (df['Close'] < df['SMA_20'])
        df.loc[buy, 'Signal'] = 1; df.loc[sell, 'Signal'] = -1

    cash = capital
    shares = 0
    history = []
    log = []
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i].strftime('%Y-%m-%d')
        sig = df['Signal'].iloc[i]
        
        if sig == 1 and shares == 0:
            invest = cash * 0.98
            shares = int(invest / (price * (1 + COMMISSION_RATE)))
            cost = shares * price * (1 + COMMISSION_RATE)
            cash -= cost
            log.append({'التاريخ': date, 'العملية': 'شراء 🟢', 'السعر': price, 'الكمية': shares, 'الرصيد': round(cash,2)})
            
        elif sig == -1 and shares > 0:
            revenue = shares * price * (1 - COMMISSION_RATE)
            cash += revenue
            shares = 0
            log.append({'التاريخ': date, 'العملية': 'بيع 🔴', 'السعر': price, 'الكمية': 0, 'الرصيد': round(cash,2)})
            
        val = cash + (shares * price)
        history.append(val)
        
    df['Portfolio_Value'] = history
    return {
        'return_pct': ((history[-1]-capital)/capital)*100,
        'final_value': history[-1],
        'trades_log': pd.DataFrame(log),
        'df': df
    }
