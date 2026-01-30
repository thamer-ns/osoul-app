#analytics.py
import pandas as pd
import numpy as np
from database import fetch_table, execute_query
from market_data import fetch_batch_data
import streamlit as st

# === أدوات مساعدة ===
def _clean_num(df, col):
    """تنظيف البيانات الرقمية لضمان عدم توقف الحسابات"""
    if col not in df.columns: 
        df[col] = 0.0
    # التحويل القسري إلى أرقام مع استبدال الأخطاء بصفر
    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

@st.cache_data(ttl=60, show_spinner=False)
def calculate_portfolio_metrics():
    """
    حساب مقاييس المحفظة (بدون أي عمولات أو ضرائب).
    الحساب يعتمد على التدفق النقدي الصافي المباشر.
    """
    default_res = {
        "cost_open": 0.0, "market_val_open": 0.0, "cash": 0.0,
        "unrealized_pl": 0.0, "realized_pl": 0.0,
        "total_deposited": 0.0, "total_withdrawn": 0.0, "total_returns": 0.0,
        "deposits": pd.DataFrame(), "withdrawals": pd.DataFrame(),
        "returns": pd.DataFrame(), "all_trades": pd.DataFrame()
    }
    
    try:
        # 1. جلب الجداول دفعة واحدة
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")
        
        # 2. تنظيف الأرقام المالية (لمنع الأخطاء الحسابية)
        for df in [dep, wit, ret]: 
            _clean_num(df, 'amount')
            
        total_dep = dep['amount'].sum()
        total_wit = wit['amount'].sum()
        total_ret = ret['amount'].sum()
        
        # إذا لم توجد صفقات، الكاش هو الفرق بين الإيداع والسحب
        if trades.empty:
            default_res.update({
                "total_deposited": total_dep, "total_withdrawn": total_wit,
                "total_returns": total_ret,
                "cash": (total_dep + total_ret) - total_wit,
                "deposits": dep, "withdrawals": wit, "returns": ret
            })
            return default_res

        # 3. معالجة بيانات الصفقات
        for c in ['quantity', 'entry_price', 'exit_price', 'current_price']:
            _clean_num(trades, c)

        # --- حساب التكلفة (Cash Out) ---
        # التكلفة = الكمية * سعر الدخول (بدون عمولة)
        trades['total_cost'] = trades['quantity'] * trades['entry_price']
        
        # تحديد حالة الصفقات (مفتوحة / مغلقة)
        if 'status' not in trades.columns: trades['status'] = 'Open'
        if 'exit_date' not in trades.columns: trades['exit_date'] = None
        if 'asset_type' not in trades.columns: trades['asset_type'] = 'Stock'

        is_closed = (
            (trades['exit_price'] > 0) | 
            (trades['status'].astype(str).str.lower().isin(['close', 'sold', 'مغلقة'])) |
            (trades['exit_date'].notna() & (trades['exit_date'].astype(str) != 'None'))
        )
        trades['status'] = np.where(is_closed, 'Close', 'Open')

        # --- تحديث الأسعار الحالية ---
        # للمغلقة: السعر الحالي هو سعر البيع
        trades.loc[is_closed, 'current_price'] = trades['exit_price']
        
        # للصكوك المفتوحة: السعر الحالي هو سعر الشراء (ثابت عادة)
        is_open_sukuk = (trades['status'] == 'Open') & (trades['asset_type'] == 'Sukuk')
        trades.loc[is_open_sukuk, 'current_price'] = trades.loc[is_open_sukuk, 'entry_price']
        
        # للبقية: ملء الفراغات
        trades['current_price'] = trades['current_price'].replace(0, np.nan).fillna(trades['entry_price'])

        # --- الحسابات النهائية للصفقات ---
        trades['market_value'] = trades['quantity'] * trades['current_price']
        trades['gain'] = trades['market_value'] - trades['total_cost']
        
        # نسبة الربح
        mask = trades['total_cost'] != 0
        trades['gain_pct'] = 0.0
        trades.loc[mask, 'gain_pct'] = (trades.loc[mask, 'gain'] / trades.loc[mask, 'total_cost']) * 100

        # تقسيم البيانات
        open_trades = trades[trades['status'] == 'Open']
        closed_trades = trades[trades['status'] == 'Close']
        
        # --- 4. معادلة الكاش (السيولة) الدقيقة ---
        # الكاش = (كل ما دخل المحفظة) - (كل ما خرج من المحفظة)
        
        # الداخل (+): الإيداعات + العوائد + مبيعات الصفقات المغلقة
        # ملاحظة: market_value للصفقات المغلقة هو (الكمية * سعر الخروج) أي الكاش المستلم
        cash_inflow = total_dep + total_ret + closed_trades['market_value'].sum()
        
        # الخارج (-): السحوبات + تكلفة شراء جميع الصفقات (المفتوحة والمغلقة)
        # ملاحظة: total_cost هو (الكمية * سعر الدخول) أي الكاش المدفوع
        cash_outflow = total_wit + trades['total_cost'].sum()
        
        cash_calculated = cash_inflow - cash_outflow
        
        return {
            "cost_open": open_trades['total_cost'].sum(),
            "market_val_open": open_trades['market_value'].sum(),
            "unrealized_pl": open_trades['gain'].sum(),
            "realized_pl": closed_trades['gain'].sum(),
            "cash": cash_calculated,
            "total_deposited": total_dep,
            "total_withdrawn": total_wit,
            "total_returns": total_ret,
            "all_trades": trades,
            "deposits": dep, "withdrawals": wit, "returns": ret
        }
        
    except Exception as e:
        st.error(f"خطأ في التحليل المالي: {e}")
        return default_res

def update_prices():
    """تحديث الأسعار"""
    try:
        df = fetch_table("Trades")
        if df.empty: return True
        
        # فقط الأسهم المفتوحة (ليست صكوك)
        open_stocks = df[(df['status'] == 'Open') & (df.get('asset_type', 'Stock') != 'Sukuk')]['symbol'].unique().tolist()
        
        if not open_stocks: return True
        
        live_data = fetch_batch_data(open_stocks)
        
        for sym, data in live_data.items():
            try:
                price = float(data.get('price', 0))
                if price > 0:
                    execute_query(
                        "UPDATE Trades SET current_price = %s WHERE symbol = %s AND status = 'Open'",
                        (price, sym)
                    )
            except: continue 
        
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"فشل تحديث الأسعار: {e}")
        return False

def generate_equity_curve(df):
    """توليد منحنى النمو"""
    if df.empty or 'date' not in df.columns: return pd.DataFrame()
    df = df.copy()
    try:
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        # منحنى تراكمي للاستثمار
        df['cumulative_invested'] = df['total_cost'].cumsum()
        return df
    except: return pd.DataFrame()

def create_smart_backup():
    try:
        from backup_system import generate_full_backup
        return generate_full_backup()
    except Exception as e:
        st.error(f"فشل النسخ الاحتياطي: {e}")
        return None, None
