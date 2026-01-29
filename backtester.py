import pandas as pd
import numpy as np

# العمولة شاملة الضريبة تقريباً لضمان التحوط
COMMISSION = 0.00178  

def calculate_indicators(df):
    df = df.copy()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['SMA_50'] = df['Close'].rolling(50).mean()
    
    delta = df['Close'].diff()
    avg_gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
    avg_loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    
    # حماية من القسمة على صفر
    rs = avg_gain / avg_loss
    rs = rs.replace([np.inf, -np.inf], np.nan) # استبدال اللانهاية
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['RSI'] = df['RSI'].fillna(50)
    df.dropna(inplace=True)
    return df

def run_backtest(df, strategy, capital=100000):
    if df is None or len(df) < 60: return None
    df = calculate_indicators(df)
    df['Signal'] = 0
    
    # توليد الإشارات
    if 'Trend' in strategy:
        condition_buy = (df['Close'] > df['SMA_50']) & (df['RSI'] > 50)
        condition_sell = (df['Close'] < df['SMA_50'])
    elif 'Sniper' in strategy:
        condition_buy = (df['Close'] > df['SMA_20']) & (df['Close'].shift(1) <= df['SMA_20'].shift(1))
        condition_sell = (df['Close'] < df['SMA_20'])
    else:
        return None

    df.loc[condition_buy, 'Signal'] = 1
    df.loc[condition_sell, 'Signal'] = -1
    
    # === تصحيح التحيز للمستقبل ===
    # الإشارة اليوم تنفذ غداً، لذا نزيح الإشارة يوماً واحداً للأمام
    df['Trade_Signal'] = df['Signal'].shift(1).fillna(0)
    
    cash = float(capital)
    shares = 0
    log = []
    hist = []
    
    for r in df.itertuples():
        # التنفيذ يتم على سعر الافتتاح (Open) لليوم التالي للإشارة
        # لضمان واقعية الاختبار
        # ملاحظة: إذا كنت تريد التنفيذ على الإغلاق، ابق على Close لكن كن واعياً بالتحيز
        # سنستخدم Open هنا للدقة، أو يمكنك استخدام Close مع علمك بالمخاطرة
        
        p = r.Open # تغيير السعر إلى الافتتاح لزيادة الواقعية
        sig = r.Trade_Signal # استخدام الإشارة المزاحة
        d = r.Index.strftime('%Y-%m-%d')
        
        # منطق التداول
        if sig == 1 and shares == 0:
            invest = cash / (1 + COMMISSION)
            shares = int(invest / p)
            if shares > 0:
                cost = shares * p * (1 + COMMISSION)
                cash -= cost
                log.append({'Date': d, 'Type': 'Buy', 'Price': p, 'Qty': shares, 'Cash': cash, 'Value': cost})
                
        elif sig == -1 and shares > 0:
            revenue = shares * p * (1 - COMMISSION)
            cash += revenue
            log.append({'Date': d, 'Type': 'Sell', 'Price': p, 'Qty': shares, 'Cash': cash, 'Value': revenue})
            shares = 0
            
        # تقييم المحفظة يومياً يتم على سعر الإغلاق (Mark to Market)
        current_val = cash + (shares * r.Close)
        hist.append(current_val)
        
    df['Portfolio_Value'] = hist
    
    # حماية في حال كانت القائمة فارغة
    final_val = hist[-1] if hist else capital
    
    return {
        'return_pct': ((final_val - capital) / capital) * 100,
        'final_value': final_val,
        'trades_log': pd.DataFrame(log),
        'df': df
    }
