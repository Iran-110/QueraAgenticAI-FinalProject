# سه dev case و baseline محدود core — ۱۴ اکتبر ۲۰۲۶

این packet کمک مستقل ساسان به E1/E2 است؛ سه خانوادهٔ dev و صفر test دارد.
fixture، مسیر پاسخ شرطی، known/unknown و oracle قبل از مدل ثبت می‌شوند.
شماره‌های Issue فقط در metadata ارزیاب هستند؛ runtime case IDها opaque اند.
هیچ داوری انسانی یا ادعای تکمیل split نهایی در این تحویل نیست.

| پرونده | ورودی و ادامه | تصمیم قابل دفاع |
| --- | --- | --- |
| #12782، خانوادهٔ #12629 | multiselect/fragment؛ نسخه نامعلوم، reduction کار می‌کند؛ پاسخ نسخهٔ تألیفی 1.50.0 فقط پس از سؤال canonical | سؤال نسخه یا callback/ترتیب state؛ پاسخ مستند صرفاً با حدود منبع؛ علت/fix اثبات نشده |
| #9770 | درخواست تصویر برای icon؛ نسخه نامعلوم؛ پاسخ تألیفی 1.39.0 | قابلیت button فقط طبق docstring همان نسخه؛ وضعیت feature و warning از این منبع معلوم نیست |
| #8129، closure محافظه‌کارانهٔ #2379/#8180 | نسخهٔ 1.31.0 و کد کامل Enum معلوم؛ correction تألیفی 1.31.1 | کمبود مستندات علت/fix، نه کمبود اطلاعات کاربر؛ سؤال تکراری نسخه/کد لازم نیست |

متن اولیه paraphrase از body cached است؛ chronology اولیهٔ واقعی تأیید نشده.
comment/outcome برای شناخت case خوانده شده‌اند و این exposure/answer-informed
در [گزارش](../data/evaluation/dev-three-v1/exposure-review-v1.json) ثبت است.
راهنمای مستقیم حل Enum به evidence/corpus نمی‌رود. duplicate خارجی هنوز
بازبینی انسانی ندارد. این‌ها هیچ‌وقت held-out test محسوب نمی‌شوند.

## استفاده و manifest

[manifest تازه](../data/evaluation/dev-three-v1/split-manifest.json) مسیر جاری
این آزمایش است و `draft_not_frozen` می‌ماند. manifest تاریخیِ pilot و PR35
byte-identical حفظ‌اند. افزودن case، سند جدید وارد index نمی‌کند؛ index و
snapshot تازه باید با مسیر manifest و pin صریح ساخته و وصل شوند.

از ریشهٔ repository:

```bash
uv run python -m agent_app.evaluation.runner data/evaluation/dev-three-v1/cases --conditional-routes
uv run python scripts/dev_three_index_acceptance.py --help
uv run python scripts/dev_three_model_probe.py
```

دستور اول scripted و آفلاین است. دستور مدل در حالت پیش‌فرض فقط preflight
بدون credential/send می‌کند؛ پس از تغییر ledger، registration تاریخی دوباره
eligible نمی‌شود. receiptها overwrite و grantها refill نمی‌شوند.

## دو شرط شواهد جدا

پذیرش index با Chroma/adapter واقعی و مدل mock روی همان ۱۴ docs/۳۰ chunk
انجام می‌شود؛ Issue/comment/outcome داخل corpus نیست. منابع دقیق 1.31 و
1.39 و fragment/multiselect مخصوص fixture در این index موجود نیستند.
receipt index کیفیت semantic retrieval را اندازه نمی‌گیرد.

مقایسهٔ مدل **شواهد ثابت** خود fixture را مصرف می‌کند: همین case/message/
bundle در دو arm؛ A catalog معمول، B vocabulary دو سؤال neutral برای
callback و ترتیب state. سؤالِ تکرار availability نمونهٔ خراب اضافه نشده،
چون کاربر قبلاً گفته reduction کار می‌کند و نمونهٔ failing ندارد.
انتخاب route به سؤال واقعی released وابسته است؛ answer/escalate ممکن است
زودتر مسیر را تمام کند. شش case-arm کامل الزاماً دوازده turn نیست.

## مجوز و حسابداری آزمایش

مجوز تازهٔ کاربر برای API در همین گفتگو، به scope جدید و finite ثبت می‌شود.
حداکثر ۲۴ slot دقیق، شامل repair؛ مدل `gpt-4o-mini`، خروجی ۱۰۲۴ و ورودی
۱۶۳۸۴ یا ۲۴۵۷۶. با نرخ pinشدهٔ ledger، بدترین رزرو $0.091914240 و cap
آزمایش $0.10 است. این مبلغ سقف رزرو است، نه پیش‌بینی مصرف واقعی.

سقف جهانی قبلی $4.50 زیر سقف تیم $5، grant قدیمی، hold نامعلوم $0.02 و halt
عمومی تغییر نمی‌کنند. این exception خاص C5 را reconcile نمی‌کند و factory
معمول همچنان halted است. protocol/slotها immutable؛ replay اعتبار تازه
نمی‌سازد؛ عدم قطعیت یا overrun اجرای ادامه را می‌بندد. پایان آزمایش slotهای
مصرف‌نشده را با event مستقل می‌بندد. هزینهٔ receipt تخمین reasoner است، نه
تطبیق صورتحساب provider یا کل هزینهٔ تیم.

## اتصال کار تیم

- محمدحسن: review مستقل خانواده/chronology، oracle و همهٔ سطح‌های خروجی؛
  adoption همین routeها و vocabulary؛ usefulness انسانی و باقی ۱۵/۱۵ هنوز باز.
- حسن: همین manifest جدید را با مسیر صریح مصرف کند؛ coverage واقعی button
  1.39 و multiselect/fragment را در allowlist/build epoch جدا بیاورد. متن
  PR43 باید با محتوا هماهنگ شود؛ HEAD بدون diff، baseline جدید تحویل نمی‌دهد.
- ساسان: اجرای محدود مدل، claim/source و سؤال ضروری را با reviewer kind
  صریح ثبت کند؛ fixed-evidence را با RAG واقعی یا test نهایی یکی نکند.

نتیجهٔ اجرا و محدودیت‌هایش در
[packet آزمایش](../experiments/dev_three_baseline/README.md) ثبت می‌شود.
