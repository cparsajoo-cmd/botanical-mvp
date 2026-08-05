# PHASE 3 — Source Authority / Evidence Quality Implementation Report

> این نسخه گزارش، ادامه‌ی session قبلی است (بخش‌های ۱-۹ زیر بدون تغییر
> از آن session، مگر جایی که صراحتاً «SESSION 2 — به‌روزرسانی» علامت
> خورده). بخش «۱۰. SESSION 2» در انتها، کاری را مستند می‌کند که در این
> session روی همان working tree ادامه یافت: verify مستقل تمام ادعاهای
> session قبلی (نه صرفاً پذیرش گزارش)، و رفع دو مشکل باقی‌مانده‌ای که
> session قبلی به‌درستی به‌عنوان محدودیت مستند (نه ادعای دروغ) گزارش
> کرده بود.

## 1. وضعیت قبلی Source Authority در نسخه جدید (89)

مطابق ممیزی (`PHASE3_SOURCE_AUTHORITY_AUDIT.md`)، Source Authority در نسخه
(89) دقیقاً همان وضعیت نسخه ممیزی‌شده‌ی قبلی را داشت: `authority_weight`
در `source_registry.py` تعریف می‌شد، در زمان collection
(`multi_source_collector.py`) روی رکورد قرار می‌گرفت، از استانداردسازی و
مدل canonical (`EvidenceRecord.source_authority`) عبور می‌کرد، اما در
`database.py::save_evidence_record` **کاملاً حذف می‌شد** — نه در دیتابیس
ذخیره می‌شد، نه دوباره خوانده می‌شد، نه در `candidate_shortlisting.py`
وارد امتیازدهی می‌شد. عملاً metadata‌ای بود که جمع‌آوری و سپس بی‌سروصدا
دور ریخته می‌شد.

## 2. نتیجه revision verification

تنها تفاوت نسخه (89) با نسخه‌ای که ممیزی اول روی آن انجام شد، یک تقویت در
`database.py::_missing_postgrest_column` برای تشخیص خطای PostgreSQL
`42703` (علاوه بر `PGRST204`) به‌همراه سه تست متناظر بود — کاملاً بی‌ربط
به مسیر Source Authority. تمام ۱۱ یافته ممیزی اول دوباره مستقیماً روی کد
نسخه (89) تأیید شد. یک تصحیح هم به آن سند اضافه شد: `Scientific_Triage_Score`
(برخلاف ادعای اول) واقعاً در `candidate_shortlisting.py` وجود دارد —
فیلدی عددی مجزا از `Scientific_Triage_Status` categorical.

نتیجه: نسخه جدید هیچ یافته یا تصمیم معماری فاز ۳ را باطل نکرد؛
پیاده‌سازی دقیقاً بر همان مبنا ادامه یافت.

## 3. معماری (SESSION 2 — به‌روزرسانی: هر دو pipeline اکنون واقعاً متصل‌اند)

```
                     ┌─────────────────────────┐
                     │   evidence_authority.py   │   (ماژول جدید، pure،
                     │   -- منبع واحد حقیقت --    │    بدون وابستگی به
                     │  taxonomy + classify_*     │    pandas/دیتابیس)
                     │  + formulas (strength,      │
                     │    signed_contribution)     │
                     └─────────────┬───────────────┘
                                    │ import (یک‌طرفه)
                    ┌───────────────┴────────────────┐
                    │                                  │
       evidence_interpretation.py          evidence_standardizer.py
       (Study_Design/Direction/Quality        (ingestion: کلاسیفای
        constants -- بدون تغییر، فقط          می‌کند و
        source_authority_factor اختیاری       Source_Authority/_Score/
        اضافه شد به interpret_evidence)        _Reason را روی رکورد
                    │                          می‌گذارد)
                    │                                  │
       botanical_rd_candidate_engine.py                │
       (مسیر زنده Phase 1 -- SESSION 2: اکنون از        │
        authority_index واقعی، ساخته‌شده در              │
        _build_evidence_text_index()، برای هر           │
        compound/problem/plant key واقعی که              │
        _collect_raw_evidence() برمی‌گرداند،              │
        source_authority_factor واقعی را به               │
        interpret_evidence() پاس می‌دهد -- دیگر            │
        همیشه ۱.۰ نیست)                                 │
                                                         ▼
                                              standard_evidence_schema.py
                                              (EvidenceRecord: دو فیلد
                                               canonical جدید +
                                               legacy map اصلاح‌شده)
                                                         │
                                                         ▼
                                                  database.py
                                              (سه ستون optional جدید:
                                               نوشتن + خواندن،
                                               migrations/0007)
                                                         │
                                                         ▼
                                           candidate_shortlisting.py
                                        (_evidence_quality: مسیر زنده
                                         ۳۰-امتیازی -- Authority با ضریب
                                         میراشده داخل همان سقف ادغام شد
                                         + دیکشنری explainability؛
                                         SESSION 2: outcome_multiplier
                                         از این total حذف شد)
```

