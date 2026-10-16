# Enum و آمادگی freeze — ۱۶ اکتبر

**ادامهٔ C4p:** [قالب اختیاری review brief](maintainer-review-brief.fa.md)
خوانایی کد USER و ساختار ارجاع را در replay بهبود داد؛ تشخیص Enum یا نمرهٔ
usefulness تازه ندارد. renderer تاریخی/default همچنان حفظ است. این policy
به factory یا descriptor نهایی متصل نشده و قبل از adoption باید جدا bind شود.


**Enum هنوز پاسخ مفید و کاملِ تأییدشده ندارد.** این مرحله review خروجی‌های
موجود و آماده‌سازی ثبت دقیق تنظیم‌هاست؛ مدل تازه‌ای اجرا نشده و defaultها
به‌خاطر یک replay آفلاین تغییر نمی‌کنند.

## آپدیت تیم

پس از main`18b49a6`، PR#78محمدحسن برای question coverage دریافت شد؛ آپدیت
تازه‌ای از حسن یا بهنام در refs/PRهای بررسی‌شده نبود. [review مستقل PR78](receipts/pr78-review-2026-10-16.json)
در head`3402a59`،
دو mismatch قابل بازتولید با core پیدا کرد: incoming ask به‌تنهایی fact را
معلوم نمی‌کند؛ state شاخهٔ بازدیدنشده نیز نباید در مسیر دیگر جمع شود. یک
اختلاف normalization نام fact هم ثبت شد. در review اولیه PR باز ماند و فایل‌های صاحب بخش
بازنویسی نشدند. dev-onlyrebuild عدد۱۱/۱۱سؤال و۴extraoffer فعلی را عیناً
بازتولید کرد؛ این counterexampleها نمرهٔ فعلی dev را جعل یا رد نمی‌کنند، ولی
ادعای projection عمومیِ معادل core را پشتیبانی نمی‌کنند. report فقط summary
عددی test را دارد؛ هیچ fixture، سؤال یا gold از test باز نشد.

**اصلاح بعدی E2aa:** [گزارش state و سؤال](question-coverage-state.fa.md) و
[verification](receipts/question-coverage-state-2026-10-16.json) ایرادهای PR78
را با transition/catalog واقعی و مسیرهای جدا می‌بندند؛ v1 تاریخی ثابت است.
v2 فقطdev ساخته شد و شمارش۱۱ask/۴extraoffer را بازتولید کرد؛ هیچ summary
test دوباره اجرا یا تأیید نشده است. این اصلاح گزارش است، نه بهبود Enum یا
انتخاب تنظیم نهایی.

## از خروجی‌ها چه فهمیدیم؟

review انسانی محمدحسن در [PR77](pr77-review.fa.md) به خروجی‌های تاریخی C4g
مربوط است. support بررسی نشده؛ پاسخ طولانی Enum هم decision نامطمئن و
usefulness۱ دارد. این review را به تنظیم فعلی یا test تعمیم نمی‌دهیم.

سه شکست اصلی در [inventory موجود](../experiments/core_evidence_selection_v1/failure-inventory-v1.json)
و receiptهای اصلی قابل بررسی‌اند:

| شاهد | مشکل واقعی | نتیجه برای core |
| --- | --- | --- |
| OBS-01، passage plan | پاراگراف identity و فقط عنوان module انتخاب شد؛ بدنه و caveat موجود بودند | renderer متن انتخاب‌شده را حذف نکرده؛ انتخاب و مرزبندی passage ناکافی است |
| OBS-11، draft۱۴۴۹۴کاراکتری | سند عمومی همراه فقط یک بخش مرتبط آمده است | نقل کامل و طول زیاد، پوشش کامل راهکار را ثابت نمی‌کند |
| OBS-12، draft۵۹۹کاراکتری پس از correction | از سند بی‌نسخه، ادعای رفتار نسخه‌های۱٫۲۹و۱٫۳۱ساخته شده | متن کوتاه و citation معتبر، کاربرد برای نسخهٔ کاربر را اثبات نمی‌کنند |

در OBS-01، انتخاب واقعی `[[2,5],[1,1]]` است؛ بدنهٔ module در span`[98,544)`
و caveat ویرایش/reload در`[1896,2143)` انتخاب نشده‌اند. در replay موجود، section
کامل این بدنه و caveat را بازمی‌گرداند، ولی draftاز۱۴۵۹به۵۹۶۲کاراکتر می‌رسد.
این انتخاب تألیفی است؛ انتخاب موفق تازهٔ مدل یا نمرهٔ usefulness نیست.

