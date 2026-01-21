import yfinance as yf
import pandas as pd
import streamlit as st
import plotly.express as px
from market_data import get_ticker_symbol
from database import execute_query, get_db
from components import render_table

@st.cache_data(ttl=3600*4)
def get_fundamental_ratios(symbol):
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, "EPS": None, "Profit_Margin": None,
        "Book_Value": None, "Current_Price": 0.0, "Fair_Value": None, 
        "Dividend_Yield": None, "Debt_to_Equity": None, "Score": 0, 
        "Rating": "غير متاح", "Opinions": []
    }
    
    if not symbol: return metrics

    ticker_sym = get_ticker_symbol(symbol)
    ticker = yf.Ticker(ticker_sym)
    
    # 1. محاولة جلب السعر
    try:
        # History أسرع وأدق للسعر الحالي
        hist = ticker.history(period="5d")
        if not hist.empty:
            metrics["Current_Price"] = float(hist['Close'].iloc[-1])
        elif hasattr(ticker, 'fast_info'):
             metrics["Current_Price"] = ticker.fast_info.last_price
    except: pass

    if metrics["Current_Price"] == 0:
        metrics["Opinions"].append("تعذر جلب السعر الحالي")
        return metrics

    # 2. محاولة جلب البيانات المالية
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
        
        # تحسين النسب المئوية
        if metrics["ROE"]: metrics["ROE"] *= 100
        if metrics["Profit_Margin"]: metrics["Profit_Margin"] *= 100
        metrics["Dividend_Yield"] = (info.get('dividendYield', 0) or 0) * 100

        # حسابات تكميلية
        if metrics["P/E"] is None and metrics["EPS"] and metrics["EPS"] > 0:
            metrics["P/E"] = metrics["Current_Price"] / metrics["EPS"]
            
        # معادلة جراهام
        if metrics["EPS"] and metrics["EPS"] > 0 and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["Fair_Value"] = (22.5 * metrics["EPS"] * metrics["Book_Value"]) ** 0.5

    except Exception as e:
        metrics["Opinions"].append(f"بيانات جزئية مفقودة: {str(e)}")

    # 3. التقييم
    score = 0
    if metrics["Fair_Value"] and metrics["Current_Price"] < metrics["Fair_Value"]:
        score += 3; metrics["Opinions"].append("💎 سعر مغري (أقل من العادلة)")
    if metrics["P/E"] and 0 < metrics["P/E"] < 15:
        score += 2; metrics["Opinions"].append("✅ مكرر ربحية ممتاز")
    if metrics["ROE"] and metrics["ROE"] > 15:
        score += 2; metrics["Opinions"].append("🚀 عائد حقوق ملكية قوي")
    if metrics["Profit_Margin"] and metrics["Profit_Margin"] > 10:
        score += 2; metrics["Opinions"].append("💰 هوامش ربحية عالية")
    if metrics["P/B"] and metrics["P/B"] < 1.5:
        score += 1; metrics["Opinions"].append("قيمة دفترية جيدة")

    metrics["Score"] = min(score, 10)
    if score >= 7: metrics["Rating"] = "شراء قوي 🌟"
    elif score >= 5: metrics["Rating"] = "إيجابي ✅"
    elif score >= 3: metrics["Rating"] = "محايد 😐"
    else: metrics["Rating"] = "للمراجعة ⚠️"

    return metrics