هر دو pipeline زنده (`botanical_rd_candidate_engine.py` از طریق
`evidence_interpretation.py`، و `candidate_shortlisting.py` مستقیماً) از
**همان** `evidence_authority.classify_source_authority[_from_row]` و
**همان** فرمول‌های `weighted_evidence_strength`/`signed_evidence_contribution`
استفاده می‌کنند -- هیچ classifier مستقل دومی ساخته نشد.

## 4. فایل‌های تغییرکرده تا پایان session قبلی

| فایل | نوع | دلیل |
|---|---|---|
| `evidence_authority.py` | جدید | ماژول متمرکز taxonomy/classification/formulas |
| `migrations/0007_add_source_authority.sql` | جدید | افزودن سه ستون optional به `evidence_records` |
| `migrations/0007_add_source_authority_down.sql` | جدید | rollback |
| `test_source_authority.py` | جدید | ۳۱ تست واحد روی `evidence_authority.py` |
| `test_phase3_authority_quality_integration.py` | جدید (SESSION 2: ۵ تست اضافه) | تست integration روی مسیر زنده |
| `test_database_source_authority_persistence.py` | جدید | ۷ تست round-trip و optional-column fallback |
| `test_evidence_quality_engine.py` | جدید | ۶ تست مستقیم روی `evidence_quality_engine.py` |
| `standard_evidence_schema.py` | تغییر | دو فیلد canonical جدید + اصلاح mapping |
| `evidence_standardizer.py` | تغییر | فراخوانی `classify_source_authority_from_row` در ingestion |
| `database.py` | تغییر | سه ستون optional: نوشتن + خواندن |
| `evidence_quality_engine.py` | تغییر | حذف coupling outcome/quality |
| `evidence_interpretation.py` | تغییر | پارامتر اختیاری `source_authority_factor` |
| `candidate_shortlisting.py` | تغییر (SESSION 2: تغییر بیشتر -- بخش ۱۰) | ادغام Authority در `_evidence_quality` |
| `botanical_rd_candidate_engine.py` | **SESSION 2: تغییر جدید** | وصل واقعی authority به `interpret_evidence()` |
| `benchmark_cases/smoke_cases.json` | **SESSION 2: تغییر جدید** | یک fixture منسوخ‌شده به‌روزرسانی شد |
| `test_task10_2_preparation_applicability.py` | **SESSION 2: تغییر جدید** | تطبیق با امضای ۴-مقداری جدید `_build_evidence_text_index()` |
| `PHASE3_SOURCE_AUTHORITY_AUDIT.md` | به‌روزرسانی | بخش Revision Verification |

## 5. نحوه اثرگذاری Source Authority بر تصمیم

**فرمول** (`evidence_authority.py`):

```
evidence_strength = study_quality_factor x source_authority_factor x applicability_factor
signed_evidence_contribution = evidence_strength x direction_sign
```

**Mapping** (۱۴ دسته، `AUTHORITY_FACTORS`، از ۰.۱۵ تا ۱.۰۰): EMA HMPC
(1.00) > WHO (0.97) > ESCOP/Cochrane (0.93) > Systematic Review (0.85) >
RCT (0.80) > Controlled Clinical Trial (0.72) > Observational (0.60) >
**Unknown (0.50)** > Case Report (0.45) > Animal (0.40) > In-vitro
(0.35) > Commercial Website (0.20) > Blog (0.15).

**Cap در `candidate_shortlisting._evidence_quality`**: سقف موجود ۳۰.۰
دست‌نخورده ماند. Authority هر ردیف شواهد را با ضریب میراشده
(`0.85 + 0.15 x authority_score`, بازه ۰.۸۷۲۵ تا ۱.۰) قبل از تجمیع در
`hierarchy_points` ضرب می‌کند -- نه ضرب مستقیم ضریب خام (که برای اکثریت
شواهد بدون هویت سازمانی امتیاز پیش‌فرض را تقریباً نصف می‌کرد و عملاً
بازطراحی Ranking Logic بود).

**حفظ Direction**: Authority هرگز در محاسبه‌ی `direction`/`sign` دخالت
نمی‌کند -- یک RCT منفی معتبر همیشه contribution منفی می‌گیرد، هرگز مثبت.

**Persistence**: `source_authority`، `source_authority_score`،
`source_authority_reason` سه ستون optional در `evidence_records` هستند
(migration 0007)، نوشته و خوانده می‌شوند، و از optional-column fallback
موجود بهره می‌برند.

## 6. نحوه اثرگذاری Evidence Quality بر تصمیم (SESSION 2 -- بخش اصلاح‌شده)

