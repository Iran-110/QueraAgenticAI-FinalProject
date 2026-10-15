# اتصال اطلاعات کاربر به core — pilot آفلاین C2 / P2

به‌روزرسانی C2j در۱۶اکتبر: [validation پیش از dump](intake-validation.fa.md)
در helperهای pending/approved اعمال شد؛ خروجی‌های معتبر ثبت‌شده ثابت‌اند.
نتایج milestone زیر تاریخی‌اند؛ receiptها و fixtureهای اولیه حفظ شده‌اند.

این milestone ورودی HTTP را به همان `UserTurn` و transition موجود وصل می‌کند.
متن آزاد fact تأییدشده نمی‌شود؛ UI باید اطلاعاتی را که کاربر صریحاً گفته در
`reported_facts`، نتیجهٔ بررسی را در `checks_performed` و تغییر محیط را در
`context_changed` بفرستد. withdrawal با `value: null` است.

## دو تغییر و مقایسه با baseline

| تغییر | مشکل روی `main` در `5af98e6` | رفتار جدید |
| --- | --- | --- |
| اتصال structured event | API فیلدهای fact، event ID و revision را نادیده می‌گرفت؛ فقط متن به core می‌رسید | validation قبل از mutation؛ attribution کاربر؛ correction/withdrawal و invalidation با helper موجود |
| اتصال پاسخ به سؤال تأییدشده و replay | approval، pending ID را پاک می‌کرد؛ جواب کوتاه به سؤال وصل نبود؛ retry پیام دوباره run می‌ساخت | record جدا برای سؤال نمایش‌داده‌شده؛ original hash پیش از stale/preparation؛ هر event فقط یک revision/run در همین process |

چهار regression روی کد Git قبلی **۰ پاس / ۴ fail** و روی adapter جدید
**۴ پاس / ۰ fail** شدند: ورود fact با provenance کاربر، رد revision قدیمی،
replay بدون اجرای دوباره، و رد فیلدهای جعلی authority قبل از ساخت پرونده.
[baseline اولیه](../experiments/user_intake/baseline.json) حفظ شده؛
[بازپخش جدا روی Git قبلی](../experiments/user_intake/baseline-recheck.json)
تغییر جزئی assertion مربوط به replay را هم توضیح می‌دهد. این عدد رفتار نرم‌افزار
را می‌سنجد؛ امتیاز تصمیم مدل یا کیفیت پاسخ نیست.

## case چندمرحله‌ای و چیزی که واقعاً بررسی شد

[fixture](../experiments/user_intake/case-widget-version-correction.json) در commit
`a3d5eeb`، پیش از replay ثبت شد. anchor آن Issue #12782 است؛ ادامهٔ گفتگو و
reasoner را توسعه‌دهنده نوشته است. انتخاب case از مطالعهٔ workaround و commentها
اثر گرفته و **answer-informed** است؛ جواب Issue وارد evidence نشده. پنج hit رسمی
از fixture منجمد V8 با commit و source span ثابت استفاده شده‌اند. این خانواده و
duplicate #12629 برای RAG و final test مجاز نیستند؛ حذف واقعی در index با حسن است.

برای هر turn، اطلاعات معلوم، gap قابل پاسخ توسط کاربر، کمبود منبع و تصمیم‌های
قابل قبول پیش از اجرا در `inventory` ثبت شده‌اند. این اطلاعات و انتظارها ورودی
reasoner نیستند. فقط CaseState جاری، پیام همان نوبت و EvidenceBundle ثابت به
port می‌رسند؛ continuationهای بعدی زودتر آشکار نمی‌شوند.

| Turn | انتظار بررسی‌شده |
| --- | --- |
| ۱ | نسخه نامعلوم است؛ سؤال canonical قبل از approval به کاربر ارسال نمی‌شود |
| ۲ | جواب `1.50.0` فقط با ID دقیق سؤال تأییدشده به fact کاربر تبدیل می‌شود |
| ۳ | correction به `1.49.1` نسخهٔ قبلی را superseded، inference/ref قبلی را غیرفعال و approval قبلی را نامعتبر می‌کند |
| ۴ | withdrawal نسخه را unknown می‌کند؛ مقدار تازه حدس زده نمی‌شود |
| ۵ | محیط جدید فقط factهای reconfirmed را فعال نگه می‌دارد؛ Python و سایر factهای محیط قبلی تاریخچه‌اند |
| ۶ | check جدید، inference/ref قبلی را کنار می‌گذارد و نسخهٔ کاربر را حفظ می‌کند |
| ۷ | تکرار normalized همان check، inference/ref مربوط به precondition جدید را حفظ می‌کند؛ event جدید revision را یک واحد بالا می‌برد |

در replay، **۷ turn، ۷ retrieval call و ۷ reasoning call** انجام شد؛ ۳ seed
کنترل‌شده برای اثبات transition، ۲ بررسی نقل کامل source و ۳ نمایش تأییدشده
ثبت شدند. همهٔ seedها در receipt با هدف و revision مشخص‌اند؛ API خروجی
`facts_delta` مدل را ذخیره نمی‌کند. eventهای تکراری call اضافه ندارند؛ content
تغییریافته با همان ID conflict است. approval قدیمی و approval دوم رد می‌شوند.
این بررسی‌ها فقط با storage حافظه‌ای انجام شده‌اند.

