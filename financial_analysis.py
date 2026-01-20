import yfinance as yf
import pandas as pd
import streamlit as st
import plotly.express as px
from market_data import get_ticker_symbol
from database import execute_query, fetch_table, get_db

# ... (انسخ نفس دوال الجلب السابقة update_financial_statements وغيرها هنا) ...

def render_financial_dashboard_ui(symbol):
    """واجهة عرض القوائم المالية المصممة"""
    from components import render_table
    from financial_analysis import get_stored_financials, update_financial_statements

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

        # 2. الجدول (الإصلاح الجذري هنا)
        st.markdown("##### 📑 التفاصيل المالية")
        
        # نقوم بقلب الجدول ليصبح السنوات هي الأعمدة (أسهل للقراءة)
        # نختار الأعمدة المهمة فقط
        pivot_df = df.set_index('year')[['revenue', 'gross_profit', 'net_income', 'operating_cash_flow', 'total_assets', 'total_equity']]
        
        # إعادة تسمية المؤشرات للعربية
        pivot_df = pivot_df.rename(columns={
            'revenue': 'الإيرادات',
            'gross_profit': 'إجمالي الربح',
            'net_income': 'صافي الدخل',
            'operating_cash_flow': 'التدفق التشغيلي',
            'total_assets': 'مجموع الأصول',
            'total_equity': 'حقوق الملكية'
        })
        
        # التدوير (Transpose)
        display_df = pivot_df.T.reset_index()
        display_df.columns.name = None # إزالة اسم الفهرس
        display_df = display_df.rename(columns={'index': 'المؤشر المالي'})
        
        # بناء تعريف الأعمدة ديناميكياً بناءً على السنوات الموجودة
        cols_def = [('المؤشر المالي', 'المؤشر المالي')]
        # الأعمدة الباقية هي السنوات (أسماء الأعمدة أصبحت سنوات الآن)
        for col in display_df.columns:
            if col != 'المؤشر المالي':
                cols_def.append((col, str(col)))
        
        render_table(display_df, cols_def)

    else:
        st.info("لا توجد بيانات. اضغط تحديث.")
