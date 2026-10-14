# اتصال سه dev به index واقعی

این مرحله با هماهنگی ساسان ادامهٔ کار حسن است؛ PR43 در شروع همان head قبلی و
zero diff داشت. چهار رکورد رسمی موجود در seed به profile جدا اضافه شدند.
profile قبلی و فایل‌های ارزیابی تاریخی تغییر نمی‌کنند. split جدید در
`experiments/dev_rag_coverage_v1/split-manifest.json` همان سه خانواده exposed را
با exclusion کامل نگه می‌دارد؛ split نهایی یا case تازهٔ test نیست.

sourceها: button1.39.0، fragment1.50.0 و multiselect1.49.0/1.50.0. متن‌های دو
multiselect یکسان‌اند ولی نسخه و source/chunk ID مستقل‌اند. هر چهار متن، hash،
URL و spanهایشان به seed اصلی pin شده‌اند. profile بسته۱۸source/۳۶chunk دارد؛
۴۶ Issue رزرو شده و همهٔ Issue/comment/outcome/fixtureها بیرون corpus هستند.
راهنمای پاسخ مستقیم Enum هم خارج allowlist است.

[دستور build و روش آزمایش](../experiments/dev_rag_coverage_v1/README.md).
index از Chroma واقعی با lexical embedding محلی استفاده می‌کند؛ semantic
embedding یا کیفیت عمومی RAG از آن نتیجه نمی‌گیریم. مدل با adapter واقعی سرچ
می‌کند، نه evidence fixture؛ متن‌ها کامل ثبت می‌شوند. top5 قبل از فیلتر نسخه
است، پس نبودن source در نتیجه می‌تواند ranking miss باشد و نبودن corpus نیست.
برای رساندن پاسخ مطلوب، filter مبتنی بر Issue/source ID اضافه نشده است.

pilot هنوز callback/order کاربر را کم دارد؛ کوچک‌شدهٔ کاربر کار می‌کند و
reproduction شکست نیست. button فقط برای نسخهٔ واقعی و سند برگشتی قابل استناد
است، warning/تحویل feature جدا می‌ماند. Enum نسخه و code کامل دارد ولی علت/fix
با docs عمومی ثابت نمی‌شود؛ correction1.31.1 باید facts/code فعلی را حفظ کند و
approval قبلی را رد کند. gold و آیندهٔ گفتگو وارد planner نمی‌شوند.

کار حسن پس از sync: این profile و رسیدهای سرچ را بررسی کند و ranking/backfill
یا semantic retrieval را با method جدا پیشنهاد بدهد؛ build و exclusion نهایی
به split انسانی محمدحسن وابسته است. محمدحسن review انسانی متن‌ها و خانواده‌ها
و سپس dev/test نهایی را دارد. smoke دستی UI/SQLite بهنام جدا باقی است.
