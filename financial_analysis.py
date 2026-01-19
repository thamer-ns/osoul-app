import yfinance as yf
import pandas as pd
import streamlit as st
import requests
from bs4 import BeautifulSoup
from market_data import get_ticker_symbol

def scrape_google_finance(symbol):
    """
    محاولة جلب السعر والمؤشرات الأساسية من Google Finance
    كدعم إضافي في حال فشل Yahoo.
    """
    clean_sym = str(symbol).replace('.SR', '').replace('.sr', '')
    url = f"https://www.google.com/finance/quote/{clean_sym}:TADAWUL?hl=en"
    
    data = {}
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=3) # تقليل المهلة لتسريع التطبيق
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. السعر
            price_div = soup.find('div', {'class': 'YMlKec fxKbKc'})
            if price_div:
                data['price'] = float(price_div.text.replace(',', '').replace('SAR', '').strip())

            # 2. المؤشرات من الجدول
            items = soup.find_all('div', {'class': 'gyFHrc'})
            for item in items:
                text = item.text.upper()
                val_div = item.find('div', {'class': 'P6K39c'})
                if not val_div: continue
                val_str = val_div.text.strip()
                
                if val_str == '-': continue
                
                if 'P/E RATIO' in text:
                    data['pe'] = float(val_str.replace(',', ''))
                elif 'DIVIDEND YIELD' in text:
                    data['div_yield'] = float(val_str.replace('%', '').strip())
                elif 'MARKET CAP' in text:
                    # تحويل القيم النصية (B, M, T)
                    mult = 1
                    if 'T' in val_str: mult = 1e12
                    elif 'B' in val_str: mult = 1e9
                    elif 'M' in val_str: mult = 1e6
                    clean_val = val_str.replace('SAR', '').replace('T', '').replace('B', '').replace('M', '').strip()
                    try: data['mcap'] = float(clean_val) * mult
                    except: pass
    except:
        pass
    
    return data

