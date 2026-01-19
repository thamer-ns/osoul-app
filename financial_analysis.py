import yfinance as yf
import pandas as pd
import streamlit as st
import requests
from bs4 import BeautifulSoup
from market_data import get_ticker_symbol

# === دالة مساعدة لجلب البيانات من Google Finance ===
def scrape_google_finance(symbol):
    """
    يقوم هذا الروبوت بزيارة صفحة جوجل المالية وسحب البيانات الأساسية
    عندما يفشل ياهو في توفيرها.
    """
    # تنظيف الرمز (حذف .SR) لأن جوجل يستخدم صيغة مختلفة أحياناً
    clean_sym = str(symbol).replace('.SR', '').replace('.sr', '')
    
    # رابط جوجل للسوق السعودي (TADAWUL)
    url = f"https://www.google.com/finance/quote/{clean_sym}:TADAWUL?hl=en"
    
    data = {}
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. جلب السعر الحالي
            # جوجل يضع السعر عادة في كلاس محدد، نبحث عنه
            price_div = soup.find('div', {'class': 'YMlKec fxKbKc'})
            if price_div:
                data['price'] = float(price_div.text.replace(',', '').replace('SAR', '').strip())

            # 2. جلب المؤشرات (P/E, Div Yield, Market Cap)
            # هذه البيانات موجودة في جدول، نبحث عن النصوص
            items = soup.find_all('div', {'class': 'gyFHrc'})
            for item in items:
                text = item.text.upper()
                val_div = item.find('div', {'class': 'P6K39c'})
                if not val_div: continue
                val_str = val_div.text.strip()
                
                if 'P/E RATIO' in text:
                    data['pe'] = float(val_str.replace(',', '')) if val_str != '-' else 0.0
                elif 'DIVIDEND YIELD' in text:
                    data['div_yield'] = float(val_str.replace('%', '').strip()) if val_str != '-' else 0.0
                elif 'MARKET CAP' in text:
                    # تحويل (T, B, M) إلى أرقام
                    mult = 1
                    if 'T' in val_str: mult = 1000000000000
                    elif 'B' in val_str: mult = 1000000000
                    elif 'M' in val_str: mult = 1000000
                    clean_val = val_str.replace('SAR', '').replace('T', '').replace('B', '').replace('M', '').strip()
                    try: data['mcap'] = float(clean_val) * mult
                    except: pass
    except:
        pass
    
    return data

