import yfinance as yf
import pandas as pd
import streamlit as st
import requests
from bs4 import BeautifulSoup
from market_data import get_ticker_symbol

# === روبوت جوجل المالي المحسن (Google Finance Scraper) ===
def scrape_google_finance_advanced(symbol):
    """
    محاولة قوية لسحب البيانات من واجهة جوجل المالية
    تعتمد على البحث عن النصوص بدلاً من الكلاسات المتغيرة.
    """
    clean_sym = str(symbol).replace('.SR', '').replace('.sr', '')
    url = f"https://www.google.com/finance/quote/{clean_sym}:TADAWUL?hl=en"
    
    data = {}
    try:
        # استخدام هيدر متصفح حقيقي لتجنب الحجب
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        response = requests.get(url, headers=headers, timeout=4)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. البحث عن السعر (عادة يكون أكبر رقم في الصفحة)
            # نبحث عن الكلاس الذي يحتوي العملة SAR أو الرقم الكبير
            price_candidates = soup.find_all('div', string=lambda t: t and '.' in t)
            for tag in price_candidates:
                # محاولة التقاط السعر من السياق
                parent = tag.parent
                if 'SAR' in parent.text or 'YMlKec' in str(tag.get('class')):
                    try:
                        price_val = float(tag.text.replace(',', '').replace('SAR', '').strip())
                        if price_val > 0:
                            data['price'] = price_val
                            break
                    except: continue

            # 2. البحث عن المؤشرات في الجدول (P/E, Market Cap, Yield)
            # هذه الطريقة تبحث عن "Label" ثم تأخذ القيمة التي تليها
            all_text = soup.get_text()
            
            # دالة مساعدة لاستخراج القيمة بعد نص معين
            def extract_val(label):
                try:
                    # نبحث عن النص في الـ HTML الخام لأنه أدق في الترتيب
                    items = soup.find_all("div", text=label)
                    if not items: items = soup.find_all("div", string=label)
                    
                    for item in items:
                        # القيمة عادة تكون في العنصر المجاور أو الابن
                        parent = item.parent
                        value_div = parent.find_next_sibling("div")
                        if value_div:
                            return value_div.text.strip()
                except: return None
                return None

            # استخراج P/E
            pe_str = extract_val("P/E ratio")
            if pe_str and pe_str != '-':
                data['pe'] = float(pe_str.replace(',', ''))

            # استخراج العائد
            div_str = extract_val("Dividend yield")
            if div_str and div_str != '-':
                data['div_yield'] = float(div_str.replace('%', '').strip())
                
            # استخراج القيمة السوقية
            mcap_str = extract_val("Market cap")
            if mcap_str:
                mult = 1
                if 'T' in mcap_str: mult = 1e12
                elif 'B' in mcap_str: mult = 1e9
                elif 'M' in mcap_str: mult = 1e6
                clean = mcap_str.replace('SAR', '').replace('T', '').replace('B', '').replace('M', '').strip()
                try: data['mcap'] = float(clean) * mult
                except: pass

    except Exception as e:
        pass # الفشل الصامت للمتابعة
    
    return data