پاسخ‌های ثابت turn ۲ و ۵ یک release event را با نقل کامل source توضیح می‌دهند؛
علت خطا یا fix برنامهٔ ندیده را ادعا نمی‌کنند. سند 1.49.0 یا 1.50.0، پوشش patch
1.49.1 را اثبات نمی‌کند. سؤال callback را کاربر می‌تواند پاسخ بدهد؛ نبود پوشش
مستندات آن patch، کمبود retrieval است و با سؤال تکراری نسخه حل نمی‌شود.
وجود citation به‌تنهایی entailment معنایی را ثابت نمی‌کند.

pool ثابت همچنان سندهای چند نسخه دارد؛ هدف این pilot حفظ current user state و
کنارگذاری استنتاج‌های قبلی است. قرار نیست همهٔ سندهای تاریخی از retrieval حذف
شوند. کاربرد نسخهٔ هر source باید در پاسخ/review مشخص باشد؛ فیلتر اختیاری
`exact_user_version` تغییر جداگانه‌ای است و پیش‌فرض این API نشده است.

## بازپخش و بررسی

از root ریپو:

```bash
uv sync --locked --group dev
uv run python experiments/user_intake/replay.py
uv run python experiments/user_intake/replay.py --output /tmp/user-intake-review.json
uv run pytest -q tests/test_api_user_intake.py tests/test_api_ingress_guards.py tests/test_approved_reply_intake.py tests/test_user_intake_pilot.py
```

runner فایل موجود را overwrite نمی‌کند. UUID ثابت فقط داخل fixture اعمال می‌شود
تا hash واقعی ingress و receipt قابل تکرار باشد؛ runtime همچنان UUID تازه می‌سازد.
[receipt](../experiments/user_intake/results-user-intake-v1.json) جزئیات state،
proposal، approval، replay و ورودی‌های واقعی port را نگه می‌دارد.
receipt قدیمی V9 هم دست‌نخورده مانده؛ بازپخش فعلی همهٔ نتایج رفتاری‌اش را با آن
برابر می‌خواهد و فقط تفاوت fingerprint کد به‌خاطر قرارداد جدید را جدا ثبت می‌کند.

بررسی نهایی: **۱۵۲۹ pytest پاس**، Ruff lint/format و ۱۶ دستور آفلاین موجود CI
شامل validation پروتکل‌ها، replayهای V8/V9 و سه دمو پاس شدند. pilot جدید هم
به CI اضافه شد. ۱۰۱ تست تازه مربوط به این مرزهاست؛ تعداد تست، تعداد case مستقل
یا کیفیت تصمیم مدل محسوب نمی‌شود. یک warning موجود Starlette/httpx باقی است.
receipt، SHA فایل‌های کد و `uv.lock`، نسخهٔ Python/dependencyها و hash شواهد را
ثبت می‌کند؛ تغییر source حین اجرا یا Python با `-O` اجازهٔ گزارش موفقیت نمی‌دهد.

## ورودی/خروجی لازم برای اتصال تیم

| مسئول | کار مشخص بعدی | قرارداد آماده |
| --- | --- | --- |
| محمدحسن — U2 | UI، stable event ID را یک‌بار بسازد و همان payload را retry کند؛ fact/correction/check و تغییر محیط را صریح بفرستد؛ 409 را با refresh حل کند | [wire نمونه، error و receipt](user-turns.md#additive-offline-http-ingress)؛ `awaiting_reply` و facts با active/superseded |
| بهنام — T1/T2/T3 | state/event/hash/prepared transition و سؤال تأییدشده را در transaction پایدار نگه دارد؛ reviewer، CAS، outcome و recovery/restart را enforce کند | `UserTurn`، `CaseTransition`، `ApprovedReplyQuestion`؛ lookup اصل event پیش از stale و preparation |
| حسن — P4/R3 | EvidenceBundle همان snapshot را بدهد؛ scope/commit/source span مشخص؛ خانواده‌های evaluation از index کنار بمانند | `Retriever.search(RetrievalRequest)`؛ fixture ثابت فعلی تا آماده‌شدن adapter واقعی |
| محمدحسن — E1/E2/E3 | split مستقل و fixture/rubric/runner evaluation را freeze کند | این pack یک نمونهٔ **dev و exposed** است؛ دادهٔ gold یا test مستقل نیست |

تست و مثال اتصال سهم core انجام شده؛ کنترل‌های UI و tracker پایدار هنوز شرط
بسته‌شدن کامل C2 هستند. ساختار تک agent حفظ شد و هیچ framework تازه‌ای لازم نبود.
هزینهٔ API **صفر** است؛ کلید و ledger استفاده نشدند. halted ledger حل نشده و
پاس شدن این pilot، کیفیت مدل/RAG، اجرای fix، دوام approval پس از restart یا
موفقیت test نهایی را ثابت نمی‌کند.
