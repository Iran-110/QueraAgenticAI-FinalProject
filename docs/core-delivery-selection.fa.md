# تنظیم منتخب core و اتصال به اجرای واقعی — C4r

تنظیم نرم‌افزاری منتخب `grounded_candidate_v1` در
[فایل تنظیم](../config/core-delivery-grounded-v1.json) ثبت شده است.
این انتخاب، پایان آزمایش featureهای core برای تحویل فعلی است؛ freeze مشترک
corpus/index، داوری انسانی کیفیت و اجرای نهایی همچنان gateهای جدا هستند.
JSON ثبتِ نسخه‌دار recipe است، نه فایل دلخواه برای override؛ عوض کردن این
انتخاب به نسخه و review جدید نیاز دارد.

| بخش | تنظیم منتخب | دلیل |
| --- | --- | --- |
| مدل و تصمیم | `gpt-4o-mini`، `grounded_plan`، prompt پایه | مدل تصمیم/منبع را انتخاب می‌کند؛ renderer متن مستند را می‌سازد |
| prompt | decision contracts، compact plan، source-selection reminder روشن | ترکیب اصلی مسیر ثبت‌شدهٔ C4h5؛ validator و دو تلاش تغییر نمی‌کنند |
| ارجاع | source-gap handoff و investigation روشن | کمبود سند از سؤال قابل‌پاسخ کاربر جدا می‌ماند |
| retrieval | `candidate_relevance_v1`؛ ۲۵ کاندیدا، ۵ رکورد کامل، سقف ۱۲۰۰۰ بایت | scope با نسخهٔ فعال USER اعمال می‌شود؛ حذف/بریدن بخشی از نقل نداریم |
| renderer | `legacy_v1`؛ brief/background/concise خاموش | کیفیت انسانی قالب جدید هنوز بررسی نشده است |
| گزینه‌های کنارگذاشته | JSON-object، resource guidance، source capacity، complementary sources خاموش | بهبود قابل اتکای کافی برای انتخاب این گزینه‌ها ثبت نشده است |
| حدود | input reserve ۳۲۷۶۸، output ۱۰۲۴، سقف هر درخواست ۰٫۰۲ دلار | همان حدود ثبت‌شده؛ سقف کل، halt و holdها مجاز نمی‌شوند |
| سؤال‌ها | `config/user-gap-support-dev-v1.json` | همان vocabulary بازبینی‌شده؛ از test سؤال استخراج نشده است |

شاهد تاریخی C4h5، مسیرهای قابل‌قبول ۵/۶ در برابر ۶/۶ و راهنمای جزئی button در
۰/۲ در برابر ۲/۲ تکرار **یک case آشکار dev** را ثبت می‌کند. این داده انتخاب
یک recipe قابل دفاع را پشتیبانی می‌کند؛ برتری عمومی، حل Enum یا usefulness
ترکیب فعلی با vocabulary جدید را ثابت نمی‌کند. نمره‌های تاریخی منتقل نمی‌شوند.

## اتصال واقعی و استفاده

در تنظیم خصوصی اپراتور، `AGENT_CORE_PROFILE=grounded_candidate_v1` را برای
factory موجود `agent_app.evaluation.live:factory` یا backend موجود
`agent_app.live_backend:app_factory` انتخاب کنید. لازم نیست تک‌تک flagهای جدول
را دوباره بنویسید. تنظیم عمومیِ صریحِ مغایر رد می‌شود؛ index، snapshot، hash
manifest، phase، کلید، live-enable و ledger همان ورودی‌های قبلی‌اند.
این selector کلید نمی‌خواند، فایل `.env` بار نمی‌کند و live را روشن نمی‌کند.

