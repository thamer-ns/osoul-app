import yfinance as yf
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from market_data import get_ticker_symbol

# --- قاموس الترجمة الموحد ---
TERM_MAPPING = {
    "Total Revenue": "إجمالي الإيرادات", "Revenue": "الإيرادات",
    "Cost Of Revenue": "تكلفة الإيرادات", "Gross Profit": "مجمل الربح",
    "Operating Expense": "المصاريف التشغيلية", "Operating Income": "الربح التشغيلي",
    "Net Income": "صافي الربح", "EBITDA": "الربح قبل الفائدة والضرائب والإهلاك",
    "Basic EPS": "ربحية السهم الأساسية", "Diluted EPS": "ربحية السهم المخفضة",
    "Total Assets": "إجمالي الأصول", "Total Liab": "إجمالي الالتزامات",
    "Total Liabilities Net Minority Interest": "إجمالي الالتزامات",
    "Total Stockholder Equity": "حقوق المساهمين", "Cash And Cash Equivalents": "النقد وما في حكمه",
    "Inventory": "المخزون", "Total Debt": "إجمالي الديون",
    "Operating Cash Flow": "التدفق النقدي التشغيلي", "Investing Cash Flow": "التدفق النقدي الاستثماري",
    "Financing Cash Flow": "التدفق النقدي التمويلي", "Free Cash Flow": "التدفق النقدي الحر"
}

def translate_index(df):
    if df is None or df.empty: return df
    df.index = df.index.map(lambda x: TERM_MAPPING.get(str(x).strip(), x))
    return df

# --- المحرك القديم (للمؤشرات) ---
@st.cache_data(ttl=3600*4)
def get_fundamental_ratios(symbol):
    metrics = {
        "P/E": None, "P/B": None, "ROE": None, "EPS": None, 
        "Book_Value": None, "Current_Price": 0.0, "Fair_Value": None, 
        "Dividend_Yield": None, "Score": 0, "Rating": "تحليل غير متاح", "Opinions": [],
        "Profit_Margin": None, "Debt_to_Equity": None
    }
    ticker_sym = get_ticker_symbol(symbol)
    ticker = yf.Ticker(ticker_sym)
    
    try:
        hist = ticker.history(period="5d")
        if not hist.empty: metrics["Current_Price"] = float(hist['Close'].iloc[-1])
        elif hasattr(ticker, 'fast_info') and ticker.fast_info.last_price:
             metrics["Current_Price"] = ticker.fast_info.last_price
    except: pass

    if metrics["Current_Price"] == 0:
        metrics["Rating"] = "السعر غير متاح"; return metrics

    try:
        info = ticker.info if ticker.info else {}
        metrics["EPS"] = info.get('trailingEps')
        metrics["Book_Value"] = info.get('bookValue')
        metrics["P/E"] = info.get('trailingPE')
        metrics["P/B"] = info.get('priceToBook')
        metrics["ROE"] = info.get('returnOnEquity', 0)
        if metrics["ROE"]: metrics["ROE"] *= 100
        metrics["Profit_Margin"] = info.get('profitMargins', 0)
        if metrics["Profit_Margin"]: metrics["Profit_Margin"] *= 100
        metrics["Debt_to_Equity"] = info.get('debtToEquity', 0)
        metrics["Dividend_Yield"] = info.get('dividendYield')
        if metrics["Dividend_Yield"]: metrics["Dividend_Yield"] *= 100

        if metrics["P/E"] is None and metrics["EPS"] and metrics["EPS"] > 0:
            metrics["P/E"] = metrics["Current_Price"] / metrics["EPS"]
        if metrics["P/B"] is None and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["P/B"] = metrics["Current_Price"] / metrics["Book_Value"]
        if metrics["EPS"] and metrics["EPS"] > 0 and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["Fair_Value"] = (22.5 * metrics["EPS"] * metrics["Book_Value"]) ** 0.5
    except Exception as e: metrics["Opinions"].append(f"بيانات ناقصة: {str(e)}")

    score = 0; ops = []
    if metrics["Fair_Value"]:
        if metrics["Current_Price"] < metrics["Fair_Value"]:
            score += 3; ops.append(f"💎 فرصة: أقل من العادلة")
        else: ops.append("⚖️ أعلى من العادلة")
    
    pe = metrics["P/E"]
    if pe:
        if 0 < pe <= 15: score += 2; ops.append(f"✅ مكرر ممتاز ({pe:.1f})")
        elif 15 < pe <= 25: score += 1; ops.append(f"👌 مكرر مقبول ({pe:.1f})")
        else: ops.append("⚠️ مكرر مرتفع")

    if metrics["ROE"] and metrics["ROE"] > 15: score += 2
    if metrics["Profit_Margin"] and metrics["Profit_Margin"] > 20: score += 2
    if metrics["Debt_to_Equity"] and metrics["Debt_to_Equity"] < 100: score += 1

    metrics["Score"] = min(score, 10)
    metrics["Opinions"] = ops
    metrics["Rating"] = "إيجابي ✅" if score >= 7 else ("محايد 😐" if score >= 4 else "تحفظ ⚠️")
    return metrics