نسخه، کد و محیط کاربر از قبل معلوم‌اند و correctionنسخه را از۱٫۳۱٫۰به۱٫۳۱٫۱
تغییر می‌دهد. سؤال دوبارهٔ نسخه/کد، کمبود مستندات را رفع نمی‌کند. مثال کاربر
widget ندارد؛ `enumCoercion` مربوط به خروجی widget را remedy مستقیم Session
State حساب نمی‌کنیم. کاربرد راهنمای مفهومی برای همان runtime اثبات نشده است.

راهنمای custom classes همچنان answer-linked و fixture-only است؛ برای بهتر
کردن جواب یا نمره وارد index نمی‌شود. نتیجهٔ بدون guide و دارای guide، دو شرط
شواهد متفاوت‌اند. معیار قبلی، gold و خروجی‌های شکست‌خورده حفظ می‌شوند.

## چه اصلاح مستقلی برای freeze لازم بود؟

metadata قدیمی `LiveEvaluationAdapters.config` همهٔ flagها، token limitها و
هویت vocabulary را ثبت نمی‌کند. دو تنظیم متفاوت می‌توانند metadata یکسانی
داشته باشند. آن metadata تاریخی و allowlist runner را بازنویسی نمی‌کنیم؛ مسیر
جداگانهٔ descriptor و مقایسهٔ تنظیم پیشنهادی، این تفاوت را صریح و قابل بررسی
می‌کند. این fingerprint به معنی تأیید کیفیت، احراز runtime یا مجوز live نیست.

descriptor فقط تنظیم و pinهای **صریحاً داده‌شدهٔ caller** را بررسی می‌کند؛
کلید API، env، index، provider یا ledger را نمی‌خواند. hash درست، اثبات وجود
فایل، commit یا سازگاری سرورِ درحال‌اجرا نیست. مرحلهٔ اتصال نهایی باید descriptor
همان تنظیم واقعی را پیش از ساخت runtime با نسخهٔ ثبت‌شده مقایسه کند.
کامل‌بودن مجموعهٔ source pinها نیز احراز نمی‌شود؛ انتخاب و مشاهدهٔ تمام
فایل‌های مؤثر، مسئولیت caller و review نهایی است.

API داخلی در
[`configuration_freeze.py`](../src/agent_app/orchestration/configuration_freeze.py)
است: `describe_candidate_configuration` و `compare_candidate_configuration`.
اولی همهٔ فیلدهای غیرمحرمانهٔ `MetisConfig`، policy جداگانهٔ adapter و engine،
scope caller و override profile، display flagها، limits، vocabulary و pinها
را bind می‌کند. دومی schema، hash و سازگاری همین declaration را دوباره بررسی
می‌کند. اضافه‌شدن فیلدی که هنوز پشتیبانی نشده، به‌جای حذف بی‌صدا رد می‌شود.

```python
from agent_app.orchestration.configuration_freeze import (
    describe_candidate_configuration,
    compare_candidate_configuration,
)

# reviewed_arguments را caller از تنظیم‌های بازبینی‌شدهٔ همان composition
# می‌سازد؛ مثال مصنوعی تست‌ها، تنظیم نهایی تیم نیست.
candidate = describe_candidate_configuration(**reviewed_arguments)
check = compare_candidate_configuration(registered_descriptor, candidate)
if not check["accepted"]:
    raise ValueError("CandidateConfigurationMismatch")
```

پارامترهای صریح شامل `config`، `retrieval_profile`، `adapter_top_k`، `caller`،
`caller_evidence_scope`، `engine_top_k`، `run_limits`، `proposal_checks`، دو flag
نمایش، `user_gaps`، `snapshot_id`، `index_manifest_sha256`، `code_commit` و
`source_sha256` هستند؛ `vocabulary_raw_sha256` اختیاری است. hash raw فایل صرفاً
pin اعلام‌شده است؛ تعریف‌های واقعی vocabulary جدا در hash معنایی bind می‌شوند.

دو composition موجودِ `memory_api` و `persistent_service` پشتیبانی می‌شوند؛
این API مسیرهای بستهٔ آزمایشی را ثبت یا مجاز نمی‌کند. native می‌تواند cap
adapter متفاوتی با engine داشته باشد؛ profile کاندیدا به top-kپنج نیاز دارد
و policy ثابت خودش را اعمال می‌کند. هزینهٔ مورد نیاز برای bounds نیز با نرخ‌های
محلی موجود و حساب Decimal مستقل از precision/rounding caller بررسی می‌شود؛
این، بررسی موجودی ledger یا نرخ/صورتحساب به‌روز provider نیست.

