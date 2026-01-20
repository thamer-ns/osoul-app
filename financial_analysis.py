import yfinance as yf
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from market_data import get_ticker_symbol

# --- قاموس الترجمة الموحد (لتعريب المصطلحات) ---
TERM_MAPPING = {
    # قائمة الدخل
    "Total Revenue": "إجمالي الإيرادات",
    "Revenue": "الإيرادات",
    "Cost Of Revenue": "تكلفة الإيرادات",
    "Gross Profit": "مجمل الربح",
    "Operating Expense": "المصاريف التشغيلية",
    "Operating Income": "الربح التشغيلي",
    "Net Income": "صافي الربح",
    "EBITDA": "الربح قبل الفائدة والضرائب والإهلاك",
    "Basic EPS": "ربحية السهم الأساسية",
    "Diluted EPS": "ربحية السهم المخفضة",
    # الميزانية
    "Total Assets": "إجمالي الأصول",
    "Total Liab": "إجمالي الالتزامات",
    "Total Liabilities Net Minority Interest": "إجمالي الالتزامات",
    "Total Stockholder Equity": "حقوق المساهمين",
    "Cash And Cash Equivalents": "النقد وما في حكمه",
    "Inventory": "المخزون",
    "Total Debt": "إجمالي الديون",
    # التدفقات
    "Operating Cash Flow": "التدفق النقدي التشغيلي",
    "Investing Cash Flow": "التدفق النقدي الاستثماري",
    "Financing Cash Flow": "التدفق النقدي التمويلي",
    "Free Cash Flow": "التدفق النقدي الحر",
    "Capital Expenditure": "النفقات الرأسمالية"
}

def translate_index(df):
    """دالة مساعدة لترجمة صفوف البيانات"""
    if df is None or df.empty: return df
    # تنظيف الأسماء الإنجليزية ومحاولة ترجمتها
    df.index = df.index.map(lambda x: TERM_MAPPING.get(str(x).strip(), x))
    return df

def format_large_number(num):
    """تنسيق الأرقام الكبيرة للقراءة السهلة"""
    if num is None: return "-"
    try:
        val = float(num)
        if abs(val) >= 1_000_000_000:
            return f"{val / 1_000_000_000:.2f} مليار"
        elif abs(val) >= 1_000_000:
            return f"{val / 1_000_000:.2f} مليون"
        return f"{val:,.2f}"
    except:
        return str(num)

