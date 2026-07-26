# استجابة حادثة الأسرار المنشورة

كان ملف `.streamlit/secrets.toml` متعقبًا داخل المستودع العام. حذفه من الفرع الحالي يمنع الاستخدام المستقبلي، لكنه لا يلغي القيم التي ظهرت في تاريخ Git.

## إجراءات إلزامية خارج الكود

1. غيّر كلمة مرور قاعدة PostgreSQL وأصدر `DATABASE_URL` جديدًا.
2. ألغِ مفتاح Twelve Data وأصدر مفتاحًا جديدًا.
3. أنشئ `AUTH_SECRET` جديدًا بطول لا يقل عن 32 حرفًا، ويفضل 64 حرفًا عشوائيًا.
4. حدّث القيم الجديدة داخل Streamlit Cloud Secrets فقط.
5. أنهِ الجلسات الحالية؛ تغيير `AUTH_SECRET` يبطل الرموز الموقعة القديمة.
6. نظّف تاريخ المستودع باستخدام `git filter-repo` أو BFG، ثم نفّذ force-push من جهاز موثوق.
7. راجع سجلات Supabase/Twelve Data لأي استخدام غير معتاد منذ أول رفع للملف.

## منع التكرار

- `.streamlit/secrets.toml` موجود في `.gitignore`.
- GitHub Actions يشغّل Gitleaks على كل Pull Request وPush إلى `main`.
- استخدم `.streamlit/secrets.example.toml` للقيم الوهمية فقط.
