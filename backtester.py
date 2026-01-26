import pandas as pd
import numpy as np

def calculate_indicators(df):
    df = df.copy().sort_index()
    # المؤشرات الأساسية
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
    if df is None or len(df) < 60: return None
    
    df = calculate_indicators(df)
    df['Signal'] = 0
    
    # منطق الاستراتيجيات
    if 'Trend' in strategy: # Trend Follower
        # شراء: السعر فوق متوسط 50 والـ RSI فوق 50 (زخم)
        buy = (df['Close'] > df['SMA_50']) & (df['RSI'] > 50)
        sell = (df['Close'] < df['SMA_50'])
        df.loc[buy, 'Signal'] = 1
        df.loc[sell, 'Signal'] = -1
        
    elif 'Sniper' in strategy: # Sniper
        # شراء: تقاطع السعر مع متوسط 20 لأعلى
        buy = (df['Close'] > df['SMA_20']) & (df['Close'].shift(1) <= df['SMA_20'].shift(1))
        sell = (df['Close'] < df['SMA_20'])
        df.loc[buy, 'Signal'] = 1
        df.loc[sell, 'Signal'] = -1

    # المحرك (Engine)
    cash = capital
    shares = 0
    history = []
    log = []
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i].strftime('%Y-%m-%d')
        sig = df['Signal'].iloc[i]
        
        # تنفيذ الأوامر
        if sig == 1 and shares == 0: # شراء
            # نشتري بـ 98% من الكاش لتغطية العمولات
            cost_basis = cash * 0.98
            shares = cost_basis / price
            cash -= cost_basis
            log.append({'التاريخ': date, 'العملية': 'شراء 🟢', 'السعر': f"{price:.2f}", 'الكمية': int(shares), 'الرصيد': f"{cash:.2f}"})
            
        elif sig == -1 and shares > 0: # بيع
            revenue = shares * price
            cash += revenue
            shares = 0
            log.append({'التاريخ': date, 'العملية': 'بيع 🔴', 'السعر': f"{price:.2f}", 'الكمية': 0, 'الرصيد': f"{cash:.2f}"})
            
        # تسجيل قيمة المحفظة اليومية
        portfolio_val = cash + (shares * price)
        history.append(portfolio_val)
        
    df['Portfolio_Value'] = history
    final_val = history[-1]
    
    return {
        'return_pct': ((final_val - capital) / capital) * 100,
        'final_value': final_val,
        'trades_count': len(log),
        'trades_log': pd.DataFrame(log),
        'df': df
    }