# ---------------------------------------------------------
# الجزء 1: المحرك القديم (للحفاظ على توافق الكود مع الصفحات الأخرى)
# ---------------------------------------------------------
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
    
    # جلب السعر
    try:
        hist = ticker.history(period="5d")
        if not hist.empty:
            metrics["Current_Price"] = float(hist['Close'].iloc[-1])
        elif hasattr(ticker, 'fast_info') and ticker.fast_info.last_price:
             metrics["Current_Price"] = ticker.fast_info.last_price
    except: pass

    if metrics["Current_Price"] == 0:
        metrics["Rating"] = "السعر غير متاح"
        return metrics

    # جلب البيانات المالية
    try:
        info = ticker.info
        if not info: info = {}
        
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

        # حسابات يدوية عند الحاجة
        if metrics["P/E"] is None and metrics["EPS"] and metrics["EPS"] > 0:
            metrics["P/E"] = metrics["Current_Price"] / metrics["EPS"]
            
        if metrics["P/B"] is None and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["P/B"] = metrics["Current_Price"] / metrics["Book_Value"]

        # القيمة العادلة (Graham)
        if metrics["EPS"] and metrics["EPS"] > 0 and metrics["Book_Value"] and metrics["Book_Value"] > 0:
            metrics["Fair_Value"] = (22.5 * metrics["EPS"] * metrics["Book_Value"]) ** 0.5

    except Exception as e:
        metrics["Opinions"].append(f"بيانات ناقصة: {str(e)}")

    # نظام التقييم
    score = 0
    ops = []
    
    if metrics["Fair_Value"]:
        if metrics["Current_Price"] < metrics["Fair_Value"]:
            diff = ((metrics['Fair_Value'] - metrics['Current_Price']) / metrics['Fair_Value']) * 100
            score += 3
            ops.append(f"💎 فرصة: السعر أقل من العادلة بـ {diff:.1f}%")
        else:
            ops.append("⚖️ السعر الحالي أعلى من القيمة العادلة")
    
    pe = metrics["P/E"]
    if pe:
        if 0 < pe <= 15: score += 2; ops.append(f"✅ مكرر أرباح ممتاز ({pe:.1f})")
        elif 15 < pe <= 25: score += 1; ops.append(f"👌 مكرر أرباح مقبول ({pe:.1f})")
        else: ops.append("⚠️ مكرر أرباح مرتفع")

    if metrics["ROE"] and metrics["ROE"] > 15: score += 2; ops.append(f"🔥 عائد على حقوق الملكية قوي ({metrics['ROE']:.1f}%)")
    if metrics["Profit_Margin"] and metrics["Profit_Margin"] > 20: score += 2; ops.append(f"💰 هوامش ربحية عالية ({metrics['Profit_Margin']:.1f}%)")
    if metrics["Debt_to_Equity"] and metrics["Debt_to_Equity"] < 100: score += 1; ops.append("🛡️ مديونية منخفضة وآمنة")

    metrics["Score"] = min(score, 10)
    metrics["Opinions"] = ops
    
    if score >= 7: metrics["Rating"] = "إيجابي جداً ✅"
    elif score >= 4: metrics["Rating"] = "محايد 😐"
    else: metrics["Rating"] = "سلبي/تحفظ ⚠️"
    
    return metrics

# ---------------------------------------------------------
# الجزء 2: محرك القوائم المالية الجديد (يدعم الاستيراد)
# ---------------------------------------------------------

def fetch_yahoo_financials(symbol):
    """جلب القوائم من Yahoo Finance"""
    ticker = yf.Ticker(get_ticker_symbol(symbol))
    try:
        return {
            "income": translate_index(ticker.financials),
            "balance": translate_index(ticker.balance_sheet),
            "cashflow": translate_index(ticker.cashflow),
            "source": "Yahoo Finance"
        }
    except Exception as e:
        return None

def parse_uploaded_excel(uploaded_file):
    """معالجة ملفات الإكسل (تداول / TradingView / سهمي)"""
    try:
        # قراءة الملف
        df = pd.read_excel(uploaded_file)
        
        # تنظيف البيانات: نفترض أن العمود الأول هو البنود والباقي تواريخ
        # سنقوم بجعل العمود الأول هو الـ Index
        df.set_index(df.columns[0], inplace=True)
        
        # محاولة تنظيف القيم (إزالة الفواصل والنصوص)
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        # ترجمة الصفوف
        df = translate_index(df)
        
        # بما أن الملفات المرفوعة غالباً تحتوي كل البيانات في صفحة واحدة أو صفحات متعددة
        # سنعيد نفس الـ DF للثلاث قوائم مؤقتاً أو نقسمها إذا كان الهيكل معروفاً
        # للتبسيط والعمومية: سنعتبرها قائمة شاملة
        return {
            "income": df,
            "balance": pd.DataFrame(), # يمكن تحسين هذا مستقبلاً لقراءة شيتات متعددة
            "cashflow": pd.DataFrame(),
            "source": "ملف خارجي"
        }
    except Exception as e:
        st.error(f"خطأ في قراءة الملف: {e}")
        return None

