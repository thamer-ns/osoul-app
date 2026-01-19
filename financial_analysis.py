import yfinance as yf
import pandas as pd
import streamlit as st
import requests
from bs4 import BeautifulSoup
from market_data import get_ticker_symbol

# === روبوت جوجل المالي الذكي (يدعم الأمريكي والسعودي) ===
def scrape_google_finance_advanced(symbol):
    clean_sym = str(symbol).replace('.SR', '').replace('.sr', '')
    
    # تحديد السوق بناءً على الرمز
    if clean_sym.isdigit():
        # إذا كان أرقاماً -> سوق سعودي
        market = "TADAWUL"
    else:
        # إذا كان حروفاً (LCID, TSLA) -> غالباً NASDAQ أو NYSE
        # نجرب NASDAQ افتراضياً (جوجل ذكي وسيحولنا)
        market = "NASDAQ"

    url = f"https://www.google.com/finance/quote/{clean_sym}:{market}?hl=en"
    
    data = {}
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        response = requests.get(url, headers=headers, timeout=4)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. البحث عن السعر
            price_candidates = soup.find_all('div', string=lambda t: t and '.' in t)
            for tag in price_candidates:
                parent = tag.parent
                # التحقق من العملة (SAR للسعودي، USD للأمريكي)
                if any(curr in parent.text for curr in ['SAR', '$', 'USD']) or 'YMlKec' in str(tag.get('class')):
                    try:
                        clean_price = tag.text.replace(',', '').replace('SAR', '').replace('$', '').strip()
                        price_val = float(clean_price)
                        if price_val > 0:
                            data['price'] = price_val
                            break
                    except: continue

            # 2. البحث عن المؤشرات
            def extract_val(label):
                try:
                    # البحث عن النص بدقة
                    items = soup.find_all("div", string=lambda t: t and label.upper() in t.upper())
                    for item in items:
                        parent = item.parent
                        # القيمة تكون في العنصر التالي
                        val_div = parent.find_next_sibling("div")
                        if val_div: return val_div.text.strip()
                except: return None
                return None

            pe_str = extract_val("P/E ratio")
            if pe_str and pe_str != '-': data['pe'] = float(pe_str.replace(',', ''))

            div_str = extract_val("Dividend yield")
            if div_str and div_str != '-': data['div_yield'] = float(div_str.replace('%', '').strip())

    except Exception as e:
        pass
    
    return data

@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    ticker_sym = get_ticker_symbol(symbol)
    
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, "EPS": None, 
        "Book_Value": None, "Current_Price": 0.0, "Fair_Value": None,
        "Dividend_Yield": None, "Debt_to_Equity": None, "Profit_Margin": None,
        "Score": 0, "Rating": "غير متاح", "Opinions": []
    }
    
    try:
        t = yf.Ticker(ticker_sym)
        
        # 1. معركة السعر
        g_data = scrape_google_finance_advanced(symbol)
        price = g_data.get('price', 0.0)
        
        if price == 0:
            hist = t.history(period="5d")
            # إصلاح الانهيار هنا أيضاً إذا كانت الأعمدة MultiIndex
            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = hist.columns.get_level_values(0)
            
            if not hist.empty:
                price = float(hist['Close'].iloc[-1])
        
        metrics["Current_Price"] = price
        if price == 0: return metrics

        # 2. البيانات المالية
        info = t.info if t.info else {}
        
        metrics["P/E"] = g_data.get('pe') or info.get('trailingPE')
        metrics["Dividend_Yield"] = g_data.get('div_yield')
        if metrics["Dividend_Yield"] is None and info.get('dividendYield'):
            metrics["Dividend_Yield"] = info.get('dividendYield') * 100

        metrics["P/B"] = info.get('priceToBook')
        metrics["EPS"] = info.get('trailingEps')
        metrics["Book_Value"] = info.get('bookValue')
        if info.get('returnOnEquity'): metrics["ROE"] = info.get('returnOnEquity') * 100
        if info.get('profitMargins'): metrics["Profit_Margin"] = info.get('profitMargins') * 100
        metrics["Debt_to_Equity"] = info.get('debtToEquity')

        # 3. الحساب اليدوي (للأسهم الأمريكية والسعودية)
        if metrics["EPS"] is None:
            try:
                financials = t.financials
                shares = info.get('sharesOutstanding')
                if not shares: shares = t.get_shares_full(start="2024-01-01").iloc[-1]
                
                if not financials.empty and shares:
                    # البحث عن صافي الدخل بذكاء
                    net_income = None
                    for label in financials.index:
                        if 'Net Income' in str(label) and 'Common' in str(label):
                            net_income = financials.loc[label].iloc[0]; break
                    if not net_income and 'Net Income' in financials.index:
                        net_income = financials.loc['Net Income'].iloc[0]
                        
                    if net_income: metrics["EPS"] = net_income / shares
            except: pass

        if metrics["P/E"] is None and metrics["EPS"] and metrics["EPS"] > 0:
            metrics["P/E"] = price / metrics["EPS"]

        if metrics["Book_Value"] is None:
            try:
                balance = t.balance_sheet
                shares = info.get('sharesOutstanding')
                if not balance.empty and shares:
                    equity = None
                    for label in balance.index:
                        if 'Stockholders Equity' in str(label) or 'Total Equity' in str(label):
                            equity = balance.loc[label].iloc[0]; break
                    
                    if equity: metrics["Book_Value"] = equity / shares
            except: pass

        if metrics["P/B"] is None and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["P/B"] = price / metrics["Book_Value"]

        # 4. التقييم
        if metrics["EPS"] and metrics["EPS"] > 0 and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["Fair_Value"] = (22.5 * metrics["EPS"] * metrics["Book_Value"]) ** 0.5

        score = 0
        opinions = []
        
        if metrics["P/E"]:
            if 0 < metrics["P/E"] <= 15: score += 2; opinions.append("✅ مكرر ربحية ممتاز")
            elif metrics["P/E"] > 25: score -= 1; opinions.append("⚠️ مكرر ربحية مرتفع")
        else:
            if metrics["EPS"] and metrics["EPS"] < 0: opinions.append("⚠️ الشركة تحقق خسائر")

        if metrics["Fair_Value"] and price < metrics["Fair_Value"]:
            score += 2; opinions.append("💎 سعر أقل من القيمة العادلة")

        metrics["Score"] = max(0, min(10, 5 + score))
        if metrics["Score"] >= 7: metrics["Rating"] = "إيجابي ✅"
        elif metrics["Score"] >= 4: metrics["Rating"] = "محايد 😐"
        else: metrics["Rating"] = "سلبي ❌"
        
        metrics["Opinions"] = opinions
        return metrics

    except:
        return metrics
