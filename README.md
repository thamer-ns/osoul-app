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


---

## 13) خريطة الدوال المهمة (Function Map)

> هذا القسم يساعدك تعرف: **أين تُحسب الأشياء؟ ومن يستدعي من؟** بسرعة عند أي تعديل.

### 13.1 مسار “تحليل سهم” داخل الواجهة
- `views/analysis/__init__.py`
  - ينشئ Tabs التحليل ويستدعي:
    - `views/analysis/financial.py`
    - `views/analysis/technical.py`
    - `views/analysis/classical.py`
    - `views/analysis/advisor.py`
    - `views/analysis/thesis.py`

### 13.2 دوال الشارت والسعر (Market)
- `market_data.get_chart_history(symbol, period, interval)`
  - **وظيفة:** جلب OHLCV
  - **يُستدعى من:**
    - `views/shared.py::_render_technical_chart_flex`
    - `views/analysis/technical.py` (لبعض الـ fallbacks/advanced packs)
    - `ai_engine_core/reporting.py` (وقود التقرير الفني)

- `views/shared.py::_render_technical_chart_flex(symbol, period, interval)`
  - **وظيفة:** رسم شارت مرن + عرض أخطاء بطريقة لطيفة
  - **ملاحظة:** الأفضل عدم تمرير `df` لها إلا إذا الدالة تدعم ذلك.

### 13.3 المؤشرات المتقدمة (Advanced Pack)
- `technical_indicators.advanced.compute_advanced_technical_pack(df, symbol, timeframe)`
  - **وظيفة:** إنتاج Pack قياسي للمؤشرات المتقدمة
  - **يُعرض في:** `views/analysis/technical.py`
  - **يُخزن عبر:** `ai_engine_core/db.py::save_advanced_indicators(...)` (إذا تم ربط التخزين)

### 13.4 التحليل المالي + الجودة
- `financial_analysis/yahoo_data.py` (fetchers)
  - **وظيفة:** جلب القوائم من Yahoo + تشخيص rate limit

- `financial_analysis/store.py`
  - **وظيفة:** حفظ/استرجاع القوائم + Freshness
  - **دوال مهمة شائعة:**
    - `save_full_statement_record(...)`
    - `fetch_full_statement_records(...)`
    - `get_full_statements_freshness(...)`

- `financial_analysis/data_quality.py`
  - **وظيفة:** بوابة جودة البيانات
  - **مخرجات نموذجية:** pass/score/issues/confidence

- `financial_analysis/metrics.py`
  - **وظيفة:** حساب النسب والمؤشرات
  - **قاعدة:** missing ⇒ None (وليس 0) + issues + خفض ثقة

### 13.5 المستشار (AI Engine)
- `ai_engine.generate_ai_report(...)`
  - **وظيفة:** واجهة ثابتة للـ UI (Facade)
  - **يستدعي:** `ai_engine_core.reporting.generate_ai_report(...)`

- `ai_engine_core/reporting.py::generate_ai_report(...)`
  - **وظيفة:** بناء تقرير المستشار
  - **يعتمد على:**
    - OHLCV + مؤشرات + Structure
    - Financial packs
    - Advanced packs (إن تم حفظها/تمريرها)

- `ai_engine_core/risk.py`
  - **وظيفة:** Risk Gates
  - **مبدأ:** Data Quality Fail أو Low confidence ⇒ منع توصية قوية

- `ai_engine_core/db.py`
  - **وظيفة:** جداول ai_signals/ai_weights + user_rules + advanced indicators

- `ai_engine_core/logging_learning.py`
  - **وظيفة:** تسجيل الإشارات + أوزان بسيطة تتغير مع الزمن

- `ai_engine_core/user_rules.py`
  - **وظيفة:** قواعد المستخدم، تحميل/تقييم/حفظ

---

## 14) Checklist قبل أي تعديل أو Pull Request (Quality Gate)

> طبق هذه القائمة قبل رفع أي تحديث حتى لا “تصلح خطأ وتكسر مكان ثاني”.

### 14.1 ثوابت لا تُكسر
- [ ] **لا حذف** دوال/أسماء تُستدعى من الراوتر أو من ملفات أخرى (إلا مع wrapper توافق).
- [ ] أي تبويب جديد يجب أن يكون **Fail-safe** (try/except + رسالة UI).
- [ ] لا تخلط Annual/Quarterly/TTM بدون إعلان + خفض ثقة.
- [ ] missing ≠ 0 في سياق النسب والمؤشرات.
- [ ] لا تعرض بيانات قديمة بدون **Data Freshness Badge**.

### 14.2 اختبار تشغيل سريع (Smoke Test)
- [ ] `streamlit run app.py` يعمل بدون Traceback
- [ ] Dashboard يفتح
- [ ] Portfolio يفتح + جدول الصفقات يظهر
- [ ] Analysis يفتح:
  - [ ] الشارت يظهر (أو fallback لطيف)
  - [ ] تبويب الفني يعمل
  - [ ] المؤشرات المتقدمة تعمل (أو تظهر “غير متوفرة” بدون كسر)
  - [ ] تبويب المالي يعرض بوابة الجودة (Pass/Issues/Confidence)
  - [ ] المستشار يولد تقرير

### 14.3 جودة البيانات (Data Quality)
- [ ] إذا القوائم ناقصة: يظهر Fail/Issues بوضوح
- [ ] إذا Fail: المستشار **لا** يعطي توصية قوية
- [ ] إذا Low confidence: التوصية تُخفض تلقائيًا + تبرير واضح

### 14.4 توحيد العرض (UI Consistency)
- [ ] أي جدول جديد في التحليل يُعرض مثل جدول الصفقات عبر `render_custom_table`
- [ ] الأرقام المالية تُعرض بوحدة واضحة (SAR + ألف/مليون/مليار)
- [ ] العناوين/الأزرار الرئيسية بالعربي، والاختصارات (RSI/MACD) تُذكر بين قوسين عند الحاجة

### 14.5 الأداء والثبات
- [ ] لا تضع حسابات ثقيلة داخل render loop بدون caching
- [ ] لا تسوي requests متكررة في كل rerun (استخدم caching/DB عند الحاجة)
- [ ] التعامل مع 429 من Yahoo: لا تُخفي المشكلة — اعرض تنبيه واضح + freshness

---

## 15) قوالب جاهزة للاستخدام عند إضافة ميزات

### 15.1 قالب “Pack” لمؤشر جديد
```python
def build_my_indicator_pack(df):
    return {
        "bias": "bullish",
        "confidence": 67,
        "summary": "زخم إيجابي مع تراجع في الضغط البيعي.",
        "evidence": ["RSI أعلى من 50", "اختراق مقاومة قصيرة"],
        "signals": [{"signal": "Breakout", "score": 12, "note": "تأكيد بحجم"}],
        "features": {"rsi": 56.2, "atr": 0.14},
        "errors": [],
        "warnings": []
    }
```

### 15.2 قالب عرض جدول موحد (مثل جدول الصفقات)
> الأفضل استخدام: `views.shared.render_custom_table(df, col_types=..., key=...)`
