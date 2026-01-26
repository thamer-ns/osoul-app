import pandas as pd
import numpy as np

COMMISSION_RATE = 0.00155  # 0.155% عمولة + ضريبة

def calculate_indicators(df):
    df = df.copy().sort_index()
    # المتوسطات
    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['SMA_50'] = df['Close'].rolling(50).mean()
    
    # RSI (Relative Strength Index)
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
    if 'Trend' in strategy: # تتبع الاتجاه
        # شراء: السعر فوق متوسط 50 والزخم قوي
        buy_cond = (df['Close'] > df['SMA_50']) & (df['RSI'] > 50)
        sell_cond = (df['Close'] < df['SMA_50'])
        
        df.loc[buy_cond, 'Signal'] = 1
        df.loc[sell_cond, 'Signal'] = -1
        
    elif 'Sniper' in strategy: # قناص (تقاطعات)
        # شراء: اختراق متوسط 20
        buy_cond = (df['Close'] > df['SMA_20']) & (df['Close'].shift(1) <= df['SMA_20'].shift(1))
        sell_cond = (df['Close'] < df['SMA_20'])
        
        df.loc[buy_cond, 'Signal'] = 1
        df.loc[sell_cond, 'Signal'] = -1

    # محرك المحاكاة
    cash = capital
    shares = 0
    history = []
    log = []
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i].strftime('%Y-%m-%d')
        sig = df['Signal'].iloc[i]
        
        # تنفيذ الشراء
        if sig == 1 and shares == 0:
            # حساب الكمية الممكن شراؤها (مع خصم العمولة)
            investable_cash = cash / (1 + COMMISSION_RATE)
            shares = int(investable_cash / price)
            cost = shares * price * (1 + COMMISSION_RATE)
            
            if shares > 0:
                cash -= cost
                log.append({
                    'التاريخ': date, 'العملية': 'شراء 🟢', 
                    'السعر': round(price, 2), 'الكمية': shares, 
                    'الرصيد': round(cash, 2)
                })
            
        # تنفيذ البيع
        elif sig == -1 and shares > 0:
            revenue = shares * price * (1 - COMMISSION_RATE)
            cash += revenue
            shares = 0
            log.append({
                'التاريخ': date, 'العملية': 'بيع 🔴', 
                'السعر': round(price, 2), 'الكمية': 0, 
                'الرصيد': round(cash, 2)
            })
            
        # تسجيل قيمة المحفظة اليومية (كاش + قيمة أسهم)
        portfolio_value = cash + (shares * price)
        history.append(portfolio_value)
        
    df['Portfolio_Value'] = history
    final_val = history[-1]
    return {
        'return_pct': ((final_val - capital) / capital) * 100,
        'final_value': final_val,
        'trades_log': pd.DataFrame(log),
        'df': df
    }
