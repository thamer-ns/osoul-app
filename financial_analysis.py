import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol
from database import execute_query, fetch_table, get_db

@st.cache_data(ttl=3600*4)
def get_fundamental_ratios(symbol):
    metrics = {"P/E": None, "P/B": None, "ROE": None, "Current_Price": 0, "Fair_Value": None, "Score": 0, "Rating": "N/A", "Opinions": []}
    if not symbol: return metrics
    t = yf.Ticker(get_ticker_symbol(symbol))
    try:
        info = t.info
        metrics['Current_Price'] = info.get('currentPrice', 0)
        metrics['P/E'] = info.get('trailingPE')
        metrics['P/B'] = info.get('priceToBook')
        metrics['ROE'] = info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else 0
        eps = info.get('trailingEps', 0)
        bv = info.get('bookValue', 0)
        if eps > 0 and bv > 0: metrics['Fair_Value'] = (22.5 * eps * bv) ** 0.5
        
        score = 0
        if metrics['Fair_Value'] and metrics['Current_Price'] < metrics['Fair_Value']: score += 3; metrics['Opinions'].append("أقل من القيمة العادلة")
        if metrics['P/E'] and 0 < metrics['P/E'] < 15: score += 2; metrics['Opinions'].append("مكرر ربحية مغري")
        if metrics['ROE'] > 15: score += 2; metrics['Opinions'].append("عائد حقوق مرتفع")
        if metrics['P/B'] and metrics['P/B'] < 1.5: score += 1; metrics['Opinions'].append("قيمة دفترية جيدة")
             
        metrics['Score'] = min(score, 10)
        metrics['Rating'] = "شراء قوي" if score >= 7 else "إيجابي" if score >= 5 else "محايد"
    except: pass
    return metrics

def render_financial_dashboard_ui(symbol):
    st.info("البيانات المالية التفصيلية (قريباً).")

def get_thesis(symbol):
    # استخدام Pandas للسهولة والأمان بدلاً من التعامل المباشر مع Cursor
    query = "SELECT * FROM InvestmentThesis WHERE symbol = %s"
    with get_db() as conn:
        if conn:
            try:
                df = pd.read_sql(query, conn, params=(symbol,))
                if not df.empty:
                    return df.iloc[0]
            except:
                pass
    return None

def save_thesis(symbol, text, target, rec):
    query = """
    INSERT INTO InvestmentThesis (symbol, thesis_text, target_price, recommendation, last_updated)
    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
    ON CONFLICT (symbol) DO UPDATE SET 
        thesis_text = EXCLUDED.thesis_text,
        target_price = EXCLUDED.target_price,
        recommendation = EXCLUDED.recommendation,
        last_updated = CURRENT_TIMESTAMP;
    """
    execute_query(query, (symbol, text, target, rec))
