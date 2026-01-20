import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol
from database import execute_query, fetch_table, get_db

@st.cache_data(ttl=3600*4)
def get_fundamental_ratios(symbol):
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, "EPS": None, "Profit_Margin": None,
        "Book_Value": None, "Current_Price": 0.0, "Fair_Value": None, 
        "Dividend_Yield": None, "Debt_to_Equity": None, "Score": 0, 
        "Rating": "تحليل غير متاح", "Opinions": []
    }
    
    ticker_sym = get_ticker_symbol(symbol)
    ticker = yf.Ticker(ticker_sym)
    
    try:
        hist = ticker.history(period="5d")
        if not hist.empty: metrics["Current_Price"] = float(hist['Close'].iloc[-1])
        else:
            if hasattr(ticker, 'fast_info') and ticker.fast_info.last_price:
                 metrics["Current_Price"] = ticker.fast_info.last_price
    except: pass

    if metrics["Current_Price"] == 0:
        metrics["Rating"] = "السعر غير متاح"
        return metrics

    try:
        info = ticker.info
        if not info: info = {}
        
        metrics["EPS"] = info.get('trailingEps')
        metrics["Book_Value"] = info.get('bookValue')
        metrics["P/E"] = info.get('trailingPE')
        metrics["P/B"] = info.get('priceToBook')
        metrics["ROE"] = info.get('returnOnEquity', 0)
        metrics["Profit_Margin"] = info.get('profitMargins', 0)
        metrics["Debt_to_Equity"] = info.get('debtToEquity', 0)
        
        if metrics["ROE"]: metrics["ROE"] *= 100
        if metrics["Profit_Margin"]: metrics["Profit_Margin"] *= 100
        
        metrics["Dividend_Yield"] = info.get('dividendYield')
        if metrics["Dividend_Yield"]: metrics["Dividend_Yield"] *= 100

        # حسابات يدوية عند الحاجة
        if metrics["P/E"] is None and metrics["EPS"] and metrics["EPS"] > 0:
            metrics["P/E"] = metrics["Current_Price"] / metrics["EPS"]
            
        # القيمة العادلة (Graham Number مخفف)
        if metrics["EPS"] and metrics["EPS"] > 0 and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["Fair_Value"] = (22.5 * metrics["EPS"] * metrics["Book_Value"]) ** 0.5

    except Exception as e:
        metrics["Opinions"].append(f"بيانات ناقصة: {str(e)}")

    # نظام التقييم
    score = 0
    ops = []
    
    if metrics["Fair_Value"] and metrics["Current_Price"] < metrics["Fair_Value"]:
        score += 3; ops.append("💎 سعر مغري (أقل من العادلة)")
    
    pe = metrics["P/E"]
    if pe:
        if 0 < pe <= 15: score += 2; ops.append("✅ مكرر ربحية ممتاز")
        elif 15 < pe <= 22: score += 1
    
    if metrics["ROE"] and metrics["ROE"] > 15: score += 2; ops.append("🚀 عائد على حقوق الملكية قوي")
    if metrics["Profit_Margin"] and metrics["Profit_Margin"] > 10: score += 2; ops.append("💰 هوامش ربحية عالية")
    if metrics["Debt_to_Equity"] and metrics["Debt_to_Equity"] < 100: score += 1

    metrics["Score"] = min(score, 10)
    metrics["Opinions"] = ops
    
    if score >= 7: metrics["Rating"] = "شراء قوي 🌟"
    elif score >= 5: metrics["Rating"] = "إيجابي ✅"
    elif score >= 3: metrics["Rating"] = "محايد 😐"
    else: metrics["Rating"] = "سلبي/للمراجعة ⚠️"

    return metrics

def update_financial_statements(symbol):
    """جلب القوائم المالية وتخزينها في قاعدة البيانات"""
    ticker_sym = get_ticker_symbol(symbol)
    ticker = yf.Ticker(ticker_sym)
    
    try:
        financials = ticker.financials.T
        balance_sheet = ticker.balance_sheet.T
        cashflow = ticker.cashflow.T
        
        if financials.empty: return False

        df = pd.DataFrame(index=financials.index)
        
        # تعيين الأعمدة بمرونة
        if 'Total Revenue' in financials.columns: df['revenue'] = financials['Total Revenue']
        elif 'Operating Revenue' in financials.columns: df['revenue'] = financials['Operating Revenue']
        else: df['revenue'] = 0
        
        df['net_income'] = financials.get('Net Income', 0)
        df['gross_profit'] = financials.get('Gross Profit', 0)
        df['operating_income'] = financials.get('Operating Income', 0)
        
        for date in df.index:
            try:
                bs_row = balance_sheet.loc[balance_sheet.index == date]
                if not bs_row.empty:
                    df.at[date, 'total_assets'] = bs_row.get('Total Assets', [0])[0]
                    df.at[date, 'total_liabilities'] = bs_row.get('Total Liabilities Net Minority Interest', [0])[0]
                    df.at[date, 'total_equity'] = bs_row.get('Stockholders Equity', [0])[0]
                
                cf_row = cashflow.loc[cashflow.index == date]
                if not cf_row.empty:
                    df.at[date, 'operating_cash_flow'] = cf_row.get('Operating Cash Flow', [0])[0]
                    df.at[date, 'free_cash_flow'] = cf_row.get('Free Cash Flow', [0])[0]
            except: pass

        df.fillna(0, inplace=True)
        
        for date, row in df.iterrows():
            d_str = str(date.date())
            execute_query("""
                INSERT OR REPLACE INTO FinancialStatements 
                (symbol, period_type, date, revenue, net_income, gross_profit, total_assets, total_liabilities, total_equity, operating_cash_flow, free_cash_flow, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, 'Annual', d_str, row['revenue'], row['net_income'], row['gross_profit'], 
                  row.get('total_assets',0), row.get('total_liabilities',0), row.get('total_equity',0), 
                  row.get('operating_cash_flow',0), row.get('free_cash_flow',0), 'Yahoo'))
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def get_stored_financials(symbol):
    with get_db() as conn:
        try:
            return pd.read_sql(f"SELECT * FROM FinancialStatements WHERE symbol = '{symbol}' ORDER BY date ASC", conn)
        except: return pd.DataFrame()

def save_thesis(symbol, text, target, rec):
    import datetime
    now = str(datetime.date.today())
    execute_query("""
        INSERT OR REPLACE INTO InvestmentThesis (symbol, thesis_text, target_price, recommendation, last_updated)
        VALUES (?, ?, ?, ?, ?)
    """, (symbol, text, target, rec, now))

def get_thesis(symbol):
    with get_db() as conn:
        return conn.execute("SELECT * FROM InvestmentThesis WHERE symbol = ?", (symbol,)).fetchone()
