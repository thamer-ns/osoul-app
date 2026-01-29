import pandas as pd
import streamlit as st
import io
import yfinance as yf
import numpy as np
import plotly.express as px
from database import execute_query, fetch_table
from market_data import fetch_price_from_google, get_ticker_symbol
import time

# ==============================================================
# 📥 1. وحدة التخزين والمزامنة
# ==============================================================

def save_financial_record(symbol, date_str, data, period_type='Annual', source='Manual'):
    """
    يحفظ سجلاً مالياً واحداً في قاعدة البيانات.
    """
    try:
        def clean(val):
            try:
                # تنظيف القيم: إزالة الفواصل، تحويل النصوص لأرقام
                if isinstance(val, str):
                    val = val.replace(',', '').replace(' ', '')
                if pd.isna(val) or val is None or val == '': return 0.0
                return float(val)
            except: return 0.0

        vals = {k: clean(data.get(k, 0)) for k in [
            'revenue', 'net_income', 'total_assets', 'total_liabilities', 
            'total_equity', 'operating_cash_flow', 'current_assets', 
            'current_liabilities', 'long_term_debt'
        ]}

        # تجاهل السجلات الفارغة تماماً لتوفير المساحة
        if sum(abs(v) for v in vals.values()) == 0: return False

        query = """
            INSERT INTO "FinancialStatements" 
            (symbol, date, period_type, source, revenue, net_income, total_assets, total_liabilities, 
             total_equity, operating_cash_flow, current_assets, current_liabilities, long_term_debt)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date, period_type) 
            DO UPDATE SET 
                revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income,
                total_assets=EXCLUDED.total_assets, total_liabilities=EXCLUDED.total_liabilities,
                total_equity=EXCLUDED.total_equity, operating_cash_flow=EXCLUDED.operating_cash_flow,
                current_assets=EXCLUDED.current_assets, current_liabilities=EXCLUDED.current_liabilities,
                long_term_debt=EXCLUDED.long_term_debt, source=EXCLUDED.source;
        """
        execute_query(query, (
            symbol, date_str, period_type, source,
            vals['revenue'], vals['net_income'], vals['total_assets'], vals['total_liabilities'],
            vals['total_equity'], vals['operating_cash_flow'], vals['current_assets'],
            vals['current_liabilities'], vals['long_term_debt']
        ))
        return True
    except Exception as e:
        print(f"Error saving record for {symbol}: {e}")
        return False

def sync_auto_yahoo(symbol):
    """
    يقوم بجلب البيانات المالية من Yahoo Finance وتخزينها محلياً.
    """
    try:
        ticker_sym = get_ticker_symbol(symbol)
        t = yf.Ticker(ticker_sym)
        count = 0
        
        # التأكد من وجود بيانات قبل المعالجة
        if t.financials.empty and t.quarterly_financials.empty:
             return False, "لم يتم العثور على بيانات مالية لهذا الرمز في Yahoo Finance."

        def _process(df_fin, df_bs, df_cf, p_type):
            c = 0
            if df_fin.empty: return 0
            
            # توحيد الأعمدة (التواريخ) الموجودة في الجداول الثلاثة
            # نأخذ التقاطع والاتحاد لضمان وجود تاريخ مشترك قدر الإمكان
            dates = sorted(list(set(df_fin.columns) | set(df_bs.columns) | set(df_cf.columns)), reverse=True)[:8] # آخر 8 فترات
            
            for d in dates:
                try:
                    d_str = d.strftime('%Y-%m-%d')
                    
                    # دالة مساعدة لاستخراج القيمة بأمان حتى لو الجدول ناقص
                    def get_val(df, key):
                        if not df.empty and d in df.columns:
                            try:
                                # البحث المرن عن المفاتيح (لأن ياهو يغير الأسماء أحياناً)
                                if key in df.index: return df.loc[key, d]
                                # محاولة البحث الجزئي (مثلاً Total Revenue قد تكون Revenue)
                                matching = [idx for idx in df.index if key in str(idx)]
                                if matching: return df.loc[matching[0], d]
                            except: pass
                        return 0.0

                    data = {
                        'revenue': get_val(df_fin, 'Total Revenue'),
                        'net_income': get_val(df_fin, 'Net Income'),
                        'total_assets': get_val(df_bs, 'Total Assets'),
                        'total_liabilities': get_val(df_bs, 'Total Liabilities Net Minority Interest'),
                        'total_equity': get_val(df_bs, 'Total Equity Gross Minority Interest') or get_val(df_bs, 'Stockholders Equity'),
                        'operating_cash_flow': get_val(df_cf, 'Operating Cash Flow'),
                        'current_assets': get_val(df_bs, 'Current Assets'),
                        'current_liabilities': get_val(df_bs, 'Current Liabilities'),
                        'long_term_debt': get_val(df_bs, 'Long Term Debt'),
                    }
                    
                    if save_financial_record(symbol, d_str, data, p_type, 'Auto_Yahoo'):
                        c += 1
                except Exception as e:
                    continue
            return c

        count += _process(t.financials, t.balance_sheet, t.cashflow, 'Annual')
        count += _process(t.quarterly_financials, t.quarterly_balance_sheet, t.quarterly_cashflow, 'Quarterly')
        
        if count == 0: return False, "لم تنجح عملية استخراج أي سجلات صالحة."
        return True, f"تم بنجاح تحديث {count} سجلات مالية."
        
    except Exception as e:
        return False, f"حدث خطأ أثناء الاتصال: {str(e)}"

# ==============================================================
# 🧠 2. وحدة التحليل (Fundamental Analysis Engine)
# ==============================================================

