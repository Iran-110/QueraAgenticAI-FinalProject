# C2k — بررسی ورودی core پیش از serialize

این اصلاح ادامهٔ C2j است: همان validator بازگشتی موجود را در چند مرز داخلی
باقی‌مانده به‌کار می‌برد. قرارداد، prompt، renderer، پیش‌فرض مدل و اختیار اجرا
تغییر نکرده‌اند. هدف، رد ورودی نامعتبر است؛ بهبود کیفیت پاسخ مدل ادعا نمی‌شود.

## مشکل واقعی چه بود؟

نوع Python به‌تنهایی اعتبار داده را تضمین نمی‌کند. adapter می‌تواند با
`model_copy` یا `model_construct` یک شیء Pydantic نامعتبر برگرداند. قبلاً در
این مرزها، `model_dump` پیش از بررسی کامل اجرا می‌شد و بعضی extraها و metadata
خصوصی را بی‌صدا حذف می‌کرد. همچنین Mapping می‌توانست `EvidenceHit`، `Fact` یا
`EvidenceLink` دست‌ساز داشته باشد؛ نمونه‌های hidden state تا مرز اصلی حفظ و
بررسی نمی‌شدند. بعضی declared fieldهای نامعتبر در Fact/Link خروجی reasoner
نیز از validation معمولی می‌گذشتند.

برای نمونه، یک Mapping با `EvidenceHit` دارای metadata خصوصیِ نامعتبر از مرز
retrieval می‌گذشت. اکنون پیش از هر تلاش reasoning با `RetrievalResultInvalid`
رد می‌شود. URL یا excerpt نامعتبرِ همان hit از قبل در مرحلهٔ ثبت round رد
می‌شد؛ آن سه regression کنترلِ رفتار قبلی‌اند، نه بهبود تازه. این بازتولید
آفلاینِ مرز درون Python است؛ اجرای snippet، سوءاستفاده
از HTTP یا اجرای بدون approval مشاهده نشده است.

| مرز اصلاح‌شده | رفتار نامعتبر |
| --- | --- |
| خروجی retrieval، مدل یا Mapping | رد پیش از فراخوانی reasoner؛ صفر تلاش مدل |
| خروجی `AnalysisResult`، مدل یا Mapping | diagnostic مجاز؛ repair فقط در سقف دو تلاش قبلی |
| `propose_user_turn` | رد پیش از تولید transition؛ اطلاعات ورودی تغییر نمی‌کند |
| ساخت و validation درخواست grounded/claim و hash منبع | رد snapshot نامعتبر، بدون پاک‌کردن فیلد برای معتبر جلوه‌دادن آن |

`detached_contract`، shared contractها و adapterهای اعضای تیم تغییر نکرده‌اند.
Mapping معتبر و JSON معتبر همچنان پذیرفته می‌شوند. خطاهای معمول declared field
در parser همان diagnosticهای قبلی را دارند؛ hidden state با کد ثابت و بدون
نام/متن فیلد ناشناخته رد می‌شود. نسخه، scope منابع، revision، canonical question،
binding فعلی، terminal stop و approval/retry همان قواعد قبلی را دارند.

## شواهد قبل و بعد

سه مجموعهٔ regression پیش از اصلاح مرز مربوطه اجرا شدند:

| مجموعه | کد قبلی | پس از اصلاح |
| --- | --- | --- |
| خروجی retrieval/reasoner | ۲۹fail،۲۲pass | ۵۱pass |
| درخواست grounded/claim و hash منبع | ۸۴fail،۱۰pass | ۹۴pass |
| ورودی transition کاربر | ۱۲fail،۱۲pass | ۲۴pass |

این‌ها ۱۶۹ کنترل software برای یک خانوادهٔ خطا هستند؛ ۱۲۵ ضعف مستقل یا امتیاز
کیفیت پاسخ نیستند. ۳۲ digest پیش از تغییر ثبت شد: چهار خروجی parser، یک اجرای
کامل engine، هشت transition و۱۹سطح کامل request/messages/render. همهٔ این
خروجی‌های معتبر دقیقاً ثابت‌اند. تست‌های قبلی C2j/C4k/C4l نیز حفظ شده‌اند.

[رسید verification و review](receipts/core-boundary-validation-2026-10-16.json)
شاهد suite توسعه، HTTP/SQLite، حفظ ledger/pinها و محدودیت‌هاست. دستور متمرکز:

```bash
uv run pytest tests/test_reasoning_boundary_detachment.py \
  tests/test_grounding_boundary_detachment.py tests/test_turn_boundary_detachment.py
```

suite توسعه طبق AGENTS یک مصرف‌کنندهٔ محتوای held-out را صریحاً deselect می‌کند؛
این اجرای test نهایی مدل نیست. halt و سه hold هزینه محفوظ‌اند؛ API تازه‌ای
فراخوانی نشده و corpus/index/exclusion یا محتوای test تغییر نکرده‌اند.

## چه چیزی هنوز باقی است؟

این تحویل تمام مرزهای Python را بی‌نقص اعلام نمی‌کند. در بعضی ورودی‌های typed
planner، context و configuration هنوز serialization پیش از revalidation وجود
دارد؛ probe خنثی در آن‌ها تغییر declared decision، متن، digest یا اختیار اجرا
نشان نداد. گسترش این اصلاح به آن‌ها نیاز به review جداگانهٔ diagnostic و
compatibility دارد؛ برای deadline flag یا بازنویسی parser اضافه نشده است.

برای کیفیت واقعی هنوز review انسانی relevance، کامل‌بودن شواهد و usefulness،
انتخاب/freeze تنظیم‌های نهایی و اجرای ارزیابی بدون tuning لازم است. C5 نیز
به شواهد usage/charge از حساب mentor نیاز دارد؛ حساب شخصی یا موجودی کلی جای
تطبیق سه درخواست نامعلوم را نمی‌گیرد. این اصلاح هیچ‌یک از آن gateها را نمی‌بندد.
