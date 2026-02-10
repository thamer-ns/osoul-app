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


---

## 16) خريطة البيانات (Data Lineage) — من المصدر إلى الرقم المعروض

> الهدف: إذا رقم “طلع غريب” تعرف بسرعة أين تبحث: **مصدر؟ تخزين؟ تحويل؟ حساب؟ عرض؟**

### 16.1 بيانات السعر/الشارت (OHLCV)
**المصدر الأساسي:** Yahoo عبر `yfinance`  
**المسار:**
1) `market_data.get_chart_history(symbol, period, interval)`
2) الرسم:
   - `views/shared.py::_render_technical_chart_flex(...)`
3) المؤشرات:
   - `technical_indicators/*` أو `ai_engine_core/indicators.py`
4) المستشار:
   - `ai_engine_core/reporting.py` يقرأ OHLCV ويبنّي الإشارات

**نقاط فشل شائعة:**
- symbol غير مُطبع (بدون `.SR`)
- تاريخ قصير (أقل من 220 شمعة) → انخفاض ثقة المؤشرات
- فجوات أو شموع غير منطقية → تحذير جودة بيانات

### 16.2 القوائم المالية (Financial Statements)
**المصدر الأساسي:** Yahoo (JSON/HTML)  
**المسار:**
1) جلب: `financial_analysis/yahoo_data.py`
2) مزامنة: `financial_analysis/sync.py`
3) تخزين: `financial_analysis/store.py`
4) جودة: `financial_analysis/data_quality.py`
5) حساب نسب: `financial_analysis/metrics.py`
6) العرض:
   - `views/analysis/financial.py`
7) المستشار:
   - `ai_engine_core/reporting.py` + `ai_engine_core/packs.py`

**نقاط فشل شائعة:**
- 429 Rate limit → بيانات قديمة مخزنة
- missing essentials (Revenue/NI/Equity/OCF) → Fail/Low confidence
- خلط Annual/Quarterly/TTM → نتائج تبدو “صحيحة” لكنها غير موثوقة

### 16.3 المؤشرات المتقدمة (Advanced Indicators)
**المصدر:** حساب محلي على OHLCV  
**المسار:**
1) حساب: `technical_indicators/advanced.py::compute_advanced_technical_pack(df, ...)`
2) عرض: `views/analysis/technical.py` (تبويب المؤشرات المتقدمة)
3) تخزين (اختياري): `ai_engine_core/db.py::save_advanced_indicators(...)`
4) إدخال للمستشار (اختياري):
   - `ai_engine_core/packs.py` ثم `ai_engine_core/reporting.py`

**نقاط فشل شائعة:**
- ملف advanced.py فيه SyntaxError أو استيرادات ناقصة
- df ناقص أعمدة OHLCV أو تاريخ قصير → تحذيرات + خصم Score

---

## 17) معيار موحد للأخطاء والتحذيرات (Error/Warn Contract)

> هدفنا: المستخدم لا يرى Traceback. يرى رسالة واضحة + سبب + ما الذي يمكن فعله.

### 17.1 قواعد عامة
- **No Tracebacks** في UI: أي Exception تُلتقط وتُعرض كـ `st.warning/st.error`.
- أي بيانات ناقصة: تظهر “غير متوفر (—)” بدل 0.
- أي مصدر خارجي Rate limit: يظهر تنبيه “البيانات قد تكون قديمة”.

### 17.2 قوالب رسائل مقترحة
**429 Rate Limit:**
- “تعذر تحديث البيانات الآن بسبب ضغط على المصدر (429). سيتم عرض آخر بيانات مخزنة إن وجدت. حاول لاحقًا.”

**بيانات جزئية:**
- “تم جلب جزء من القوائم فقط. قد تتأثر بعض النسب. راجع بوابة الجودة.”

**خلط فترات:**
- “تم استخدام Quarterly بدل Annual لعدم توفر السنوي. تم خفض الثقة.”

