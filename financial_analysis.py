import yfinance as yf
import pandas as pd
import streamlit as st
import plotly.express as px
import requests
from datetime import datetime
from market_data import get_ticker_symbol
from database import execute_query, get_db
from components import render_table

# === أدوات التشخيص ===
def debug_msg(msg):
    st.toast(msg)
    print(msg)

# === إعداد جلسة الاتصال ===
def get_yf_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    return session

@st.cache_data(ttl=3600*4)
def get_fundamental_ratios(symbol):
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, "EPS": None, "Profit_Margin": None,
        "Book_Value": None, "Current_Price": 0.0, "Fair_Value": None, 
        "Dividend_Yield": None, "Debt_to_Equity": None, "Score": 0, 
        "Rating": "جاري التحليل...", "Opinions": []
    }
    
    if not symbol: return metrics
    ticker_sym = get_ticker_symbol(symbol)
    
    try:
        session = get_yf_session()
        ticker = yf.Ticker(ticker_sym, session=session)
    except:
        ticker = yf.Ticker(ticker_sym)
    
    # 1. جلب السعر (عادة لا يتم حظره بسهولة مثل القوائم)
    try:
        if hasattr(ticker, 'fast_info') and ticker.fast_info.last_price:
             metrics["Current_Price"] = ticker.fast_info.last_price
        else:
            hist = ticker.history(period="5d")
            if not hist.empty:
                metrics["Current_Price"] = float(hist['Close'].iloc[-1])
    except Exception as e:
        metrics["Opinions"].append(f"سعر السوق غير متاح حالياً")

    if metrics["Current_Price"] == 0:
        metrics["Rating"] = "السعر غير متاح"
        return metrics

    # 2. جلب المعلومات المالية
    try:
        info = ticker.info
        if not info or info.get('trailingEps') is None: 
            metrics["Opinions"].append("لم يتم العثور على بيانات مالية آلية")
        else:
            metrics["EPS"] = info.get('trailingEps')
            metrics["Book_Value"] = info.get('bookValue')
            metrics["P/E"] = info.get('trailingPE')
            metrics["P/B"] = info.get('priceToBook')
            metrics["ROE"] = (info.get('returnOnEquity') or 0) * 100
            metrics["Profit_Margin"] = (info.get('profitMargins') or 0) * 100
            metrics["Debt_to_Equity"] = info.get('debtToEquity', 0)
            metrics["Dividend_Yield"] = (info.get('dividendYield') or 0) * 100

            if metrics["EPS"] and metrics["EPS"] > 0 and metrics["Book_Value"] and metrics["Book_Value"] > 0:
                metrics["Fair_Value"] = (22.5 * metrics["EPS"] * metrics["Book_Value"]) ** 0.5

    except: pass

    # 3. التقييم
    score = 0
    ops = []
    
    if metrics["Fair_Value"] and metrics["Current_Price"] < metrics["Fair_Value"]:
        score += 3; ops.append("💎 سعر مغري (أقل من العادلة)")
    
    pe = metrics["P/E"]
    if pe:
        if 0 < pe <= 15: score += 2; ops.append("✅ مكرر ربحية ممتاز")
        elif 15 < pe <= 20: score += 1
    
    if metrics["ROE"] and metrics["ROE"] > 15: score += 2; ops.append("🚀 عائد حقوق ملكية قوي")
    
    metrics["Score"] = min(score, 10)
    metrics["Opinions"].extend(ops)
    
    if score >= 7: metrics["Rating"] = "شراء قوي 🌟"
    elif score >= 5: metrics["Rating"] = "إيجابي ✅"
    elif score >= 3: metrics["Rating"] = "محايد 😐"
    else: metrics["Rating"] = "للمراجعة ⚠️"

    return metrics

def update_financial_statements(symbol):
    ticker_sym = get_ticker_symbol(symbol)
    debug_msg(f"محاولة اتصال بـ Yahoo Finance لـ {ticker_sym}...")
    
    try:
        session = get_yf_session()
        ticker = yf.Ticker(ticker_sym, session=session)
        
        financials = ticker.financials.T
        if financials.empty:
            debug_msg("محاولة بديلة...")
            financials = ticker.get_financials().T
        
        if financials.empty:
            st.error(f"المصدر (Yahoo) يرفض الاتصال حالياً. يرجى استخدام الإدخال اليدوي بالأسفل.")
            return False

        df = pd.DataFrame(index=financials.index)
        
        # تعيين الأعمدة
        cols_map = {
            'revenue': ['Total Revenue', 'Operating Revenue'],
            'net_income': ['Net Income'],
            'gross_profit': ['Gross Profit'],
            'operating_income': ['Operating Income'],
            'eps': ['Basic EPS']
        }

        for db_col, candidates in cols_map.items():
            df[db_col] = 0.0
            for cand in candidates:
                if cand in financials.columns:
                    df[db_col] = financials[cand]
                    break
        
        balance = ticker.balance_sheet.T
        cashflow = ticker.cashflow.T
        
        # إضافة باقي الأعمدة وتعبئتها
        for col in ['total_assets', 'total_liabilities', 'total_equity', 'operating_cash_flow', 'free_cash_flow']:
            df[col] = 0.0

        for date in df.index:
            if not balance.empty:
                try:
                    r = balance.loc[balance.index == date]
                    if not r.empty:
                        df.at[date, 'total_assets'] = r.get('Total Assets', [0])[0]
                        df.at[date, 'total_liabilities'] = r.get('Total Liabilities Net Minority Interest', [0])[0]
                        df.at[date, 'total_equity'] = r.get('Stockholders Equity', [0])[0]
                except: pass
            
            if not cashflow.empty:
                try:
                    r = cashflow.loc[cashflow.index == date]
                    if not r.empty:
                        df.at[date, 'operating_cash_flow'] = r.get('Operating Cash Flow', [0])[0]
                        df.at[date, 'free_cash_flow'] = r.get('Free Cash Flow', [0])[0]
                except: pass

        df.fillna(0, inplace=True)
        
        # الحفظ
        for date, row in df.iterrows():
            save_financial_row(symbol, str(date.date()), row, 'Yahoo')
            
        debug_msg("تم الجلب والحفظ بنجاح.")
        return True

    except Exception as e:
        st.error(f"فشل الاتصال الآلي: {str(e)}")
        return False

