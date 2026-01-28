import pandas as pd
import io
from datetime import datetime
from database import fetch_table
import streamlit as st

def generate_full_backup():
    """
    يقوم بإنشاء ملف Excel يحتوي على كافة بيانات النظام
    """
    output = io.BytesIO()
    
    # قائمة الجداول المراد حفظها
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
        # إنشاء ملف Excel في الذاكرة
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            data_found = False
            
            for table_name, sheet_name in tables.items():
                df = fetch_table(table_name)
                if not df.empty:
                    # تحويل التواريخ لنص لضمان التنسيق
                    for col in df.columns:
                        if 'date' in col.lower():
                            df[col] = df[col].astype(str)
                            
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    data_found = True
            
            # في حال كانت قاعدة البيانات فارغة تماماً
            if not data_found:
                pd.DataFrame({"Status": ["Empty Database"]}).to_excel(writer, sheet_name="Info")
                
        # تجهيز الملف للتحميل
        output.seek(0)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        file_name = f"Osoli_Backup_{timestamp}.xlsx"
        
        return output, file_name
        
    except Exception as e:
        st.error(f"حدث خطأ أثناء إنشاء النسخة الاحتياطية: {e}")
        return None, None