---

## 18) دليل التنسيق (Formatting Guide) — توحيد الأرقام والنصوص

### 18.1 الأرقام المالية
- اعرض العملة: `SAR`
- استخدم ألف/مليون/مليار:
  - 1,200,000 → “1.20 مليون”
  - 3,400,000,000 → “3.40 مليار”
- لا تعرض رقم خام كبير بدون وحدة.

### 18.2 النسب
- نسب مئوية: `%` مع 1–2 decimals
- إذا missing: “—”

### 18.3 الجداول
- أي جدول في الواجهة: استخدم `render_custom_table` (نفس شكل جدول الصفقات)
- لا تستخدم `st.dataframe` إلا كـ fallback عند الضرورة

### 18.4 المصطلحات
- أول مرة: عربي + (اختصار)
  - “مؤشر القوة النسبية (RSI)”
- لاحقًا: عربي فقط أو اختصار حسب تفضيلك

---

## 19) نظام ترجمة رسمي (i18n) — أفضل ممارسة

> بدل تعريب متفرق: اعتمد قاموس ترجمة مركزي.

### 19.1 المقترح
- ملف: `i18n_ar.py` يحتوي قاموس كبير:
  - UI labels
  - أسماء الأعمدة
  - أسماء المؤشرات
- دالة: `tr(key: str) -> str`
- في الواجهات:
  - `st.write(tr("Score"))`

### 19.2 ترجمة أعمدة features/signals
أنشئ mapping مثل:
- `breakout_strength` → “قوة الاختراق”
- `regime` → “نظام السوق”
- `cluster_score` → “درجة التجمع”

ثم عند بناء الجدول:
- rename columns قبل العرض.

---

## 20) مواصفات الحزم (Packs Spec) للمستشار

> أي Pack يُنتج للمستشار يجب أن يكون قابل للدمج والشرح.

### 20.1 Technical Pack (مثال)
```python
{
  "score": 0-100,
  "confidence": 0-100,
  "bias": "bullish|bearish|neutral",
  "signals": [...],
  "evidence": [...],
  "features": {...},
  "issues": [...]
}
```

### 20.2 Fundamental Pack (مثال)
- يجب أن يحمل:
  - الفترة المستخدمة (Annual/Quarterly/TTM)
  - مشاكل الجودة (issues)
  - confidence
  - النسب الأساسية (None إذا missing)

### 20.3 Risk Gates
- مدخلاته:
  - dq_pass, dq_confidence
  - volatility window OK?
  - trend regime
- مخرجاته:
  - `allowed_actions`: مثل “لا شراء قوي”
  - `reasons`: قائمة أسباب

---

## 21) Playbook لتشخيص المشاكل بسرعة (Troubleshooting)

### 21.1 الشارت لا يظهر
**افحص:**
- `market_data.get_chart_history`
- هل الرمز مطبّع `.SR`؟
- هل df فارغ؟

**الحل:**
- اعرض fallback (آخر 10 شموع)
- اعرض رسالة “لا توجد بيانات”

### 21.2 المؤشرات المتقدمة “غير متوفرة”
**افحص:**
- `technical_indicators/advanced.py` هل يستورد بدون خطأ؟
- هل compute_advanced_technical_pack موجودة؟

**الحل:**
- Fail-safe import + رسالة واضحة للمستخدم

### 21.3 القوائم لا تُجلب أو 429
**افحص:**
- `financial_analysis/yahoo_data.py` diagnostics
- “Data Freshness Badge” هل يقول بيانات قديمة؟

**الحل:**
- backoff + cache + توضيح مصدر/تاريخ

### 21.4 المستشار يعطي رأي ضعيف/محايد
**افحص:**
- dq_pass / confidence
- عدد الشموع (تاريخ قصير)
- تعارض إشارات

**الحل:**
- هذا متوقع إذا الجودة منخفضة؛ اعرض الأسباب ضمن evidence.

