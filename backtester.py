import pandas as pd
import numpy as np

def calculate_indicators(df):
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    return df

def run_backtest(df, strategy_type, initial_capital=100000):
    if df is None or df.empty: return None
    
    df = calculate_indicators(df)
    df['Portfolio_Value'] = initial_capital # تبسيط للكود
    
    # منطق وهمي سريع للتجربة
    final_val = initial_capital * 1.05
    
    return {
        'df': df,
        'final_value': final_val,
        'return_pct': 5.0,
        'trades_log': pd.DataFrame()
    }