def update_financial_statements(symbol):
    ticker_sym = get_ticker_symbol(symbol)
    ticker = yf.Ticker(ticker_sym)
    try:
        financials = ticker.financials.T
        if financials.empty:
            financials = ticker.get_financials().T
            if financials.empty: return False

        df = pd.DataFrame(index=financials.index)
        
        # تعبئة البيانات بأمان
        cols_map = {
            'Total Revenue': 'revenue', 'Operating Revenue': 'revenue',
            'Net Income': 'net_income', 'Gross Profit': 'gross_profit',
            'Operating Income': 'operating_income', 'Basic EPS': 'eps'
        }
        for api_col, db_col in cols_map.items():
            if api_col in financials.columns:
                df[db_col] = financials[api_col]
            elif db_col not in df.columns:
                df[db_col] = 0

        # معالجة التدفقات والميزانية
        balance = ticker.balance_sheet.T
        cashflow = ticker.cashflow.T
        
        for date in df.index:
            # الميزانية
            try:
                if not balance.empty:
                    row = balance.loc[balance.index == date]
                    if not row.empty:
                        df.at[date, 'total_assets'] = row.get('Total Assets', [0])[0]
                        df.at[date, 'total_liabilities'] = row.get('Total Liabilities Net Minority Interest', [0])[0]
                        df.at[date, 'total_equity'] = row.get('Stockholders Equity', [0])[0]
            except: pass
            
            # التدفقات
            try:
                if not cashflow.empty:
                    row = cashflow.loc[cashflow.index == date]
                    if not row.empty:
                        df.at[date, 'operating_cash_flow'] = row.get('Operating Cash Flow', [0])[0]
                        df.at[date, 'free_cash_flow'] = row.get('Free Cash Flow', [0])[0]
            except: pass

        df.fillna(0, inplace=True)
        
        # الحفظ في قاعدة البيانات
        for date, row in df.iterrows():
            d_str = str(date.date())
            query = """
                INSERT INTO FinancialStatements 
                (symbol, period_type, date, revenue, net_income, gross_profit, operating_income, total_assets, total_liabilities, total_equity, operating_cash_flow, free_cash_flow, eps, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, period_type, date) DO UPDATE SET
                revenue=EXCLUDED.revenue, net_income=EXCLUDED.net_income, gross_profit=EXCLUDED.gross_profit,
                operating_income=EXCLUDED.operating_income, total_assets=EXCLUDED.total_assets, 
                total_liabilities=EXCLUDED.total_liabilities, total_equity=EXCLUDED.total_equity,
                operating_cash_flow=EXCLUDED.operating_cash_flow, free_cash_flow=EXCLUDED.free_cash_flow, eps=EXCLUDED.eps;
            """
            vals = (
                symbol, 'Annual', d_str, 
                float(row.get('revenue',0)), float(row.get('net_income',0)), float(row.get('gross_profit',0)), 
                float(row.get('operating_income', 0)), float(row.get('total_assets',0)), 
                float(row.get('total_liabilities',0)), float(row.get('total_equity',0)), 
                float(row.get('operating_cash_flow',0)), float(row.get('free_cash_flow',0)), 
                float(row.get('eps', 0)), 'Yahoo'
            )
            execute_query(query, vals)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def get_stored_financials(symbol):
    with get_db() as conn:
        if conn:
            try: 
                return pd.read_sql("SELECT * FROM FinancialStatements WHERE symbol = %s ORDER BY date ASC", conn, params=(symbol,))
            except: pass
    return pd.DataFrame()

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

def get_thesis(symbol):
    with get_db() as conn:
        if conn:
            try:
                df = pd.read_sql("SELECT * FROM InvestmentThesis WHERE symbol = %s", conn, params=(symbol,))
                if not df.empty:
                    return df.iloc[0]
            except: pass
    return None

def render_financial_dashboard_ui(symbol):
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 تحديث القوائم", key="upd_fin"):
            with st.spinner("جاري جلب البيانات..."):
                if update_financial_statements(symbol):
                    st.success("تم التحديث")
                    st.rerun()
                else:
                    st.error("فشل الجلب")

    df = get_stored_financials(symbol)
    if not df.empty:
        df['year'] = pd.to_datetime(df['date']).dt.year
        df = df.sort_values('year')

        st.markdown("##### 📊 الأداء المالي (بالمليون)")
        chart_df = df.melt(id_vars=['year'], value_vars=['revenue', 'net_income'], var_name='Metric', value_name='Value')
        chart_df['Metric'] = chart_df['Metric'].map({'revenue': 'الإيرادات', 'net_income': 'صافي الربح'})
        fig = px.bar(chart_df, x='year', y='Value', color='Metric', barmode='group', color_discrete_map={'الإيرادات': '#0052CC', 'صافي الربح': '#006644'})
        fig.update_layout(paper_bgcolor="white", plot_bgcolor="white", font={'family': "Cairo"})
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("##### 📑 التفاصيل المالية")
        cols_display = {
            'revenue': 'الإيرادات', 'net_income': 'صافي الدخل', 
            'total_assets': 'الأصول', 'total_equity': 'حقوق الملكية', 
            'operating_cash_flow': 'التدفق التشغيلي'
        }
        # فلترة الأعمدة الموجودة فقط
        valid_cols = [c for c in cols_display.keys() if c in df.columns]
        
        if valid_cols:
            df_disp = df[['year'] + valid_cols].set_index('year').T
            df_disp.index = df_disp.index.map(cols_display)
            st.dataframe(df_disp, use_container_width=True)
    else: st.info("اضغط تحديث لجلب البيانات.")