- `evidence_interpretation.py` (Phase 1): `classify_evidence_quality`
  کاملاً مبتنی بر طراحی مطالعه است، نه نتیجه -- دست‌نخورده ماند.
- `evidence_quality_engine.py` (مسیر مرده): coupling صریح مثبت/منفی حذف
  شد؛ اکنون فقط از سلسله‌مراتب مطالعه/طراحی/اندازه نمونه می‌آید.
- **`candidate_shortlisting._evidence_quality` (مسیر زنده ۳۰-امتیازی) --
  SESSION 2**: `outcome_multiplier` (که در session قبلی به‌عنوان
  «مکانیزم موجود، مستند، و عمداً بدون تغییر» توصیف شده بود) واقعاً هنوز
  در کد بود و به‌صورت مستقیم unsigned total را بر اساس ترکیب
  positive/null/harmful/mixed یک plant در ۰.۵۵ یا ۰.۸۰ ضرب می‌کرد --
  دقیقاً همان چیزی که این session به‌عنوان «مشکل ۲» گزارش کرد. با بررسی
  مستقیم کد (نه پذیرش ادعای session قبلی) تأیید و حذف شد: اکنون
  `total = round(min(30.0, hierarchy_points + depth_points +
  diversity_points + consistency_points), 1)` -- بدون ضرب در هیچ عامل
  وابسته به direction. Direction هنوز کاملاً قابل مشاهده است (از طریق
  `signed_contribution`/`direction` هر ردیف در دیکشنری `explain`)، فقط
  دیگر total نهایی سقف‌دار را تغییر نمی‌دهد. وزن‌های
  `hierarchy_points`/`depth_points`/`diversity_points`/`consistency_points`
  و سقف ۳۰.۰ **بدون تغییر** ماندند، طبق دستور صریح.
- `_evidence_points` (تابع خواهر، تغذیه‌کننده‌ی `Scientific_Triage_Score`
  -- یک امتیاز ۰-۱۰۰ کاملاً جدا، **نه** `Evidence_Quality_Score`/
  `Overall_Score`/`R&D_Opportunity_Score`) هنوز `outcome_multiplier`ی
  محلی و مستقل خودش را دارد. این عمداً دست‌نخورده ماند: دستور صریح این
  session محدود به «Evidence Quality مستقل از Evidence Direction» بود،
  و «وزن‌های componentهای دیگر و total Opportunity Score را تغییر نده»
  -- `Scientific_Triage_Score` یکی از همان componentهای دیگر است. کامنت
  کد به‌روزرسانی شد تا این تفاوت عمدی را مستند کند (این دو امتیاز از این
  به بعد آگاهانه با هم موافق نیستند).

## 7. تست‌های اضافه‌شده تا پایان session قبلی

**`test_source_authority.py`** (۳۱ تست)، **`test_phase3_authority_quality_integration.py`**
(۱۳ تست پایه + ۵ تست SESSION 2 = ۱۸)، **`test_database_source_authority_persistence.py`**
(۷ تست)، **`test_evidence_quality_engine.py`** (۶ تست) -- شرح کامل هر
گروه بدون تغییر از نسخه قبلی این گزارش.

## 8. نتیجه واقعی اجرای تست‌ها -- تاریخچه (session قبلی)

```
python3 -m pytest -q          (کل مخزن، پایان session قبلی)
  -> 2405 passed
```

این عدد (۲۴۰۵) صرفاً به‌عنوان تاریخچه ثبت می‌شود؛ نتیجه نهایی این
session در بخش ۱۰.۴ زیر است.

## 9. محدودیت‌های باقی‌مانده -- وضعیت در پایان session قبلی (تاریخچه)

1. `botanical_rd_candidate_engine.py` هنوز per-source authority واقعی
   دریافت نمی‌کرد (رفع شد -- بخش ۱۰.۱).
2. `outcome_multiplier` در `candidate_shortlisting._evidence_quality`
   بازطراحی نشده بود (رفع شد -- بخش ۶ و ۱۰.۲).
3. `decision_engine.py`/`evidence_quality_engine.py` هنوز کد مرده بودند.
4. هیچ connector واقعی commercial-website/blog وجود نداشت.
5. UI/Dashboard تغییر نکرده بود.
6. مخزن `.git` واقعی نداشت.

---

## 10. SESSION 2 -- ادامه‌ی کار از همان نقطه

### ۱۰.۰ روش کار

از صفر شروع نشد. ZIP پایه (`botanical-mvp-main (90).zip`) extract و
فایل‌های standalone تحویلی روی آن merge شدند تا working tree واقعی
بازسازی شود. سپس **هیچ ادعای session قبلی صرفاً از روی گزارش پذیرفته
نشد** -- هر یافته با مشاهده مستقیم کد و اجرای تست تأیید شد:

- عدد «۲۴۰۵ passed» با اجرای واقعی کل suite تأیید شد (قبل از هر تغییری
  در این session) -- درست بود.
- هر دو محدودیت مستندشده (بخش ۹، آیتم‌های ۱ و ۲) با خواندن مستقیم کد
  `botanical_rd_candidate_engine.py` و `candidate_shortlisting.py` تأیید
  شدند که واقعاً هنوز حل‌نشده بودند -- نه صرفاً بر اساس گزارش قبلی.
- سایر بخش‌های معماری (persistence round-trip، عدم‌تغییر sign توسط
  authority، سقف ۳۰، جدایی `evidence_quality_engine.py` از هر importer
  زنده) با خواندن کد `database.py`/`evidence_authority.py`/
  `standard_evidence_schema.py`/`evidence_standardizer.py` و جست‌وجوی
  importer در کل مخزن دوباره تأیید شدند -- بدون یافتن هیچ تناقضی با
  ممیزی قبلی.

### ۱۰.۱ رفع مشکل ۱ -- اتصال واقعی `botanical_rd_candidate_engine.py` به `interpret_evidence()`

اتصال واقعی، **بدون بازطراحی گسترده Ranking Logic**، ممکن بود -- با
همان الگویی که خود تابع `_build_evidence_text_index()` از قبل برای
`applicability_index` (Task 10.2) استفاده می‌کرد: یک ایندکس ساختاریافته
موازی، نه دخالت در متن ادغام‌شده‌ای که classifierهای متنی
(`_evidence_level`, `classify_evidence_hierarchy`, ...) می‌خوانند.

تغییرات دقیق:

1. `_build_evidence_text_index()` اکنون یک `authority_index` چهارم هم
   برمی‌گرداند -- همان کلید نرمال‌شده‌ی `text_index`/`source_index`/
   `applicability_index`، مقداردهی‌شده فقط از ردیف‌های `self.evidence_df`
   (تنها جدولی که فیلدهای `Source_Organization`/`Source_Type`/
   `Source_Category` را دارد) از طریق همان
   `evidence_authority.classify_source_authority_from_row` که هر دو
   pipeline از قبل استفاده می‌کردند -- **بدون classifier دوم**.
2. `_collect_raw_evidence()` اکنون یک پارامتر اختیاری `authority_index`
   می‌پذیرد و به‌جای دو مقدار، سه مقدار برمی‌گرداند:
   `(text, source_ids, authority_factor)`. `authority_factor` قوی‌ترین
   (بیشترین) عامل تأیید‌شده در میان ردیف‌هایی است که واقعاً در ساخت
   `text` همان کلید (compound/problem یا fallback به plant) مشارکت
   داشتند -- هیچ metadata‌ای حدس زده یا برای ردیف‌های غیرمرتبط اعمال
   نمی‌شود؛ وقتی هیچ ردیفی مشارکت نکرده، پیش‌فرض همان ۱.۰ بدون‌اثر قبلی
   است (سازگاری کامل با رفتار قدیمی برای هر داده‌ای که این ایندکس را
   ندارد).
3. تنها call site واقعی (`run()`) اکنون `authority_index` را از
   `_build_evidence_text_index()` می‌گیرد، به `_collect_raw_evidence()`
   پاس می‌دهد، و مقدار سوم بازگشتی را مستقیماً به
   `interpret_evidence(..., source_authority_factor=evidence_authority_factor)`
   می‌دهد -- به‌جای پیش‌فرض همیشگی ۱.۰.

قواعد الزامی رعایت شد: Authority هرگز sign را تغییر نمی‌دهد (فقط
magnitude)، RCT منفی معتبر همچنان contribution منفی قوی می‌گیرد، fallback
برای داده بدون metadata سازمانی همان ۱.۰ (یا رفتار سازگار Unknown=۰.۵۰
در کلاسیفایر خودش، نه یک مقدار جعلی) است، و هیچ metadata علمی ساخته یا
حدس زده نشد.

اثبات (تست جدید `test_botanical_rd_candidate_engine_passes_real_source_authority_into_interpret_evidence`):
دو evidence pool کاملاً یکسان، فقط با/بدون `Source_Organization="EMA HMPC Monograph"`،
از طریق زنجیره واقعی `_build_evidence_text_index -> _collect_raw_evidence
-> interpret_evidence` عبور داده شدند -- هر دو sign یکسان (مثبت) گرفتند،
اما magnitude متفاوت، و reason هرکدام از طریق همان classifier مشترک
قابل توضیح و متفاوت بود.