---

## 22) خطة اختبار Regression (أوسع من Smoke Test)

### 22.1 سيناريوهات بيانات
- سهم بتاريخ طويل (1y+)
- سهم بتاريخ قصير (أقل من 120 شمعة)
- سهم بسيولة ضعيفة (volume منخفض)
- سهم بقوائم ناقصة (Revenue/Equity مفقود)
- سهم يتعرض لـ 429 (تجربة وقت الذروة)

### 22.2 توقعات السلوك
- لا Traceback
- ظهور Freshness
- Fail/Low confidence يظهر للمستخدم
- المستشار لا يعطي “Strong Buy” مع dq_fail

---

## 23) قالب “ملاحظة تعديل” (Change Note Template)

ضعه أعلى أي دالة جديدة أو تعديل مهم:
```python
# CHANGE NOTE (YYYY-MM-DD):
# - لماذا تم التعديل؟
# - ما الذي يعتمد عليه؟
# - ما هي حالات الفشل؟
# - ما هو الـ fallback؟
```



---

## 24) قاموس القرار (Decision Glossary) — ماذا تعني الكلمات فعليًا؟

> هذا القسم يقلل اللبس بين “الدرجة” و“الثقة” و“التحيز” و“التوصية”.

### 24.1 الفرق بين Score و Confidence
- **الدرجة (Score):** تقييم رقمي لمجموعة إشارات/معايير (0–100).  
  مثال: “التحليل الفني” قد يعطي Score = 72.
- **الثقة (Confidence):** مدى موثوقية هذا التقييم بناءً على جودة البيانات واتساق الأدلة.  
  مثال: Confidence = 45% بسبب تاريخ قصير أو بيانات ناقصة.

**قاعدة ذهبية:**  
Score مرتفع + Confidence منخفض ⇒ *لا توصية قوية*.

### 24.2 Bias / Trend / Regime
- **التحيز (Bias):** ميل عام (إيجابي/سلبي/محايد)
- **الاتجاه (Trend):** اتجاه سعري واضح (صاعد/هابط/عرضي)
- **نظام السوق (Regime):** بيئة السوق (ترند/تذبذب/انضغاط…)
> قد يكون Bias إيجابي لكن Regime “متذبذب” ⇒ توصيات متحفظة.

### 24.3 توصيات المستشار
> هذه مجرد تعريفات تشغيلية (Operational Definitions) وليست توصية استثمارية.

- **Strong Buy (شراء قوي):**
  - إشارات متعددة متوافقة
  - جودة بيانات Pass
  - Confidence مرتفع (مثلاً ≥ 70)
  - بوابات المخاطر تسمح

- **Buy (شراء):**
  - إشارات إيجابية واضحة
  - Confidence متوسط/مرتفع
  - مخاطر مقبولة

- **Hold (احتفاظ/مراقبة):**
  - إشارات مختلطة أو انتظار تأكيد
  - أو Confidence منخفض

- **Sell / Reduce (بيع/تخفيف):**
  - إشارات سلبية أو كسر مستويات مهمة
  - أو مخاطر عالية مقابل عائد متوقع ضعيف

### 24.4 Data Quality Pass/Fail
- **Pass:** القوائم الأساسية متوفرة ومتناسقة
- **Fail:** نقص جوهري (Revenue/NI/Equity/OCF…) أو تناقضات تمنع حسابات موثوقة

---

## 25) عقود الصفحات (UI Contracts) — ماذا تتوقع كل صفحة؟ وماذا تُرجع؟

> الهدف: عند تعديل صفحة أو دالة، تعرف ما الذي لا يجب تغييره حتى لا تكسر الترابط.

### 25.1 صفحة التحليل `views/analysis/__init__.py`
**Inputs:**
- `symbol: str`
- `interval: str` (افتراضي 1d)
**Guarantees:**
- تبويبات التحليل يجب أن تُفتح حتى لو تبويب واحد فشل (Fail-safe).

