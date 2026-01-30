import pandas as pd
import numpy as np
from config import COMMISSION_RATE


def calculate_indicators(df):
    df = df.copy()

    # تأكد من الترتيب الزمني
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.sort_index()

    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['SMA_50'] = df['Close'].rolling(50).mean()

    delta = df['Close'].diff()
    avg_gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
    avg_loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()

    # حماية من القسمة على صفر / اللانهاية
    rs = avg_gain / avg_loss
    rs = rs.replace([np.inf, -np.inf], np.nan)

    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI'] = df['RSI'].fillna(50)

    # لا نحذف كل شيء — لكن نحذف الصفوف اللي لازمها المؤشرات
    df.dropna(subset=['SMA_20', 'SMA_50', 'RSI'], inplace=True)

    return df


def run_backtest(df, strategy, capital=100000):
    if df is None or len(df) < 60:
        return None

    # تحصين الأعمدة
    required_cols = {'Open', 'Close', 'High', 'Low', 'Volume'}
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        # أقل تحصين: لو Open ناقص نستخدم Close
        if 'Open' in missing and 'Close' in df.columns:
            df = df.copy()
            df['Open'] = df['Close']
            missing.remove('Open')
        if missing:
            return None

    df = calculate_indicators(df)
    if df.empty or len(df) < 10:
        return None

    df['Signal'] = 0

    # توليد الإشارات (نفس منطقك)
    strategy = str(strategy or "")

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

    # ✅ تصحيح التحيز للمستقبل
    df['Trade_Signal'] = df['Signal'].shift(1).fillna(0)

    cash = float(capital)
    shares = 0
    log = []
    hist = []

    COMMISSION = float(COMMISSION_RATE or 0.0)

    for r in df.itertuples():
        # تنفيذ على Open (واقعي) + تقييم يومي على Close
        p = float(getattr(r, 'Open', r.Close))
        sig = float(getattr(r, 'Trade_Signal', 0))
        d = r.Index.strftime('%Y-%m-%d') if hasattr(r.Index, 'strftime') else str(r.Index)

        if p <= 0:
            current_val = cash + (shares * float(r.Close))
            hist.append(current_val)
            continue

        # شراء
        if sig == 1 and shares == 0:
            invest = cash / (1 + COMMISSION)
            shares_to_buy = int(invest / p)

            if shares_to_buy > 0:
                cost = shares_to_buy * p * (1 + COMMISSION)
                cash -= cost
                shares = shares_to_buy
                log.append({'Date': d, 'Type': 'Buy', 'Price': p, 'Qty': shares, 'Cash': cash, 'Value': cost})

        # بيع
        elif sig == -1 and shares > 0:
            revenue = shares * p * (1 - COMMISSION)
            cash += revenue
            log.append({'Date': d, 'Type': 'Sell', 'Price': p, 'Qty': shares, 'Cash': cash, 'Value': revenue})
            shares = 0

        # Mark-to-market
        current_val = cash + (shares * float(r.Close))
        hist.append(current_val)

    df['Portfolio_Value'] = hist

    final_val = hist[-1] if hist else float(capital)
    ret_pct = ((final_val - float(capital)) / float(capital)) * 100

    return {
        'return_pct': ret_pct,
        'final_value': final_val,
        'trades_log': pd.DataFrame(log),
        'df': df
    }
