import pandas as pd
import numpy as np
from database import fetch_table, execute_query
from market_data import fetch_batch_data
import streamlit as st
import logging
from datetime import datetime, timedelta
import pytz # مكتبة التوقيت

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# === ضبط توقيت السعودية ===
KSA_TZ = pytz.timezone('Asia/Riyadh')

# === تحديث الأسعار (المقيد بالوقت والفاصل الزمني) ===
def update_prices():
    try:
        # 1. التحقق من الوقت (السوق السعودي 10:00 ص - 04:00 م)
        now_ksa = datetime.now(KSA_TZ)
        market_open = now_ksa.replace(hour=10, minute=0, second=0, microsecond=0)
        market_close = now_ksa.replace(hour=16, minute=0, second=0, microsecond=0)
        
        # إذا كان الوقت الحالي خارج أوقات التداول
        if not (market_open <= now_ksa <= market_close):
            # نسمح بالتحديث مرة واحدة فقط بعد الإغلاق لضمان تثبيت سعر الإغلاق، 
            # لكن حسب طلبك: "بعدها يكتفى بسعر الاغلاق"، لذا سنوقف التحديث تماماً.
            # يمكنك إرجاع True وهمي لعدم إظهار خطأ للمستخدم
            st.toast("⚠️ السوق مغلق حالياً. يتم عرض أسعار الإغلاق.", icon="🌙")
            return False

        # 2. التحقق من فاصل الـ 15 دقيقة (Throttling)
        if 'last_update_time' in st.session_state:
            last_run = st.session_state['last_update_time']
            diff = (now_ksa - last_run).total_seconds() / 60
            if diff < 15:
                st.toast(f"⏳ تم التحديث قبل {int(diff)} دقيقة. التحديث متاح كل 15 دقيقة.", icon="wait")
                return False

        # 3. جلب الرموز المفتوحة فقط لتحديثها
        trades = fetch_table("Trades")
        wl = fetch_table("Watchlist")
        
        symbols = set()
        if not trades.empty:
            # نحدث فقط الصفقات المفتوحة (Open)
            open_symbols = trades.loc[trades['status'] == 'Open', 'symbol'].dropna().unique().tolist()
            symbols.update(open_symbols)
            
        if not wl.empty:
            symbols.update(wl['symbol'].dropna().unique().tolist())
            
        if not symbols: return False
        
        # 4. جلب الأسعار من المصدر
        data = fetch_batch_data(list(symbols))
        if not data: return False
        
        # 5. التحديث في قاعدة البيانات
        from database import get_db
        with get_db() as conn:
            with conn.cursor() as cur:
                for s, d in data.items():
                    if d['price'] > 0:
                        # تحديث السعر الحالي والإغلاق السابق
                        cur.execute("""
                            UPDATE Trades 
                            SET current_price=%s, prev_close=%s, year_high=%s, year_low=%s 
                            WHERE symbol=%s AND status = 'Open'
                        """, (d['price'], d['prev_close'], d['year_high'], d['year_low'], str(s)))
                conn.commit()
        
        # تسجيل وقت التحديث الناجح
        st.session_state['last_update_time'] = now_ksa
        st.cache_data.clear() # مسح الكاش لرؤية الأسعار الجديدة
        st.toast("✅ تم تحديث الأسعار بنجاح", icon="🚀")
        return True

    except Exception as e:
        logger.error(f"Update prices error: {e}")
        return False

# === الحسابات المالية الدقيقة ===
@st.cache_data(ttl=60) # الكاش دقيقة واحدة لتسريع التصفح
def calculate_portfolio_metrics():
    try:
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")

        # هيكل فارغ في حال عدم وجود بيانات
        empty_res = {
            "cost_open": 0, "market_val_open": 0, "cash": 0, 
            "all_trades": pd.DataFrame(), "unrealized_pl": 0, "realized_pl": 0, 
            "total_deposited": 0, "total_withdrawn": 0, "total_returns": 0,
            "deposits": dep, "withdrawals": wit, "returns": ret
        }

        if trades.empty and dep.empty: return empty_res

        # تحويل الأرقام (مهم جداً للحسابات)
        num_cols = ['quantity', 'entry_price', 'current_price', 'exit_price']
        for c in num_cols:
            if c in trades.columns:
                trades[c] = pd.to_numeric(trades[c], errors='coerce').fillna(0.0)

        # 1. حسابات الصفقات المفتوحة
        open_trades = trades[trades['status'] == 'Open'].copy()
        
        # التكلفة = الكمية * سعر الشراء
        open_trades['total_cost'] = open_trades['quantity'] * open_trades['entry_price']
        
        # القيمة السوقية = الكمية * السعر الحالي (الذي يتم تحديثه)
        open_trades['market_value'] = open_trades['quantity'] * open_trades['current_price']
        
        # الربح غير المحقق
        open_trades['gain'] = open_trades['market_value'] - open_trades['total_cost']
        
        # المجاميع
        cost_open = open_trades['total_cost'].sum()
        market_val_open = open_trades['market_value'].sum()
        unrealized_pl = market_val_open - cost_open

        # 2. حسابات الصفقات المغلقة (الربح المحقق)
        closed_trades = trades[trades['status'] == 'Close'].copy()
        # الربح المحقق = (سعر البيع - سعر الشراء) * الكمية
        closed_trades['realized_gain'] = (closed_trades['exit_price'] - closed_trades['entry_price']) * closed_trades['quantity']
        realized_pl = closed_trades['realized_gain'].sum()

        # 3. حساب الكاش الدقيق
        total_dep = dep['amount'].sum() if not dep.empty else 0
        total_wit = wit['amount'].sum() if not wit.empty else 0
        total_ret = ret['amount'].sum() if not ret.empty else 0
        
        # الكاش الناتج من البيع
        sales_cash = (closed_trades['quantity'] * closed_trades['exit_price']).sum()
        
        # الكاش المستهلك في الشراء (للمفتوح والمغلق)
        total_spent = (trades['quantity'] * trades['entry_price']).sum()
        
        # المعادلة: الكاش = (إيداع + توزيعات + مبيعات) - (سحب + مشتريات)
        cash_available = (total_dep + total_ret + sales_cash) - (total_wit + total_spent)

        # دمج البيانات للعرض
        trades_final = pd.concat([open_trades, closed_trades], ignore_index=True)

        return {
            "cost_open": cost_open,
            "market_val_open": market_val_open,
            "unrealized_pl": unrealized_pl,
            "realized_pl": realized_pl,
            "cash": cash_available,
            "total_deposited": total_dep,
            "total_withdrawn": total_wit,
            "total_returns": total_ret,
            "all_trades": trades_final,
            "deposits": dep,
            "withdrawals": wit,
            "returns": ret
        }

    except Exception as e:
        logger.error(f"Metrics Error: {e}")
        return empty_res

# دوال مساعدة أخرى
def generate_equity_curve(trades_df):
    if trades_df.empty: return pd.DataFrame()
    df = trades_df[['date', 'quantity', 'entry_price']].copy()
    df['cost'] = df['quantity'] * df['entry_price']
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df['cumulative_invested'] = df['cost'].cumsum()
    return df

def calculate_historical_drawdown(df):
    return pd.DataFrame() # Placeholder

def create_smart_backup(): return True
def run_backtest(*args): return None