**اثر جانبی واقعی، نه رگرسیون**: یک case ثابت در fixture داخلی
`benchmark_cases/smoke_cases.json` (`smoke_direct_evidence_present`) که
هیچ `Source_Organization`ی ندارد، اکنون واقعاً یک ضریب Authority غیر از
۱.۰ (۰.۸۰ -- literature-fallback RCT) می‌گیرد و `decision_class` آن از
«Early-stage candidate; more evidence needed» به «Low priority /
insufficient data» تغییر کرد؛ `gate_status`/`decision_class_ah` تغییر
نکردند. این دقیقاً اثر مطلوب رفع باگ است (پیش‌تر این عدد ۱.۰ ثابت و
بدون‌اثر بود)، نه یک regression علمی -- fixture با توضیح کامل به‌روزرسانی
شد، نه پنهان یا حذف.

### ۱۰.۲ رفع مشکل ۲ -- جداسازی واقعی Evidence Quality از Outcome Direction

شرح کامل در بخش ۶ بالا. خلاصه: `outcome_multiplier` از `total` نهایی
`candidate_shortlisting._evidence_quality` حذف شد؛ فرمول واقعی اکنون:

```
unsigned_total = hierarchy_points + depth_points + diversity_points + consistency_points
Evidence_Quality_Score = round(min(30.0, unsigned_total), 1)
```

Direction هرگز دیگر این عدد را تغییر نمی‌دهد؛ فقط در `signed_contribution`
per-record (لایه explainability) دیده می‌شود. `Scientific_Triage_Score`
(component جداگانه) عمداً دست‌نخورده ماند.

### ۱۰.۳ تست‌های جدید این session (۵ تست، همگی در `test_phase3_authority_quality_integration.py`)

1. `test_evidence_quality_total_no_longer_scaled_by_outcome_multiplier`
   -- یک pool کاملاً مثبت و یک pool کاملاً منفی (طراحی/authority یکسان)
   دقیقاً total یکسان می‌گیرند.
2. `test_evidence_quality_total_unchanged_for_mixed_pool_versus_all_positive_pool`
   -- pool مخلوط (یک مثبت + یک منفی) همان total یک pool تماماً مثبت با
   طراحی مشابه را می‌گیرد؛ signed contribution منفی همچنان در `explain`
   دیده می‌شود.
3. `test_positive_animal_versus_negative_rct_magnitude_comparison` --
   `abs(negative RCT contribution) > positive animal contribution`.
4. `test_mixed_evidence_does_not_gain_artificial_quality_boost_from_diversity_alone`
   -- pool مخلوط هرگز پایین‌تر از قوی‌ترین مطالعه‌ی منفرد آن امتیاز
   نمی‌گیرد، اما diversity به‌تنهایی هم آن را به‌طور مصنوعی از RCT منفرد
   قوی‌تر نشان نمی‌دهد.
5. `test_botanical_rd_candidate_engine_passes_real_source_authority_into_interpret_evidence`
   -- شرح در بخش ۱۰.۱.

هر پنج تست از اولین اجرا پاس شدند (بدون نیاز به تغییر پیاده‌سازی برای
پاس‌کردن تست).

همچنین یک تست موجود (`test_build_evidence_text_index_excludes_platform_generated_fields`
در `test_task10_2_preparation_applicability.py`) که مقدار بازگشتی
سه‌تایی قدیمی `_build_evidence_text_index()` را unpack می‌کرد، با امضای
چهارتایی جدید تطبیق داده شد (فقط unpack؛ منطق تست دست‌نخورده ماند).

### ۱۰.۴ نتیجه واقعی اجرای تست‌ها -- این session (نتیجه نهایی)

```
python3 -m pytest -q test_source_authority.py
  -> 31 passed

python3 -m pytest -q test_phase3_authority_quality_integration.py
  -> 18 passed   (۱۳ قبلی + ۵ جدید)

python3 -m pytest -q test_database_source_authority_persistence.py
  -> 7 passed

python3 -m pytest -q test_evidence_quality_engine.py
  -> 6 passed

python3 -m pytest -q          (کل مخزن)
  -> 2410 passed in ~55s
```

۲۴۰۵ (پایان session قبلی) + ۵ تست جدید = ۲۴۱۰ -- دقیقاً مطابق شمارش
واقعی. صفر تست skip/xfail/حذف شد. صفر رگرسیون واقعی؛ تنها یک fixture
منسوخ (بخش ۱۰.۱) با توضیح کامل به‌روزرسانی شد چون رفتار زیرینش عمداً
تغییر کرد.

### ۱۰.۵ آیا `candidate_shortlisting` (مسیر اصلی) کاملاً یکپارچه است؟

بله. Source Authority و اکنون هم عدم‌وابستگی Evidence Quality به
Direction، هر دو در مسیر زنده‌ی واقعی (`_evidence_quality`، مصرف‌شده در
`build_plant_candidate_shortlist` -> `Overall_Score`/
`R&D_Opportunity_Score`) عمل می‌کنند؛ نه در یک مسیر موازی تست‌شده و جدا.

