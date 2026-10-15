# C4h3 — ظرفیت source بدون بزرگ‌کردن prompt

[protocol](../experiments/core_source_capacity_v1/protocol-v1.json) قبل از کد ثبت
شد. شکست مبنا همان Enum با چهار source است: draft21805 و summary22871 کاراکتر
بودند، درحالی‌که هر کدام سقف20000 دارند. متن سند را کوتاه نمی‌کنیم.

`METIS_GROUNDED_SOURCE_CAPACITY=true` همراه decision-contracts گزینه‌ای اختیاری
و پیش‌فرض خاموش است. core از renderer موجود طول کامل و escaped هر quote و
متن ثابت هر تصمیم را می‌گیرد؛ تعداد امن را با بزرگ‌ترین quoteها می‌سنجد و فقط
`maxItems` فعلی در schema و قواعد تصمیم را کاهش می‌دهد. هیچ متن راهنمای تازه‌ای
به prompt اضافه نمی‌شود. انتخاب شاهد مرتبط همچنان با مدل است؛ این محدودیت
کفایت منبع یا پاسخ صحیح را ثابت نمی‌کند و بعضی ترکیب‌های کوچک‌ترِ قابل‌جاگیری
را محافظه‌کارانه کنار می‌گذارد.

اگر یک singleton یا متن پایه قابل render نباشد، یا conflict جاری/حل‌نشده داشته
باشیم، راهنما اعمال نمی‌شود؛ renderer اصلی همچنان مرجع نهایی است. conflict
اجباری، همهٔ شواهد، hash، facts، correction و سقف دو attempt محفوظ‌اند. در هر
درخواست از اطلاعات همان revision حساب می‌کنیم؛ cache شواهد قدیمی نداریم.

ساخت prompt و hash آن در gateway و runner از یک تابع مشترک استفاده می‌کند تا
رسید prompt با چیزی که واقعاً به مدل می‌رسد یکسان بماند. این کمک محدود به اتصال
و evaluation است؛ ساخت UI یا rubric انسانی محمدحسن را تغییر نمی‌دهد.

کنترل‌های آفلاین شامل تمام subsetهای زیر سقف، متن escaped، اندازه‌های نامساوی،
correction، conflict، singleton بیش‌ازحد، request قدیمی و HTTP mock هستند.
اصل receiptهای تاریخی تغییر نمی‌کند؛ render کردن subset تألیفی بهبود مدل نیست.
مقایسهٔ live پس از freeze کد، index و ledger در همان پوشهٔ experiment ثبت می‌شود.

## نتیجهٔ ثبت‌شده

[مقایسه و receiptها](../experiments/core_source_capacity_v1/README.md): دو دور
balanced با همان index۱۸/۳۶، مدل gpt-4o-mini و۲۸send. OFF وON هر دو۴/۶ مسیر
کامل و۸ پیشنهاد تازه داشتند؛ هر کدام۵ سؤال و۳ ارجاع، صفر پاسخ فنی. راهنما فقط
در دو call یک correction واقعاً سقف را از۸ به۳ رساند. هیچ arm این بار overflow
نداشت؛ شواهد زندهٔ کاهش overflow یا افزایش کیفیت نداریم و گزینه خاموش می‌ماند.

دو پاسخ provider با length متوقف شدند؛ schema نامعتبر و یک source mismatch
هم باقی‌اند.۴empty و۴unvisited را حذف نکردیم. دو correction موفق نسخه۱.۳۱.۱
را حفظ کردند؛ review انسانی هنوز لازم است. هزینهٔ تخمینی این اجرا$0.032721150،
صفر hold تازه، هر۶ scope بسته؛ هزینهٔ تخمینی کل ledger$0.330022770 به‌علاوه
$0.0233792 hold قدیمی است. halt و سقف قبلی محفوظ‌اند.