بدون selector، رفتار، defaultها و metadata هفت‌فیلدی قبلی حفظ می‌شود. حالت
منتخب قبل از lookup کلید با `MetisConfig` آماده و catalog واقعی تطبیق می‌یابد؛
سپس پیش از allocation و هر plan، تنظیم owner و planner و sender واقعی، flagهای
renderer و catalog دوباره کنترل می‌شوند. mismatch پیش از ارسال رد می‌شود.
budget/index guardهای اصلی همچنان اجرا می‌شوند. halt فعلی مانع startup واقعی
است؛ انتخاب recipe مجوز رفع halt یا تکرار آزمایش‌های بسته نیست.

`factory.core_binding` یک کپی جداشده از receipt غیرمحرمانه است. هر observation
حالت منتخب همان binding را کنار شناسهٔ درخواست دارد؛ runner فقط metadata با
schema شناخته‌شده و binding سازگار را وارد رسید می‌کند. اطلاعات compact wire
هم فقط hash، شمارش و labelهای مجاز است، نه متن خام مدل یا سؤال/مقادیر ناشناخته.
receipt تنظیم عمومی/catalog را ثبت می‌کند؛ هویت منبع، code/build فیزیکی، کفایت
شواهد، صحت معنایی یا مصرف واقعی provider را از یک declaration نتیجه نمی‌گیرد.

در پذیرش آفلاین از factory/backend واقعی، index تازهٔ موقت، ledger/SQLite موقت
و `MockTransport` استفاده می‌شود. policy واقعی engine، درخواست compact، catalog،
handoff تازه، correction، رد approval قدیمی و restart/retry بررسی می‌شوند.
این پذیرش، تست نرم‌افزار است؛ پاسخ mock نمرهٔ کیفیت مدل نیست.
[رسید تست و review](receipts/core-delivery-selection-2026-10-16.json) source،
شمارش و محدودیت‌های اجرای نهایی این تغییر را ثبت می‌کند.

روی source `9fdb132`، تعداد ۶۲۶۵ تست توسعه در دو context از پیش تعیین‌شده پاس
شدند: ۶۲۶۰ در CWD خنثی و پنج تست مسیر نسبی در root؛ source/testها بین دو اجرا
عوض نشدند و دو مجموعه هم‌پوشانی ندارند. مصرف‌کنندهٔ held-out پیش از اجرا از
collection حذف شد. ۱۲۹ regression تازه داخل همین شمارش است؛ review مستقل
۴۷ و ۱۲۱ تست هم‌پوشان را پاس کرد. Ruff روی ۳۸۸ فایل و سه demo آفلاین پاس‌اند.
اجرای یک‌تکهٔ full-suite یا کیفیت مدل ادعا نمی‌شود. اشتباه مسیر deselect در
فرمان اولیه، توقف پیش از مصرف‌کنندهٔ محافظت‌شده و اصلاح collection با log
حفظ شده‌اند؛ در parentها صفر open محافظت‌شده ثبت شد، نه attestation subprocessها.

## باقی‌ماندهٔ مشترک

حسن build و exclusion نهایی را pin می‌کند؛ محمدحسن native gold/routes، freeze و
review انسانی تنظیم منتخب را جمع می‌کند. دو شرط escalation مربوط به fix بدون
passage در PR81 با [نسخهٔ افزایشی E2ac](native-dev-gold-amendment.fa.md) اصلاح
شدند؛ ثبت فعال ۱۶ dev، تأیید انسانی دو بند تازه و pin بیلد را از هم جدا می‌کند.
این ثبت مجوز اجرای native پیش از pin نهایی نیست.
ادعای قبلی ما دربارهٔ rollback plan اشتباه بود؛ diff از merge-base فقط یک خط
اضافه می‌کند. [تصحیح ثبت‌شده](core-selected-runner-acceptance.fa.md) receipt
تاریخی C4r را عوض نمی‌کند. بهنام و محمدحسن مرز session تازهٔ review تأییدنشده را
می‌بندند. C5 به مدرک صاحب حساب mentor برای سه درخواست نامعلوم نیاز دارد.
guide آزمایشی Enum همچنان fixture-only است؛ تشخیص/fix آن تأیید نشده است.
