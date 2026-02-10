# أصولي (Osoli) — دليل هيكلة المشروع والتطوير (Developer README)

> هذه الوثيقة تهدف أن تكون “مرجعًا دائمًا” عند التعديل أو إضافة ميزات جديدة **بدون كسر الترابط** بين الواجهة والتحليل والمستشار.
>  
> **مبدأ المشروع:**  
> **UI (views)** تعرض النتائج → **طبقات البيانات والتحليل** تحسب → **المستشار (AI Engine)** يجمع ويقيّم ويصدر توصية **مع بوابات جودة/مخاطر**.

---

## 1) كيف تبدأ (Quick Start)

### 1.1 المتطلبات
- Python 3.10+ (يفضل 3.11)
- تثبيت المتطلبات من:
  - `requirements.txt`
  - `packages.txt` (إن كنت على Streamlit Cloud)

### 1.2 التشغيل محليًا
```bash
pip install -r requirements.txt
streamlit run app.py
```

### 1.3 التشغيل على Streamlit Cloud
- ارفع المشروع على GitHub
- اجعل **Entry point** هو `app.py`
- فعّل `secrets.toml` في إعدادات Streamlit Cloud (لو تستخدم Postgres/API Keys)

---

## 2) هيكلة المشروع (Project Map)

### 2.1 نقطة الدخول
- `app.py`
  - تشغيل Streamlit + إعدادات RTL/تعريب افتراضي لعناصر Streamlit إن مفعلة
  - يستدعي راوتر الصفحات عبر `views.router()`

### 2.2 الواجهة (UI) — مجلد `views/`
> هنا كل صفحات المستخدم. **ممنوع وضع حسابات ثقيلة هنا** — فقط عرض واستدعاء طبقات التحليل.

- `views/__init__.py`  
  الراوتر: يحدد الصفحة الحالية ويستدعي الصفحة المناسبة.

- `views/navbar.py`  
  شريط التنقل + العناصر الرئيسية/الفرعية.

- `views/shared.py`  ✅ (مهم جدًا)
  - CSS/RTL وحقن ستايل موحد  
  - أدوات عرض جاهزة مثل:
    - `render_custom_table`  ← **هذا هو ستايل “جدول الصفقات”**
    - `_render_technical_chart_flex` ← شارت مرن
  - Fail-safe imports (حتى لا يكسر تبويب واحد الصفحة)

#### صفحة التحليل — `views/analysis/`
> أهم مكان للمستخدم: تحليل مالي + فني + كلاسيكي + مستشار

- `views/analysis/__init__.py`  
  يجمع تبويبات التحليل (Financial/Technical/Classical/Advisor/Thesis)

- `views/analysis/financial.py`  
  واجهة التحليل المالي + بوابة جودة البيانات + عرض النسب

- `views/analysis/technical.py`  
  واجهة التحليل الفني + الشارت + المؤشرات + **المؤشرات المتقدمة**

- `views/analysis/classical.py`  
  واجهة التحليل الكلاسيكي (نماذج/دعوم/مقاومات…)

- `views/analysis/advisor.py`  
  واجهة المستشار (تقرير + أدلة + ثقة + توصية)  
  يعتمد على `ai_engine.py` و `ai_engine_core/*`

- `views/analysis/thesis.py`  
  خلاصة القرار/السيناريوهات/ملخص رأي منظم

---

## 3) طبقة البيانات (Market + DB)

### 3.1 أسعار السوق والرموز
- `market_data.py`
  - توحيد الرمز (مثلاً: `4161` → `4161.SR`)
  - جلب تاريخ الشموع عبر Yahoo/yfinance
  - يُستخدم في:
    - الشارت
    - المؤشرات الفنية
    - التحليل الكلاسيكي
    - المستشار (AI)

### 3.2 قاعدة البيانات
- `database.py`
  - Postgres إن توفر
  - fallback SQLite
  - دوال عامة:
    - `execute_query`
    - `fetch_table`

> أي تخزين للمخرجات (Indicators/AI logs/User rules/Statements…) يتم عبر طبقة DB.