### ۱۰.۶ آیا `botanical_rd_candidate_engine.py` کاملاً یکپارچه است یا فقط API-ready؟

**کاملاً یکپارچه، نه صرفاً API-ready.** پیش از این session،
`source_authority_factor` فقط یک پارامتر پذیرفته‌شده با پیش‌فرض بی‌اثر
بود (API-ready، بدون caller واقعی). اکنون تنها call site واقعی
(`run()`) یک مقدار غیر پیش‌فرض، مشتق از metadata واقعی هر ردیف evidence
که در ساخت متن آن مشارکت داشته، پاس می‌دهد. محدودیت باقی‌مانده: این
عامل authority یک مقدار نماینده در سطح هر کلید (compound/problem/plant)
است -- «قوی‌ترین منبع تأییدشده‌ای که واقعاً در متن آن کلید مشارکت کرد»
-- نه یک عامل جداگانه به‌ازای هر جمله در بلاک متنی ادغام‌شده (که نیازمند
بازطراحی کامل پایه‌ی aggregation متنی `_collect_raw_evidence` بود، بیرون
از محدوده‌ی «بدون بازطراحی گسترده»). این یک ساده‌سازی محافظه‌کارانه و
مستند است، نه یک ادعای کاذب یکپارچگی کامل.

### ۱۰.۷ آیا Outcome کاملاً از Evidence Quality جدا شده؟

در مسیر زنده‌ای که `Evidence_Quality_Score`/`Overall_Score`/
`R&D_Opportunity_Score` را می‌سازد (`candidate_shortlisting._evidence_quality`)
-- بله، کاملاً. در `evidence_quality_engine.py` (مسیر مرده) هم -- بله. در
`Scientific_Triage_Score` (component جداگانه‌ی ۰-۱۰۰، خارج از تعریف
Phase 3 برای «Evidence Quality») -- خیر، عمداً، طبق محدوده‌ی صریح این
session.

### ۱۰.۸ محدودیت‌های باقی‌مانده (پایان این session)

1. عامل Authority در `botanical_rd_candidate_engine.py` یک مقدار
   نماینده در سطح هر کلید evidence-index است (بخش ۱۰.۶) -- نه
   per-sentence.
2. `Scientific_Triage_Score` هنوز outcome-coupled است (عمدی، خارج از
   محدوده).
3. `decision_engine.py`/`evidence_quality_engine.py::assess_evidence_quality`
   هنوز کد مرده‌اند -- بدون importer زنده در مخزن.
4. هیچ connector واقعی commercial-website/blog در `source_registry.py`
   وجود ندارد؛ آن دو دسته فقط heuristic-detectable هستند.
5. UI/Dashboard تغییر نکرد.
6. مخزن `.git` واقعی ندارد (zip ساده است).

---

## 11. SESSION 3 -- تصحیح: یک مسیر دوم و نادیده‌گرفته‌شده برای نشت Direction

**تصحیح صریح روی ادعای Session 2**: بخش‌های ۱۰.۲ و ۱۰.۷ بالا نوشته
بودند که `Evidence_Quality_Score` «کاملاً مستقل از Evidence_Direction»
شده است. این ادعا **نادرست/ناقص** بود. `outcome_multiplier` واقعاً حذف
شده بود، اما یک مسیر دوم و مجزا برای همان نوع نشت -- از طریق
`consistency_points`، که مستقیماً از `negative_count`
(`Has_Negative_Evidence`) مشتق می‌شد و در `raw_total` جمع می‌شد -- نادیده
گرفته شده بود. Session 3 این مسیر را با بازرسی مستقیم کد (طبق گزارش
دقیق کاربر) پیدا و حذف کرد. عبارت «کاملاً مستقل از Direction» اکنون --
و فقط اکنون -- درست است.

### ۱۱.۱ چه outcome-derived logic از Quality Score خارج شد

```python
# حذف‌شده از raw_total (کد قبلی، Session 2):
negative_count = int(
    empirical.get("Has_Negative_Evidence", ...).fillna(False).astype(bool).sum()
)
if independent_count <= 1:
    consistency_points = 0.0
elif negative_count == 0:
    consistency_points = min(2.0, 0.5 * (independent_count - 1))   # تا سقف ۲
elif negative_count < independent_count:
    consistency_points = max(0.0, 1.0 - negative_count / independent_count)
else:
    consistency_points = 0.0
...
raw_total = hierarchy_points + depth_points + diversity_points + consistency_points
```

مشکل دقیقاً همان الگوی `outcome_multiplier` بود: یک pool کاملاً منفی
(`negative_count == independent_count`) دقیقاً همان `consistency_points
= 0.0` یک pool آشکارا متناقض (نیمه مثبت/نیمه منفی) را می‌گرفت، در حالی
که یک pool کاملاً مثبت تا ۲ امتیاز اضافه می‌گرفت -- یعنی `Direction`
مستقیماً `raw_total`، و از آن طریق `Evidence_Quality_Score` نهایی، را
تعیین می‌کرد.