@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    """
    نظام هجين: يدمج Yahoo Finance (للقوائم) + Google Finance (للسعر والمكررات)
    """
    ticker_sym = get_ticker_symbol(symbol)
    
    # الهيكل الأساسي
    final_data = {
        "P/E": 0.0, "P/B": 0.0, "ROE": 0.0, "EPS": 0.0, 
        "Book_Value": 0.0, "Current_Price": 0.0, "Fair_Value": 0.0,
        "Dividend_Yield": 0.0, "Debt_to_Equity": 0.0, "Profit_Margin": 0.0,
        "Score": 0, "Rating": "غير متاح", "Opinions": []
    }
    
    try:
        # === المصدر 1: Yahoo Finance (للقوائم المالية العميقة) ===
        t = yf.Ticker(ticker_sym)
        y_info = t.info if t.info else {}
        
        # === المصدر 2: Google Finance (للسعر والمؤشرات السريعة) ===
        # نستدعي جوجل كخطة دعم (Backup)
        g_data = scrape_google_finance(symbol)
        
        # --- دمج السعر ---
        # الأولوية لجوجل في السعر لأنه أسرع تحديثاً، ثم ياهو اللحظي، ثم ياهو التاريخي
        price = g_data.get('price', 0.0)
        
        if price == 0:
            if hasattr(t, 'fast_info') and t.fast_info.last_price:
                price = float(t.fast_info.last_price)
            else:
                hist = t.history(period="5d")
                if not hist.empty: price = float(hist['Close'].iloc[-1])
        
        final_data["Current_Price"] = price
        if price == 0: return final_data # فشل المصدرين

        # --- دمج مكرر الربحية (P/E) ---
        # الأولوية لجوجل لأنه دقيق في المكررات، ثم ياهو، ثم الحساب اليدوي
        pe = g_data.get('pe', 0.0)
        if pe == 0: pe = y_info.get('trailingPE', 0.0)
        
        # --- دمج التوزيعات ---
        div = g_data.get('div_yield', 0.0)
        if div == 0 and y_info.get('dividendYield'): 
            div = y_info.get('dividendYield') * 100
        
        final_data["P/E"] = pe
        final_data["Dividend_Yield"] = div

        # --- حسابات Yahoo العميقة (التي لا يوفرها جوجل بسهولة) ---
        # 1. القيمة الدفترية و P/B
        bv = y_info.get('bookValue', 0.0)
        pb = y_info.get('priceToBook', 0.0)
        
        # محاولة الحساب اليدوي من القوائم إذا كانت القيم صفر
        if bv == 0 or pb == 0:
            try:
                balance = t.balance_sheet
                shares = y_info.get('sharesOutstanding')
                if not shares: shares = t.get_shares_full(start="2024-01-01").iloc[-1]
                
                if not balance.empty and shares:
                    equity_row = balance.loc['Stockholders Equity'] if 'Stockholders Equity' in balance.index else \
                                 (balance.loc['Total Assets'] - balance.loc['Total Liabilities Net Minority Interest'])
                    equity = equity_row.iloc[0]
                    bv = equity / shares
                    pb = price / bv
            except: pass
            
        final_data["Book_Value"] = float(bv)
        final_data["P/B"] = float(pb)

        # 2. ربح السهم (EPS) والعائد (ROE)
        eps = y_info.get('trailingEps', 0.0)
        # إذا كان لدينا P/E والسعر، يمكننا استنتاج EPS بدقة
        if eps == 0 and pe > 0:
            eps = price / pe
        
        roe = y_info.get('returnOnEquity', 0.0) * 100
        debt = y_info.get('debtToEquity', 0.0)
        margin = y_info.get('profitMargins', 0.0) * 100
        
        final_data["EPS"] = float(eps)
        final_data["ROE"] = float(roe)
        final_data["Debt_to_Equity"] = float(debt)
        final_data["Profit_Margin"] = float(margin)

        # === القيمة العادلة والتقييم ===
        if final_data["EPS"] > 0 and final_data["Book_Value"] > 0:
            final_data["Fair_Value"] = (22.5 * final_data["EPS"] * final_data["Book_Value"]) ** 0.5

        # نظام التقييم (Score)
        score = 0
        opinions = []
        
        if 0 < pe <= 15: score += 2; opinions.append(f"✅ مكرر ممتاز ({pe:.1f})")
        elif 15 < pe <= 25: score += 1; opinions.append(f"ℹ️ مكرر متوسط ({pe:.1f})")
        elif pe > 25: score -= 1; opinions.append("⚠️ مكرر مرتفع")
        elif pe == 0: opinions.append("⚪ لا يوجد مكرر (خسائر أو عدم توفر بيانات)")

        if 0 < final_data["P/B"] <= 2: score += 1; opinions.append("✅ قيمة دفترية جيدة")
        if final_data["Dividend_Yield"] > 4: score += 1; opinions.append(f"💰 توزيعات قوية ({div:.1f}%)")
        if final_data["ROE"] > 15: score += 2; opinions.append("🔥 عائد حقوق ملكية مرتفع")
        
        if final_data["Fair_Value"] > 0 and price < final_data["Fair_Value"]:
            diff = ((final_data['Fair_Value'] - price) / final_data['Fair_Value']) * 100
            score += 2; opinions.append(f"💎 أقل من العادلة بـ {diff:.1f}%")

        final_data["Score"] = max(0, min(10, 5 + score))
        if final_data["Score"] >= 8: final_data["Rating"] = "شراء قوي ⭐"
        elif final_data["Score"] >= 6: final_data["Rating"] = "شراء ✅"
        elif final_data["Score"] >= 4: final_data["Rating"] = "محايد 😐"
        else: final_data["Rating"] = "حذر ❌"
        
        final_data["Opinions"] = opinions
        
        return final_data

    except Exception as e:
        return final_data
