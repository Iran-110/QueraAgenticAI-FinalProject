# انتخاب منابع مکمل و خوانایی Enum — C4h9/C4h9b

این مرحله بهبود پایدار خوانایی را نشان نداد. دو مقایسهٔ محدود با API انجام شد؛
نتیجه‌های منفی هم حفظ شده‌اند و هیچ تنظیمی پیش‌فرض نشده است.

## چه چیزی را مقایسه کردیم؟

همان سه dev دیده‌شده، مدل `gpt-4o-mini` و دو تکرار متوازن را نگه داشتیم.
در هر مقایسه۱۲job،۲۴turn و۲۴send بود. هر دو حالت، منابع کامل یکسان داشتند؛
برای Enum، منبع عمومی Session State و دو بخش کامل راهنمای رسمی در دسترس بودند.
در C4h9 فقط یک دستور عمومی SYSTEM برای انتخاب منابع مکمل اضافه شد. در C4h9b،
prompt مشترک ماند و فقط اولین رکورد کامل به انتهای فهرست رفت؛ این عمل برای
همهٔ caseها انجام شد، بدون شرط روی محتوا، نسخه یا شناسهٔ case/source.

متن guide قبلاً عمداً به‌عنوان answer-linked کنار گذاشته شده بود. فقط supplier
آزمایش آن را می‌دهد؛ سند و aliasهایش وارد corpus واقعی نشدند. هر۱۹فایل محافظت‌شده،
index۱۸source/۳۶chunk، exclusion، caseها و gold اصلی بدون تغییرند.
این آزمایش با شواهد ثابت است؛ کیفیت retrieval واقعی یا test نهایی نیست.

## نتیجهٔ واقعی

| مقایسه | پوشش هر دو بخش کامل در draftهای Enum | در correction واقعاً منتشرشده | خوانایی متن |
| --- | --- | --- | --- |
| C4h9؛ دستور فعلی / دستور مکمل | ۰/۴ / ۰/۴ | ۰/۲ / ۰/۲ | همه۱۴۴۹۴کاراکتر؛ هر۱۲جفت analysis یکسان |
| C4h9b؛ ترتیب اصلی / چرخش یک رکورد | ۰/۴ / ۱/۴ | ۰/۲ / ۰/۲ | فقط یک initial منتشرنشده۷۰۹۹؛ باقی۱۴۴۹۴ |

این چهار draft در هر حالت، دو تکرار از **یک Issue** هستند. initialهای Enum
عمداً approve/release نشدند؛ فقط correctionها منتشر شدند. در یک initial چرخیده،
دو guide کامل با caveat انتخاب شدند، ولی correction همان اجرا دوباره منبع عمومی
و بخش Enum را انتخاب کرد. کاهش طول بدون حفظ پوشش، معیار موفقیت نبود.

مدل صرفاً شمارهٔ source را تکرار نکرد: در سه جفت از چهار جفت Enum، محتوای
انتخاب‌شده ثابت ماند و index/ترتیب quote تغییر کرد؛ در یک جفت محتوا تغییر کرد.
در A با نسخهٔ معلوم نیز انتخاب inventory به ترتیب حساس بود؛ سؤال لازم callback
حفظ شد. B با تک‌منبع تغییر نکرد. این‌ها دلیل کافی برای توصیهٔ ترتیب تازه در
RAG نیستند. این شاخهٔ انتخاب را با همین نتیجه می‌بندیم؛ permutation یا prompt
بعدی برای گرفتن نمرهٔ بهتر اجرا نمی‌کنیم.

منابع مدرن، توضیح مفهومی می‌دهند و اثبات fix برای Streamlit۱٫۳۱ نیستند.
بخش enumCoercion مربوط به خروجی widget است؛ reproduction این case widget ندارد.
نسخه و کد کاربر معلوم‌اند؛ سؤال دوباره دربارهٔ آن‌ها جای کمبود مستندات را نمی‌گیرد.
داوری usefulness انسانی هنوز خالی است؛ review دستیار با پیاده‌سازی/تست هم‌پوشانی دارد.

## رفتار کد و اتصال

`MetisConfig.grounded_complementary_sources` و
`METIS_GROUNDED_COMPLEMENTARY_SOURCES`، boolean سخت‌گیرانه و پیش‌فرض `false`
دارند. فعال‌سازی به `grounded_source_selection_reminder` نیاز دارد. فقط suffix ثابت
SYSTEM اضافه می‌شود؛ USER/evidence/schema و renderer ثابت‌اند. factory و runner
تنظیم معتبر را عبور می‌دهند و adapter ID حالت روشن را مشخص می‌کند. این flag
برای بازتولید آزمایش نگه داشته شده؛ **به‌عنوان بهبود کیفیت توصیه نمی‌شود**.

چرخش منابع فقط در `agent_app.testing.source_order` است؛ flag محصول یا تغییر
ranking نیست. بعد از چرخش، context و mapping indexها دوباره ساخته می‌شوند.
context قدیمی رد می‌شود؛ عدد index با context تازه به موقعیت فعلی اشاره می‌کند،
پس تکرار عدد به‌تنهایی به معنی تکرار محتوای انتخاب‌شده نیست.
قراردادها، UI/tracker، proposal/approval، revision و حد دو تلاش تغییر نکرده‌اند.

## شواهد و ادامهٔ کار

۴۸۹۶pytest،Ruff۳۲۹فایل،سهdemo و پذیرش fixtureHTTP/SQLite۴۵۷/۴۵۷ محلی پاس‌اند.
تست‌های provider ماک، repair،correction،approval قدیمی،restart وretry را پوشش
می‌دهند؛ مقایسهٔ paid از runner حافظه‌ای/gateway بود، نه اجرای تازهٔ مرورگر یا
paidSQLite. مجموع۴۸send این مرحله تخمین$0.032036400 هزینه داشت؛ تخمین تجمعی
ledger محلی$0.473438955 است و$0.0233792hold قدیمی دست‌نخورده مانده.
این اعداد صورتحساب تأییدشده یا مجموع لپ‌تاپ‌های تیم نیستند. CI به علت Billing
اجرا نشده؛ انتشار بر اساس review و تست محلی مجازشده است.

- [C4h9؛ protocol، روش، receipt، review و هزینه](../experiments/core_complementary_sources_v1/README.md).
- [C4h9b؛ protocol، روش، receipt، review و هزینه](../experiments/core_source_order_v1/README.md).
- worksheetهای بدون نمره در هر دو packet، با نسخهٔ فعال و initial/released جدا،
  برای review انسانی آماده‌اند. نمرهٔ دستیار به‌عنوان نمرهٔ انسان کپی نشود.
- کار باقی‌مانده، review خوانایی و کفایت پوشش توسط محمدحسن، dev گسترده‌تر و
  freeze تنظیمات پیش از test است. حسن همچنان مالک relevance/provenance و
  exclusion corpus واقعی است؛ این آزمایش تغییر branch او نیست.

برای بازتولید آفلاین، خروجی تازه انتخاب کنید:

```bash
uv run python -m agent_app.testing.complementary_replay --output /tmp/complementary-replay-new.json
uv run python -m agent_app.testing.source_order --output /tmp/source-order-replay-new.json
```

این replayها انتخاب‌های authored را هم بررسی می‌کنند؛ انتخاب دستی دو guide
می‌تواند۷۰۹۹کاراکتر شود، ولی شاهد بهبود خودکار مدل نیست. روش‌های paid بسته‌اند؛
شناسه‌ها و slotهای آن‌ها دوباره استفاده نمی‌شوند. holdها، halt و سقف ledger حفظ‌اند.