---

## 4) التحليل المالي (Fundamental) — `financial_analysis/`

> الهدف: جلب القوائم، تنظيفها، تخزينها، ثم حساب النسب والمؤشرات.

- `financial_analysis/yahoo_data.py`  
  جلب القوائم من Yahoo + تشخيص rate limit

- `financial_analysis/sync.py`  
  مزامنة القوائم (Yahoo + fallbacks)

- `financial_analysis/store.py`  
  تخزين القوائم + الاسترجاع + “Freshness” (آخر تحديث/المصدر/كاملة أو جزئية)

- `financial_analysis/data_quality.py` ✅  
  بوابة جودة البيانات:  
  تعيد:
  - `pass/fail`
  - `score`
  - `issues[]`
  - (اختياري) confidence

- `financial_analysis/metrics.py` ✅  
  حساب النسب والمؤشرات  
  **قاعدة مهمة:**  
  - القيم الناقصة يجب ألا تتحول لصفر في سياق النسب  
  - الأفضل: missing ⇒ `None` + تحذير + خفض ثقة

- `financial_analysis/utils.py`  
  أدوات safe float/div وتهيئة القيم

---

## 5) التحليل الفني المتقدم (Advanced Technical) — `technical_indicators/`

- `technical_indicators/advanced.py` ✅  
  يُنتج “حزمة (Pack)” موحدة للمؤشرات المتقدمة.

### 5.1 شكل الـ Pack القياسي (مهم)
كل مؤشر يُفضل أن يرجع:
```python
{
  "bias": "bullish|bearish|neutral",
  "confidence": 0-100,
  "summary": "جملة مختصرة",
  "evidence": ["دليل 1", "دليل 2"],
  "signals": [{"signal": "...", "score": 12, "note": "..."}],
  "features": {"k": v, "k2": v2},
  "errors": [],
  "warnings": []
}
```

> هذا الشكل يجعل:
- UI تعرض بسهولة
- المستشار يدمج النتائج بسهولة
- يمكن تخزينه في DB كما هو

---

## 6) المستشار (AI Engine) — `ai_engine.py` و `ai_engine_core/`

### 6.1 `ai_engine.py` (Facade)
واجهة مستقرة للـ UI:
- الهدف: UI لا تستورد ملفات داخلية كثيرة
- إذا تغيّر منطق `ai_engine_core` لا تتكسر الواجهة

### 6.2 قلب التقرير
- `ai_engine_core/reporting.py` ✅  
  يجمع:
  - السعر/الشموع
  - المؤشرات الفنية
  - التحليل البنيوي (Structure)
  - التحليل المالي (Fundamental)
  - (اختياري) المؤشرات المتقدمة المخزّنة

### 6.3 بوابات المخاطر والجودة
- `ai_engine_core/risk.py`  
  قواعد منع التوصيات “القوية” عند:
  - Data Quality Fail
  - Low confidence
  - مخاطرة مفرطة

### 6.4 التخزين والتعلم
- `ai_engine_core/db.py`
  - حفظ/قراءة advanced indicators
  - user rules
  - ai logging tables

- `ai_engine_core/logging_learning.py`
  - تسجيل إشارات
  - أوزان بسيطة `_get_weight`

- `ai_engine_core/user_rules.py`
  - قواعد تخص المستخدم لتعديل السلوك

---

## 7) “أين أعدّل؟” (Common Change Locations)

### 7.1 تعديل شكل الجداول (موحد مثل “جدول الصفقات”)
- استخدم `render_custom_table` من:
  - `views/shared.py`
- أي مكان عندك `st.dataframe(...)` في الواجهات:
  - استبدله بـ `render_custom_table(df, ...)`  
  لتوحيد التصميم.

### 7.2 تعريب النصوص (UI)
- الأفضل إنشاء/استخدام `tr()` (قاموس ترجمة خفيف)
- في UI:
  - لا تترك labels إنجليزية (خصوصًا: Score / Confidence / Issues / Signals)

