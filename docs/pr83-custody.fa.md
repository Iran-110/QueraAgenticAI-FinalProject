# ثبت opaque دادهٔ native test — PR83 / E2ae

PR83 متعلق به مالک evaluation است. review توسعه، fixtureهای `native/test/` یا
فایل `native-test-gold-review-v1.json` را باز یا اجرا نکرد. مسیرها، mode فایل،
شناسهٔ Git tree، metadata ثبت و تغییرهای مجازِ AGENTS/README/plan بررسی شدند.

۱۵ path یکتا و ۱۵ blob معمولی با پسوند JSON و declarationهای SHA خوش‌قالب
ثبت شده‌اند؛ محتوای آن‌ها parse نشده است.
مرجع manifest/observer با فایل‌های مجاز فعلی سازگار است. hashهای اعلام‌شدهٔ
fixtureها با byteهای payload مقایسه نشدند؛ review معنایی، ادعای انسانی و
۲۶۰ check آفلاین نیز مستقل توسط core تأیید نشده‌اند. این ادعاها متعلق به
مالک بخش‌اند و نمرهٔ کیفیت مدل یا اجرای نهایی نیستند.

شناسهٔ native-test tree دقیقاً
`ad71753ec31937383696d099e94ee4cedd849613` و blob فایل review برابر
`55d725d1101d9d49a41444724cafb49831dcfb30` باقی ماندند. این‌ها کنترل custody
با metadata Git هستند؛ بازکردن gold یا تأیید محتوای آن نیستند. pinهای بیلد هنوز
`pending_final_build` هستند؛ ثبت این artifactها freeze یا مجوز اجرا نمی‌سازد.

## اصلاح plan و محدودیت exposure

یادداشت اولیهٔ PR در plan مشترک، یک جزئیات خاص از review مربوط به test داشت.
این جزئیات هنگام بررسی مجازِ diff مربوط به plan/metadata دیده شد. پیش از انتشار
روی main، آن خط به جمع‌بندی آماریِ owner-attested تبدیل شد؛ هیچ جزئیات gold
در این گزارش تکرار نمی‌شود. commit اصلاحی `b0515be` فقط همان خط plan را تغییر
می‌دهد و payloadها و review اصلی را عوض نمی‌کند.

این پاک‌سازی، مشاهدهٔ قبلی را برنمی‌گرداند. تاریخچهٔ Git نیز بازنویسی نشده است.
مالک evaluation باید اثر exposure محدود را خصوصی بررسی و تصمیم eligibility
را پیش از اجرای نهایی ثبت کند. core از این جزئیات برای تنظیم prompt، model،
retrieval، vocabulary یا انتخاب شواهد استفاده نکرده و «کاملاً دیده‌نشده ماندن»
همهٔ test را از این review نتیجه نمی‌گیرد.

در این مرحله outcome-aware reasoning اضافه نشد؛ تغییر UI و تست custody با
fixtureهای ساختگیِ مستقل انجام می‌شوند. سیاست AGENTS اکنون native test و
review آن را هم صریحاً ممنوع می‌کند. ابزارهای توسعه نباید آن‌ها را با glob
یا preflight کل packet بخوانند. مالک evaluation بررسی نهاییِ کامل را انجام
می‌دهد؛ گزارش فعلی فقط metadata/custody است.

[رسید بررسی، redaction و وضعیت انتشار](receipts/team-closeout-2026-10-17.json).
