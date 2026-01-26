import streamlit as st
import psycopg2
import pandas as pd

st.title("🔌 فحص اتصال قاعدة البيانات")

# 1. قراءة الرابط
try:
    # محاولة القراءة من secrets
    DB_URL = st.secrets["postgres"]["url"]
    st.success(f"✅ تم العثور على الرابط: {DB_URL[:20]}...***")
except:
    st.error("❌ لم يتم العثور على الرابط في secrets.toml")
    st.stop()

# 2. محاولة الاتصال
try:
    conn = psycopg2.connect(DB_URL, sslmode='require')
    st.success("✅ الاتصال بالسيرفر نجح!")
    
    # 3. محاولة جلب بيانات
    cur = conn.cursor()
    
    # فحص جدول التداولات
    try:
        cur.execute("SELECT count(*) FROM Trades")
        count = cur.fetchone()[0]
        st.info(f"📊 عدد الصفقات في قاعدة البيانات: {count}")
    except Exception as e:
        st.warning(f"⚠️ جدول Trades غير موجود أو فيه مشكلة: {e}")
        conn.rollback()

    # فحص جدول الودائع
    try:
        cur.execute("SELECT * FROM Deposits LIMIT 5")
        rows = cur.fetchall()
        st.info(f"💰 أول 5 عمليات إيداع: {rows}")
    except Exception as e:
        st.warning(f"⚠️ جدول Deposits فيه مشكلة: {e}")
        
    conn.close()

except Exception as e:
    st.error(f"❌ فشل الاتصال النهائي: {e}")
    st.write("الأسباب المحتملة:")
    st.write("1. كلمة المرور خطأ.")
    st.write("2. الرابط Direct Connection (منفذ 5432) وهذا لا يعمل مع Streamlit Cloud (يحتاج IPv6).")
    st.write("3. الرابط Transaction Pooler (منفذ 6543) هو الصحيح.")
