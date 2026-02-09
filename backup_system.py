import pandas as pd
import io
from datetime import datetime
from database import fetch_table
import streamlit as st

def generate_full_backup():
    """
    يقوم بإنشاء ملف Excel منسق يحتوي على كافة بيانات النظام
    """
    output = io.BytesIO()
    
    tables = {
        "Trades": "صفقات",
        "Deposits": "إيداعات",
        "Withdrawals": "سحوبات",
        "ReturnsGrants": "عوائد",
        "Watchlist": "مراقبة",
        "FinancialStatements": "قوائم_مالية",
        "InvestmentThesis": "أطروحات"
    }
    
    try:
        # تحديد تنسيق التاريخ لملف الإكسل
        with pd.ExcelWriter(output, engine='xlsxwriter', date_format='YYYY-MM-DD') as writer:
            data_found = False
            workbook = writer.book
            
            # تنسيق للخلايا (اختياري: لتوسيط النص مثلاً)
            # cell_format = workbook.add_format({'align': 'center', 'valign': 'vcenter'})

            for table_name, sheet_name in tables.items():
                df = fetch_table(table_name)
                
                if not df.empty:
                    # كتابة البيانات
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    data_found = True
                    
                    # --- كود إضافي لتوسيع الأعمدة تلقائياً ---
                    worksheet = writer.sheets[sheet_name]
                    for idx, col in enumerate(df.columns):
                        # حساب أقصى طول في العمود (العنوان أو أطول قيمة)
                        # نضيف القليل من المساحة (padding)
                        series = df[col]
                        max_len = max(
                            series.astype(str).map(len).max(),
                            len(str(col))
                        ) + 2
                        
                        # تحديد حد أقصى للعرض حتى لا يكون العمود عريضاً جداً
                        worksheet.set_column(idx, idx, min(max_len, 50))
                    # ----------------------------------------

            if not data_found:
                pd.DataFrame({"Status": ["Empty Database"]}).to_excel(writer, sheet_name="Info")
                
        output.seek(0)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        file_name = f"Osoli_Backup_{timestamp}.xlsx"
        
        return output, file_name
        
    except Exception as e:
        st.error(f"حدث خطأ أثناء إنشاء النسخة الاحتياطية: {e}")
        # طباعة الخطأ في الكونسول للمطور
        print(f"Backup Error: {e}")
        return None, None