@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    ticker_sym = get_ticker_symbol(symbol)
    
    # تهيئة القيم بـ None لتمييز "عدم التوفر" عن "الصفر"
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, "EPS": None, 
        "Book_Value": None, "Current_Price": 0.0, "Fair_Value": None,
        "Dividend_Yield": None, "Debt_to_Equity": None, "Profit_Margin": None,
        "Score": 0, "Rating": "غير متاح", "Opinions": []
    }
    
    try:
        t = yf.Ticker(ticker_sym)
        
        # ==========================================
        # 1. معركة السعر (Price Hunting)
        # ==========================================
        # أ) محاولة جوجل
        g_data = scrape_google_finance_advanced(symbol)
        price = g_data.get('price', 0.0)
        
        # ب) محاولة ياهو التاريخية (موثوقة جداً للإغلاقات)
        if price == 0:
            hist = t.history(period="5d")
            if not hist.empty:
                price = float(hist['Close'].iloc[-1])
        
        # ج) محاولة ياهو اللحظية
        if price == 0 and hasattr(t, 'fast_info') and t.fast_info.last_price:
            price = float(t.fast_info.last_price)
            
        metrics["Current_Price"] = price
        if price == 0: return metrics # لا يمكن عمل شيء بدون سعر

        # ==========================================
        # 2. تعبئة المؤشرات المتاحة (Hybrid)
        # ==========================================
        info = t.info if t.info else {}
        
        # دمج بيانات جوجل
        metrics["P/E"] = g_data.get('pe')
        metrics["Dividend_Yield"] = g_data.get('div_yield')
        
        # دمج بيانات ياهو الجاهزة (إذا لم نجدها في جوجل)
        if metrics["P/E"] is None: metrics["P/E"] = info.get('trailingPE')
        if metrics["Dividend_Yield"] is None and info.get('dividendYield'):
            metrics["Dividend_Yield"] = info.get('dividendYield') * 100

        metrics["P/B"] = info.get('priceToBook')
        metrics["EPS"] = info.get('trailingEps')
        metrics["Book_Value"] = info.get('bookValue')
        if info.get('returnOnEquity'): metrics["ROE"] = info.get('returnOnEquity') * 100
        if info.get('profitMargins'): metrics["Profit_Margin"] = info.get('profitMargins') * 100
        metrics["Debt_to_Equity"] = info.get('debtToEquity')

        # ==========================================
        # 3. الحساب اليدوي (للبيانات الناقصة)
        # ==========================================
        # محاولة حساب EPS إذا كان مفقوداً
        if metrics["EPS"] is None:
            try:
                financials = t.financials
                shares = info.get('sharesOutstanding')
                if not shares: shares = t.get_shares_full(start="2024-01-01").iloc[-1]
                
                if not financials.empty and shares:
                    # البحث بذكاء عن صف الدخل
                    net_income = None
                    for label in ['Net Income', 'Net Income Common Stockholders', 'Net Income Continuous Operations']:
                        if label in financials.index:
                            net_income = financials.loc[label].iloc[0]
                            break
                    
                    if net_income: metrics["EPS"] = net_income / shares
            except: pass

        # إعادة حساب P/E إذا توفر EPS والسعر
        if metrics["P/E"] is None and metrics["EPS"] and metrics["EPS"] > 0:
            metrics["P/E"] = price / metrics["EPS"]

        # محاولة حساب Book Value يدوياً
        if metrics["Book_Value"] is None:
            try:
                balance = t.balance_sheet
                shares = info.get('sharesOutstanding') or t.get_shares_full(start="2024-01-01").iloc[-1]
                
                if not balance.empty and shares:
                    equity = None
                    if 'Stockholders Equity' in balance.index:
                        equity = balance.loc['Stockholders Equity'].iloc[0]
                    elif 'Total Assets' in balance.index:
                        equity = balance.loc['Total Assets'].iloc[0] - balance.loc['Total Liabilities Net Minority Interest'].iloc[0]
                    
                    if equity: metrics["Book_Value"] = equity / shares
            except: pass

        # إعادة حساب P/B
        if metrics["P/B"] is None and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["P/B"] = price / metrics["Book_Value"]

        # ==========================================
        # 4. القيمة العادلة والتقييم
        # ==========================================
        if metrics["EPS"] and metrics["EPS"] > 0 and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["Fair_Value"] = (22.5 * metrics["EPS"] * metrics["Book_Value"]) ** 0.5

        # حساب النقاط
        score = 0
        opinions = []
        
        # P/E
        if metrics["P/E"]:
            pe = metrics["P/E"]
            if 0 < pe <= 15: score += 2; opinions.append(f"✅ مكرر ربحية ممتاز ({pe:.1f})")
            elif 15 < pe <= 25: score += 1; opinions.append(f"ℹ️ مكرر ربحية مقبول ({pe:.1f})")
            elif pe > 25: score -= 1; opinions.append(f"⚠️ مكرر ربحية مرتفع ({pe:.1f})")
        
        # P/B
        if metrics["P/B"] and 0 < metrics["P/B"] <= 2: 
            score += 1; opinions.append("✅ يتداول قرب القيمة الدفترية")
            
        # Dividend
        if metrics["Dividend_Yield"] and metrics["Dividend_Yield"] > 4: 
            score += 1; opinions.append(f"💰 توزيعات قوية ({metrics['Dividend_Yield']:.1f}%)")
            
        # Fair Value
        if metrics["Fair_Value"] and metrics["Fair_Value"] > 0:
            if price < metrics["Fair_Value"]:
                diff = ((metrics['Fair_Value'] - price) / metrics['Fair_Value']) * 100
                score += 2; opinions.append(f"💎 فرصة: أقل من العادلة بـ {diff:.1f}%")
            else:
                opinions.append("📉 السعر الحالي أعلى من القيمة العادلة")

        metrics["Score"] = max(0, min(10, 5 + score))
        if metrics["Score"] >= 8: metrics["Rating"] = "شراء قوي ⭐"
        elif metrics["Score"] >= 6: metrics["Rating"] = "شراء ✅"
        elif metrics["Score"] >= 4: metrics["Rating"] = "محايد 😐"
        else: metrics["Rating"] = "حذر ❌"
        
        metrics["Opinions"] = opinions
        return metrics

    except Exception as e:
        # إرجاع ما تم جمعه حتى لو ناقص لتجنب انهيار الواجهة
        return metrics
