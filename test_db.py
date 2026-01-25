import psycopg2

# ضع الرابط كاملاً بكلمة المرور هنا للتجربة
DB_URL = "ضع_الرابط_هنا_مع_كلمة_المرور_للتحقق"

try:
    print("جاري محاولة الاتصال...")
    conn = psycopg2.connect(DB_URL)
    print("✅ تم الاتصال بنجاح! قاعدة البيانات تعمل.")
    conn.close()
except Exception as e:
    print(f"❌ فشل الاتصال: {e}")
