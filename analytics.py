import pandas as pd
import numpy as np
from database import fetch_table
import streamlit as st

@st.cache_data(ttl=60)
def calculate_portfolio_metrics():
    # 1. إعداد الهيكل الافتراضي (صمام الأمان)
    empty_df = pd.DataFrame(columns=['date', 'amount', 'note'])
    default_res = {
        "cost_open": 0.0, "market_val_open": 0.0, "cash": 0.0, 
        "unrealized_pl": 0.0, "realized_pl": 0.0, 
        "total_deposited": 0.0, "total_withdrawn": 0.0, "total_returns": 0.0,
        "deposits": empty_df.copy(),
        "withdrawals": empty_df.copy(),
        "returns": pd.DataFrame(columns=['date', 'amount', 'symbol', 'note']),
        "all_trades": pd.DataFrame()
    }

    try:
        # جلب الجداول
        trades = fetch_table("Trades")
        dep = fetch_table("Deposits")
        wit = fetch_table("Withdrawals")
        ret = fetch_table("ReturnsGrants")

        # 2. الحل الجذري لـ KeyError: ضمان وجود عمود amount
        # إذا جاء الجدول فارغاً أو بدون أعمدة، نقوم بإنشائها يدوياً
        if dep.empty or 'amount' not in dep.columns:
            dep = pd.DataFrame(columns=['date', 'amount', 'note'])
        
        if wit.empty or 'amount' not in wit.columns:
            wit = pd.DataFrame(columns=['date', 'amount', 'note'])
            
        if ret.empty or 'amount' not in ret.columns:
            ret = pd.DataFrame(columns=['date', 'amount', 'symbol', 'note'])

        # تنظيف البيانات وتحويلها لأرقام
        dep['amount'] = pd.to_numeric(dep['amount'], errors='coerce').fillna(0.0)
        wit['amount'] = pd.to_numeric(wit['amount'], errors='coerce').fillna(0.0)
        ret['amount'] = pd.to_numeric(ret['amount'], errors='coerce').fillna(0.0)

        # حساب المجاميع
        total_dep = dep['amount'].sum()
        total_wit = wit['amount'].sum()
        total_ret = ret['amount'].sum()

        # إذا لا توجد صفقات، نرجع السيولة فقط
        if trades.empty:
            default_res.update({
                "total_deposited": total_dep, "total_withdrawn": total_wit, "total_returns": total_ret,
                "cash": (total_dep + total_ret) - total_wit,
                "deposits": dep, "withdrawals": wit, "returns": ret
            })
            return default_res

        # معالجة الصفقات (Trades)
        # التأكد من وجود الأعمدة الحيوية
        req_cols = ['quantity', 'entry_price', 'exit_price', 'current_price', 'status', 'asset_type', 'total_cost', 'market_value']
        for c in req_cols:
            if c not in trades.columns:
                trades[c] = 0.0 if c not in ['status', 'asset_type'] else ('Open' if c=='status' else 'Stock')

        # تحويل الأرقام
        for c in ['quantity', 'entry_price', 'exit_price', 'current_price']:
            trades[c] = pd.to_numeric(trades[c], errors='coerce').fillna(0.0)

        # منطق الإغلاق
        is_closed = (trades['exit_price'] > 0) | (trades['status'].astype(str).str.lower().isin(['close', 'sold', 'مغلقة']))
        trades['status'] = np.where(is_closed, 'Close', 'Open')
        trades.loc[is_closed, 'current_price'] = trades['exit_price']

        # الحسابات المالية
        trades['total_cost'] = trades['quantity'] * trades['entry_price']
        trades['market_value'] = trades['quantity'] * trades['current_price']
        trades['gain'] = trades['market_value'] - trades['total_cost']
        
        # النسب
        trades['gain_pct'] = 0.0
        mask_cost = trades['total_cost'] != 0
        trades.loc[mask_cost, 'gain_pct'] = (trades.loc[mask_cost, 'gain'] / trades.loc[mask_cost, 'total_cost']) * 100

        # فصل المحافظ
        open_trades = trades[trades['status'] == 'Open']
        closed_trades = trades[trades['status'] == 'Close']

        cost_open = open_trades['total_cost'].sum()
        market_val_open = open_trades['market_value'].sum()
        sales_closed = closed_trades['market_value'].sum()
        cost_closed = closed_trades['total_cost'].sum()
        
        # معادلة الكاش النهائية
        total_buy_cost = trades['total_cost'].sum()
        cash = (total_dep + total_ret + sales_closed) - (total_wit + total_buy_cost)

        return {
            "cost_open": cost_open, "market_val_open": market_val_open,
            "unrealized_pl": market_val_open - cost_open,
            "realized_pl": sales_closed - cost_closed,
            "cash": cash,
            "total_deposited": total_dep, "total_withdrawn": total_wit, "total_returns": total_ret,
            "all_trades": trades, "deposits": dep, "withdrawals": wit, "returns": ret
        }

    except Exception as e:
        print(f"Analytics Error: {e}")
        return default_res

def generate_equity_curve(df):
    if df.empty: return pd.DataFrame()
    try:
        return df[['date', 'total_cost']].sort_values('date').assign(cumulative_invested=lambda x: x['total_cost'].cumsum())
    except: return pd.DataFrame()

def run_backtest(df, s, c): return None 
def update_prices(): return False
