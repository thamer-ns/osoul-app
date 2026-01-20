import pandas as pd
import numpy as np

# 1. دوال المساعدة لحساب المؤشرات الفنية
def calculate_indicators(df):
    """إضافة المؤشرات الفنية للبيانات"""
    df = df.copy()
    # التأكد من ترتيب التاريخ
    df = df.sort_index(ascending=True)
    
    # متوسطات متحركة
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    
    # مؤشر RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    return df

# 2. محرك الاختبار (The Engine)
def run_backtest(df, strategy_type, initial_capital=100000):
    """
    تنفيذ الاختبار التاريخي
    df: بيانات السهم (Date, Open, High, Low, Close)
    strategy_type: نوع الاستراتيجية ('Trend', 'Sniper')
    """
    if df.empty or len(df) < 50:
        return None

    # تجهيز البيانات
    df = calculate_indicators(df)
    df['Signal'] = 0 # 0: لا شيء، 1: شراء، -1: بيع
    
    # --- تطبيق الخوارزميات ---
    
    if strategy_type == 'Trend Follower (جون ميرفي)':
        # شراء: السعر فوق متوسط 50 + RSI فوق 50
        buy_condition = (df['Close'] > df['SMA_50']) & (df['RSI'] > 50)
        # بيع: كسر متوسط 50
        sell_condition = (df['Close'] < df['SMA_50'])
        
        df.loc[buy_condition, 'Signal'] = 1
        df.loc[sell_condition, 'Signal'] = -1

    elif strategy_type == 'Sniper (هجين)':
        # استراتيجية سريعة: تقاطع السعر فوق متوسط 20 (دخول)
        # ملاحظة: التحليل المالي يتم تصفيته قبل استدعاء هذه الدالة
        buy_condition = (df['Close'] > df['SMA_20']) & (df['Close'].shift(1) <= df['SMA_20'].shift(1))
        # خروج: كسر متوسط 20
        sell_condition = (df['Close'] < df['SMA_20'])
        
        df.loc[buy_condition, 'Signal'] = 1
        df.loc[sell_condition, 'Signal'] = -1

    # --- محاكاة المحفظة ---
    cash = initial_capital
    position = 0 # عدد الأسهم
    portfolio_values = []
    trades = []
    
    in_position = False
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        signal = df['Signal'].iloc[i]
        
        # تنفيذ الشراء
        if signal == 1 and not in_position:
            position = (cash * 0.98) / price # نشتري بـ 98% من الكاش (لترك هامش)
            cash = cash - (position * price)
            in_position = True
            trades.append({'date': date, 'type': 'شراء', 'price': price, 'balance': cash + (position*price)})
            
        # تنفيذ البيع
        elif signal == -1 and in_position:
            cash = cash + (position * price)
            position = 0
            in_position = False
            trades.append({'date': date, 'type': 'بيع', 'price': price, 'balance': cash})
            
        # تسجيل قيمة المحفظة اليومية
        current_val = cash + (position * price)
        portfolio_values.append(current_val)
        
    df['Portfolio_Value'] = portfolio_values
    
    # حساب النتائج النهائية
    final_value = portfolio_values[-1]
    total_return = ((final_value - initial_capital) / initial_capital) * 100
    
    return {
        'df': df,
        'final_value': final_value,
        'return_pct': total_return,
        'trades_count': len(trades),
        'trades_log': pd.DataFrame(trades)
    }
