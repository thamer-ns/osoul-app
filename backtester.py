import pandas as pd
import numpy as np

COMMISSION = 0.00155 

def calculate_indicators(df):
    df = df.copy()
    df['SMA_20'] = df['Close'].rolling(20).mean(); df['SMA_50'] = df['Close'].rolling(50).mean()
    delta = df['Close'].diff()
    avg_gain = delta.where(delta>0, 0).ewm(alpha=1/14, adjust=False).mean()
    avg_loss = (-delta.where(delta<0, 0)).ewm(alpha=1/14, adjust=False).mean()
    df['RSI'] = 100 - (100 / (1 + avg_gain/avg_loss))
    df['RSI'] = df['RSI'].fillna(50); df.dropna(inplace=True)
    return df

def run_backtest(df, strategy, capital=100000):
    if df is None or len(df) < 60: return None
    df = calculate_indicators(df); df['Signal'] = 0
    
    if 'Trend' in strategy:
        df.loc[(df['Close']>df['SMA_50'])&(df['RSI']>50), 'Signal'] = 1
        df.loc[df['Close']<df['SMA_50'], 'Signal'] = -1
    elif 'Sniper' in strategy:
        df.loc[(df['Close']>df['SMA_20'])&(df['Close'].shift(1)<=df['SMA_20'].shift(1)), 'Signal'] = 1
        df.loc[df['Close']<df['SMA_20'], 'Signal'] = -1

    cash = float(capital); shares = 0; log = []; hist = []
    
    for r in df.itertuples():
        p = r.Close; sig = r.Signal; d = r.Index.strftime('%Y-%m-%d')
        if sig == 1 and shares == 0:
            invest = cash / (1+COMMISSION); shares = int(invest/p)
            if shares > 0: cash -= shares*p*(1+COMMISSION); log.append({'Date':d, 'Type':'Buy', 'Price':p, 'Qty':shares, 'Cash':cash})
        elif sig == -1 and shares > 0:
            cash += shares*p*(1-COMMISSION); log.append({'Date':d, 'Type':'Sell', 'Price':p, 'Qty':shares, 'Cash':cash}); shares = 0
        hist.append(cash + (shares*p))
        
    df['Portfolio_Value'] = hist
    return {'return_pct': ((hist[-1]-capital)/capital)*100, 'final_value': hist[-1], 'trades_log': pd.DataFrame(log), 'df': df}