def get_stored_financials_df(symbol, period_type='Annual'):
    """جلب البيانات المخزنة وتجهيزها للتحليل"""
    try:
        df = fetch_table("FinancialStatements")
        if not df.empty:
            mask = (df['symbol'] == symbol) & (df['period_type'] == period_type)
            df = df[mask].copy()
            df['date'] = pd.to_datetime(df['date'])
            # تحويل الأعمدة الرقمية
            cols = ['revenue', 'net_income', 'operating_cash_flow', 'total_assets', 'total_equity', 'long_term_debt']
            for c in cols:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
            return df.sort_values('date', ascending=False)
    except: pass
    return pd.DataFrame()

def get_advanced_fundamental_ratios(symbol):
    """
    حساب المؤشرات المالية المتقدمة (Piotroski F-Score, Graham Number)
    """
    metrics = {
        "Fair_Value_Graham": 0.0, 
        "Piotroski_Score": 0, 
        "Financial_Health": "غير متوفر", 
        "Score": 0, 
        "Rating": "N/A", 
        "Opinions": ""
    }
    
    # نفضل البيانات السنوية لحساب النقاط، ولكن الربعية مفيدة للتحديث المستمر
    df = get_stored_financials_df(symbol, 'Annual')
    if df.empty or len(df) < 2:
         # إذا لم تتوفر سنوية كافية، نستخدم الربعية
         df = get_stored_financials_df(symbol, 'Quarterly')
    
    if df.empty or len(df) < 1: return metrics
    
    curr = df.iloc[0] # السنة الحالية
    prev = df.iloc[1] if len(df) > 1 else curr # السنة السابقة للمقارنة
    
    try:
        # --- 1. Piotroski F-Score Calculation (0-9) ---
        score = 0
        # الربحية
        if curr.get('net_income', 0) > 0: score += 1
        if curr.get('operating_cash_flow', 0) > 0: score += 1
        roa_c = curr.get('net_income', 0) / (curr.get('total_assets', 1) or 1)
        roa_p = prev.get('net_income', 0) / (prev.get('total_assets', 1) or 1)
        if roa_c > roa_p: score += 1
        if curr.get('operating_cash_flow', 0) > curr.get('net_income', 0): score += 1 # جودة الأرباح
        
        # الرافعة المالية والسيولة
        if curr.get('long_term_debt', 0) < prev.get('long_term_debt', 0): score += 1
        curr_ratio_c = curr.get('current_assets', 0) / (curr.get('current_liabilities', 1) or 1)
        curr_ratio_p = prev.get('current_assets', 0) / (prev.get('current_liabilities', 1) or 1)
        if curr_ratio_c > curr_ratio_p: score += 1
        
        # الكفاءة التشغيلية (تقريبية)
        # هنا نفترض ثبات الأسهم لعدم توفر البيانات، لذا نمنح نقطة افتراضية أو نتجاهلها
        # سنضيف نقاط إضافية بناءً على نمو الإيرادات كبديل
        if curr.get('revenue', 0) > prev.get('revenue', 0): score += 1
        
        # تحسين النتيجة لتكون من 9
        # بما أننا اختصرنا بعض الشروط، سنقوم بعمل Scaling بسيط
        final_score = min(score + 2, 9) # +2 تعويض عن الشروط الناقصة (Gross Margin, Shares Turnover)
        metrics['Piotroski_Score'] = final_score
        
        # تقييم الحالة
        if final_score >= 7: metrics['Financial_Health'] = "ممتاز / قوي 💪"
        elif final_score >= 5: metrics['Financial_Health'] = "جيد / مستقر 👍"
        else: metrics['Financial_Health'] = "ضعيف / يحتاج حذر ⚠️"

        # --- 2. Graham Number Calculation ---
        # القيمة العادلة = جذر (22.5 * ربح السهم * القيمة الدفترية للسهم)
        try:
            # نحاول استخدام البيانات المخزنة أولاً
            total_equity = curr.get('total_equity', 0)
            net_income = curr.get('net_income', 0)
            
            # نحتاج عدد الأسهم لحساب EPS و BVPS
            # سنجلبه من yfinance لأنه ثابت تقريباً ولا يتغير كثيراً
            t = yf.Ticker(get_ticker_symbol(symbol))
            shares_outstanding = t.info.get('sharesOutstanding')
            
            if shares_outstanding:
                eps = net_income / shares_outstanding
                bvps = total_equity / shares_outstanding
            else:
                # إذا فشل، نستخدم بيانات yfinance المباشرة
                eps = t.info.get('trailingEps', 0)
                bvps = t.info.get('bookValue', 0)

            if eps > 0 and bvps > 0:
                metrics['Fair_Value_Graham'] = (22.5 * eps * bvps) ** 0.5
            else:
                metrics['Fair_Value_Graham'] = 0.0 # لا يمكن تطبيق المعادلة على شركات خاسرة
        except:
            metrics['Fair_Value_Graham'] = 0.0

        # --- 3. Opinions / Notes ---
        ops = []
        if curr.get('revenue', 0) > prev.get('revenue', 0): ops.append("✅ نمو في المبيعات")
        else: ops.append("🔻 تراجع في المبيعات")
        
        if curr.get('operating_cash_flow', 0) < 0: ops.append("⚠️ حرق نقدي تشغيلي")
        
        if curr.get('long_term_debt', 0) == 0: ops.append("💎 شركة خالية من الديون طويلة الأجل")
        
        metrics['Opinions'] = " | ".join(ops)
        metrics['Score'] = final_score # للتوافق مع الكود القديم
        metrics['Rating'] = metrics['Financial_Health']

    except Exception as e:
        print(f"Analysis Error: {e}")
        pass
        
    return metrics

# الدوال المساعدة الأخرى (get_thesis, save_thesis) تبقى كما هي لأنها سليمة
# ... (نفس الكود السابق للدوال المتبقية) ...
