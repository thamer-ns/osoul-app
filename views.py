import streamlit as st
import pandas as pd

def display_metrics(total_assets, total_pl, daily_change):
    col1, col2, col3 = st.columns(3)
    with col3:
        st.metric(label="صافي الأصول", value=f"{total_assets:,.2f}")
    with col2:
        st.metric(label="الربح/الخسارة", value=f"{total_pl:,.2f}")
    with col1:
        st.metric(label="التغير اليومي", value=f"{daily_change:,.2f}")
    st.markdown("---")

def display_open_positions(df):
    st.subheader("محفظة الأسهم")
    if df.empty:
        st.info("لا توجد بيانات")
        return

    # نسخ البيانات لتجنب تعديل الأصل
    display_df = df.copy()
    
    # التأكد من وجود الأعمدة قبل عرضها
    cols_to_show = [c for c in ['رمز الشركة', 'اسم الشركة', 'الكمية', 'متوسط التكلفة', 'السعر الحالي', 'الربح/الخسارة', 'نسبة الربح %'] if c in display_df.columns]
    display_df = display_df[cols_to_show]

    # التنسيق البسيط (بدون Styler معقد مبدئياً للتأكد من حل المشكلة)
    st.dataframe(display_df, use_container_width=True)
