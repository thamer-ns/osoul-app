import pandas as pd
import numpy as np

# نسبة العمولة (0.155% شاملة ضريبة القيمة المضافة)
COMMISSION_RATE = 0.00155 

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
    position_qty = 0 # عدد الأسهم المملوكة
    portfolio_values = []
    trades = []
    in_position = False
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        signal = df['Signal'].iloc[i]
        
        if pd.isna(price): portfolio_values.append(cash); continue

        # === منطق الشراء (مع خصم العمولة) ===
        if signal == 1 and not in_position:
            # نخصص 98% من الكاش للشراء (لترك هامش للعمولات وتغير السعر)
            invest_amount = cash * 0.98
            
            # حساب التكلفة شاملة العمولة
            # المبلغ المطلوب = (الكمية * السعر) * (1 + نسبة العمولة)
            # إذاً الكمية = المبلغ المستثمر / (السعر * (1 + نسبة العمولة))
            qty = int(invest_amount / (price * (1 + COMMISSION_RATE)))
            
            if qty > 0:
                trade_value = qty * price
                commission = trade_value * COMMISSION_RATE
                total_cost = trade_value + commission
                
                if cash >= total_cost:
                    cash -= total_cost
                    position_qty = qty
                    in_position = True
                    trades.append({
                        'التاريخ': date.strftime('%Y-%m-%d'),
                        'العملية': 'شراء 🟢',
                        'السعر': round(price, 2),
                        'الكمية': qty,
                        'العمولة': round(commission, 2),
                        'الرصيد': round(cash + (position_qty * price), 2)
                    })
            
        # === منطق البيع (مع خصم العمولة) ===
        elif signal == -1 and in_position:
            sale_value = position_qty * price
            commission = sale_value * COMMISSION_RATE
            net_profit = sale_value - commission
            
            cash += net_profit
            trades.append({
                'التاريخ': date.strftime('%Y-%m-%d'),
                'العملية': 'بيع 🔴',
                'السعر': round(price, 2),
                'الكمية': position_qty,
                'العمولة': round(commission, 2),
                'الرصيد': round(cash, 2)
            })
            position_qty = 0
            in_position = False
            
        # حساب قيمة المحفظة اللحظية (كاش + قيمة سوقية للأسهم)
        current_equity = cash + (position_qty * price)
        portfolio_values.append(current_equity)
        
    df['Portfolio_Value'] = portfolio_values
    
    final_val = portfolio_values[-1]
    return {
        'df': df,
        'final_value': final_val,
        'return_pct': ((final_val - initial_capital) / initial_capital) * 100,
        'trades_count': len(trades),
        'trades_log': pd.DataFrame(trades)
    }