### 25.2 الفني `views/analysis/technical.py`
**Inputs:**
- `symbol`
- `interval`
**Dependencies:**
- `market_data.get_chart_history`
- `views.shared._render_technical_chart_flex`
- `technical_indicators.advanced.compute_advanced_technical_pack` (اختياري)
**Output (UI):**
- لا يُرجع قيمة (render فقط)  
**Contract:**
- ممنوع تغيير اسم `render_technical_tab` بدون wrapper توافق.

### 25.3 المالي `views/analysis/financial.py`
**Inputs:**
- `symbol`
- فترة القوائم (Annual/Quarterly)
**Dependencies:**
- `financial_analysis/store.py`
- `financial_analysis/metrics.py`
- `financial_analysis/data_quality.py`
**Contract:**
- أي نسبة غير قابلة للحساب يجب أن تظهر “—” وليس 0.

### 25.4 المستشار `views/analysis/advisor.py`
**Inputs:**
- `symbol`
- `interval`
- (اختياري) إعدادات المستخدم/قواعد
**Dependencies:**
- `ai_engine.generate_ai_report`
**Contract:**
- إذا dq_fail أو low confidence ⇒ لا توصية قوية + سبب واضح.

---

## 26) قواعد التسمية والتوافق (Naming & Versioning Rules)

### 26.1 دوال عامة في الواجهة
أي دالة تُستدعى بالاسم من `views/analysis/__init__.py` أو router:
- لا تُعاد تسميتها مباشرة.
- إن لزم: أنشئ Wrapper توافق:
  - مثال: `render_technical_tab` يستدعي `view_technical`.

### 26.2 Schema Version للحزم (Packs)
أي Pack يُفضل يحمل:
```python
{"schema_version": 1, ...}
```
إذا غيرت المفاتيح/الهيكل:
- زِد `schema_version`
- واجعل المستهلك (UI/Advisor) يتعامل مع النسخ القديمة.

### 26.3 قاعدة “لا تغيّر شكل البيانات بصمت”
- إذا غيّرت units أو الفترات، اكتبها صراحة في UI.

---

## 27) المراقبة والتشخيص (Observability) — بدون تعقيد

### 27.1 مبادئ
- أي خطأ خارجي (429/timeout) يجب أن يترك أثرًا:
  - diagnostics محفوظ
  - ويمكن عرضه في صفحة Tools

### 27.2 أين نضع التشخيص؟
- Yahoo:
  - `financial_analysis/yahoo_data.py` (diagnostics)
- AI:
  - `ai_engine_core/logging_learning.py` (ai_signals)
- Advanced:
  - `ai_engine_core/db.py` (advanced_indicators cache)

### 27.3 واجهة Tools (اقتراح)
- صفحة `views/tools.py` أو `views/settings.py`:
  - “آخر تشخيص Yahoo”
  - “آخر تقرير جودة بيانات”
  - “آخر إشارة AI”
> هذا يقلل احتياجك لفتح logs في Streamlit Cloud.

---

## 28) الأمن والأسرار (Security & Secrets Guide)

### 28.1 ماذا يوضع في `.streamlit/secrets.toml`؟
- كلمات مرور قاعدة البيانات
- مفاتيح API (إن وجدت)
- connection strings

### 28.2 ماذا لا يوضع في GitHub؟
- `secrets.toml`
- أي ملفات تحتوي tokens
- مفاتيح خاصة

### 28.3 نصيحة عملية
- أضف `secrets.toml` إلى `.gitignore`
- استخدم env vars على السيرفر إن أمكن

---

## 29) خارطة الطريق (Roadmap) + Definition of Done

