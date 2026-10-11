# بازبینی اتصال تیم — ۱۱ اکتبر ۲۰۲۶

مبنای بازبینی: `main` در `613109187e30eebd22c26250845da0a1f290edb0` و
PR #19 در `faedfc14cabfc78803f08e0ab7226cd9037cf2c3`. تغییرات محلی قبلی
حفظ شدند. PRهای #13، #14، #15، #17 و #18 قبلاً merge شده‌اند؛ گزارش اولیهٔ
«PR #15 در حال انجام» دیگر وضعیت فعلی Git نیست. PR #19 هنگام بازبینی باز بود.

## چیزی که تأیید شد

- روی main، ۱۶۷۴ تست آفلاین پاس شدند. یک warning موجود مربوط به TestClient
  باقی است؛ شکست تست نیست.
- UI اطلاعات صریح، correction، منابع و review کامل را به API متصل کرده و
  انتخاب پرونده دارد. retriever/reasoner هنوز اسکریپتی و storage حافظه‌ای‌اند.
- runner، case ثبت‌شدهٔ #12782 و سناریوهای عملیاتی را از همان API اجرا می‌کند.
  manifest فعلی فقط یک dev و صفر test دارد؛ دو scenario ساختگی جزو ۳۰ case نیستند.
- ۱۴ تست مستقل tracker و `scripts/tracker_pilot.py` روی PR #19 پاس شدند.
  SQLite از قراردادهای فعلی UserTurn/CaseState/ProposalHandoff استفاده می‌کند؛
  reviewer معتبر، proposal/hash دقیق، revision، rollback و dedup را جدا از
  پیشنهاد مدل کنترل می‌کند. اتصال آن به FastAPI/UI هنوز انجام نشده است.

## ایرادهای بازتولیدشده با تست هدفمند

| مرز | نتیجهٔ نسخهٔ مبنا | اصلاح لازم |
| --- | --- | --- |
| runner و دو پرونده | مسیر A/B/A، adapter پروندهٔ A را سه بار می‌خواست؛ checkهای قبلی پاس بودند | انتخاب adapter با case_id همان turn |
| هویت اجرای live | تکرار یک fixture در دو آزمایش مستقل با ledger موقت، در بار دوم `DuplicateModelRequest` داد؛ ارسال دوم صفر بود | run ID تازه برای آزمایش تازه؛ replay رخداد پذیرفته‌شده بدون فراخوانی تازه |
| ادعای کیفیت | افزودن تشخیص ممنوع به draft، با adapter آزمایشی و ledger=None، صفر fail و quality_claim=true داشت | نوع اجرا معیار کیفیت نباشد؛ ledger الزامی و review معنایی جدا |
| receipt ارزیابی | فقط چهار فیلد proposal و ID citationها می‌ماند؛ متن کامل/packet پس از approve از دست می‌رفت | نگهداری handoff اصلی، نسخهٔ edited و خروجی released با provenance |
| فرم UI | بعد از رد ورودی ساختاری، فرم پروندهٔ A هنگام New case در B می‌ماند و قابل ثبت در B بود | جداسازی/reset همهٔ ورودی‌های ارسال‌نشده هنگام تغییر پرونده |
| نمایش ادعاهای منبع | دو claim متفاوت برای یک chunk در API بود؛ UI فقط claim دوم را نشان می‌داد | نگهداری و نمایش تمام claimهای هر chunk |
| خواندن tracker | correction از connection دیگر، state revision=1 را کنار history شامل revision=2 برمی‌گرداند | یک transaction خواندنی برای snapshot کامل؛ write CAS قبلاً fail closed بود |

این‌ها regression نرم‌افزار و قراردادند. اجرای intercepted با MockTransport
مدل واقعی نیست؛ ledgerهای آزمایش موقت‌اند و هزینهٔ واقعی این بازبینی صفر است.
کلید و ledger واقعی خوانده یا تغییر داده نشدند. آزمایش‌های تاریخی و receiptهای
تیم بازنویسی نشدند. تست همزمانی tracker، fixture اصلی ارزیابی یا gold تازه نیست.