جایگزین (`reproducibility_points`، همان سقف ۲.۰، اما **کاملاً
outcome-agnostic**):

```python
reproducibility_points = (
    min(2.0, 0.5 * (independent_count - 1)) if independent_count > 1 else 0.0
)
raw_total = hierarchy_points + depth_points + diversity_points + reproducibility_points
```

این فقط از `independent_count` (تعداد رکورد مستقل، از قبل
de-duplicate‌شده) می‌آید -- هرگز از `Has_Negative_Evidence`،
`_result_category()`، یا هر فیلد outcome-derived دیگری. این همان نوع
consistency‌ای است که خود کاربر صراحتاً مجاز دانست: «استقلال منابع،
تکرارپذیری طراحی» -- تعداد مطالعه‌ی مستقل واقعاً موجود، نه توافق آن‌ها
بر سر نتیجه.

هیچ فیلد دیگری در فرمول `raw_total` به `Has_Negative_Evidence` یا
`_result_category()` وابسته نبود (بررسی مجدد صریح این session):
`hierarchy_points`/`ranked`/`best`/`top_mean` فقط از `positive_scores`
می‌آیند که خودشان فقط بر اساس **طراحی مطالعه** (`row_hierarchy_points`)
غیرصفر یا صفر می‌شوند (صفر فقط برای `registry_no_results`)، نه بر اساس
نتیجه؛ `diversity_points` فقط از `strata` (برچسب طراحی) می‌آید؛
`depth_points` فقط از `independent_count` (تعداد رکورد) می‌آید؛ و
`_row_has_candidate_specific_empirical_support()` (فیلتر اولیه‌ی
`empirical`) فقط بر اساس traceability و واژگان نوع مطالعه فیلتر
می‌کند، نه نتیجه.

### ۱۱.۲ کجا Conflict/Direction اکنون نگهداری می‌شود

در دیکشنری `explain` بازگشتی از `_evidence_quality` (تابع
`_build_evidence_quality_explain`)، سه فیلد دیاگنوستیک جدید -- هرگز در
`raw_total`/`total`:

- **`evidence_direction_balance`**: دیکشنری شمارش هر برچسب Direction در
  میان رکوردهای این pool (مثلاً `{"positive": 2, "negative": 1}`).
- **`evidence_conflict`**: بولین -- `True` اگر هم رکورد مثبت هم رکورد
  منفی واقعی در همان pool وجود داشته باشد.
- **`outcome_consistency`**: نسبت غالب‌ترین جهت به کل رکوردها (بین ۰ و
  ۱) -- هرچه به ۱ نزدیک‌تر، رکوردها بیشتر با هم موافق‌اند.

این‌ها علاوه بر فیلدهای دیاگنوستیک از قبل موجود
(`positive_weighted_contribution`/`negative_weighted_contribution`/
`null_weighted_contribution`، از session‌های قبلی) هستند، نه جایگزین
آن‌ها.

### ۱۱.۳ چرا یک RCT منفی همچنان شاهد منفی قوی است

جداسازی از `Evidence_Quality_Score` (بخش ۱۱.۱) هیچ ربطی به
`signed_contribution` per-record ندارد -- آن مسیر (فرمول
`evidence_authority.weighted_evidence_strength` ×
`signed_evidence_contribution`، از Session 1) دست‌نخورده ماند. یک RCT
منفی معتبر همچنان:

- **طراحی**‌اش (`row_hierarchy_points`) یکسان با RCT مثبت طبقه‌بندی
  می‌شود (۱۶ امتیاز پایه، بدون افت) -- چون طراحی مستقل از نتیجه است.
- **`direction`**‌اش `DIRECTION_NEGATIVE` است -> `signed_contribution`
  منفی و **بزرگ‌تر در قدرمطلق** از یک مطالعه‌ی حیوانی مثبت با طراحی
  ضعیف‌تر (تست
  `test_negative_high_authority_rct_retains_larger_magnitude_than_positive_animal_evidence`).
- در دیکشنری `explain`، در `top_contradicting_evidence` و
  `negative_weighted_contribution` منفی ظاهر می‌شود -- کاملاً قابل رؤیت.

### ۱۱.۴ چرا Quality Score آن با RCT مثبت هم‌طراحی برابر است