### 29.1 Roadmap مقترحة
1) تعريب 100% للـ UI + مصطلحات المؤشرات + أعمدة الجداول
2) توحيد كل الجداول بـ `render_custom_table`
3) توحيد Units (Normalizer رسمي) لكل القوائم والنسب
4) تحسين مصادر القوائم (Fallbacks) + caching
5) صفحة Tools للتشخيص
6) إضافة Regression Tests بسيطة

### 29.2 Definition of Done (DoD)
الميزة تعتبر مكتملة إذا:
- لا Traceback للمستخدم
- يظهر Freshness + Source
- Data Quality Gate موجودة وواضحة
- المستشار يشرح “لماذا” (Evidence)
- الأداء مقبول (لا requests متكررة بلا caching)
- Smoke tests + regression الأساسية تمر

---

## 30) حوكمة البيانات (Data Governance) — أهم نقطة للثقة

### 30.1 قواعد
- أي قيمة تُعرض يجب أن تُعرّف:
  - المصدر
  - الفترة
  - الوحدة
  - حداثة البيانات
- أي حساب يعتمد على missing essentials يجب أن:
  - يرجع None
  - ويسجّل issue

### 30.2 أسباب شائعة لبيانات “مقنعة لكنها غلط”
- خلط Annual/Quarterly/TTM
- اختلاف Units بين مصادر
- تحويل missing إلى 0
- استخدام تاريخ قصير للمؤشرات

---

## 31) دليل توحيد الأعمدة (Column Translation / Mapping)

> حتى لا تظهر مفاتيح تقنية داخل الجداول.

### 31.1 مثال Mapping
- `breakout_strength` → “قوة الاختراق”
- `regime` → “نظام السوق”
- `cluster_score` → “درجة التجمع”
- `signal` → “الإشارة”
- `score` → “الدرجة”
- `note` → “ملاحظة”

### 31.2 أين تطبق؟
- قبل عرض الجداول في UI:
  - rename columns
- أو عند بناء الجدول من features/signals:
  - اعرض `display_name` بدل key الخام

---

## 32) نمط كتابة الأقسام التفسيرية داخل UI (Explainability Pattern)

> هدفنا: أي قسم يعطي “نتيجة” يجب أن يعطي “معنى” و “حدود” و “متى تثق فيه”.

### 32.1 قالب “ماذا يعني هذا؟”
- ماذا يقيس؟
- لماذا مهم؟
- متى يعطي إشارة جيدة؟
- متى يكون مضلل؟
- ما الذي يؤثر على الثقة؟

### 32.2 لماذا هذا مهم؟
لأن المستخدم يرى رقمًا؛ بدون شرح قد يفهمه غلط أو يثق به أكثر من اللازم.

---

## 33) أسلوب صيانة الإصدارات (Maintenance)

### 33.1 سياسة التغييرات
- أي تغيير كبير → Patch صغير أولاً
- ثم دمج تدريجي
- لا “Rewrite” شامل إلا لو مع اختبارات قوية

### 33.2 سياسة الرجوع
- احتفظ بنسخة سابقة تعمل (`*_old_v.py` موجودة)
- وثّق سبب الاختلاف في README

---

## 34) ملحق: قائمة الملفات الأكثر حساسية (High-Risk Files)

> هذه الملفات إذا تغيرت غالبًا تكسر أشياء أخرى — تعامل معها بحذر.

- `views/shared.py`
- `views/analysis/__init__.py`
- `views/analysis/technical.py`
- `views/analysis/financial.py`
- `ai_engine_core/reporting.py`
- `ai_engine_core/db.py`
- `financial_analysis/metrics.py`
- `financial_analysis/store.py`

---

## 35) ملحق: قواعد تصميم UI (UI Design Rules)

- لا تكدّس أرقام بدون وحدات/شرح
- اجعل كل تبويب:
  - Header + Freshness + Source
  - KPI cards قليلة وواضحة
  - جدول موحد
  - Expanders للأدلة والتفاصيل
- استعمل نفس المصطلحات في كل مكان (لا “Score” مرة و“Rating” مرة)

---