اصلاح tracker در [PR #20](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/20)
روی branch #19 منتشر شد. regression snapshot روی کد اصلی `faedfc14` یک fail
و بعد از اصلاح یک pass دارد. ۱۴ تست قبلی همراه دو تست تازه، ۱۶ pass؛ بعد از
sync با `6131091`، کل suite آن branch ۱۶۹۰ pass و Ruff lint/format هم پاس شدند.
sync تغییرات هم‌تیمی‌ها را حفظ می‌کند؛ این PR، branch بهنام یا main را تغییر نداده است.

## rubric و راه اتصال

[پیشنهاد rubric سمت core](evaluation-rubric.md) با قرارداد فعلی سازگار است.
material claim در draft، summary، rationale، question و fact/checkها باید
بررسی شود. یک ادعای مؤثر unsupported می‌تواند support را صفر کند؛ N/A، review
ناقص و insufficient جدا گزارش شوند. gap کاربر با gap منبع، نسخهٔ جاری با نقل
تاریخی، و امتیاز مدل با متن ویرایش‌شدهٔ انسان یکی نیستند. معیارهای شرطی و
پاسخ‌های متناسب با سؤال باید قبل از اجرای کیفیت ثبت شوند.

برای اتصال tracker، API باید state را از خود SQLite بخواند؛ همزمان نگه‌داشتن
`_cases` به‌عنوان مرجع دوم سازگاری را از بین می‌برد. event اصلی و reply binding
به `apply_turn`، handoff واقعی core به `stage_proposal` و reviewer معتبر همراه
review_id/revision/proposal/hash دقیق به `review` برسند. replay event باید قبل
از ساخت adapter/اجرای مدل تشخیص داده شود. بعد از قطع ارتباط یا restart ابتدا
receipt و pending را بخوانید؛ ledger یا مدل را برای جبران دوباره اجرا نکنید.
بازیابی امن اجرای نیمه‌تمام بین commit event و stage proposal، و نمایش توقف/خطای
ابزار در API، نیاز به قرارداد و تست اتصال دارند؛ تست مستقل tracker آن را حل نمی‌کند.

## داده و کار باقی‌مانده

ZIP محلی `streamlit-data-for-dev-test.zip` دوباره بررسی شد: ۱۵ entry، CRC سالم و
۱۴ فایل مطابق manifest؛ SHA-256 بسته
`02408667f34d9d0ff4adc9c055685d8ba7fd6fbd3f45ea8b4bf4d88b2ef42d80`.
۲۴۰ Issue و ۱۱۷۸ comment، ۵۶ Markdown و ۱۱۷۲ API record؛ snapshot ششم اکتبر.
این بسته seed انتخاب است و در Git پروژه نیست. وجودش در workspace ساسان، رسید
تحویل به هم‌تیمی نیست. محمدحسن می‌تواند انتخاب خانواده‌های dev/test را از همین
بسته شروع کند؛ حسن provenance و corpus allowlist/exclusion را تکمیل کند.

E1/E2 هنوز نیاز به schema معتبر، مسیرهای شرطی و freeze دارند. runner فعلی
manifest frozen، exposureها، حداقل تعداد و exclusion واقعی corpus را enforce
نمی‌کند. تا RAG، tracker/API، داوری معنایی و حل C5، نتیجهٔ کیفیت نهایی نداریم.
تک agent همچنان مبناست؛ این ایرادها به اصلاح مرز اتصال نیاز داشتند.

## بازپخش و محدودیت گزارش

نه regression runner/UI روی archive کد واقعی `6131091` fail شدند و روی اصلاحات
pass شدند؛ شکست import نبود. هشت تست اول با همان bytes بازپخش و سپس تست
چند claim نیز روی همان baseline بررسی شد. SHA-256 فایل‌های تست هنگام این مقایسه:
`test_eval_runner.py=4029a295bec42662a24952ead965688c0573f6aa8b7a3347423de772d517a3d5`،
`test_ui.py=33688657ea61754a507a18b50244e1ff1c5ab671a58af0670eea9ff3583d5a01`.
این‌ها آزمون‌های کشف باگ هستند؛ labelهای پیش از اجرای مدل یا human gold نیستند.

نسخهٔ نهایی runner/UI: ۱۶۹۴ تست، Ruff lint/format و locked dependencies پاس؛
۶۳ تست متمرکز اتصال پاس‌اند (۲۰ بیشتر از ۴۳ تست مبنا). تمام ۱۹ فرمان آفلاین
workflow نیز پاس شدند؛ آخرین تغییر نمایش claim با تست UI و full suite دوباره
بررسی شد. baseline main بدون تغییر بود و هیچ regression نادیده گرفته نشد.
در یک checkout آزمایشی، ترکیب PR #20 با این branch نیز ۱۷۱۰ تست و Ruff را
پاس کرد؛ main و branch هم‌تیمی تغییر نکردند. شمارش caseهای پاس‌شده با شرط
coverage کامل دقیق‌تر شد؛ ۳۹ تست runner و سپس دوباره ۱۷۱۰ تست ترکیب نهایی پاس شدند.

برای بررسی اصلاحات:

```bash
uv sync --locked --group dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python -m agent_app.evaluation.runner data/evaluation/dev data/evaluation/scenarios
```

اصلاح receipt از schema 1 به 2، handoff اصلی، edited و released را نگه می‌دارد؛
همچنین source hash و snapshot واقعاً دیده‌شده ثبت می‌شوند. هزینهٔ tracked
reasoner با ledger entry همان درخواست join می‌شود، نه اختلاف مجموع ledger.
cost/usage غایب، pending یا uncertain می‌تواند null باشد؛ settlement معلوم و
reservation/uncertainty جدا می‌مانند. هزینهٔ retrieval/embedding/setup با این
metric پوشش داده نمی‌شود و همچنان بخشی از سقف مشترک است. `quality_claim=false`
برای هر دو mode است؛ unsupported claim و سؤال نامناسب هنوز نیاز به داوری E2 دارند.

انتظار دقیق script فقط در offline بررسی می‌شود. اگر مدل سؤال معتبر دیگری بپرسد
و جواب متناسب در fixture فعلی نداشته باشیم، runner پیش از ارسال reply ناسازگار
با `FixtureBranchUnavailable` متوقف و coverage ناقص ثبت می‌کند؛ شکست معنایی مدل
فرض نمی‌شود. CLI برای coverage ناقص بدون check ناموفق کد 2 می‌دهد. این محافظ
جای اجرای branchهای شرطی E2 را نمی‌گیرد.
case ناقص در `cases_all_passed` هم شمرده نمی‌شود؛ صفر fail تنها شرط پایان نیست.

[receipt نهایی v3](../data/evaluation/receipts/offline/core-boundary-review-2026-10-11-v3.json)
روی source commit `37ab853` ثبت شد: یک dev و دو scenario ساختگی، ۱۱ turn،
۱۳۶ check و صفر fail؛ coverage کامل و هزینهٔ واقعی صفر. source hashها قبل و
بعد یکسان بودند و fixtureهای ثبت‌شده تغییر نکردند. SHA-256 receipt:
`f90e2d8c98b05a53b473c7e3d6b33cb2fb25c22b84aa04e03b7e05142f07fae1`.
نسخهٔ میانی v2 روی `85f5dc8` نیز ۱۳۶ check پاس داشت؛ پیش از دقیق‌کردن شمارش
coverage ساخته شد و بدون تغییر در output محلی حفظ شد. هیچ‌کدام نتیجهٔ مدل،
RAG واقعی یا final test نیستند؛ approved/edit در runner از fixture می‌آیند.
