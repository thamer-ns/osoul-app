import psycopg2

# ضع الرابط كاملاً بكلمة المرور هنا للتجربة
DB_URL ="postgresql://postgres.uxcdbjqnbphlzftpfajm:Tm1074844687@aws-1-ap-northeast-2.pooler.supabase.com:6543/postgres"

try:
    print("جاري محاولة الاتصال...")
    conn = psycopg2.connect(DB_URL)
    print("✅ تم الاتصال بنجاح! قاعدة البيانات تعمل.")
    conn.close()
except Exception as e:
    print(f"❌ فشل الاتصال: {e}")