چون `Evidence_Quality_Score` اکنون فقط تابعی از
design/methodological-quality/source-authority/applicability/
independent-depth/design-diversity/reproducibility (بخش ۱۱.۱) است --
هیچ‌کدام از این‌ها به `direction` وابسته نیستند. یک RCT منفی و یک RCT
مثبت هم‌طراحی، هم‌authority، در یک pool با همان تعداد رکورد مستقل،
دقیقاً همان `hierarchy_points`/`depth_points`/`diversity_points`/
`reproducibility_points` -- و بنابراین دقیقاً همان
`Evidence_Quality_Score` -- می‌گیرند (تست‌های ۱۱.۶ زیر).

### ۱۱.۵ اصلاح تست‌ها

- `test_mixed_evidence_does_not_gain_artificial_quality_boost_from_diversity_alone`
  با assertion اشتباه (`mixed_total >= rct_alone_total`، که مجموعه‌ای
  با ترکیب متفاوت -- ۱ رکورد در برابر ۲ رکورد -- را مقایسه می‌کرد و
  می‌توانست حتی با یک باگ واقعی هم پاس شود) حذف و با
  **`test_mixed_evidence_scores_same_as_identical_composition_all_positive_pool`**
  جایگزین شد: مقایسه‌ی صحیح اکنون بین دو pool با ترکیب **دقیقاً یکسان**
  (همان دو طراحی، همان دو authority، همان دو رکورد) است که فقط جهت
  رکورد دوم در آن‌ها فرق می‌کند -- و اکنون `==` است، نه `>=`.
- خط تکراری گزارش‌شده در تست magnitude (`positive_animal_contribution`
  دو بار) در نسخه‌ی فعلی فایل یافت نشد (بررسی مستقیم با `grep -c`؛ فقط
  یک انتساب + یک استفاده -- الگوی طبیعی). ممکن است در نسخه‌ای که کاربر
  بازبینی کرده وجود داشته و در ویرایش‌های بعدی همین session قبلاً حذف
  شده باشد؛ در هر صورت اکنون در فایل تحویلی تکراری وجود ندارد.

### ۱۱.۶ تست‌های اجباری جدید (۸ تست، همگی در `test_phase3_authority_quality_integration.py`)

1. `test_one_positive_rct_equals_one_negative_rct`
2. `test_three_positive_rcts_equals_two_positive_plus_one_negative_rct`
3. `test_three_positive_rcts_equals_three_negative_rcts`
4. `test_three_positive_rcts_equals_three_null_rcts`
5. `test_changing_only_direction_does_not_change_evidence_quality_score`
   (۴ حالت positive/negative/mixed/null هم‌ترکیب را با هم مقایسه می‌کند)
6. `test_direction_changes_signed_contribution_but_not_evidence_quality_score`
7. `test_negative_high_authority_rct_retains_larger_magnitude_than_positive_animal_evidence`
8. `test_evidence_quality_score_never_derived_from_result_category_or_negative_evidence_field`
   (۵ رکورد یکسان با ۳ توزیع مختلف مثبت/منفی/null -- هر سه دقیقاً همان
   عدد baseline را می‌گیرند)

به‌علاوه، تست ۳۲ قبلی (`test_mixed_evidence_does_not_gain_artificial_...`)
بازنویسی شد (بخش ۱۱.۵) -- نه یک تست خالص جدید، اما assertion آن به‌طور
substantive تغییر کرد.

هر ۹ مورد از اولین اجرا پاس شدند؛ هیچ تغییری در پیاده‌سازی صرفاً برای
پاس‌کردن تست انجام نشد.

### ۱۱.۷ نتیجه واقعی اجرای تست‌ها -- این session (نتیجه نهایی)

```
python3 -m pytest -q test_phase3_authority_quality_integration.py
  -> 26 passed   (۱۸ قبلی + ۸ جدید)

python3 -m pytest -q          (کل مخزن)
  -> 2418 passed
```

۲۴۱۰ (پایان Session 2) + ۸ تست جدید = ۲۴۱۸ -- دقیقاً مطابق شمارش واقعی.
صفر تست skip/xfail/حذف شد (به‌جز جایگزینی assertion اشتباه‌شده در بخش
۱۱.۵، که یک تصحیح تست بود نه حذف پوشش). صفر رگرسیون در بقیه‌ی suite --
یعنی هیچ تست دیگری (از جمله `test_candidate_shortlisting.py`) به مقدار
دقیق قبلی `consistency_points` وابسته نبود.

### ۱۱.۸ محدودیت‌های باقی‌مانده (پایان Session 3)

فهرست بخش ۱۰.۸ همچنان برقرار است، با این تغییر: آیتم اول آن فهرست
(«عامل Authority ... نه per-sentence») و بقیه بدون تغییر می‌مانند.
هیچ محدودیت جدیدی از این session باقی نماند -- هر دو مسیر نشت Direction
به `Evidence_Quality_Score` (مستقیم از طریق `outcome_multiplier`، و
غیرمستقیم از طریق `consistency_points`) اکنون بسته شده‌اند.

