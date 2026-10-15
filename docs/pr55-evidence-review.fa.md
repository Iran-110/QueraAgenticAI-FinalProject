# بررسی افزودهٔ PR #55 و شرط شواهد case-a

هدف این یادداشت تکمیل review انسانی محمدحسن در head
`fdec087116df5255c0ee4d9693abc5eb9a057483` است. PR فقط یک review record، ابزار
آماده‌سازی، تست آن و یادداشت plan اضافه می‌کند؛ fixture، gold، manifest و
receiptهای قبلی را تغییر نمی‌دهد. پذیرش سه پرونده برای dev، پذیرش پاسخ‌های مدل
یا split نهایی نیست. CI به علت مسئلهٔ حساب Actions شروع نشده است.

## سند معتبر و شاهد مصرف‌شده

اصل پیشنهادِ وابسته‌کردن داوری به evidence درست است. متن cacheشدهٔ release note
نسخهٔ1.50.0، `st.multiselect` را صریحاً در فهرست widgetهایی دارد که با key مشخص
فقط از key هویت می‌گیرند. این یک واقعیت مستند دربارهٔ API است؛ به‌تنهایی علت
مشکل برنامهٔ کاربر، رفتار callback واقعی یا موفقیت fix را ثابت نمی‌کند.

رکورد `docs:content/develop/quick-references/release-notes/2025.md`، hash متن
`51ddfb5da2d2dfd88c2917b1b1542e74e892459c591de3cc1d25159632c4889a`
دارد. release noteها فعلاً طبق policy هر دو allowlist بیرون corpus هستند؛
این انتخابِ profile ثابت، به معنی نامعتبر یا الزاماً leaked بودن همهٔ release
noteها نیست. افزودن منبع معتبر در epoch بعد به review متن/زمان و pin تازه نیاز دارد.

متن `widget-behavior.md` با hash
`025129790a1fcb2d448e9ab608389f2ec55ef26751b64d1937cef5705837efeb`
فقط rollout تدریجی از1.50 تا1.55 را می‌گوید و برای API/نسخهٔ خاص به release
notes ارجاع می‌دهد. به‌تنهایی تغییر دقیق multiselect در1.50 را تعیین نمی‌کند.
متن docstringهای multiselect1.49 و1.50 هم یکسان است، با hash
`070b426e56bd72a0e19ba8ccc5c3282d26f95b5212adfee37f3fde31acb7bc76`؛
شرح key موجود در آن‌ها، ادعای تغییر هویت در یک release مشخص را ثابت نمی‌کند.

حضور در allowlist، حضور در index، برگشتن در top-k، رسیدن پس از version scope
به planner و پشتیبانی ادعا پنج موضوع متفاوت‌اند. در attemptهای case-aِ C4g،
C4h1، C4h2 وC4h3 به‌ترتیب9،4،8 و8 درخواست واقعی بررسی شد؛ هیچ‌کدام hitِ
widget-behavior یا release note را به planner نداده‌اند. پس نتیجهٔ قبلی را
نمی‌توان صرفاً بر مبنای وجود سند در corpus دوباره supported حساب کرد.

شرط پیشنهادی برای reviewهای آینده:

> ادعای version-specific دربارهٔ key-only identity در multiselect1.50 فقط زمانی
> supported است که excerpt رسمیِ واقعاً مصرف‌شده در همان request صریحاً همان
> API و نسخه را پشتیبانی کند. rollout عمومی، membership و metadata کافی نیستند.
> آن واقعیتِ release همچنان تشخیص علت یا fix این برنامه نیست. نیاز به callback
> و ترتیب تغییر state باقی است؛ نسخهٔ اعلام‌شدهٔ کاربر دوباره پرسیده نمی‌شود.

این شرط به‌صورت amendment افزوده و قبل از اجرای بعد ثبت می‌شود. اصل gold ثابت،
criterion native ثبت‌شده و همهٔ نمره‌ها/receiptهای قبلی محفوظ‌اند؛ تغییر نمرهٔ
گذشته، اگر لازم شد، گزارش جدا و دلیلِ قابل بررسی می‌خواهد.

## خانواده و chronology

review تازه هفت reservation پیشنهاد می‌دهد:4909،6985،7300،7419،8734،13022،14297.
در manifest بعدی،46 مورد قبلی حفظ و مجموعهٔ conservative به53 می‌رسد؛ index
ثابت فعلی عوض نمی‌شود. duplicate تأییدشده، related و umbrella consolidation
باید edgeهای جدا با URL/مبنای انسانی داشته باشند. جست‌وجوی انجام‌شده exhaustive
نیست. مسیر جدید `content/develop/concepts/app-design/custom-classes.md` و aliasهای
قدیمی آن برای exclusion آینده ثبت شوند؛ این راهنما اکنون بیرون هر دو allowlist است.

برای Enum، عبارت دقیق «paraphrase از آخرین body cacheشده با code عیناً نقل‌شده»
است. متن اصلیِ لحظهٔ ایجاد Issue تأیید نشده؛ body پس از ایجاد ویرایش شده است.
`original_initial_text_verified:false` در هر سه fixture همچنان معتبر می‌ماند.
پاسخ قبل و بعد correction هم واحدهای داوری جدا هستند.

این دو اصلاحِ wording و افزودن لینک edgeها برای تکمیل PR #55 پیشنهاد می‌شوند؛
محتوای review انسانی یا دادهٔ تاریخی به‌جای نویسنده بازنویسی نمی‌شود.
