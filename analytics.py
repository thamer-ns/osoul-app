import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from database import fetch_table, execute_query, get_db
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# --- 1. التحليل المالي السريع (SQL Optimization) ---
def get_portfolio_summary_sql():
    """حساب الإجماليات مباشرة من قاعدة البيانات لتسريع الأداء"""
    query = """
    SELECT 
        (SELECT COALESCE(SUM(amount), 0) FROM Deposits) as total_dep,
        (SELECT COALESCE(SUM(amount), 0) FROM Withdrawals) as total_wit,
        (SELECT COALESCE(SUM(amount), 0) FROM ReturnsGrants) as total_ret,
        (SELECT COALESCE(SUM((exit_price - entry_price) * quantity), 0) FROM Trades WHERE status = 'Close') as realized_pl,
        (SELECT COALESCE(SUM(quantity * entry_price), 0) FROM Trades WHERE status = 'Open') as cost_open
    """
    with get_db() as conn:
        if conn:
            with conn.cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()
                if row:
                    return {
                        "total_deposited": row[0],
                        "total_withdrawn": row[1],
                        "total_returns": row[2],
                        "realized_pl": row[3],
                        "cost_open": row[4]
                    }
    return {"total_deposited": 0, "total_withdrawn": 0, "total_returns": 0, "realized_pl": 0, "cost_open": 0}

# --- 2. المحرك الأساسي ---
def calculate_portfolio_metrics():
    # 1. جلب الإجماليات بسرعة البرق من SQL
    sql_sums = get_portfolio_summary_sql()
    
    # 2. جلب جداول البيانات للعرض (نحتاج التفاصيل للجدول فقط)
    trades = fetch_table("Trades")
    dep = fetch_table("Deposits")
    wit = fetch_table("Withdrawals")
    ret = fetch_table("ReturnsGrants")
    
    # تحسين: إذا لم تكن هناك صفقات، نعود مبكراً
    if trades.empty:
        return {
            **sql_sums, "market_val_open": 0, "unrealized_pl": 0, "cash": 0,
            "all_trades": pd.DataFrame(), "deposits": dep, "withdrawals": wit, "returns": ret
        }

    # معالجة الصفقات المفتوحة والمغلقة
    trades['current_price'] = pd.to_numeric(trades['current_price'], errors='coerce').fillna(0.0)
    trades['entry_price'] = pd.to_numeric(trades['entry_price'], errors='coerce').fillna(0.0)
    
    # حساب القيم للسجلات المفتوحة فقط في بايثون (أقل تكلفة من الجدول كامل)
    open_trades = trades[trades['status'] == 'Open'].copy()
    market_val_open = (open_trades['quantity'] * open_trades['current_price']).sum()
    unrealized_pl = market_val_open - sql_sums['cost_open']
    
    # حساب الكاش المتوفر
    # الكاش = (إيداعات + عوائد + مبيعات الأسهم) - (سحوبات + مشتريات الأسهم)
    # معادلة مبسطة: الكاش = (صافي التمويل) + (الربح المحقق) + (رأس المال المسترد من البيع) - (تكلفة الشراء المفتوح)
    # الأسهل: نعتمد على حركة الأموال المسجلة لو أردنا دقة، أو المعادلة التالية:
    
    total_sales_value = trades[trades['status'] == 'Close'].apply(lambda x: x['quantity'] * x['exit_price'], axis=1).sum()
    total_buy_cost_all = (trades['quantity'] * trades['entry_price']).sum()
    
    cash = (sql_sums['total_deposited'] + sql_sums['total_ret'] + total_sales_value) - (sql_sums['total_withdrawn'] + total_buy_cost_all)

    return {
        **sql_sums,
        "market_val_open": market_val_open,
        "unrealized_pl": unrealized_pl,
        "cash": cash,
        "all_trades": trades,
        "deposits": dep,
        "withdrawals": wit,
        "returns": ret
    }

# --- 3. مقاييس المخاطر المتقدمة (Missing Features) ---
def calculate_risk_metrics(symbol_list):
    """حساب Beta و Max Drawdown للمحفظة"""
    if not symbol_list: return {"beta": 0, "sharpe": 0, "max_drawdown": 0}
    
    try:
        # نحتاج بيانات تاريخية للسهم وللسوق (تاسي)
        tickers = [f"{s.replace('.SR','').strip()}.SR" for s in symbol_list]
        tickers.append("^TASI.SR")
        
        # تحميل بيانات سنة
        data = yf.download(tickers, period="1y", progress=False)['Close']
        
        # حساب العوائد اليومية
        returns = data.pct_change().dropna()
        
        if returns.empty: return {"beta": 0, "sharpe": 0, "max_drawdown": 0}

        # 1. حساب Beta (حساسية المحفظة للسوق)
        # نفترض المحفظة متساوية الأوزان للتبسيط هنا
        port_returns = returns.drop(columns=["^TASI.SR"], errors='ignore').mean(axis=1)
        market_returns = returns["^TASI.SR"]
        
        covariance = np.cov(port_returns, market_returns)[0][1]
        market_variance = np.var(market_returns)
        beta = covariance / market_variance if market_variance != 0 else 0
        
        # 2. Sharpe Ratio (العائد مقابل المخاطرة)
        risk_free_rate = 0.05 / 252 # فرضية 5% سنوياً
        excess_returns = port_returns - risk_free_rate
        sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252) if excess_returns.std() != 0 else 0
        
        # 3. Max Drawdown
        cumulative = (1 + port_returns).cumprod()
        peak = cumulative.cummax()
        drawdown = (cumulative - peak) / peak
        max_dd = drawdown.min() * 100
        
        return {
            "beta": round(beta, 2),
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(max_dd, 2)
        }
    except Exception as e:
        logger.error(f"Risk Metrics Error: {e}")
        return {"beta": 0, "sharpe": 0, "max_drawdown": 0}

# دالة لتوليد منحنى السيولة (موجودة سابقاً لكن تأكد من وجودها)
def generate_equity_curve(trades_df):
    if trades_df.empty: return pd.DataFrame()
    df = trades_df[['date', 'total_cost']].copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df['cumulative_invested'] = df['total_cost'].cumsum()
    return df

# دالة تحديث الأسعار (ضرورية)
def update_prices():
    from market_data import fetch_batch_data
    trades = fetch_table("Trades")
    wl = fetch_table("Watchlist")
    
    symbols = set()
    if not trades.empty: symbols.update(trades[trades['status']=='Open']['symbol'].unique())
    if not wl.empty: symbols.update(wl['symbol'].unique())
    
    if not symbols: return
    
    data = fetch_batch_data(list(symbols))
    if not data: return
    
    with get_db() as conn:
        with conn.cursor() as cur:
            for s, d in data.items():
                if d['price'] > 0:
                    cur.execute("""
                        UPDATE Trades SET current_price=%s, prev_close=%s 
                        WHERE symbol=%s AND status='Open'
                    """, (d['price'], d['prev_close'], s))
            conn.commit()
