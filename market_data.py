import yfinance as yf
import streamlit as st
from config import TADAWUL_DB # الآن تأتي من الملف المركزي تلقائياً

def get_ticker_symbol(symbol):
    s = str(symbol).strip().upper()
    if s.isdigit(): return f"{s}.SR"
    return s

def get_static_info(symbol):
    # تنظيف الرمز
    s_clean = str(symbol).strip().replace('.SR', '').replace('.sr', '')
    
    # البحث في القاعدة الضخمة الجديدة
    if s_clean in TADAWUL_DB:
        return TADAWUL_DB[s_clean]['name'], TADAWUL_DB[s_clean]['sector']
        
    return f"سهم {s_clean}", "أخرى" # احتياط فقط

# ... (باقي الكود كما هو في الردود السابقة بدون تغيير) ...