خروجی حتی در مقایسهٔ پذیرفته‌شده، `runtime_verified=false`،
`live_authorization=false` و `quality_claim=false` دارد. تغییر کلید API،
fingerprint را عوض نمی‌کند؛ خود کلید نه خوانده، نه hash و نه صادر می‌شود.
قبولی صرفاً سازگاری و برابری همین ورودی‌هاست. در factory/runner hook تازه‌ای
فعال نشده؛ caller باید مقایسه را صریحاً استفاده کند و guardهای هزینهٔ موجود
همچنان مستقل اجرا شوند. هیچ candidate به‌عنوان تنظیم نهایی انتخاب نشده است.

## شرط‌های باقی‌ماندهٔ freeze

### بازخورد تکمیلی محمدحسن دربارهٔ ارجاع و CRLF

سه متن escalation اصلی C4g با۲۸۶۴،۳۳۰۲ و۱۹۶۷کاراکتر بررسی شدند؛ هر سه
opening و قدم بعدی عمومی مشابه دارند. در requestهای مربوط،۳،۴و۵source
عرضه شده، ولی هیچ citation انتخاب نشده است. پس «منبعی بازیابی نشده» برداشت
درستی نیست. نمرهٔ انسانی همان است و پشتیبانی ادعاها همچنان unassessed است.

یک یادداشت بررسی مفید باید موضوع فعلی کاربر، منابع عرضه‌شده/انتخاب‌شده،
کمبود صریح و قدم بعدی مشخص را نشان بدهد. ولی انتخاب source اثبات «خواندن»
یا review معنایی آن نیست. مدل فعلی authority کافی برای ساخت فرضیه، دلیل
ناکافی‌بودن هر سند یا نتیجهٔ reproduction ندارد؛ این‌ها به declaration و
review مستقل نیاز دارند. مثلاً تعریف دوبارهٔ Enum یک فرضیه است، نه تشخیص
اثبات‌شده برای نسخهٔ کاربر. شناسهٔ داخلی case هم URL واقعی Issue نیست؛ link
دلخواه از متن کاربر به مرجع معتبر تبدیل نمی‌شود. این نیاز کیفیت باز می‌ماند؛
در اصلاح PR78 هیچ متن فنی یا فرضیهٔ تازه‌ای به renderer اضافه نشده است.

در دو متن Enum، کد اصلی۱۶CRLF دارد و تکرار message/fact آن را به۳۲نشانگر
قابل‌دیدن `\\u000d` در هر draft تبدیل کرده است؛ خطای JSON مدل نیست.
آزمایش قدیمی normalization فقط۴از۱۶digest معتبرِ سطح `maintainer_summary`
را عوض می‌کرد؛ این شمارش شامل همهٔ خروجی‌های تاریخی نیست. renderer فعلی
حفظ می‌شود. revision بعدی باید baseline جدا، بازسازی سؤال‌های قدیمی در
route، escape کنترل/HTML/Markdown، کد کامل و حفظ approval/handoffهای ذخیره‌شده
را بررسی کند. در این task renderer جدید یا بهبود readability اندازه‌گیری‌شده
منتشر نشده است.

### مسئولیت‌های باقی‌مانده

- core: ثبت دقیق model/mode/prompt، flagها، bounds، policy نسخه/retrieval،
  vocabulary و pinها؛ descriptor پیشنهادی بدون انتخابِ برندهٔ ادعایی کیفیت.
- محمدحسن: review مستقل تمام ادعاها، پوشش بدنه و caveat، سؤال لازم و usefulness
  روی **تنظیم انتخاب‌شده**؛ native fixture/gold/routes و rubric/vocabulary نهایی.
  worksheetهای موجود استفاده شوند؛ نمرهٔ دستیار جای نمرهٔ انسان نرود.
- حسن: corpus/index/build و exclusion نهایی و شواهد واقعاً رسیده به مدل؛
  نتیجهٔ fixture به کیفیت retrieval واقعی تبدیل نشود.
- ساسان و صاحب حساب mentor: مدرک provider برای سه درخواست نامعلوم C5.
  `halt` و holdها تا آن زمان محفوظ‌اند؛ موجودی کلی حساب کافی نیست.

پس از انتخاب و ثبت تنظیم، test نهایی با مالک evaluation و بدون tuning اجرا
می‌شود. حل‌نشدن Enum باید در گزارش بماند؛ خروجی محافظه‌کارانه هم بدون داوری
به‌عنوان «حل مسئله» شمرده نمی‌شود. هیچ پیام تیمی از این task ارسال نشده است.
