import yfinance as yf
import pandas as pd
import streamlit as st
import plotly.express as px
from market_data import get_ticker_symbol
from database import execute_query, get_db
from components import render_table

# === أدوات التشخيص ===
def debug_msg(msg):
    """دالة مساعدة لإظهار خطوات العمل على الشاشة"""
    st.toast(msg)
    print(msg)

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
    ticker = yf.Ticker(ticker_sym)
    
    # 1. جلب السعر
    try:
        # محاولة 1: Fast Info (الأسرع)
        if hasattr(ticker, 'fast_info') and ticker.fast_info.last_price:
             metrics["Current_Price"] = ticker.fast_info.last_price
        else:
            # محاولة 2: History
            hist = ticker.history(period="5d")
            if not hist.empty:
                metrics["Current_Price"] = float(hist['Close'].iloc[-1])
    except Exception as e:
        metrics["Opinions"].append(f"خطأ في السعر: {str(e)}")

    if metrics["Current_Price"] == 0:
        metrics["Rating"] = "السعر غير متاح"
        return metrics

    # 2. جلب المعلومات المالية (Info)
    try:
        info = ticker.info
        if not info or info.get('trailingEps') is None: 
            # محاولة fallback إذا فشل yfinance العادي
            metrics["Opinions"].append("لم يتم العثور على بيانات مالية تفصيلية من المصدر")
        else:
            metrics["EPS"] = info.get('trailingEps')
            metrics["Book_Value"] = info.get('bookValue')
            metrics["P/E"] = info.get('trailingPE')
            metrics["P/B"] = info.get('priceToBook')
            metrics["ROE"] = (info.get('returnOnEquity') or 0) * 100
            metrics["Profit_Margin"] = (info.get('profitMargins') or 0) * 100
            metrics["Debt_to_Equity"] = info.get('debtToEquity', 0)
            metrics["Dividend_Yield"] = (info.get('dividendYield') or 0) * 100

            # معادلة جراهام
            if metrics["EPS"] and metrics["EPS"] > 0 and metrics["Book_Value"] and metrics["Book_Value"] > 0:
                metrics["Fair_Value"] = (22.5 * metrics["EPS"] * metrics["Book_Value"]) ** 0.5

    except Exception as e:
        metrics["Opinions"].append(f"خطأ في جلب المؤشرات: {e}")

    # 3. حساب التقييم
    score = 0
    ops = []
    
    if metrics["Fair_Value"] and metrics["Current_Price"] < metrics["Fair_Value"]:
        score += 3; ops.append("💎 سعر مغري (أقل من القيمة العادلة)")
    
    pe = metrics["P/E"]
    if pe:
        if 0 < pe <= 15: score += 2; ops.append("✅ مكرر ربحية ممتاز")
        elif 15 < pe <= 20: score += 1
    
    if metrics["ROE"] and metrics["ROE"] > 15: score += 2; ops.append("🚀 عائد حقوق ملكية قوي")
    if metrics["Profit_Margin"] and metrics["Profit_Margin"] > 10: score += 2; ops.append("💰 هوامش ربحية عالية")

    metrics["Score"] = min(score, 10)
    metrics["Opinions"].extend(ops)
    
    if score >= 7: metrics["Rating"] = "شراء قوي 🌟"
    elif score >= 5: metrics["Rating"] = "إيجابي ✅"
    elif score >= 3: metrics["Rating"] = "محايد 😐"
    else: metrics["Rating"] = "للمراجعة ⚠️"

    return metrics

