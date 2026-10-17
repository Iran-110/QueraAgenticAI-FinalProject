# گزارش پوشش سؤال و وضعیت کاربر — اصلاح PR78

این اصلاح **گزارش آفلاین** را دقیق‌تر می‌کند؛ سؤال تازه‌ای به agent اضافه
نمی‌کند و نشانهٔ بهترشدن تصمیم یا جواب مدل نیست. بازخورد محمدحسن دربارهٔ
usefulness و پاسخ Enum همچنان gate کیفیت جداگانه است.

## ایراد و اصلاح

در head اولیهٔ PR78، واردشدن از یک مسیر `ask` به معنی معلوم‌شدن پاسخ حساب
می‌شد. اما کاربر ممکن است هنوز کد را نداده باشد؛ core فقط اطلاعات صریح و
پاسخ معتبر به سؤال canonical نسخه را ثبت می‌کند. جمع‌کردن متوالی turnها نیز
می‌توانست fact شاخه‌ای را که بازدید نشده، وارد شاخهٔ دیگر کند. normalization
نام fact هم باید از همان قرارداد واقعی core بیاید.

[review پیش از اصلاح](receipts/pr78-review-2026-10-16.json) و
[گزارش تاریخی v1](../data/evaluation/split-e1-v1/question-coverage-v1.json)
بدون تغییر حفظ شده‌اند. محاسبهٔ تازه از `UserTurn`، `propose_user_turn`،
intake نسخه و catalog موجود استفاده می‌کند. مسیرهای ثبت‌شده جدا شبیه‌سازی
می‌شوند؛ availability در همه/بعضی/هیچ مسیر از انتخاب واقعی مدل جداست.
این‌ها فرض‌های مسیر fixture هستند، نه شاهد approval، انتشار یا اجرای واقعی.
سقف هر fixture،۱۰۲۴state و۲۵۶مسیر terminal است؛ عبور از آن یا workflow
پشتیبانی‌نشده با خطای ثابت `QuestionCoverageRejected` رد می‌شود. ادامهٔ سؤال
باید approval ثبت‌شدهٔ فرضی و متن مطابق route داشته باشد؛ edit نامطابق یا
سؤال ردشده پشتیبانی نمی‌شود. این بررسی اعتبارسنجی tracker واقعی نیست.

## اجرای امن برای توسعه

[گزارش dev مرحلهٔ E2aa](../data/evaluation/split-e1-v1/question-coverage-dev-v2.json)
روی۱۶fixture،۱۱شاخهٔ ask دارد:۵سؤال نسخه و۶vocabulary، همگی در تمام مسیرهای
ثبت‌شدهٔ مربوط در دسترس‌اند.۴turn هم گزینهٔ سؤال دارند درحالی‌که gold آن را
قبول نمی‌کند. شمارش فعلی dev با گزارش قبلی هم‌نتیجه است؛ counterexampleهای
خنثی نشان می‌دهند چرا الگوریتم قبلی برای وضعیت‌های دیگر قابل اتکا نبود.
پس از PR79، [v3](../data/evaluation/split-e1-v1/question-coverage-dev-v3.json)
فقط pin manifest تازهٔ v2 سه dev را عوض می‌کند؛ شمارش و projection همان است.
هیچ گزارش قدیمی بازنویسی نشده است.

```bash
QUESTION_COVERAGE_OUTPUT="$(mktemp -d)/question-coverage-dev-v2.json"
uv run python scripts/report_question_coverage.py --output "$QUESTION_COVERAGE_OUTPUT"
```

پیش‌فرض فقط dev است. report v2 در Git موجود است؛ خروجی تازه باید مسیر جدید
داشته باشد و حتی default موجود هم بازنویسی نمی‌شود. summary تاریخی test
دوباره محاسبه نشده و معتبرشدن آن با این اصلاح
ادعا نمی‌شود. اجرای held-out با مالک evaluation و پس از freeze است؛ در توسعه
هیچ سؤال، fixture، evidence یا gold از test باز نمی‌شود. vocabulary و exclusion
نیز از روی شمارش test تنظیم نشده‌اند.

وجود سؤال در catalog به معنی ضرورت سؤال، انتخاب آن توسط مدل یا مفیدبودن جواب
نیست. بخش extra-offer فقط گزینهٔ موجود برخلاف gold همان turn را توصیف می‌کند.
gold ثابت/native، rubric، manifest و تنظیم نهایی همچنان با مالک evaluation
و هماهنگی حسن freeze می‌شوند؛ این task آن‌ها را تغییر نمی‌دهد.

## بررسی انجام‌شده

[رسید source و review](receipts/question-coverage-state-2026-10-16.json):
روی `a9f4358`،۵۹۰۹تست توسعه پاس و یک تستِ خواندن همهٔ held-outها عمداً
deselect شد؛۰تلاش برای بازکردن محتوای محافظت‌شده ثبت شد.۴۸تست متمرکز و همان
۴۸تست در review مستقل پاس‌اند؛ این اعداد با suite جمع نمی‌شوند. Ruff روی
۳۷۱فایل و diff-check پاس‌اند. runtime/renderer/API/UI/tracker/config تغییر
نکرده؛ HTTP/SQLite۴۵۷/۴۵۷ C2k شواهد قبلی همان مسیرهاست، نه اجرای تازه.
ledger و۱۹pin ثابت‌اند؛ C5read-only۳۶/۳۶ به معنی حل سه درخواست نامعلوم نیست.
halt محفوظ، APIصفر و CI موفق ادعا نشده است.
