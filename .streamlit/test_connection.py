# .streamlit/test_connection.py
import streamlit as st
import psycopg2
import pandas as pd  # ✅ التعديل 1: سنستخدم هذه المكتبة الآن

st.title("🔌 فحص اتصال قاعدة البيانات")

# 1. قراءة الرابط
try:
    DB_URL = st.secrets.get("DATABASE_URL") or st.secrets["postgres"]["url"]
    safe_url = DB_URL.split('@')[1] if '@' in DB_URL else "..."
    st.success(f"✅ تم العثور على الرابط: ...@{safe_url}")
except Exception as e:
    st.error(f"❌ لم يتم العثور على الرابط الصحيح في secrets.toml: {e}")
    st.stop()

# متغير لحفظ الاتصال
conn = None

# 2. محاولة الاتصال
try:
    conn = psycopg2.connect(DB_URL, sslmode='require')
    st.success("✅ الاتصال بالسيرفر نجح!")
    
    # 3. محاولة جلب بيانات
    cur = conn.cursor()
    
    # --- فحص جدول التداولات ---
    try:
        cur.execute("SELECT count(*) FROM trades")
        count = cur.fetchone()[0]
        st.info(f"📊 عدد الصفقات (trades): {count}")
    except:
        conn.rollback()
        try:
            cur.execute('SELECT count(*) FROM "Trades"')
            count = cur.fetchone()[0]
            st.info(f"📊 عدد الصفقات (Trades): {count}")
        except Exception as e:
            st.warning(f"⚠️ جدول التداولات غير موجود: {e}")
            conn.rollback()

    # --- فحص جدول الودائع ---
    try:
        cur.execute("SELECT * FROM deposits LIMIT 5")
        rows = cur.fetchall()
        st.write("💰 أول 5 عمليات إيداع (deposits):")
        # ✅ التعديل 1: استخدام Pandas لعرض الجدول بشكل جميل
        st.dataframe(pd.DataFrame(rows)) 
    except:
        conn.rollback()
        try:
            cur.execute('SELECT * FROM "Deposits" LIMIT 5')
            rows = cur.fetchall()
            st.write("💰 أول 5 عمليات إيداع (Deposits):")
            # ✅ التعديل 1: استخدام Pandas لعرض الجدول بشكل جميل
            st.dataframe(pd.DataFrame(rows))
        except Exception as e:
            st.warning(f"⚠️ جدول الودائع غير موجود: {e}")

except Exception as e:
    st.error(f"❌ فشل الاتصال النهائي: {e}")
    st.write("الأسباب المحتملة:")
    st.write("1. كلمة المرور خطأ.")
    st.write("2. المنفذ ليس 6543 (Pooler) أو 5432.")

finally:
    # ✅ التعديل 2: ضمان إغلاق الاتصال دائماً
    if conn:
        conn.close()
        # st.caption("🔒 تم إغلاق الاتصال بأمان.")
