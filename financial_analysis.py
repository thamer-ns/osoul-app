import yfinance as yf
import pandas as pd
import streamlit as st
import plotly.express as px
from market_data import get_ticker_symbol
from database import execute_query, fetch_table, get_db

# ---------------------------------------------------------
# 1. دوال جلب المؤشرات الأساسية (لصفحة التحليل الرئيسية)
# ---------------------------------------------------------

@st.cache_data(ttl=3600*4)
def get_fundamental_ratios(symbol):
    """جلب المؤشرات المالية الرئيسية (P/E, P/B, etc)"""
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, "EPS": None, "Profit_Margin": None,
        "Book_Value": None, "Current_Price": 0.0, "Fair_Value": None, 
        "Dividend_Yield": None, "Debt_to_Equity": None, "Score": 0, 
        "Rating": "تحليل غير متاح", "Opinions": []
    }
    
    ticker_sym = get_ticker_symbol(symbol)
    ticker = yf.Ticker(ticker_sym)
    
    # محاولة جلب السعر
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
            
        # القيمة العادلة (معادلة جراهام المخففة)
        if metrics["EPS"] and metrics["EPS"] > 0 and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["Fair_Value"] = (22.5 * metrics["EPS"] * metrics["Book_Value"]) ** 0.5

    except Exception as e:
        metrics["Opinions"].append(f"بيانات ناقصة: {str(e)}")

    # نظام التقييم البسيط
    score = 0
    ops = []
    
    if metrics["Fair_Value"] and metrics["Current_Price"] < metrics["Fair_Value"]:
        score += 3; ops.append("💎 سعر مغري (أقل من العادلة)")
    
    pe = metrics["P/E"]
    if pe:
        if 0 < pe <= 15: score += 2; ops.append("✅ مكرر ربحية ممتاز")
        elif 15 < pe <= 22: score += 1
    
    if metrics["ROE"] and metrics["ROE"] > 15: score += 2; ops.append("🚀 عائد حقوق ملكية قوي")
    if metrics["Profit_Margin"] and metrics["Profit_Margin"] > 10: score += 2; ops.append("💰 هوامش ربحية عالية")
    if metrics["Debt_to_Equity"] and metrics["Debt_to_Equity"] < 100: score += 1

    metrics["Score"] = min(score, 10)
    metrics["Opinions"] = ops
    
    if score >= 7: metrics["Rating"] = "شراء قوي 🌟"
    elif score >= 5: metrics["Rating"] = "إيجابي ✅"
    elif score >= 3: metrics["Rating"] = "محايد 😐"
    else: metrics["Rating"] = "للمراجعة ⚠️"

    return metrics

# ---------------------------------------------------------
# 2. دوال التعامل مع القوائم المالية (تحديث + جلب)
# ---------------------------------------------------------

def update_financial_statements(symbol):
    """جلب القوائم المالية من ياهو وتخزينها في قاعدة البيانات"""
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
        df['eps'] = financials.get('Basic EPS', 0) # إضافة ربحية السهم
        
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
                (symbol, period_type, date, revenue, net_income, gross_profit, operating_income, total_assets, total_liabilities, total_equity, operating_cash_flow, free_cash_flow, eps, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, 'Annual', d_str, row['revenue'], row['net_income'], row['gross_profit'], 
                  row.get('operating_income', 0),
                  row.get('total_assets',0), row.get('total_liabilities',0), row.get('total_equity',0), 
                  row.get('operating_cash_flow',0), row.get('free_cash_flow',0), row.get('eps', 0), 'Yahoo'))
        return True
    except Exception as e:
        print(f"Error fetching financials: {e}")
        return False

def get_stored_financials(symbol):
    """استرجاع البيانات من قاعدة البيانات"""
    with get_db() as conn:
        try:
            # نتأكد من جلب كل الأعمدة
            return pd.read_sql(f"SELECT * FROM FinancialStatements WHERE symbol = '{symbol}' ORDER BY date ASC", conn)
        except: return pd.DataFrame()

# ---------------------------------------------------------
# 3. دوال الأطروحة الاستثمارية
# ---------------------------------------------------------

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

# ---------------------------------------------------------
# 4. دالة عرض الواجهة (UI) - تم توسيع الصفوف هنا
# ---------------------------------------------------------

def render_financial_dashboard_ui(symbol):
    """واجهة عرض القوائم المالية المصممة بالكامل"""
    from components import render_table
    
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 تحديث القوائم", key="upd_fin"):
            with st.spinner("جاري جلب البيانات..."):
                update_financial_statements(symbol)
                st.rerun()

    df = get_stored_financials(symbol)
    if not df.empty:
        # تحسين البيانات
        df['year'] = pd.to_datetime(df['date']).dt.year
        df = df.sort_values('year')

        # 1. الرسم البياني (تم تحسين الألوان)
        st.markdown("##### 📊 الأداء المالي (بالمليون)")
        chart_df = df.melt(id_vars=['year'], value_vars=['revenue', 'net_income'], var_name='Metric', value_name='Value')
        chart_df['Metric'] = chart_df['Metric'].map({'revenue': 'الإيرادات', 'net_income': 'صافي الربح'})
        
        fig = px.bar(chart_df, x='year', y='Value', color='Metric', barmode='group',
                     color_discrete_map={'الإيرادات': '#0052CC', 'صافي الربح': '#36B37E'})
        fig.update_layout(paper_bgcolor="white", plot_bgcolor="white", font={'family': "Cairo"})
        st.plotly_chart(fig, use_container_width=True)

        # 2. الجدول (شامل لكل الصفوف)
        st.markdown("##### 📑 التفاصيل المالية السنوية")
        
        # اختيار كل الأعمدة المتاحة في قاعدة البيانات
        # ملاحظة: تأكدنا في دالة التحديث من حفظ هذه الأعمدة
        cols_to_show = [
            'revenue', 
            'gross_profit', 
            'operating_income',
            'net_income', 
            'eps',
            'operating_cash_flow', 
            'free_cash_flow',
            'total_assets', 
            'total_liabilities',
            'total_equity'
        ]
        
        # التأكد من وجود الأعمدة في الداتا فريم (لتجنب الأخطاء إذا كانت البيانات قديمة)
        available_cols = [c for c in cols_to_show if c in df.columns]
        
        pivot_df = df.set_index('year')[available_cols]
        
        # القاموس الكامل لتعريب الأسماء
        translation_map = {
            'revenue': 'الإيرادات',
            'gross_profit': 'إجمالي الربح',
            'operating_income': 'الدخل التشغيلي',
            'net_income': 'صافي الدخل',
            'eps': 'ربحية السهم (EPS)',
            'operating_cash_flow': 'التدفق التشغيلي',
            'free_cash_flow': 'التدفق الحر',
            'total_assets': 'مجموع الأصول',
            'total_liabilities': 'مجموع الالتزامات',
            'total_equity': 'حقوق الملكية'
        }
        
        # إعادة التسمية
        pivot_df = pivot_df.rename(columns=translation_map)
        
        # التدوير (Transpose) لجعل السنوات أعمدة
        display_df = pivot_df.T.reset_index()
        display_df.columns.name = None 
        display_df = display_df.rename(columns={'index': 'المؤشر المالي'})
        
        # بناء تعريف الأعمدة للجدول
        cols_def = [('المؤشر المالي', 'المؤشر المالي')]
        for col in display_df.columns:
            if col != 'المؤشر المالي':
                cols_def.append((col, str(col)))
        
        render_table(display_df, cols_def)

    else:
        st.info("لا توجد بيانات مالية محفوظة. اضغط 'تحديث القوائم' لجلبها.")