def update_financial_statements(symbol):
    ticker_sym = get_ticker_symbol(symbol)
    ticker = yf.Ticker(ticker_sym)
    
    debug_msg(f"جاري الاتصال بـ Yahoo Finance لـ {ticker_sym}...")
    
    try:
        # جلب القوائم
        financials = ticker.financials.T
        if financials.empty:
            debug_msg("محاولة بديلة لجلب القوائم...")
            financials = ticker.get_financials().T
        
        if financials.empty:
            st.error(f"عذراً، لا توجد قوائم مالية متاحة لـ {symbol} في المصدر.")
            return False

        # تحضير الـ DataFrame
        df = pd.DataFrame(index=financials.index)
        
        # تعبئة الأعمدة الأساسية
        # نتأكد من وجود الأعمدة حتى لو غير موجودة في المصدر
        target_cols = {
            'revenue': ['Total Revenue', 'Operating Revenue'],
            'net_income': ['Net Income'],
            'gross_profit': ['Gross Profit'],
            'operating_income': ['Operating Income'],
            'eps': ['Basic EPS']
        }

        for db_col, candidates in target_cols.items():
            df[db_col] = 0.0
            for cand in candidates:
                if cand in financials.columns:
                    df[db_col] = financials[cand]
                    break
        
        # جلب الميزانية والتدفقات
        balance = ticker.balance_sheet.T
        cashflow = ticker.cashflow.T
        
        df['total_assets'] = 0.0
        df['total_liabilities'] = 0.0
        df['total_equity'] = 0.0
        df['operating_cash_flow'] = 0.0
        df['free_cash_flow'] = 0.0

        for date in df.index:
            # دمج بيانات الميزانية
            if not balance.empty:
                try:
                    row_bs = balance.loc[balance.index == date]
                    if not row_bs.empty:
                        df.at[date, 'total_assets'] = row_bs.get('Total Assets', [0])[0]
                        df.at[date, 'total_liabilities'] = row_bs.get('Total Liabilities Net Minority Interest', [0])[0]
                        df.at[date, 'total_equity'] = row_bs.get('Stockholders Equity', [0])[0]
                except: pass
            
            # دمج بيانات التدفقات
            if not cashflow.empty:
                try:
                    row_cf = cashflow.loc[cashflow.index == date]
                    if not row_cf.empty:
                        df.at[date, 'operating_cash_flow'] = row_cf.get('Operating Cash Flow', [0])[0]
                        df.at[date, 'free_cash_flow'] = row_cf.get('Free Cash Flow', [0])[0]
                except: pass

        df.fillna(0, inplace=True)
        debug_msg(f"تم جلب {len(df)} سنوات مالية. جاري الحفظ...")

        # الحفظ في قاعدة البيانات
        saved_count = 0
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
            
            # تحويل القيم بأمان تام إلى float
            def safe_float(val):
                try: return float(val)
                except: return 0.0

            vals = (
                symbol, 'Annual', d_str, 
                safe_float(row['revenue']), safe_float(row['net_income']), safe_float(row['gross_profit']), 
                safe_float(row['operating_income']), safe_float(row['total_assets']), 
                safe_float(row['total_liabilities']), safe_float(row['total_equity']), 
                safe_float(row['operating_cash_flow']), safe_float(row['free_cash_flow']), 
                safe_float(row['eps']), 'Yahoo'
            )
            execute_query(query, vals)
            saved_count += 1
            
        debug_msg(f"تم حفظ {saved_count} سجلات بنجاح.")
        return True

    except Exception as e:
        st.error(f"خطأ غير متوقع أثناء المعالجة: {str(e)}")
        return False

def get_stored_financials(symbol):
    with get_db() as conn:
        if conn:
            try: 
                return pd.read_sql("SELECT * FROM FinancialStatements WHERE symbol = %s ORDER BY date ASC", conn, params=(symbol,))
            except Exception as e:
                # إذا فشل الاستعلام، غالباً الجدول غير موجود أو به مشكلة
                return pd.DataFrame()
    return pd.DataFrame()

# ... (بقية الدوال save_thesis, get_thesis كما هي) ...
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
    # زر الإصلاح السريع
    with st.expander("🛠️ أدوات الصيانة (اضغط هنا إذا لم يظهر الرسم)"):
        if st.button("إعادة بناء جدول البيانات المالية (Reset Table)"):
            execute_query("DROP TABLE IF EXISTS FinancialStatements;")
            from database import init_db
            init_db()
            st.success("تم إعادة بناء الجدول. اضغط تحديث القوائم الآن.")

    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("🔄 تحديث القوائم", key="upd_fin", type="primary"):
            if update_financial_statements(symbol):
                st.success("تم التحديث")
                st.rerun()
            
    df = get_stored_financials(symbol)
    
    if not df.empty:
        try:
            df['year'] = pd.to_datetime(df['date']).dt.year
            df = df.sort_values('year')

            st.markdown("##### 📊 الأداء المالي (بالمليون)")
            # الرسم البياني
            if 'revenue' in df.columns and 'net_income' in df.columns:
                chart_df = df.melt(id_vars=['year'], value_vars=['revenue', 'net_income'], var_name='Metric', value_name='Value')
                chart_df['Metric'] = chart_df['Metric'].map({'revenue': 'الإيرادات', 'net_income': 'صافي الربح'})
                fig = px.bar(chart_df, x='year', y='Value', color='Metric', barmode='group', 
                             color_discrete_map={'الإيرادات': '#0052CC', 'صافي الربح': '#006644'})
                fig.update_layout(paper_bgcolor="white", plot_bgcolor="white", font={'family': "Cairo"}, height=400)
                st.plotly_chart(fig, use_container_width=True)

            # الجدول
            st.markdown("##### 📑 التفاصيل المالية")
            cols_display = {
                'revenue': 'الإيرادات', 'net_income': 'صافي الدخل', 'gross_profit': 'إجمالي الربح',
                'total_assets': 'الأصول', 'total_equity': 'حقوق الملكية', 
                'operating_cash_flow': 'التدفق التشغيلي', 'free_cash_flow': 'التدفق الحر'
            }
            valid_cols = [c for c in cols_display.keys() if c in df.columns]
            
            if valid_cols:
                df_disp = df[['year'] + valid_cols].set_index('year').T
                df_disp.index = df_disp.index.map(cols_display)
                st.dataframe(df_disp, use_container_width=True)
            else:
                st.warning("البيانات موجودة لكن الأعمدة المطلوبة فارغة.")
        except Exception as e:
            st.error(f"خطأ في عرض البيانات: {e}")
            st.write(df.head()) # للمساعدة في التشخيص
    else:
        st.info("لا توجد بيانات محفوظة. يرجى الضغط على زر 'تحديث القوائم'.")