@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    ticker_sym = get_ticker_symbol(symbol)
    
    # القيم الافتراضية (None بدلاً من 0 لتمييز "البيانات المفقودة" عن "القيمة الصفرية")
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, "EPS": None, 
        "Book_Value": None, "Current_Price": 0.0, "Fair_Value": None,
        "Dividend_Yield": None, "Debt_to_Equity": None, "Profit_Margin": None,
        "Score": 0, "Rating": "غير متاح", "Opinions": []
    }
    
    try:
        t = yf.Ticker(ticker_sym)
        
        # === 1. السعر (الأولوية القصوى) ===
        # نحاول جوجل أولاً (لأنه أدق حالياً)
        g_data = scrape_google_finance(symbol)
        metrics["Current_Price"] = g_data.get('price', 0.0)
        
        # إذا فشل جوجل، نحاول ياهو (لحظي ثم تاريخي)
        if metrics["Current_Price"] == 0:
            if hasattr(t, 'fast_info') and t.fast_info.last_price:
                metrics["Current_Price"] = float(t.fast_info.last_price)
            else:
                hist = t.history(period="5d")
                if not hist.empty:
                    metrics["Current_Price"] = float(hist['Close'].iloc[-1])

        # إذا لم نجد سعراً نهائياً، نتوقف
        if metrics["Current_Price"] == 0: return None

        # === 2. دمج البيانات (Hybrid) ===
        info = t.info if t.info else {}
        
        # أ) التوزيعات (الأولوية لجوجل ثم ياهو)
        div = g_data.get('div_yield')
        if div is None and info.get('dividendYield') is not None:
            div = info.get('dividendYield') * 100
        metrics["Dividend_Yield"] = div

        # ب) مكرر الربحية (P/E)
        pe = g_data.get('pe')
        if pe is None and info.get('trailingPE') is not None:
            pe = info.get('trailingPE')
        metrics["P/E"] = pe

        # ج) باقي المؤشرات من ياهو (غالباً غير موجودة في جوجل المالي المبسط)
        metrics["EPS"] = info.get('trailingEps')
        metrics["Book_Value"] = info.get('bookValue')
        metrics["P/B"] = info.get('priceToBook')
        
        if info.get('returnOnEquity'): metrics["ROE"] = info.get('returnOnEquity') * 100
        if info.get('profitMargins'): metrics["Profit_Margin"] = info.get('profitMargins') * 100
        if info.get('debtToEquity'): metrics["Debt_to_Equity"] = info.get('debtToEquity')

        # === 3. الحساب اليدوي (للبيانات الناقصة) ===
        # محاولة أخيرة لحساب EPS و P/B من القوائم المالية إذا كانت مفقودة
        if metrics["EPS"] is None or metrics["Book_Value"] is None:
            try:
                # نحتاج عدد الأسهم
                shares = info.get('sharesOutstanding')
                if not shares: shares = t.get_shares_full(start="2024-01-01").iloc[-1]
                
                if shares:
                    # حساب EPS
                    if metrics["EPS"] is None:
                        fin_stmt = t.financials
                        if not fin_stmt.empty:
                            net_income = None
                            for k in ['Net Income', 'Net Income Common Stockholders']:
                                if k in fin_stmt.index:
                                    net_income = fin_stmt.loc[k].iloc[0]; break
                            if net_income: metrics["EPS"] = net_income / shares

                    # حساب Book Value
                    if metrics["Book_Value"] is None:
                        bal_sheet = t.balance_sheet
                        if not bal_sheet.empty:
                            equity = None
                            if 'Stockholders Equity' in bal_sheet.index:
                                equity = bal_sheet.loc['Stockholders Equity'].iloc[0]
                            elif 'Total Assets' in bal_sheet.index:
                                equity = bal_sheet.loc['Total Assets'].iloc[0] - bal_sheet.loc['Total Liabilities Net Minority Interest'].iloc[0]
                            
                            if equity: metrics["Book_Value"] = equity / shares
            except: pass

        # استكمال الحسابات المعتمدة على القيم المحسوبة
        if metrics["P/E"] is None and metrics["EPS"] and metrics["EPS"] > 0:
            metrics["P/E"] = metrics["Current_Price"] / metrics["EPS"]
            
        if metrics["P/B"] is None and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["P/B"] = metrics["Current_Price"] / metrics["Book_Value"]

        # === 4. القيمة العادلة (Graham) ===
        # نحسبها فقط إذا توفرت بيانات الربح والقيمة الدفترية (لا تصلح للريت غالباً)
        if metrics["EPS"] and metrics["EPS"] > 0 and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["Fair_Value"] = (22.5 * metrics["EPS"] * metrics["Book_Value"]) ** 0.5

        # === 5. التقييم والرأي ===
        score = 0
        opinions = []
        
        # P/E
        if metrics["P/E"]:
            if 0 < metrics["P/E"] <= 15: score += 2; opinions.append(f"✅ مكرر ربحية ممتاز ({metrics['P/E']:.1f})")
            elif 15 < metrics["P/E"] <= 25: score += 1; opinions.append("ℹ️ مكرر ربحية عادل")
            elif metrics["P/E"] > 25: score -= 1; opinions.append("⚠️ مكرر ربحية مرتفع")
        else:
            opinions.append("⚪ مكرر الربحية غير متاح (ربما خسائر أو صندوق)")

        # P/B
        if metrics["P/B"] and 0 < metrics["P/B"] <= 2: 
            score += 1; opinions.append("✅ يتداول قرب القيمة الدفترية")
            
        # Dividend
        if metrics["Dividend_Yield"] and metrics["Dividend_Yield"] > 4: 
            score += 1; opinions.append(f"💰 توزيعات قوية ({metrics['Dividend_Yield']:.1f}%)")
            
        # Fair Value
        if metrics["Fair_Value"] and metrics["Current_Price"] < metrics["Fair_Value"]:
            diff = ((metrics['Fair_Value'] - metrics['Current_Price']) / metrics['Fair_Value']) * 100
            score += 2; opinions.append(f"💎 فرصة: أقل من العادلة بـ {diff:.1f}%")

        # تصنيف النتيجة
        metrics["Score"] = max(0, min(10, 5 + score))
        if metrics["Score"] >= 8: metrics["Rating"] = "شراء قوي ⭐"
        elif metrics["Score"] >= 6: metrics["Rating"] = "شراء ✅"
        elif metrics["Score"] >= 4: metrics["Rating"] = "محايد 😐"
        else: metrics["Rating"] = "حذر ❌"
        
        metrics["Opinions"] = opinions
        return metrics

    except Exception as e:
        # في أسوأ الأحوال، نعيد السعر فقط لكي لا يفشل البرنامج
        if metrics["Current_Price"] > 0: return metrics
        return None
