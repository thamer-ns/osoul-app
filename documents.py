import streamlit as st
from database import execute_query, get_db
import pandas as pd

def upload_document(trade_id, uploaded_file):
    if uploaded_file is None: return
    try:
        bytes_data = uploaded_file.getvalue()
        query = "INSERT INTO Documents (trade_id, file_name, file_data) VALUES (%s, %s, %s)"
        # ملاحظة: بايثون يتعامل مع bytea بشكل مباشر عبر psycopg2
        execute_query(query, (trade_id, uploaded_file.name, bytes_data))
        st.success("تم رفع الملف بنجاح!")
    except Exception as e:
        st.error(f"خطأ في الرفع: {e}")

def view_documents(trade_id):
    with get_db() as conn:
        if conn:
            df = pd.read_sql("SELECT id, file_name, upload_date FROM Documents WHERE trade_id = %s", conn, params=(trade_id,))
            if not df.empty:
                st.markdown("#### 📎 المرفقات")
                for _, row in df.iterrows():
                    st.write(f"📄 {row['file_name']} ({row['upload_date']})")
                    # تنزيل الملف (يتطلب استعلام خاص لجلب البيانات الثقيلة فقط عند الطلب)
                    with st.expander("تنزيل"):
                        data = pd.read_sql("SELECT file_data FROM Documents WHERE id = %s", conn, params=(row['id'],)).iloc[0]['file_data']
                        st.download_button("تحميل", data, file_name=row['file_name'])