### 7.3 تحسين وضوح الأرقام
- استخدم تنسيق موحد:
  - `SAR`
  - ألف/مليون/مليار
  - إظهار الفترة: Annual / Quarterly / TTM

---

## 8) كيف تضيف “مؤشر جديد” خطوة بخطوة (بدون كسر الترابط)

### 8.1 إضافة مؤشر فني جديد (Advanced)
1) أضفه في `technical_indicators/advanced.py`
2) اجعله يرجع Pack بنفس الشكل القياسي
3) في UI:
   - `views/analysis/technical.py`
   - اعرضه كـ Expander جديد عبر `_render_indicator_block(...)`
4) (اختياري) احفظه في DB:
   - `ai_engine_core/db.py` (مثل `save_advanced_indicators`)
5) اربطه بالمستشار:
   - `ai_engine_core/packs.py` اجمعه ضمن technical pack
   - ثم `ai_engine_core/reporting.py` يقرأ pack ويضيفه للتقرير

### 8.2 إضافة مقياس مالي جديد (Fundamental)
1) أضفه في `financial_analysis/metrics.py`
2) اجعله:
   - لا يعتمد على قيم ناقصة كصفر
   - يعلن الفترة المستخدمة (Annual/Quarterly/TTM)
3) مرره عبر بوابة الجودة:
   - إذا essential missing → `None` + issue
4) اعرضه في:
   - `views/analysis/financial.py`

---

## 9) قواعد ذهبية تمنع الأخطاء المتكررة (Very Important)

### 9.1 لا تخلط الفترات بصمت
- إذا النسبة تتطلب Annual:
  - لا تستخدم Quarterly إلا مع تنبيه + خفض ثقة
- إذا تستخدم TTM:
  - اكتب بوضوح: “TTM”

### 9.2 missing ≠ 0
- missing يجب أن يظهر للمستخدم “غير متوفر”
- ويؤثر على الثقة (خفض)

### 9.3 Data Freshness Badge في كل تبويب
اعرض دائمًا:
- آخر تحديث
- المصدر
- كاملة/جزئية

### 9.4 Fail-safe imports
أي تبويب (فني/مالي/كلاسيكي) لا يجب أن يكسر صفحة التحليل بالكامل:
- استخدم try/except + رسالة UI لطيفة

---

## 10) اختبارات سريعة بعد أي تعديل (Smoke Tests)

1) تشغيل التطبيق وفتح:
   - Dashboard
   - Portfolio
   - Analysis
2) تحليل سهم:
   - الشارت يظهر
   - الفني يظهر
   - المؤشرات المتقدمة تعمل (أو تظهر رسالة “غير متوفرة” بدون كسر)
3) المالي:
   - بوابة الجودة تظهر
   - لا يوجد نسب “0” بسبب missing
4) المستشار:
   - يولد تقرير
   - إذا الجودة Fail → لا يعطي Strong Recommendation

---

## 11) أسلوب التعديل “المستقبلي” (كيف تضمن عدم تكرار الأعطال)
عند أي تعديل، اكتب في الكود تعليقًا ثابتًا:
- لماذا أضفت هذا؟
- أين يعتمد عليه؟
- كيف أرجع عنه لو حصل خطأ؟

مثال:
```python
# NOTE:
# - هذه الدالة تُستخدم في UI والمستشار.
# - يجب أن ترجع confidence 0-100.
# - missing => None (لا تضع default=0 في سياق النسب).
```

---

## 12) أسئلة شائعة

### لماذا بعض الأشياء تظهر بالإنجليزي؟
غالبًا لأنها labels مباشرة أو مفاتيح من packs/features. الحل:
- `tr()` قاموس ترجمة
- أو mapping لعرض أسماء الأعمدة بالعربي داخل الجداول

### لماذا المستشار “يضعف” رأيه؟
لأننا نعتمد بوابات:
- جودة البيانات
- قِصر التاريخ
- تعارض إشارات

---

### تواصل
إذا احتجت إضافة “نظام ترجمة شامل” أو “توثيق API داخلي” للمؤشرات الجديدة، يمكن توسعة هذه الوثيقة بسهولة.
