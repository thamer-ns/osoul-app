import pandas as pd
import numpy as np

def calculate_indicators(df):
    """إضافة المؤشرات الفنية بناءً على كتاب جون ميرفي"""
    df = df.copy()
    df = df.sort_index(ascending=True)
    
    # المتوسطات المتحركة (لتحديد الاتجاه)
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    
    # مؤشر الزخم RSI (لتأكيد الدخول)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    return df

def run_backtest(df, strategy_type, initial_capital=100000):
    """تنفيذ الاختبار التاريخي للاستراتيجيات"""
    if df is None or df.empty or len(df) < 55:
        return None

    # حساب المؤشرات
    df = calculate_indicators(df)
    df['Signal'] = 0 # 0: محايد، 1: شراء، -1: بيع
    
    # === تطبيق الخوارزميات المستخلصة من الكتب ===
    
    if strategy_type == 'Trend Follower (جون ميرفي)':
        # استراتيجية تتبع الاتجاه الكلاسيكية
        # شراء: السعر فوق متوسط 50 + زخم إيجابي (RSI > 50)
        buy_cond = (df['Close'] > df['SMA_50']) & (df['RSI'] > 50)
        # بيع: كسر الاتجاه (الإغلاق تحت المتوسط)
        sell_cond = (df['Close'] < df['SMA_50'])
        
        df.loc[buy_cond, 'Signal'] = 1
        df.loc[sell_cond, 'Signal'] = -1

    elif strategy_type == 'Sniper (هجين)':
        # استراتيجية المضاربة السريعة (تتطلب سهم قوي مالياً كشرط مسبق)
        # الدخول عند اختراق متوسط 20 (بداية موجة)
        buy_cond = (df['Close'] > df['SMA_20']) & (df['Close'].shift(1) <= df['SMA_20'].shift(1))
        # الخروج عند كسر المتوسط
        sell_cond = (df['Close'] < df['SMA_20'])
        
        df.loc[buy_cond, 'Signal'] = 1
        df.loc[sell_cond, 'Signal'] = -1

    # === محاكاة المحفظة ===
    cash = initial_capital
    position = 0
    portfolio_values = []
    trades = []
    in_position = False
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        signal = df['Signal'].iloc[i]
        
        # إذا لم يكن السعر متاحاً (NaN) تخطى
        if pd.isna(price):
            portfolio_values.append(cash)
            continue

        # تنفيذ الشراء
        if signal == 1 and not in_position:
            # نشتري بـ 95% من الكاش لترك هامش للعمولات
            cost = cash * 0.95
            position = cost / price
            cash -= cost
            in_position = True
            trades.append({
                'التاريخ': date.strftime('%Y-%m-%d'), 
                'العملية': 'شراء 🟢', 
                'السعر': round(price, 2), 
                'الرصيد': round(cash + (position*price), 2)
            })
            
        # تنفيذ البيع
        elif signal == -1 and in_position:
            cash += position * price
            current_balance = cash
            trades.append({
                'التاريخ': date.strftime('%Y-%m-%d'), 
                'العملية': 'بيع 🔴', 
                'السعر': round(price, 2), 
                'الرصيد': round(current_balance, 2)
            })
            position = 0
            in_position = False
            
        # تحديث قيمة المحفظة اليومية
        current_val = cash + (position * price)
        portfolio_values.append(current_val)
        
    df['Portfolio_Value'] = portfolio_values
    
    final_val = portfolio_values[-1]
    ret_pct = ((final_val - initial_capital) / initial_capital) * 100
    
    return {
        'df': df,
        'final_value': final_val,
        'return_pct': ret_pct,
        'trades_count': len(trades),
        'trades_log': pd.DataFrame(trades)
    }