def render_financial_dashboard_ui(symbol):
    """عنصر الواجهة الرئيسي للقوائم المالية"""
    
    st.markdown("#### 📑 القوائم المالية والتقارير")
    
    # 1. اختيار المصدر
    col_src, col_act = st.columns([3, 1])
    with col_src:
        source_type = st.radio("مصدر البيانات:", 
                             ["جلب آلي (Yahoo/Tadawul)", "رفع ملف (Excel/CSV)"], 
                             horizontal=True,
                             help="الجلب الآلي قد لا يوفر بيانات لجميع الشركات السعودية. استخدم رفع الملف للبيانات الدقيقة من تداول أو TradingView.")
    
    data = None
    
    # 2. جلب البيانات حسب المصدر
    if source_type == "جلب آلي (Yahoo/Tadawul)":
        with st.spinner(f"جاري الاتصال بقاعدة البيانات لجلب {symbol}..."):
            data = fetch_yahoo_financials(symbol)
            if data and data['income'].empty:
                st.warning("⚠️ لم يتم العثور على قوائم مالية مفصلة من المصدر الآلي. يفضل استخدام خيار 'رفع ملف'.")
    else:
        uploaded = st.file_uploader("ارفع ملف القوائم (Excel)", type=["xlsx", "xls", "csv"])
        if uploaded:
            data = parse_uploaded_excel(uploaded)
            if data: st.success("✅ تم تحميل الملف بنجاح")

    # 3. عرض البيانات
    if data:
        # تبويبات القوائم
        t1, t2, t3, t4 = st.tabs(["💵 قائمة الدخل", "⚖️ المركز المالي", "🌊 التدفقات النقدية", "📊 تحليل بصري"])
        
        with t1:
            st.caption(f"المصدر: {data.get('source')} | العملة: ريال سعودي (غالباً)")
            if not data['income'].empty:
                st.dataframe(data['income'].style.format("{:,.0f}", na_rep="-"), use_container_width=True)
            else: st.info("لا توجد بيانات لقائمة الدخل")
            
        with t2:
            if not data['balance'].empty:
                st.dataframe(data['balance'].style.format("{:,.0f}", na_rep="-"), use_container_width=True)
            else: st.info("لا توجد بيانات للمركز المالي (أو موجودة ضمن القائمة الشاملة)")
            
        with t3:
            if not data['cashflow'].empty:
                st.dataframe(data['cashflow'].style.format("{:,.0f}", na_rep="-"), use_container_width=True)
            else: st.info("لا توجد بيانات للتدفقات النقدية")
            
        with t4:
            st.markdown("##### تحليل الاتجاهات")
            df_chart = data['income']
            if not df_chart.empty:
                # محاولة العثور على الإيرادات وصافي الربح بالأسماء العربية أو الإنجليزية
                rev_keys = ["إجمالي الإيرادات", "Total Revenue", "Revenue", "الإيرادات", "المبيعات"]
                net_keys = ["صافي الربح", "Net Income", "Net Profit"]
                
                rev_row = next((k for k in rev_keys if k in df_chart.index), None)
                net_row = next((k for k in net_keys if k in df_chart.index), None)
                
                if rev_row and net_row:
                    try:
                        # تحضير البيانات للرسم
                        dates = df_chart.columns.astype(str)
                        # عكس الترتيب إذا كان من الأحدث للأقدم ليظهر الرسم بشكل زمني صحيح
                        dates = dates[::-1]
                        rev_vals = df_chart.loc[rev_row].values[::-1]
                        net_vals = df_chart.loc[net_row].values[::-1]

                        fig = go.Figure()
                        fig.add_trace(go.Bar(x=dates, y=rev_vals, name=rev_row, marker_color='#0e6ba8'))
                        fig.add_trace(go.Bar(x=dates, y=net_vals, name=net_row, marker_color='#10B981'))
                        
                        fig.update_layout(
                            title="الإيرادات مقابل صافي الربح",
                            barmode='group',
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            font=dict(family="Cairo")
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        st.error(f"تعذر رسم المخطط: {e}")
                else:
                    st.warning("لم يتم العثور على بنود 'الإيرادات' أو 'صافي الربح' للرسم البياني.")
            else:
                st.info("البيانات غير كافية للرسم.")
