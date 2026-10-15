# C4h7 — پایداری JSON و نمایش کوتاه‌تر

دو گزینهٔ مستقل، خاموش به‌صورت پیش‌فرض، اضافه شده‌اند. معماری تک agent،
قرارداد عمومی، corpus، exclusion و نسخهٔ index عوض نشده‌اند.

## تنظیم و رفتار واقعی

`METIS_GROUNDED_JSON_OBJECT=true` فقط در `grounded_plan` مجاز است. gateway
فقط `response_format={"type":"json_object"}` را اضافه می‌کند؛ prompt، مدل،
سقف خروجی، هویت request، validator و محدودیت دو attempt همان قبلی‌اند.
`false` پارامتر را کاملاً حذف می‌کند. مقدار غیر از `true`/`false` رد می‌شود.
نه JSON ناقص salvage می‌شود، نه خطای binding قابل repair می‌شود و نه درخواست
ردشده با تنظیم دیگری تکرار می‌شود. HTTP ناموفق همچنان terminal و هزینهٔ نامعلوم
همچنان hold است؛ این گزینه مجوز عبور از ledger نیست.

[مستند OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat)
JSON object را از تضمین schema جدا می‌کند. [مستند wrapper متیس](https://docs.metisai.ir/api/wrapper/openai/)
پوشش کامل قابلیت‌ها را تضمین نمی‌کند؛ برای همین ابتدا canary محدود ثبت و اجرا شد.
پاسخ۲۰۰ و JSON معتبر، مشاهدهٔ سازگاری همین درخواست‌هاست؛ اثبات enforcement
پارامتر در همهٔ مسیرهای درگاه یا پشتیبانی strict Structured Outputs نیست.

`AGENT_GROUNDED_CONCISE_USER_DRAFT=true` به
`concise_user_draft=True` در renderer و `GroundedReasoner` وصل می‌شود:

- در سؤال تکمیلی واجد شرایطِ [question background](ask-source-background.fa.md)،
  سؤال canonical جلو می‌ماند و فهرست منبع/نسخه/ارجاع می‌آید. متن کامل منابع
  در summary نگه‌دارنده حفظ می‌شود؛ فهرست منبع، توضیح فنی API محسوب نمی‌شود.
- پاسخ‌ها تمام نقل‌قول‌های کامل خود را حفظ می‌کنند. فقط تکرار گزارش، کد و factهای
  کاربر در بخش investigation از draft حذف و با نسخهٔ فعال USER و وضعیت پیشنهادی
  بررسی جایگزین می‌شود. همان اطلاعات کامل در summary باقی است.
- تصمیم، سؤال، missing_info، source record و evidence linkها عوض نمی‌شوند.
  تنها استثنا در rationale، یک جملهٔ ثابت دربارهٔ محل نمایش گزارش است تا متن
  به‌درستی بگوید گزارش کامل در summary و نسخه/وضعیت در draft است.
- سؤال نسخه/نسخهٔ نامعلوم دقیقاً متن قبلی را دارد. تضاد فعلی یا باقی‌مانده،
  منبع تاریخی و نسخهٔ حدس‌زده اجازهٔ background نمی‌دهند. رکورد یا quote بریده
  نمی‌شود؛ اگر کل افزودهٔ سؤال جا نشود، همان سؤال تنها حفظ می‌شود.

هر دو تنظیم trusted اپراتورند؛ پیام کاربر و مدل نمی‌توانند انتخابشان کنند.
adapter ID غیرپیش‌فرض suffix جدا دارد. runner برای ادامهٔ سؤال، draft کامل را
از handoff معتبر و همین تنظیم بازسازی می‌کند؛ داشتن prefix سؤال کافی نیست.
همان متن دقیق به approval case/revision/proposal مقید است. HTTP/SQLite با
provider ماک، correction، stale approval، restart و retry هر دو گزینه را پوشش می‌دهد.
startup معمول live همچنان به‌خاطر halt و holdهای قبلی متوقف است.

## نتیجهٔ آزمایش ثبت‌شده

[protocol](../experiments/core_json_readability_v1/protocol-v1.json) پیش از کد و
[method ثابت](../experiments/core_json_readability_v1/live-method-v1.json) پیش از
API ثبت شدند. همان سه dev exposed/answer-informed و index محدود۱۸source/۳۶chunk
با embedding محلی `lexical_hash_v1` استفاده شدند؛ test مستقل یا corpus نهایی نیست.
نه پاسخ Issue و duplicateهای ارزیابی به corpus اضافه شد، نه gold عوض شد.

canary دو نوبت جدا داشت و تمام gateها را پاس کرد. سپس دو دور با ترتیب متوازن
JSON OFF/ON، دوازده job و۲۴نوبت اجرا شدند. در هر دو حالت نمایش کوتاه روشن بود؛
مقایسهٔ خوانایی، بازپخش محلی همان request/plan با نمایش OFF/ON است و API اضافه ندارد.

| مشاهده | JSON OFF | JSON ON |
| --- | --- | --- |
| خروجی raw معتبر / فراخوانی | ۱۲/۱۲ | ۱۲/۱۲ |
| expansion معتبر | ۱۲/۱۲ | ۱۲/۱۲ |
| پیشنهاد تازه / نوبت برنامه‌ریزی‌شده | ۱۲/۱۲ | ۱۲/۱۲ |
| مسیر عملیاتی کامل / job | ۶/۶ | ۶/۶ |
| label سؤال / پاسخ | ۶ / ۶ | ۶ / ۶ |
| هزینهٔ تخمینی محلی | $0.010622370 | $0.010604550 |

متن raw provider ذخیره نشده؛ اعتبار raw، مشاهدهٔ allowlistشدهٔ gateway هنگام
اجراست و از روی hash دوباره parse نشده است. expansion canonical مستقلاً
بازمحاسبه شده. پس در این نمونه برتری JSON mode ثابت نشد؛ انتخاب منبع و پشتیبانی ادعا با
فرمت JSON یکی نیست. هر۲۶فراخوانی شامل canary settled شدند، کل هزینه
$0.023094885؛ هیچ خطای transport/schema یا hold/pending تازه ثبت نشد. هر۲۶نوبت حفظ شدند.
۵۴۶۶بازمحاسبهٔ خواندنی هزینه/index/metadata/binding پاس است؛ auditor در
پیاده‌سازی/تست همین آزمایش هم مشارکت داشته و داور مستقل انسانی نیست. تمام۴۹۳reservation قبلی
و۱۴جدول، halt، holdهای$0.0233792 و سقف$4.50 حفظ شدند. هزینهٔ تجمعی محلی
$0.426751215 است. هفت scope بسته‌اند؛۲۶slot مصرف‌نشده دائماً claimed هستند.
روش بسته را دوباره اجرا یا هویت‌هایش را جایگزین نکنید.

در بازپخش همان plan، سؤال callback از۷۸۷۰به۱۲۲۰کاراکتر رسید؛ مدارک reviewer
کامل ماندند ولی passageهای API دیگر در متن سؤال منتشر نمی‌شوند. پاسخ button
۴۹۹۹کاراکتر و نقل‌قول icon را حفظ کرد. پاسخ عمومی Enum با دو منبع
از۱۲۲۷۴به۱۰۶۱۲رسید؛ هنوز طولانی است و علت/راه‌حل Enum را ثابت نمی‌کند.
review دستیار با مشارکت در پیاده‌سازی، همهٔ۲۶نوبت/۲۲متن منتشرشدهٔ اصلی/صفرedit
را دید:۴۵نقل‌قول کامل و۱۴سؤال ضروری، بدون ادعای مادی بی‌پشتوانه در این review.
هر۴correction نسخهٔ فعال۱.۳۱.۱ و رد approval قدیمی۴۰۹ را حفظ کردند. در۳از۴summary
اولیهٔ B اسناد جانبی state انتخاب شده‌اند؛ precision کامل نیست. برچسب answer
یا کامل‌شدن route به معنی حل مسئله نیست. داوری usefulness انسانی
هنوز null است؛ این گزینه‌ها به‌عنوان پیش‌فرض بهتر promote نشده‌اند.

[بستهٔ شواهد و review](../experiments/core_json_readability_v1/README.md)،
[verification](../experiments/core_json_readability_v1/verification-v1.json) و
[plan](../plan/plan.md) مبنای ادامه‌اند. ۴۵۰۶pytest، Ruff، سه demo و پذیرش
fixture HTTP/SQLite۴۵۷/۴۵۷ محلی پاس‌اند. GitHub Actions به‌علت Billing اجرا نشده؛
انتشار بر اساس review و مجوز verification محلی است، بدون ادعای CI سبز یا
تست تازهٔ Windows/مرورگر/live SQLite.
