import yfinance as yf
import pandas as pd
import streamlit as st
from market_data import get_ticker_symbol

@st.cache_data(ttl=3600*12)
def get_fundamental_ratios(symbol):
    """
    محرك تحليل مالي شامل: يعتمد على البيانات الكلية (Market Cap, Net Income)
    لحساب المؤشرات بدقة، ويولد تقييماً آلياً للوضع المالي.
    """
    ticker_sym = get_ticker_symbol(symbol)
    t = yf.Ticker(ticker_sym)
    
    # هيكل البيانات الافتراضي
    metrics = {
        "price": 0.0,
        "pe_ratio": 0.0, "pb_ratio": 0.0, "debt_to_equity": 0.0,
        "roe": 0.0, "roa": 0.0,
        "profit_margin": 0.0, "operating_margin": 0.0,
        "current_ratio": 0.0,
        "dividend_yield": 0.0,
        "fair_value": 0.0,
        "rating": "محايد",
        "opinion": [],
        "score": 0 # من 10
    }

    try:
        # 1. جلب السعر والقيمة السوقية (بيانات حية)
        info = t.info if t.info else {}
        fast_info = t.fast_info
        
        # السعر
        price = 0.0
        if hasattr(fast_info, 'last_price') and fast_info.last_price:
            price = fast_info.last_price
        elif info.get('currentPrice'):
            price = info.get('currentPrice')
        else:
            # آخر محاولة من التاريخ
            hist = t.history(period='5d')
            if not hist.empty: price = hist['Close'].iloc[-1]
        
        metrics['price'] = float(price)

        # القيمة السوقية (Market Cap) - مهمة جداً للحسابات
        market_cap = 0.0
        if hasattr(fast_info, 'market_cap') and fast_info.market_cap:
            market_cap = fast_info.market_cap
        elif info.get('marketCap'):
            market_cap = info.get('marketCap')
        
        # 2. جلب القوائم المالية (بيانات سنوية)
        # نستخدم القوائم السنوية لأنها أدق للمؤشرات الأساسية
        financials = t.financials
        balance_sheet = t.balance_sheet
        
        # المتغيرات الأساسية للحساب
        net_income = 0.0
        total_revenue = 0.0
        total_equity = 0.0
        total_assets = 0.0
        total_liabilities = 0.0
        total_debt = 0.0
        current_assets = 0.0
        current_liab = 0.0

        # أ) من قائمة الدخل (Income Statement)
        if not financials.empty:
            # محاولة العثور على صافي الدخل بأسماء مختلفة
            for key in ['Net Income', 'Net Income Common Stockholders', 'Net Income Continuous Operations']:
                if key in financials.index:
                    net_income = financials.loc[key].iloc[0] # آخر سنة
                    break
            
            if 'Total Revenue' in financials.index:
                total_revenue = financials.loc['Total Revenue'].iloc[0]
            elif 'Total Revenue' not in financials.index and 'Operating Revenue' in financials.index: # للبنوك أحياناً
                 total_revenue = financials.loc['Operating Revenue'].iloc[0]

        # ب) من الميزانية العمومية (Balance Sheet)
        if not balance_sheet.empty:
            # حقوق المساهمين
            if 'Stockholders Equity' in balance_sheet.index:
                total_equity = balance_sheet.loc['Stockholders Equity'].iloc[0]
            elif 'Total Assets' in balance_sheet.index and 'Total Liabilities Net Minority Interest' in balance_sheet.index:
                total_equity = balance_sheet.loc['Total Assets'].iloc[0] - balance_sheet.loc['Total Liabilities Net Minority Interest'].iloc[0]
            
            # الأصول والخصوم
            if 'Total Assets' in balance_sheet.index:
                total_assets = balance_sheet.loc['Total Assets'].iloc[0]
            
            # الديون (مجموع الديون قصيرة وطويلة الأجل)
            if 'Total Debt' in balance_sheet.index:
                total_debt = balance_sheet.loc['Total Debt'].iloc[0]
            
            # السيولة (Current Ratio)
            if 'Current Assets' in balance_sheet.index:
                current_assets = balance_sheet.loc['Current Assets'].iloc[0]
            if 'Current Liabilities' in balance_sheet.index:
                current_liab = balance_sheet.loc['Current Liabilities'].iloc[0]

        # 3. الحسابات الذكية (Calculating Ratios)
        
        # P/E (مكرر الربحية) = القيمة السوقية / صافي الدخل
        if market_cap > 0 and net_income > 0:
            metrics['pe_ratio'] = market_cap / net_income
        elif info.get('trailingPE'): # محاولة استخدام الجاهز إذا فشل الحساب
            metrics['pe_ratio'] = info.get('trailingPE')

        # P/B (مكرر الدفترية) = القيمة السوقية / حقوق المساهمين
        if market_cap > 0 and total_equity > 0:
            metrics['pb_ratio'] = market_cap / total_equity
        elif info.get('priceToBook'):
            metrics['pb_ratio'] = info.get('priceToBook')

        # ROE (العائد على الحقوق) = صافي الدخل / حقوق المساهمين
        if net_income > 0 and total_equity > 0:
            metrics['roe'] = (net_income / total_equity) * 100
        
        # ROA (العائد على الأصول)
        if net_income > 0 and total_assets > 0:
            metrics['roa'] = (net_income / total_assets) * 100

        # هوامش الربحية
        if total_revenue > 0:
            metrics['profit_margin'] = (net_income / total_revenue) * 100
            
        # نسبة المديونية (Debt to Equity)
        if total_equity > 0:
            metrics['debt_to_equity'] = total_debt / total_equity
            
        # التوزيعات
        div_yield = info.get('dividendYield', 0)
        metrics['dividend_yield'] = div_yield * 100 if div_yield else 0.0

        # نسبة السيولة الجارية
        if current_liab > 0:
            metrics['current_ratio'] = current_assets / current_liab

        # 4. معادلة غراهام (معدلة لتستخدم القيم الكلية)
        # Graham Value = Sqrt(22.5 * Earnings * BookValue) / Shares ... صعب بدون عدد الأسهم الدقيق
        # سنستخدم طريقة عكسية: Fair Market Cap = Sqrt(22.5 * Net Income * Total Equity)
        # ثم نقسم على Market Cap الحالي لنعرف النسبة
        if net_income > 0 and total_equity > 0:
            fair_mcap = (22.5 * net_income * total_equity) ** 0.5
            # سعر عادل تقريبي = السعر الحالي * (القيمة السوقية العادلة / القيمة السوقية الحالية)
            if market_cap > 0:
                metrics['fair_value'] = price * (fair_mcap / market_cap)

        # 5. توليد الرأي التحليلي (Opinion Generation)
        score = 0
        opinions = []
        
        # تقييم مكرر الربح
        if 0 < metrics['pe_ratio'] < 15:
            score += 2
            opinions.append("✅ السهم مغري جداً من حيث مكرر الربحية (أقل من 15).")
        elif 15 <= metrics['pe_ratio'] < 25:
            score += 1
            opinions.append("ℹ️ مكرر الربحية مقبول وفي النطاق الطبيعي.")
        elif metrics['pe_ratio'] > 25:
            score -= 1
            opinions.append("⚠️ مكرر الربحية مرتفع، السهم قد يكون متضخماً سعرياً.")
            
        # تقييم القيمة الدفترية
        if 0 < metrics['pb_ratio'] < 1.5:
            score += 1
            opinions.append("✅ يتداول السهم بالقرب من قيمته الدفترية (صفقة جيدة).")
            
        # تقييم العائد على الحقوق
        if metrics['roe'] > 15:
            score += 2
            opinions.append("🔥 إدارة الشركة ممتازة في توليد الأرباح (ROE > 15%).")
        elif metrics['roe'] < 5:
            score -= 1
            opinions.append("⚠️ العائد على حقوق المساهمين ضعيف.")
            
        # تقييم المديونية
        if metrics['debt_to_equity'] > 2:
            score -= 1
            opinions.append("⚠️ الشركة مثقلة بالديون (نسبة الدين للملكية عالية).")
        else:
            score += 1
            opinions.append("✅ وضع المديونية آمن ومستقر.")
            
        # تقييم التوزيعات
        if metrics['dividend_yield'] > 4:
            score += 1
            opinions.append(f"💰 الشركة توزع أرباحاً مجزية ({metrics['dividend_yield']:.1f}%).")

        metrics['score'] = score
        metrics['opinion'] = opinions
        
        if score >= 4: metrics['rating'] = "شراء قوي ⭐"
        elif score >= 2: metrics['rating'] = "شراء / احتفاظ ✅"
        elif score >= 0: metrics['rating'] = "محايد 😐"
        else: metrics['rating'] = "بيع / حذر ❌"

        return metrics

    except Exception as e:
        return None