def save_financial_row(symbol, date_str, row, source='Manual'):
    """دالة مساعدة لحفظ صف واحد في قاعدة البيانات"""
    def sf(val):
        try: return float(val)
        except: return 0.0

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
        symbol, 'Annual', date_str, 
        sf(row.get('revenue', 0)), sf(row.get('net_income', 0)), sf(row.get('gross_profit', 0)), 
        sf(row.get('operating_income', 0)), sf(row.get('total_assets', 0)), 
        sf(row.get('total_liabilities', 0)), sf(row.get('total_equity', 0)), 
        sf(row.get('operating_cash_flow', 0)), sf(row.get('free_cash_flow', 0)), 
        sf(row.get('eps', 0)), source
    )
    execute_query(query, vals)

def get_stored_financials(symbol):
    with get_db() as conn:
        if conn:
            try: return pd.read_sql("SELECT * FROM FinancialStatements WHERE symbol = %s ORDER BY date ASC", conn, params=(symbol,))
            except: pass
    return pd.DataFrame()

# ... (save_thesis, get_thesis كما هي)
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
                if not df.empty: return df.iloc[0]
            except: pass
    return None

def render_financial_dashboard_ui(symbol):
    # === زر التحديث الآلي ===
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 تحديث آلي (Yahoo)", key="upd_fin", type="primary"):
            if update_financial_statements(symbol):
                st.success("تم التحديث")
                st.rerun()
    
    # === عرض البيانات الموجودة ===
    df = get_stored_financials(symbol)
    
    # === نموذج الإدخال اليدوي (الحل للمشكلة) ===
    with st.expander("📝 إضافة/تعديل قوائم مالية يدوياً (الحل عند الحظر)", expanded=(df.empty)):
        st.info("إذا فشل التحديث الآلي بسبب حظر السيرفر، أدخل بيانات سنة معينة هنا وستظهر الرسوم البيانية فوراً.")
        with st.form("manual_fin_entry"):
            f_col1, f_col2, f_col3 = st.columns(3)
            year_input = f_col1.number_input("السنة المالية", min_value=2015, max_value=2030, value=2024, step=1)
            revenue_in = f_col2.number_input("الإيرادات (Revenue)", step=100000.0)
            net_income_in = f_col3.number_input("صافي الربح (Net Income)", step=100000.0)
            
            f_col4, f_col5, f_col6 = st.columns(3)
            assets_in = f_col4.number_input("مجموع الأصول (Assets)", step=100000.0)
            equity_in = f_col5.number_input("حقوق الملكية (Equity)", step=100000.0)
            ocf_in = f_col6.number_input("التدفق التشغيلي (OCF)", step=100000.0)

            submitted = st.form_submit_button("💾 حفظ البيانات يدوياً")
            if submitted:
                # تكوين صف بيانات
                row_data = {
                    'revenue': revenue_in, 'net_income': net_income_in,
                    'total_assets': assets_in, 'total_equity': equity_in,
                    'operating_cash_flow': ocf_in
                }
                # نفترض أن تاريخ القوائم هو نهاية تلك السنة
                date_str = f"{year_input}-12-31"
                save_financial_row(symbol, date_str, row_data, 'Manual')
                st.success(f"تم حفظ بيانات سنة {year_input} بنجاح!")
                st.rerun()

    # === الرسم البياني والجدول ===
    if not df.empty:
        try:
            df['year'] = pd.to_datetime(df['date']).dt.year
            df = df.sort_values('year')

            st.markdown("##### 📊 الأداء المالي")
            if 'revenue' in df.columns and 'net_income' in df.columns:
                chart_df = df.melt(id_vars=['year'], value_vars=['revenue', 'net_income'], var_name='Metric', value_name='Value')
                chart_df['Metric'] = chart_df['Metric'].map({'revenue': 'الإيرادات', 'net_income': 'صافي الربح'})
                fig = px.bar(chart_df, x='year', y='Value', color='Metric', barmode='group', 
                             color_discrete_map={'الإيرادات': '#0052CC', 'صافي الربح': '#006644'})
                fig.update_layout(paper_bgcolor="white", plot_bgcolor="white", font={'family': "Cairo"}, height=400)
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("##### 📑 الجدول التفصيلي")
            cols_display = {
                'revenue': 'الإيرادات', 'net_income': 'صافي الدخل', 
                'total_assets': 'الأصول', 'total_equity': 'حقوق الملكية', 
                'operating_cash_flow': 'التدفق التشغيلي'
            }
            valid_cols = [c for c in cols_display.keys() if c in df.columns]
            if valid_cols:
                df_disp = df[['year'] + valid_cols].set_index('year').T
                df_disp.index = df_disp.index.map(cols_display)
                st.dataframe(df_disp, use_container_width=True)
        except Exception as e:
            st.error(f"خطأ العرض: {e}")
    else:
        st.warning("لا توجد بيانات. جرب 'التحديث الآلي' أو استخدم 'الإدخال اليدوي' أعلاه.")
