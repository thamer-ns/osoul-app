import yfinance as yf
import pandas as pd
import streamlit as st

@st.cache_data(ttl=300)
def get_tasi_data():
    try:
        # المؤشر العام للسوق السعودي
        ticker = yf.Ticker("^TASI.SR")
        # جلب بيانات يومين لحساب التغير
        hist = ticker.history(period="2d")
        if not hist.empty and len(hist) >= 1:
            curr = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2] if len(hist) > 1 else curr
            change = ((curr - prev) / prev) * 100
            return curr, change
    except: pass
    return 12000.0, 0.0

@st.cache_data(ttl=3600)
def get_static_info(symbol):
    return "شركة مساهمة", "قطاع عام"

@st.cache_data(ttl=3600)
def get_chart_history(symbol, period="1y", interval="1d"):
    try:
        # التأكد من وجود اللاحقة .SR
        ticker_sym = symbol if symbol.endswith(".SR") else f"{symbol}.SR"
        df = yf.download(ticker_sym, period=period, interval=interval, progress=False)
        if df.empty: return None
        return df
    except: return None

# جلب بيانات مجموعة أسهم لتحديث الأسعار
def fetch_batch_data(symbols):
    res = {}
    if not symbols: return res
    
    # دمج الرموز بسلسلة واحدة لتقليل الطلبات
    tickers = [s if s.endswith(".SR") else f"{s}.SR" for s in symbols]
    try:
        data = yf.download(tickers, period="2d", group_by='ticker', progress=False)
        # معالجة البيانات (تختلف الهيكلة إذا كان سهم واحد أو أكثر)
        for sym in symbols:
            t_sym = sym if sym.endswith(".SR") else f"{sym}.SR"
            try:
                if len(symbols) == 1:
                    hist = data
                else:
                    hist = data[t_sym]
                
                if not hist.empty:
                    price = hist['Close'].iloc[-1]
                    prev = hist['Close'].iloc[-2] if len(hist) > 1 else price
                    # تحويل القيم لأنواع بايثون البسيطة لتخزينها في القاعدة
                    res[sym] = {
                        'price': float(price),
                        'prev_close': float(prev),
                        'year_high': float(hist['High'].max()),
                        'year_low': float(hist['Low'].min()),
                        'dividend_yield': 0.0 # yfinance لا يعطي التوزيعات بدقة في هذا الوضع
                    }
            except: continue
    except: pass
    return res