# --- المحرك الجديد (للقوائم المالية) ---
def fetch_yahoo_financials(symbol):
    ticker = yf.Ticker(get_ticker_symbol(symbol))
    try:
        return {
            "income": translate_index(ticker.financials),
            "balance": translate_index(ticker.balance_sheet),
            "cashflow": translate_index(ticker.cashflow),
            "source": "Yahoo Finance"
        }
    except: return None

def parse_uploaded_excel(uploaded_file):
    try:
        df = pd.read_excel(uploaded_file)
        df.set_index(df.columns[0], inplace=True)
        for col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
        df = translate_index(df)
        return {"income": df, "balance": pd.DataFrame(), "cashflow": pd.DataFrame(), "source": "ملف خارجي"}
    except Exception as e: st.error(f"خطأ ملف: {e}"); return None

def render_financial_dashboard_ui(symbol):
    st.markdown("#### 📑 القوائم المالية والتقارير")
    col_src, _ = st.columns([3, 1])
    with col_src:
        source_type = st.radio("المصدر:", ["جلب آلي", "رفع ملف Excel"], horizontal=True)
    
    data = None
    if source_type == "جلب آلي":
        with st.spinner("جاري الجلب..."):
            data = fetch_yahoo_financials(symbol)
            if data and data['income'].empty: st.warning("لا توجد بيانات آلية، جرب رفع ملف.")
    else:
        uploaded = st.file_uploader("ملف القوائم", type=["xlsx", "xls", "csv"])
        if uploaded: data = parse_uploaded_excel(uploaded)

    if data:
        t1, t2, t3, t4 = st.tabs(["💵 الدخل", "⚖️ المركز المالي", "🌊 التدفقات", "📊 الرسم البياني"])
        with t1: st.dataframe(data['income'].style.format("{:,.0f}", na_rep="-"), use_container_width=True)
        with t2: st.dataframe(data['balance'].style.format("{:,.0f}", na_rep="-"), use_container_width=True)
        with t3: st.dataframe(data['cashflow'].style.format("{:,.0f}", na_rep="-"), use_container_width=True)
        with t4:
            df = data['income']
            if not df.empty:
                rev_keys = ["إجمالي الإيرادات", "Total Revenue", "Revenue", "الإيرادات"]
                net_keys = ["صافي الربح", "Net Income", "Net Profit"]
                rev = next((k for k in rev_keys if k in df.index), None)
                net = next((k for k in net_keys if k in df.index), None)
                if rev and net:
                    dates = df.columns.astype(str)[::-1]
                    fig = go.Figure()
                    fig.add_trace(go.Bar(x=dates, y=df.loc[rev].values[::-1], name=rev, marker_color='#0e6ba8'))
                    fig.add_trace(go.Bar(x=dates, y=df.loc[net].values[::-1], name=net, marker_color='#10B981'))
                    fig.update_layout(title="الإيرادات وصافي الربح", barmode='group')
                    st.plotly_chart(fig, use_container_width=True)
