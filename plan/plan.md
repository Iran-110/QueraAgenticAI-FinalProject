# plan و checklist تیم — Streamlit Support Assistant

به‌روزرسانی: ۲۰۲۶-۱۰-۲۲. این نسخه ادامهٔ plan محمدحسن روی `main` در commit `2ead870` است؛ [نسخهٔ قبلی](archive/plan-before-task-checklist.md) حفظ شده. مبنای regressionهای بازبینی `6131091` بود؛ انتشار tracker با `464e55e` و سپس #21 با `94b60e1` و [CI موفق](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38151154794) ثبت شده‌اند. مبنای baseline تازهٔ C2a همین `94b60e1` است. این فایل برای تقسیم کار و شرط پایان taskهاست؛ روزهای sprint قبلی را تاریخ تحویل حساب نمی‌کنیم. الزام‌ها از صورت اصلی پروژه می‌آیند، نه از ابزارها و frameworkهای پیشنهادی plan.

## وضعیت فعلی

**تصمیم پس از ارائه، ۲۲ اکتبر، طبق اعلام ساسان:** ارائه انجام شده و مهلت
توسعهٔ تحویل تمام شده است. کار فعلی ساسان تهیهٔ گزارش فارسی و قرار دادن گزارش
تأییدشده و فایل نهایی ارائه در Git است. اجرای اصلاح live به **Member 4،
محمدحسن گل‌محمدیان** واگذار می‌شود؛ او با agent خودش بررسی، اصلاح کوچک و review
را پیش می‌برد. این واگذاری، کار تازهٔ کدنویسی برای ساسان ایجاد نمی‌کند.
متن برنامه و واگذاری در همین فایل Markdown و راهنمای نقش می‌ماند و وارد
گزارش نهایی نمی‌شود.

راهنمای اجرایی محمدحسن: [تحویل کار live پس از ارائه](../docs/post-presentation-live-handoff.fa.md).
بازبینی و اصلاح جزئی مسیر اجرا مجاز است؛ تغییر ساختار، تعویض مدل، بازکردن کمپین‌های
بسته و مصرف تازهٔ API در دامنهٔ این تصمیم نیست. انتخاب یک ایده یا مدل دیگر، اگر
بعداً خواسته شود، به تصمیم مستقل نیاز دارد. نتیجهٔ توسعه/اجرای تازه نباید به نام
عملکرد نسخهٔ ارائه‌شده ثبت شود.

### تحویل پس از ارائه — مسئولیت و شرط پایان

- [x] **PD1 — بررسی Git و فایل ارائه؛ ساسان، ۲۲ اکتبر.** visibility واقعی repository و
  branch/commit مرجع بررسی و ثبت شود؛ عمومی‌بودن از حدس یا clone محلی نتیجه
  گرفته نشود. نسخهٔ ارائه‌شده با فایل نهایی تطبیق داده شود؛ v5 موجود در
  [پوشهٔ ارائه](../docs/presentation/README.fa.md) نقطهٔ شروع بررسی است، نه
  تأیید خودکار اینکه همان فایل ارائه شده است. نتیجه، مسیر فایل و لینک Git در
  تحویل ثبت شوند؛ فایل خصوصی presenter، credential و ledger منتشر نشوند.
  نتیجهٔ بررسی: پاسخ مستقیم GitHub برای `Iran-110/QueraAgenticAI-FinalProject`
  برابر `private=false` و `visibility=public`؛ main در `aa17a4e` بود.
  [PDF ارائه‌شدهٔ v5](../docs/presentation/judges-presentation-fa-v5.pdf) با
  فایل نهایی بستهٔ محلی v5 بایت‌به‌بایت یکسان است؛ Git blob هر دو
  `29e451c1724293e9ebbf55d883feb1d058b35fa1` و همین blob روی `origin/main` موجود است.
- [x] **PD2 — گزارش روایی فارسی RTL، بازبینی و تأیید؛ ساسان، ۲۲ اکتبر.** گزارش چندصفحه‌ای
  کوتاه با چهار نام کامل، مسئله، معماری و سهم مستند اعضا، روایت کند که چه
  انتخاب‌هایی انجام دادیم و چرا، از چه مدل تصمیم‌گیر و روش بازیابی استفاده
  کردیم، داده و build چگونه آماده شدند، چه مشکل‌هایی دیدیم و در هر مرحله
  چه اصلاح و تستی انجام دادیم. دستاوردها و زحمت‌ها از تاریخچه، PR و receipt
  مستند شوند؛ تست نرم‌افزار، آزمایش exposed-dev و کیفیت نهایی مدل جدا بیان
  شوند و مسئله‌های حل‌نشده صادقانه بمانند. برنامهٔ پس از ارائه، واگذاری L1–L4،
  وظایف آینده و هماهنگی داخلی در گزارش نهایی درج نشوند. **نسخهٔ بازنویسی‌شدهٔ
  گزارش و فایل ارائه هر دو پیش از انتشار نهایی به ساسان نشان داده شوند؛ تأیید
  هر دو لازم است.** گزارش v2 در ۶صفحه با این روایت بازنویسی و هر شش صفحه
  و منابع آن بررسی شد؛ ارائهٔ ۱۵اسلایدی v5 نیز بدون تغییر بازبینی شد.
  ساسان در پیام۲۲اکتبر **هر دو فایل را صریحاً تأیید و انتشارشان در Git روی
  main با نام رسمی و به‌روزرسانی README را درخواست کرد**؛ شرط بازبینی این
  task بسته است. شاهد خروجی‌ها و انتشار در PD3 ثبت می‌شود.
- [x] **PD3 — نام‌گذاری رسمی و انتشار تحویل نهایی روی main؛ ساسان، ۲۲ اکتبر.**
  پس از PD1 و تأیید هر دو فایل در PD2، نام‌ها و مسیرهای رسمی تحویل:
  [گزارش فنی فارسی](../docs/final-delivery/Quera-Streamlit-Support-Assistant-Technical-Report-FA.pdf)
  و [ارائهٔ نهایی فارسی](../docs/final-delivery/Quera-Streamlit-Support-Assistant-Final-Presentation-FA.pdf).
  هر دو PDF با نسخه‌های تأییدشده بایت‌به‌بایت یکسان‌اند؛ گزارش۶صفحه و ارائه۱۵
  اسلاید است. لینک مستقیم و عنوان رسمی در [README اصلی](../README.md) قرار گرفت.
  [commit تحویل `474da4b`](https://github.com/Iran-110/QueraAgenticAI-FinalProject/commit/474da4b)
  روی `origin/main` منتشر و با fetch تازه تأیید شد؛ blobهای هر دو PDF و README
  با خروجی بررسی‌شده برابرند. نسخهٔ ارائهٔ v5 و شواهد تاریخی حفظ شده‌اند؛
  فقط مستندات و فایل‌های تأییدشده منتشر شدند و runtime تغییر نکرده است.
- [ ] **L1 — بازبینی baseline و فهرست blockerهای live؛ Member 4، محمدحسن گل‌محمدیان.**
  HEAD، وضعیت branch، recipe/model، build و مسیر واقعی startup را طبق راهنمای
  handoff ثبت کند. issue مشخص و قابل بازتولید را از پیشنهاد بهبود کیفیت جدا
  کند؛ [PR #93](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/93)
  روی `feat/user-live-backend` در head `11f39d6` نیز به‌عنوان پیشنهاد باز و
  ادغام‌نشده review و هماهنگ شود، نه baseline تحویل‌شده. قبل از ساخت مسیر
  موازی، همان کار موجود بررسی شود؛ ledger جدا با سقف۱دلار در آن PR، کنترل
  بودجهٔ مشترک۵دلاری تیم را ثابت نمی‌کند و راه رفع halt/holdهای قبلی نیست.
  plan اصلاح کوچک و معیار پذیرش پیش از تغییر نوشته شود. این task شامل
  فراخوانی provider، mergeِ PR93 یا مصرف مجوز تاریخی جلسه نیست.
- [ ] **L2 — اصلاح اختیاری کوچک برای قابلیت استفادهٔ live؛ Member 4، محمدحسن گل‌محمدیان.**
  فقط blocker تأییدشدهٔ L1، مانند تنظیم آدرس/پورت، startup، پیام خطا یا wiring
  موجود UI/API، روی branch خودش اصلاح شود. قراردادها، core recipe، مدل، corpus،
  index، renderer، ledger و حدود اجرا ثابت بمانند. اگر حل مشکل به تغییر این مرزها
  نیاز داشت، پیشنهاد مستقل ثبت شود و همان بخش ادامه پیدا نکند؛ تغییر ساختار
  در این تحویل انجام نمی‌شود. نبود blocker نیز با شاهد، خروجی معتبر L1/L2 است.
- [ ] **L3 — پذیرش و review اصلاح؛ Member 4، محمدحسن گل‌محمدیان.**
  تست هدفمند آفلاین با provider ماک، index/SQLite موقت و مرورگر روی مسیر موجود
  انجام شود؛ correction، approval قدیمی، retry و restart در بخش متأثر حفظ شوند.
  خطاها، مراحل بازتولید، نتیجه قبل/بعد و محدودیت‌ها در PR ثبت و کد با agent خودش
  review شود. اصلاح روی فایل watched مجوز اجرای scope قدیمی نمی‌سازد؛ هیچ watch،
  pin، scope یا receipt تاریخی برای عبور از guard بازنویسی نشود.
- [ ] **L4 — تحویل قابل اجرای محمدحسن؛ Member 4، محمدحسن گل‌محمدیان.**
  لینک PR، source commit، دستور startup بدون secret، تست‌های واقعاً اجراشده،
  راه بازگشت و blocker باقیمانده ارائه شود. اجرای واقعیِ هزینه‌دار، اگر برای
  پذیرش بعدی لازم شد، تا مجوز صریح مستقل و بررسی scope معتبر معلق بماند؛ این
  plan هیچ بودجه، refill یا رفع halt اعطا نمی‌کند.

ارزیابی نهایی E4/E5، pinهای native gold/packet، C5 و سه hold تاریخی همچنان
بازند؛ انتشار گزارش یا تحویل ارائه checkbox آن‌ها را نمی‌بندد. baseline تاریخی
۱۸ اکتبر، از جمله ظرفیت گزارش‌شدهٔ جلسه، وضعیت امروز سرویس یا موجودی امروز
محسوب نمی‌شود و برای هر اجرای بعدی باید خواندنی بررسی شود.

### سوابق تحویل تا ۱۸ اکتبر

مرجع جمع‌بندی آن روز: [وضعیت ۱۸ اکتبر](../docs/current-status.fa.md).
گزارش‌های تاریخ‌دار پایین، شواهد هر تحویل را حفظ می‌کنند؛ عبارت‌های تمرین، جلسه
و «قدم بعد» در آن‌ها سابقه‌اند. اولویت و مالک کار جاری از تصمیم ۲۲ اکتبر بالا
خوانده می‌شود؛ موارد ارزیابی و حساب هزینهٔ حل‌نشده همچنان معتبرند.

- [x] **M2c — تحویل خواندنی ارائه و راهنمای کوتاه؛ ساسان.**
  [PDF/HTML نسخهٔ۵](../docs/presentation/README.fa.md): نام‌های کامل پایین راست؛
  markerهای روی تصویر اسلاید۳ و labelهای فارسی زیر فرم حذف شدند.۱۳صفحهٔ دیگر
  باv4 پیکسل‌به‌پیکسل یکسان‌اند؛ [QA مستقل](../docs/presentation/judges-v5-qa.json).
  [متن گفتاری](../docs/presentation/speaker-notes-fa-v5.md) با۱۵اسلاید هماهنگ است؛
  نسخهٔ گوشی با اندازهٔ متن قابل تنظیم و PDF آموزشی۶صفحه‌ای در بستهٔ خصوصی آماده‌اند.
  پورت مستقل راهنمای گوشی صرفاً خواندنی است؛ runtime/config/build/halt تغییر نکرده‌اند.
  APIمدل و ledger write صفر؛ تست‌های زندهٔ تازه در این تحویل اجرا نشده‌اند.

- [x] **M2b — اصلاح نهایی تصویر و نام‌های ارائه؛ ساسان.**
  [PDF/HTML نسخهٔ۴](../docs/presentation/README-v4-archive.fa.md) آماده است: چهار نام کامل
  پایین چپ اسلاید۱، نشانگر انگلیسی1/2 و یک ردیف کامل Name/Value با برچسب هم‌تراز
  در اسلاید۳، و نام کوتاه «محمد» در اسلاید۱۴. [QA مستقل](../docs/presentation/judges-v4-qa.json)
  هر۱۵صفحهٔPDF را render/review کرده؛۱۲صفحهٔ دیگر با v3 پیکسل‌به‌پیکسل یکسان‌اند.
  [روایت گفتاری](../docs/presentation/speaker-notes-fa-v4.md) هماهنگ است؛ مرجع
  سریع خصوصی v6 با پاسخ‌های کوتاه در بستهٔ محلی قرار دارد و وارد corpus نمی‌شود.
  v2/v3، کد و تنظیمات جلسه، build، watch و halt ثابت‌اند؛ API و ledger write صفر.

- [x] **M2a — بازطراحی روایت و راهنمای ارائه؛ ساسان.**
  [PDF/HTML نسخهٔ۳](../docs/presentation/README-v3-archive.fa.md) با۱۵اسلاید، نمودار و تصویر
  واقعی رابط، توضیح روشن ارزش محصول، داده، تصمیم agent، correction و بررسی انسان
  آماده است. نشانگرهای۱پیام/۲وضعیت/۳اطلاعات و جهت نسخه‌ها/Name/Value بررسی شدند.
  متن گفتاری، زمان‌بندی۲۹دقیقه‌ای شامل۶دقیقه دمو و جملهٔ انتقال هر اسلاید در
  [راهنمای جدا](../docs/presentation/speaker-notes-fa-v3.md) است؛ راهنمای خصوصی
  خواندنی با انتخاب اسلاید و حالت فقط گفتار هم در بستهٔ محلی آماده شد.
  [QA](../docs/presentation/judges-v3-qa.json): هر۱۵صفحهٔPDFواقعی render/review،
  منبع اعداد و دامنهٔ نتایج review، navigation و نسخهٔ موبایل راهنما پاس‌اند.
  فایل‌های v2 حفظ‌اند؛ هیچ src/UI/config/build/مجوز مالی یا halt تغییر نکرده و
  مدل/API مصرف نشده است. کیفیت مدل و ارزیابی نهایی با بازطراحی اسلاید بسته نمی‌شوند.

- [x] **C4z — بررسی منبع خام و اصلاح نسخه‌دار default؛ ساسان، آفلاین.**
  [شرح و محدودیت‌ها](../docs/core-raw-defaults.fa.md)،
  [تغییر دقیق headerها](../experiments/core_raw_defaults_v1/comparison.fa.md) و
  [verification](../experiments/core_raw_defaults_v1/verification-v1.json).
  فایل خام کامل با hash/Git blob، دو رکورد با pointer و seedهای قدیمی بایت‌به‌بایت
  تطبیق یافتند. metadata خام1.49 برای type/disabled، null وis دارد؛ signature
  و AST کد رسمی1.49، secondary وFalse را تأیید می‌کنند؛ parser تاریخی بازاجرا نشد.
  normalizer مستقل فقط default-header را از literal صریح signature می‌سازد و
  required/None/unresolved را جدا نگه می‌دارد؛ کل raw JSON و بدنهٔ متن محفوظ است.
  مشتق، هویت تازه دارد و کاملِ سند خام نیست؛ examples/deprecation در JSON باقی‌اند.
  ۸۲۴تست مرتبط شامل۱۲۴کنترل تازه، Ruff/format۴۴۱فایل و review مستقل پاس؛
  دو خطای import اجرای مستقل با bootstrap فقط تست رفع و شکست اولیه حفظ شد.
  هیچ corpus/build/gold/پاسخ قبلی یا src/UI/config عوض نشد؛ C4x/C4y بایت‌به‌بایت
  ثابت‌اند، watch۱۱۷/مالی۲۱، halt/سهhold و۷نوبت مصرف‌نشدهٔ جلسه محفوظ‌اند.
  API مدل و ledger write صفر؛ این تیک، کیفیت مدل یا اتصال واقعی را نمی‌بندد.

- [x] **C4y — review کیفی سه candidate و نمایش مسئلهٔ منبع؛ ساسان، آفلاین.**
  [نتیجه و حد review](../docs/core-parameter-review.fa.md)،
  [متن سه inspection](../experiments/core_parameter_review_v1/comparison.fa.md) و
  [verification](../experiments/core_parameter_review_v1/verification-v2.json).
  AI review هر سه انتخاب را برای سؤال محدود فعلی مرتبط دید؛ سؤال اضافهٔ کاربر
  لازم تشخیص داده نشد. این داوری انسانی یا آزمایش انتخاب مدل نیست. defaultِ
  `type/disabled` در source مشکل دارد و طول span هر سه با excerpt متفاوت است.
  inspection تازه citation امن، هشدار منتخب/peer و مختصات صریح داخل excerpt دارد؛
  اختلاف طول با trim مرز سازگار است و خرابی index را ثابت نمی‌کند.
  هیچ منبع/default/offset اصلاح نشد. candidate و payload/receiptهای C4x عیناً حفظ‌اند.
  ۷۰۰تست مرتبط شامل۱۰۰کنترل تازه، Ruff/format۴۳۶فایل و review مستقل پاس؛ شکست دو
  assertion متنی و بازاجرای موفق هم ثبت شد. فقط experiment/test/docs؛ watch۱۱۷فایل،
  binding۲۱فایل، halt/سهhold و مسیر جلسه ثابت، API/ledger write تازه صفر.

- [x] **C4x — تعریف کامل پارامتر برای پاسخ کوتاه‌تر؛ ساسان، آزمایش آفلاین.**
  [شرح](../docs/core-parameter-focus.fa.md)، [مقایسهٔ متن‌ها](../experiments/core_parameter_focus_v1/comparison.fa.md)
  و [verification](../experiments/core_parameter_focus_v1/verification-v1.json).
  هشت attempt/هفت turn آشکار C4v حفظ و عیناً بازسازی شدند. سه انتخاب تألیفی
  `icon/type/disabled` متن‌های۹۵۵۱/۹۱۹۰/۴۵۵۲را به۱۳۵۷/۱۱۹۳/۸۶۰کاراکتر رساندند؛
  تمام تعریف پارامتر، گزینه‌ها و source کامل برای review محفوظ است. کنترل پس از
  مشاهدهٔ فقط یک source هم ثبت شد؛ تغییر renderer مانع ادعای اثر خالص یک عامل است.
  ۶۰۰تست مرتبط شامل۱۹۰کنترل تازه و Ruff/format۴۳۰فایل پاس؛ review مستقل انجام شد.
  ناسازگاری headerهای default منبع ثبت و اصلاح خودسرانه نشد. فقط experiment/test/docs
  اضافه شده؛ UI/مدل/renderer فعلی،۲۱فایل مالی و watch۱۱۷فایل عوض نشده‌اند.
  API تازه/ledger write صفر؛ healthcheck جلسه بدون provider پاس،۷نوبت مصرف‌نشده.
  کیفیت انتخاب مدل، usefulness، relevanceِ multiselect و fixِ Enum هنوز اثبات نشده‌اند.

- [ ] **C4x-next — review انسانی و تصمیم اتصال نسخه‌دار؛ ساسان، اختیاری پس از جلسه.**
  candidateهای بالا هنوز پیشنهاد قابل approval نیستند. پیش از هر اتصال باید relevance،
  caveatهای خارج پارامتر، ناسازگاری default منبع و usefulness بررسی شوند؛ سپس قرارداد
  تحویل و مقایسهٔ تازهٔ انتخاب مدل با مسیرهای غیرپاسخ جدا ثبت شود. AI review و source
  inspection در C4y و بررسی خام/default/span در C4z انجام شد؛ review انسانی،
  استخراج کامل‌تر examples/deprecation و رفع تعارض prose هنوز باقی است. اتصال
  normalizer به builder/profile فقط در نسخهٔ تازه و با pin/قرارداد مستقل بررسی شود؛
  build فریز‌شده بازنویسی نمی‌شود.
  scope/watch جلسه برای این کار تغییر نمی‌کند.

- [x] **C4w — نسخهٔ داورپسند و کنترل نهایی اجرای جلسه؛ ساسان.**
  [شرح و فرمان healthcheck](../docs/presentation-readiness.fa.md)،
  [رسید](../docs/receipts/presentation-readiness-2026-10-18.json) و
  [PDF تاریخی ۱۳اسلایدی v2](../docs/presentation/judges-presentation-fa-v2.pdf).
  نمای خواندنی GET-only از UI اپراتور جداست؛ متن کامل پاسخ و منابع حفظ می‌شود.
  watch جدا۱۱۷فایل عمومی source/config را کنترل می‌کند،۲۱فایل مالی و protocolها
  ثابت‌اند؛ drain در ASGI بیرون lockِ owner انجام می‌شود و متد مستقیم قدیمی دست‌نخورده.
  healthcheck index فیزیکی/ظرفیت نوبت/API/SQLite/PDF را بدون key/provider بررسی
  می‌کند.۶۷۳۶تست توسعه با۵مصرف‌کنندهٔ محافظت‌شدهٔ deselect‌شده،۱۲۹کنترل تازه
  داخل همین شمارش،۲۶کنترل launcher جدا، Ruff/format۴۲۳فایل و سازگاری۱۰۳package
  پاس؛ review مستقل انجام شد. پایش GET حدود۲ساعت۵۰دقیقه/۳۴۰نمونه، فقط یک نمونه
  هنگام restart برنامه‌ریزی‌شده ناموجود؛ load test یا uptime پیوسته نیست.
  جلسه هنوز۰درخواست/۷نوبت باقی دارد؛۴۰۸۷ردیف قدیمی/۱۴جدول،halt/سهhold ثابت‌اند.
  PDF اصلی متن آزمایش/command/Q&A ندارد؛ یادداشت خصوصی و مرجع چتv5 جداست.
  کیفیت مدل، C5 و native/test نهایی با این تیک بسته نمی‌شوند.

- [x] **C4v — پذیرش زندهٔ محدود ارائه؛ ساسان، بدون تغییر کار native gold/test.**
  [راه‌اندازی و مرز مجوز](../docs/presentation-live.fa.md)،
  [رسید پذیرش](../docs/receipts/presentation-live-acceptance-2026-10-17.json).
  مسیر مستقل `presentation_scoped_v1` با GroundedPlan، gpt-4o-mini، retrieval v2،
  Chroma v3 و SQLite واقعی آماده است. ۱۲۶۷تست مرتبط/۴۰فایل امن، ۵۹کنترل تازه
  داخل همان شمارش و Ruff/format۴۱۳فایل پاس؛ review مستقل انجام شد. پذیرش
  واقعی۷نوبت/۸درخواست (۳نوبت مرورگر UI و۴نوبت client همان backend)، مدل
  `gpt-4o-mini-2024-07-18` و usage ثبت‌شده؛ هزینهٔ تخمینی `$0.006429390`.
  correction1.50→1.49، stale409بدون تغییر، approval/retry/reopen و restart واقعی
  هر۳پرونده پاس؛ retry درخواست مدل یا Action اضافه نساخت. کیفیت **جزئی** است:
  منابع type/disabled/icon دکمه رسیدند، ولی جواب multiselect کم‌ربط و متن‌ها
  طولانی‌اند؛ نمرهٔ کیفیت نهایی یا حل Enum ادعا نمی‌شود. تمرین بسته شد؛ scope
  مستقل ارائه۷نوبت/۱۴درخواست/سقف۰٫۱۰دلار هنوز مصرف نشده. halt/سهhold و تمام
  ردیف‌های قدیمی ledger محفوظ‌اند؛ مجوز اصلی/C5 حل نشده و تمدید خودکار نداریم.
  PDF۱۶اسلاید، sourceHTML، یادداشت گفتاری، مرجع چتv4، runbook و launcher در
  خروجی مستقل `output/presentation-2026-10-18/` تحویل می‌شوند؛ فایل‌های خصوصی
  مدل/کلید/صوت وارد Git نمی‌شوند. backend عادی و آفلاین قبلی محفوظ‌اند.

- [ ] **M2 — آخرین آمادگی جلسه؛ ساسان و تیم.** ساعت تمرین با علیرضا باید تأیید
  شود؛ ۴۵دقیقه قبل از جلسه health/pin/ظرفیت scope و فایل‌های پشتیبان بررسی
  شود. اجرای test/native gold/packet نهایی با محمدحسن می‌ماند؛ حسن rebuild
  تازه لازم ندارد و بهنام می‌تواند شاهد Windows را تکمیل کند. نتیجهٔ تحویل‌نشده
  را در اسلاید ادعا نکنیم؛ تغییر feature پس از pin نداریم.


- [x] **C4u-M1 — آمادگی نمایش جلسه؛ ساسان.** [برگهٔ فارسی](../docs/meeting-brief.fa.md) و [healthcheck](../docs/receipts/meeting-readiness-2026-10-17.json) آماده‌اند؛ ۱۶۷تست تازه UI/API/SQLite و۳demoآفلاین پاس، UI و backend محلی با DB جدا سالم‌اند. README و فرمان توسعه با freeze۹۵ و۵مصرف‌کنندهٔ محافظت‌شده هماهنگ شد. halt حفظ؛ nativegold/config/C5/testکیفیت نهایی همچنان بازند.

- [x] **C4u-v3 — پذیرش فیزیکی rebuild frozen95؛ ساسان با حسن.** PR91 review مستقل و build محلی تازه دارد؛ ۱۲۲۸source/۱۸۲۷chunk و همهٔ pinهای v3، counts و exclusion منطبق؛ deterministic/historical و دو سرچ خنثی adapter پاس. [رسید](../docs/receipts/final-build-v3-core-acceptance-2026-10-17.json). منبع اجرایی ثابت و۹۲۲تست C4u معتبرند؛ تکرار packet/model یا کیفیت نهایی ادعا نمی‌شود. halt/سهhold/test محافظت‌شده حفظ‌اند.

- [x] **C4u — پذیرش build گسترده و profile نسخه‌دار؛ ساسان با حسن.**
  [شرح](../docs/final-build-core-acceptance.fa.md)، [رسید](../docs/receipts/final-build-core-acceptance-2026-10-17.json).
  build۱۲۲۸source/۱۸۲۷chunk محلی با pinهای pre-freeze برابر شد؛ native/profile/API/SQLite/runner واقعی با provider mock پاس. profile صریح `grounded_candidate_prefilter_v2` و binding جدا، v1/defaultها ثابت؛ regression نسخهٔ طولانی رفع شد.۹۲۲تست مرتبط/۲۹فایل،۹۶کنترل تازه داخل همان شمارش، Ruff۴۰۷فایل و review مستقل پاس. بازپخشdev۲→۴از۱۶requirementسازگار درbundleاست؛ مدل/کیفیت/testنهایی نیست. PR87 تأییددوdev؛ PR88 custody؛ PR89 freezeمنابع/exclusion۹۵؛ PR90 دستورreceiptتازه با ورودیsplitفریز شده. payloadheld-out/exposure بازنشده؛ halt/سهhold حفظ؛ APIپرداختی صفر.


- [x] **U4a/T4c — بازکردن پروندهٔ ذخیره‌شده در session تازه؛ ساسان، کمک مستقل UI.**
  [رفتار و مرز](../docs/saved-case-reopen.fa.md)،
  [رسید مشترک](../docs/receipts/team-closeout-2026-10-17.json).
  Open saved case با ID معتبر فقط GET دارد؛ facts/history/revision/proposal
  جاری را پس از session تازه و restart واقعی backend روی TCP می‌خواند.
  case ناموجود یا پاسخ خراب انتخاب را عوض نمی‌کند؛ approval/retry/model خودکار
  نداریم. lost-ACK سپس reopen همان Action را یک بار نشان می‌دهد. envelopeهای
  نامطمئن همان session محفوظ‌اند؛ draft/ReviewOperation گم‌شدهٔ session قبلی
  بازسازی نمی‌شود و durable outbox اضافه نشده است.۴۱کنترل تازه؛۳۷۸تست مرتبط
  مشترک و Ruff/format۳۹۵فایل پاس، review مستقل بدون blocker؛ کیفیت مدل نیست.

- [x] **T4b/C4t — پذیرش PR82/84 و capture ورودی واقعی پس از خطا؛ ساسان با بهنام.**
  [توضیح](../docs/failure-context-custody.fa.md)،
  [رسید](../docs/receipts/team-closeout-2026-10-17.json).
  سند عملیاتی بهنام با محدودیت pin تاریخی/proxy خصوصی پذیرفته شد؛ بازتولید
  Windows تازه ادعا نمی‌شود. دو تست PR84 و یک capture مستقل روی دو نوع خطا
  پاس‌اند: outcome تاریخی درDB، replay بدون allocation/retrieval/reasoning،
  اصلاح نسخه در query واقعی و استقلال caseها. outcome خطای قبلی وارد reasoning
  بعدی نمی‌شود؛ یکسان‌بودن تصمیم scripted به‌تنهایی bug یا یادگیری/عدم‌یادگیری
  مدل نیست. قرارداد outcome تازه یا recipe جدید فعال نشده؛ T4 کلی تیک نمی‌خورد.

- [x] **E2ae — ثبت opaque native test در PR83 و پاک‌سازی plan؛ ساسان.**
  [مرز review و exposure](../docs/pr83-custody.fa.md).
  ۱۵path/metadata و custody Git بررسی شد؛ payload/review مربوط بهheld-out باز
  یا اجرا نشد. ادعاهای review انسانی و۲۶۰check با مالکevaluation است، نه تأیید
  مستقل core. یک جزئیات test در plan مشترک دیده و قبل انتشار از HEAD حذف شد؛
  اثر همان exposure محدود باید خصوصی با مالکeval تعیین تکلیف شود. tree/review
  اصلی حفظ‌اند؛ test را کاملاً دیده‌نشده یا frozen اعلام نمی‌کنیم. pinها pending؛
  دادهٔtest برای prompt/retrieval/model/vocabulary یا تغییر core استفاده نشد.

- [x] **E2ad — بررسی pin/freeze و رد native نهایی با pin ناقص؛ ساسان.**
  [قرارداد و ترتیب freeze](../docs/native-freeze-readiness.fa.md)،
  [رسید](../docs/receipts/native-freeze-readiness-2026-10-16.json).
  counterexample ساختگی قبلاً با native_scope موقت از gate می‌گذشت؛ اکنون
  pin ناقص، label/hash ناسازگار و binding متفاوت قبل از adapter رد می‌شوند.
  SHA corpus یعنی فایل corpus ارزیابی؛ hash index فیزیکی جداست. خروجی فقط
  count/hash است؛ physical/semantic verification ادعا نمی‌کند. مسیر dev و
  fixed قبلی ثابت؛ ۲۷۹تست مرتبط شامل۷۰کنترل تازه و Ruff/format۳۹۲فایل پاس‌اند.
  آخرین Git اعضا: PR72/81 رویmain، push/PR تازه در snapshot بررسی دیده نشد.
  هر۱۶native dev هنوز pending و فاقد family_id/coverage witness نهایی است؛
  تأیید انسانی دو بند تازه با محمدحسن. بیلد گسترده‌ترِ حسن به protocol/loader
  سازگار نیاز دارد؛ pilot بستهٔ۱۸source را relabel نکنیم. همهٔ۲۲artifactnative،
  test/exclusion، halt/سهhold و۱۹pin حفظ‌اند؛ API و پیام صفر. freeze بسته نشده.

- [x] **E2ac — اصلاح دو ابهام gold در PR81 روی dev؛ ساسان.**
  [شرح و بازتولید](../docs/native-dev-gold-amendment.fa.md)،
  [رسید](../docs/receipts/native-dev-gold-amendment-2026-10-16.json).
  دو شرط initial escalation برای fragment/tabs دیگر ادعای fix بدون شاهد را
  لازم نمی‌دانند؛ کمبود مهمِ واقعی، قدم بعدی و حفظ راهنمایی مستند شرط‌اند.
  USER نسخهٔ1.37.0 را گفته؛ gap منبع سؤال مجدد نسخه نیست. ثبت فعال dev v2
  دقیقاً۱۴fixtureقبلی+۲نسخهٔجدید است؛۱۸فایلv1 و review انسانی آن عین byte
  محفوظ‌اند. answer، follow-up، passage/hash، ورودی، script و route ثابت‌اند.
  اجرای scripted تازه۱۶case/۲۳turn/۲۷۳check پاس؛ این RAG/کیفیت مدل تازه نیست.
  ۲۳۳تست مرتبط شامل۱۰regressionتازه و Ruff/format۳۹۱فایل پاس؛ بررسی گستردهٔ
  قبلی تکرار نشده و CIسبز ادعا نمی‌شود. نقص helper تست اولیه اصلاح و log حفظ شد.
  review مستقل معنایی و hash-graph بدون blocker؛ تأیید انسانی دو بند تازه و
  pin بیلد نهایی هنوز pending است. test باز نشد؛ runtime/config/vocabulary،
  exclusion، halt/سهhold و۱۹pin ثابت‌اند؛ API و پیام صفر. freeze مشترک باز است.

- [x] **C4s — پذیرش تنظیم منتخب از کل runner و تصحیح review؛ ساسان.**
  [شرح و دستور](../docs/core-selected-runner-acceptance.fa.md)،
  [verification](../docs/receipts/core-selected-runner-acceptance-2026-10-16.json).
  factory واقعی، conditional runner، index و ledger موقت و HTTP mock:
  چهار مسیر سالم/repair/توقف JSON/timeout در دو phase؛۸کنترل تازه پاس‌اند.
  binding/phase/accounting/engine و عدم ورود gold/script/پاسخ آینده بررسی شد؛
  حساب unresolved، factory/allocation بعدی را پیش از key/index/send می‌بندد.
  runner حافظه‌ای است؛ این تست SQLite/restart یا کیفیت مدل تازه نیست.
  ۲۹۷تست مرتبط تازه و review مستقل۸تست، Ruff۳۸۹فایل پاس؛ runtime و تست‌های
  قبلی ثابت‌اند، بررسی گستردهٔ C4r دوباره اجرا نشده است. halt/سهhold/۱۹pin و
  test/exclusion ثابت‌اند. ادعای rollback plan درPR81 تصحیح شد: diffازmerge-base
  +۱/-۰ و merge سه‌طرفهٔ خودplan بی‌تعارض است؛ receiptقدیمی حفظ شد. دو ابهام
  native gold بعداً درE2ac اصلاح شدند؛ pinبیلد و تأییدانسانی تازه pending است. T4sessionrecovery،
  humanquality،freeze وC5/testنهایی همچنان بازند. APIپرداختی/پیام صفر.

- [x] **C4r — انتخاب recipe تحویل core و تطبیق با factory/backend واقعی؛ ساسان.**
  [تنظیم و اتصال](../docs/core-delivery-selection.fa.md)،
  [recipe](../config/core-delivery-grounded-v1.json)،
  [verification](../docs/receipts/core-delivery-selection-2026-10-16.json).
  `grounded_candidate_v1`: مدل `gpt-4o-mini`، compact GroundedPlan، candidate
  relevance و renderer قبلی؛ vocabulary بازبینی‌شدهٔ dev بدون تغییر pin شد.
  selector اختیاری در factory موجود، تنظیم مغایر را پیش از key رد می‌کند؛
  owner/planner/sender و renderer پیش از ارسال دوباره تطبیق می‌یابند.
  metadata قبلی حفظ است؛ runner binding و compact diagnostics مجاز را ثبت
  می‌کند و metadata ناسازگار را رد می‌کند. پذیرش factory واقعی با index/SQLite
  موقت و provider mock، correction، stale409، restart/retry و Action یکتا را
  پوشش می‌دهد. source `9fdb132`: تعداد۶۲۶۵تست توسعه در دو context پاس؛۱۲۹تست
  تازه داخل همین شمارش‌اند. reviewهای مستقل۴۷/۱۲۱هم‌پوشان، Ruff۳۸۸فایل و
  سهdemoپاس‌اند؛ یک مصرف‌کنندهٔheld-outکنارگذاشته شد، نه اجرایtestنهایی.
  انتخاب نرم‌افزاری core بسته شد؛ freeze نهایی index/gold، usefulness انسانی،
  C5 و test نهایی بسته نیستند. Enum fix تأییدشده ندارد؛ halt و سه hold حفظ‌اند.
  **PR81** فقط dev-native بررسی شد؛ دو قاعدهٔ fix بدون passage بعداً درE2ac
  با v2 افزایشی اصلاح شدند؛ تأیید انسانی تازه/pinبیلد pending است. ادعای قبلی rollback plan اشتباه بود:
  diff از merge-base فقط یک خط اضافه می‌کند؛ [تصحیح C4s](../docs/core-selected-runner-acceptance.fa.md).
  پیام ارسال نشده است.

- [x] **C4q — بستن اتصال ثبت تنظیم به ساخت reasoner؛ ساسان.**
  [تحویل core و شرط‌های پایان](../docs/core-closeout.fa.md)،
  [verification](../docs/receipts/core-freeze-closeout-2026-10-16.json).
  envelope v2، policy renderer و v1 معتبر را bind می‌کند؛ mismatch قبل از
  callback رد می‌شود. flagها و catalog واقعی از snapshot ثبت‌شده ساخته می‌شوند.
  v1 و default/factoryهای قبلی تغییر نکرده‌اند؛ مسیر جدید تزریق صریح است.
  receipt فقط ساخت reasoner را تأیید می‌کند، نه planner/model، engine، code/index،
  بودجه یا کیفیت. انتخاب تنظیم نهایی و freeze همچنان کار مشترک است؛ halt و سه
  hold حفظ‌اند. کار بعدی core، پشتیبانی از freeze/اجرای نهایی است؛ feature تازه
  در اولویت نیست. source `9f24376`: ۵۸۰ تست مرتبط تازه، review مستقل ۲۷۱ تست،
  سه دمو و Ruff روی ۳۸۱ فایل پاس؛ ۴۵+۱۸ کنترل تازه در شمارش‌های هم‌پوشان‌اند.
  صفر تلاش محافظت‌شده/شبکه در parent ثبت شد؛ audit شامل تمام subprocessها نیست.
  ledger و ۱۹ pin ثابت‌اند. بررسی گستردهٔ C4p تاریخی است؛ full-suite تازه برای
  این تغییرِ صرفاً افزایشی ادعا نمی‌شود.


- [x] **C4p — قالب بررسی maintainer و خوانایی Enum؛ ساسان.**
  [رفتار و اتصال](../docs/maintainer-review-brief.fa.md)،
  [verification](../docs/receipts/maintainer-review-brief-2026-10-16.json)،
  [replay](../docs/receipts/maintainer-review-brief-replay-2026-10-16.json).
  گزینهٔ صریح `review_brief=True` در دو reasoner، گزارش USER، نسخهٔ جاری، همهٔ
  منابع عرضه‌شده، gapهای جدا و قدم پیشنهادی بازتولید را مرتب می‌کند. CRLF فقط
  در نمایش دادهٔ USER اصلاح می‌شود؛ source و prompt/hash/span تغییر نمی‌کنند.
  ۸۴ کنترل تازهٔ root و ۲۱ کنترل review مستقل پاس‌اند؛ ۶۶۷ تست متمرکز مستقل
  هم پاس شدند و با suite جمع نمی‌شوند. روی source `85d89ea`، تمام ۶۰۷۳ تست
  توسعهٔ انتخاب‌شده پوشش موفق در دو context دارند: ۶۰۶۸ در CWD خنثی و پنج
  تست مسیر نسبی از root. یک مصرف‌کنندهٔ held-out عمداً کنار گذاشته شد؛ اجرای
  یک‌تکهٔ بی‌خطا ادعا نمی‌شود. canonical ask، retrieve_more و defaultها حفظ‌اند. ۱۷ پیشنهاد تازهٔ آرشیوی، ۱۵۳ کنترل ساختاری پاس؛ ۱۲ entry دیگر هم
  ثبت‌اند، نه ۱۲ turn مستقل. Enum draft ارجاع ۲۸۶۴/۳۳۰۲ به ۳۰۶ و answer بلند
  ۱۲۲۰۱ به ۹۳۸۳ کاراکتر رسید؛ تمام quoteهای انتخاب‌شده حفظ‌اند. این‌ها replay
  همان انتخاب‌های قدیمی‌اند؛ usefulness یا تشخیص/fix تازه تأیید نشده است.
  متن تازه handoff/review تازه لازم دارد؛ approval قبلی قابل انتقال نیست.
  factory/config نهایی تغییر نکرد؛ descriptor v1 این policy را bind نمی‌کند.
  انتخاب و ثبت policy، review انسانی و freeze باقی‌اند؛ halt و سه hold حفظ‌اند.


- [x] **C4o/E2ab — پذیرش PR79 و مشاهدهٔ دقیق passage برای native review؛ ساسان.**
  [رفتار و اتصال](../docs/native-evidence-review.fa.md)،
  [review PR79](../docs/receipts/pr79-review-2026-10-16.json)،
  [تست‌ها و review مستقل](../docs/receipts/native-evidence-review-2026-10-16.json).
  v2 سه dev با rubric v1 و **شواهد ثابت** پذیرفته شد؛ native gold نیست.
  fixtureهای قدیمی و فایل‌های review صاحب بخش حفظ‌اند. هشت کارت تغییر پس از
  توضیح دستیار تأیید شده‌اند؛ این عدد نمرهٔ کیفیت مدل نیست. اجرای scripted تازه
  روی سه case، شش turn و ۷۹ check پاس شد. report v3 فقط pin جدید manifest دارد.
  disclaimer برای tip بی‌منبع، support ادعای مهم را از صفر خارج نمی‌کند؛
  decision و usefulness جدا هستند. شش کنترل scorer موجود این مرز را می‌سنجند.
  observer جدید فقط حضور passage کامل را با source/revision/URL و hashهای مستقل
  ثبت می‌کند؛ ۵۲ تست دارد و به runner یا runtime متصل نشده است. حضور متن اثبات
  support یا مصرف provider نیست؛ نبود آن هم خودکار escalation را درست نمی‌کند.
  روی source `783362c`، تمام ۵۹۶۸ تست توسعهٔ انتخاب‌شده در دو context پوشش موفق
  دارند: ۵۹۶۳ در CWD خنثی و پنج تست مسیر نسبی از ریشهٔ مخزن. یک مصرف‌کنندهٔ
  held-out عمداً کنار گذاشته شد. **یک اجرای یک‌تکهٔ بی‌خطا ادعا نمی‌شود.**
  شکست‌های اولیه، logها و IDهای rerun حفظ‌اند؛ کد یا guardها برای عبور تغییر
  نکردند. audit دو اجرای نهایی فقط parent را پوشش می‌دهد، نه تمام subprocessها.
  review مستقل، Ruff و بررسی حفظ ۱۹ pin پاس‌اند؛ runtime و defaultها ثابت‌اند.
  ledger، سه hold، halt و exclusion حفظ‌اند؛ C5 read-only برابر ۳۶/۳۶، API صفر.
  **مانده:** native gold/routes و worksheet C4j با محمدحسن؛ corpus و build نهایی
  با حسن. بیلد ۱۸ منبعی فعلی release note، منبع forms.md و API نسخهٔ 1.22 ندارد.
  native gold مربوط به test را فقط مالک evaluation پیش از retrieval نهایی ثبت
  می‌کند؛ gold وارد prompt/RAG نمی‌شود. freeze، C5، کیفیت Enum و test نهایی بازند.

- [x] **E2aa — اصلاح گزارش PR78 با state واقعی core؛ ساسان.**
  [رفتار و دستور بازتولید](../docs/question-coverage-state.fa.md)،
  [verification و review](../docs/receipts/question-coverage-state-2026-10-16.json).
  سه counterexample قبلی دوباره ثبت شدند؛ سؤال بی‌پاسخ fact نمی‌سازد، state
  شاخه‌ها و پرونده‌ها جداست و normalization/intake/catalog واقعی استفاده می‌شود.
  availability در همه/بعضی/هیچ مسیر ثبت می‌شود؛ این مسیرها فرض fixture هستند،
  نه مدل/approval/release واقعی. bounds و رد صریح workflow پشتیبانی‌نشده برقرارند.
  default فقطdev؛ مسیر held-out حتی با manifest اشتباه پیش از read رد می‌شود.
  rawSHA و تعریف vocabulary از یک snapshot می‌آیند؛ output قدیمی بازنویسی نمی‌شود.
  v1 و review اولیه عین byte حفظ‌اند؛ v2 فقطdev:۱۶fixture،۱۱ask در همهٔ مسیرها
  در دسترس،۴extraoffer؛ شمارش فعلی بهتر نشده و کیفیت مدل اندازه‌گیری نشده است.
  source`a9f4358`:۴۸تست مرتبط و۵۹۰۹تست توسعه پاس؛ یک مصرف‌کنندهٔ held-out صریحاً
  deselect،۰readمحافظت‌شده. review مستقل۴۸تست را تکرار کرد؛ Ruff۳۷۱فایل پاس.
  source اجرایی/API/UI/tracker/config ثابت است؛ HTTP/SQLite۴۵۷/۴۵۷ C2k استفاده
  شده، نه اجرای تازه.۱۹pin،ledger،سهhold/halt،gold/manifest/exclusion وdefault
  محفوظ‌اند؛ C5read-only۳۶/۳۶ وAPIصفر. CI موفق ادعا نمی‌شود.
  بازخورد انسانی ارجاع وCRLF در [آمادگی freeze](../docs/enum-freeze-readiness.fa.md)
  ثبت شد؛ renderer یا نمره‌ها تغییر نکردند. E1/E2/E4،native gold/routes،v2 سه dev،
  review usefulness،freeze وC5/testنهایی همچنان بازند؛ پیام ارسال نشده است.

- [x] **C4n — review Enum و binding تنظیمِ کاندیدای freeze؛ ساسان.**
  [نتیجه، اتصال و gateها](../docs/enum-freeze-readiness.fa.md)،
  [verification](../docs/receipts/enum-freeze-readiness-2026-10-16.json).
  سه شکست مستند Enum دوباره بررسی شدند: شاهد مرتبط غایب، انتخابِ فاقد بدنه/caveat
  و ادعای نسخهٔ بی‌پشتوانه. نسخه/کد USER معلوم‌اند؛ سؤال دوباره راه‌حل نیست.
  replayهای موجود۶۲/۶۲و۸۱/۸۱عین byte آرشیو ماندند؛ مدل/API تازه،fix تأییدشده
  یا نمرهٔ انسانی تازه نداریم. guide همچنان fixture-only و Enum حل‌نشده است.
  metadata قدیمی config برای دو تنظیم متفاوت یکسان بود؛ helper خصوصی و صریحِ
  descriptor/comparison،flagها/bounds/policy/vocabulary وpinهای اعلام‌شده را
  bind می‌کند. legacy config/factory/runner/default تغییر نکرد؛ hook فعال یا
  candidate نهایی انتخاب نشده و runtime/quality/live مجاز نمی‌شود. pinها صرفاً
  declaration هستند، نه مشاهدهٔ تأییدشدهٔ فایل/سرور.۳ایراد پیش از انتشار helper
  شامل env کتابخانه و دو مشکل Decimal با شواهد حفظ و اصلاح شدند.
  source`99e3bc6`:۱۰۳تست جدید،۱۹۷تست متمرکز root و۵۸۶۱تست توسعهٔ تازه پاس؛ یک
  مصرف‌کنندهٔ held-out صریحاً deselect و readصفر. Ruff۳۶۹فایل و review مستقل
  پاس؛ HTTP/SQLite۴۵۷/۴۵۷ C2k برای runtime دقیقاً یکسان استفاده شده، نه اجرای
  تازه. C5read-only۳۶/۳۶،ledger/۱۹pin/سهhold/halt/سقف وIDهای بسته محفوظ؛APIصفر.
  **در review اولیه، PR78محمدحسن درhead`3402a59`باز ماند:** دوP2در projection سؤال/شاخه و یک
  normalization؛ [رسید review](../docs/receipts/pr78-review-2026-10-16.json).
  dev-only۱۱/۱۱سؤال و۴extraoffer آرشیوی بازتولید شدند؛ test فقط summary عددی بود.
  در آن review فایل‌های صاحب بخش تغییر نکردند؛ اصلاح بعدی در E2aa بالای همین
  checklist ثبت می‌شود. review انسانی کیفیتِ تنظیم
  منتخب،native gold/routes،freeze مشترک وC5/testنهایی هنوز بازند؛ پیام ارسال نشد.

- [x] **پذیرش محدود PR77؛ review انسانی C4g دریافت شد.**
  [بررسی و توضیح شمارش](../docs/pr77-review.fa.md)،
  [رسید](../docs/receipts/pr77-review-2026-10-16.json). نمره‌ها و byteهای فایل
  محمدحسن حفظ‌اند؛۱۷item وbinding/handoffها تطبیق دارند.۷گروه با زمینهٔ متفاوت
  داریم و۶متن یکتا؛ usefulness۱٫۲۹میانگین گروه‌هاست،۱٫۴۷باوزن پیشنهادها.
  support هنوز بررسی نشده؛ export خصوصی و hash کامل workbench وابسته‌به‌مسیر
  کاملاً تأییدنشده‌اند. این partialreview روی devexposed است؛E4باز و انتخاب
  config نهایی/کیفیتtest نامشخص است. runtimeهمان`3f8ff33`تست‌شده باقی ماند.

- [x] **C2k — validation مرزهای باقی‌ماندهٔ core؛ ساسان، ۱۶ اکتبر.**
  [رفتار و حدود](../docs/core-boundary-validation.fa.md)،
  [verification](../docs/receipts/core-boundary-validation-2026-10-16.json).
  validator بازگشتی موجود پیش از serialize برای خروجی retrieval/analysis،
  transition کاربر، snapshot درخواست grounded/claim و hash منبع اعمال شد.
  ۱۶۹regression یکسان:۱۲۵fail/۴۴pass در baseline به۱۶۹pass؛۳۲digest کامل معتبر
  ثابت‌اند. source`3f8ff33`:۵۷۵۸تست توسعه تازه پاس، یک مصرف‌کنندهٔ محتوای test
  صریحاً deselect و صفر read به held-out؛Ruff۳۶۷فایل،سهdemo وHTTP/SQLite تازه
  ۴۵۷/۴۵۷باrestart/retry پاس‌اند. review مستقل۸۸۰تست منتخب و بررسی diff blocker
  ندارد. ledger،۱۹pin،سهhold،halt،قراردادها/defaultها و فایل‌های اعضا ثابت‌اند؛
  C5read-only۳۶/۳۶،APIصفر. خطای URL درEvidenceHit از قبل رد می‌شد و بهبود تازه
  حساب نشده؛ اصلاح، رد hidden state است. این تیک کیفیت مدل/RAG/test یا اتمام
  E1/E2/R4/T4/C5 نیست. بعضی مرزهای typed planner/context/config بیرون این scope
  هستند؛ authority bypass در آن‌ها مشاهده نشد. قدم بعدی،review انسانی کیفیت،
  freeze تنظیم/native scope و تطبیق provider برایC5 است؛ feature تازه اضافه نشد.

- [x] **healthcheck روز تحویل و پیش‌نویس گزارش؛ ساسان، ۱۶ اکتبر.**
  [گزارش و دستورهای demo](../docs/delivery-report.fa.md) و
  [رسید بررسی](../docs/receipts/deadline-healthcheck-2026-10-16.json).
  بررسی مستقل، باگ فوری تازه‌ای در core پیدا نکرد؛ runtime، قراردادها و
  تنظیم‌های پیش‌فرض تغییر نکردند. ۹۷ تست متمرکز تازه، چهار مسیر CLI با exit
  مورد انتظار و HTTP/SQLite تازه۴۵۷/۴۵۷ شامل restart/retry پاس‌اند. C5 نیز
  ۳۶/۳۶ کنترل read-only را پاس کرد؛ این به معنی رفع سه درخواست نامعلوم نیست.
  source اجرایی با `5bbb133` یکسان است؛ suite۵۵۸۹تستی قبلی دوباره اجرا نشده.
  فرمان توسعه در README/AGENTS/development اصلاح شد تا مصرف‌کنندهٔ محتوای
  held-out صریحاً deselect شود؛ collection تازه۵۵۸۹/۵۵۹۰ و یک deselection است.
  Ruff۳۶۴فایل و sync قفل‌شده پاس؛ ledger و۱۹pin فعلی ثابت، API صفر و halt محفوظ.
  گزارش، پیش‌نویس کمکی E5 است و مالکیت محمدحسن را عوض نمی‌کند. برای پایان
  واقعی هنوز مدرک provider برای C5، freezeِ native gold/routes و تنظیم‌ها،
  review انسانی کیفیت و اجرای نهایی held-out لازم‌اند؛ جزئیات و مالک هر gate
  در گزارش آمده. demo/بستهٔ صادقانهٔ تحویل امروز قابل آماده‌کردن است؛ اتمام
  تمام الزام‌ها از این healthcheck نتیجه نمی‌شود. توسعهٔ feature تازه متوقف
  می‌ماند تا همین gateهای باقی‌مانده بسته شوند.

- [x] **C4m/E2z و پذیرش R4b — اتصال split تازه؛ ساسان، ۱۶ اکتبر.**
  PRهای #70 تا #76 روی main دریافت شدند. metadata ثبت۳۱fixture،۱۶dev/۱۵test،
  ۱۴مسیر چندنوبتی شامل۷test وexclusion۹۰Issue را تأیید می‌کند؛ manifest هنوز
  draft است. محتوای test، gold آن و evidenceهای آن برای توسعه باز نشده‌اند.
  [تصمیم‌ها و اتصال](../docs/evaluation-readiness.fa.md)،
  [protocol و baseline پیش از تغییر](../experiments/evaluation_readiness_v1/README.md).
  vocabulary اختیاری تازه، دو سؤال dev فرم وstate را با همان قرارداد caller
  فعال می‌کند؛۲۵کنترل،۲۱digest پیش‌فرض و تعریف‌های تاریخی ثابت‌اند. سؤال آزاد
  ساخته نمی‌شود و هیچ تعریف یاalias از رویtest اضافه نشده است.
  مرز rubric تاریخی۲۱پذیرش متن اشتباه و۲۷diagnostic نامتناسب در۴۸fail را به
  رد ثابت پیش از output تبدیل می‌کند؛۶۲/۶۲تست و هر۷workbench معتبر عین baseline.
  برای gold، نسخهٔ native باfixture/scope/routes ثبت‌شدهٔ جدا انتخاب شد؛ این
  تحویل runner را چندشرطی نمی‌کند. rubricهای تاریخی وgold ثابت دست‌نخورده‌اند؛
  دامنهٔ تحویل text-only است، OCR/تصویر اضافه نشده است.
  PR72 فقط تست/رسید بود؛ بازپخش آن به کپی index وhash همهٔ فایل‌های اصلی منتقل
  شد. native واقعی۸state/query یکتا از۲۴درخواست آرشیوی،۱/۵→۳/۵availability را
  بازتولید کرد؛ exclusion۹۰Issue ونسخه‌ها پاس. key-identity در دو state اصلی
  با۱۴۵۱۸و۱۶۲۹۶byte ازبودجه۱۲۰۰۰رد می‌شود، نه capپنج؛ bundleها۲و۴hitدارند.
  پیش‌نویس label با تأیید حسن است، نه داوری مستقل کیفیت پاسخ. ranking/core
  selector/default تغییر نکرد؛ ادامهٔ packing/relevance فقط رویdev با حسن است.
  روی source ثابت`5bbb133`،۵۵۸۹pytest توسعه،Ruff۳۶۴فایل و سهdemo پاس؛ یک تست
  که تمام fixtureهای test را می‌خواند عمداً deselect شد، نه اجراشده/پاس. guard
  در اجرای موفق،read محتوای test نداشت.۱۶dev/۲۳turn با۲۷۳check وHTTP/SQLite
  ۴۵۷/۴۵۷ باrestart پاس؛ [verification](../experiments/evaluation_readiness_v1/verification-v1.json).
  تلاش اولِ harness و اصلاح منع اضافی.env ثبت‌اند؛ یک تفاوت ترتیب candidate
  native حفظ شده و final-hitهای۲۴arm دقیقاً برابرند. review جدا blocker ندارد.
  C5، سهhold، ledger،۱۹pin،exclusion وIDهای بسته حفظ‌اند؛APIصفر.
  CI به علت Billing اجرا نشده؛ E1/E2/R4/T4،freeze وtest نهایی بازند.

**جمع‌بندی پس از C2j — ۱۶ اکتبر:** audit آفلاینِ شکست‌های ثبت‌شده، انتخاب
شاهد، سؤال تکمیلی و نمایش پاسخ انجام شد؛ تغییر اجرایی تازه‌ای که بهبود معنایی
آن قابل دفاع باشد پیدا نشد. فعلاً توسعهٔ core را در همین checkpoint متوقف
می‌کنیم؛ تنظیم نهایی و کیفیت پاسخ تیک نمی‌خورند. ۲۴۵ تست مرتبط تازه پاس شدند؛
replayهای موجود ۶۲/۶۲ و۸۱/۸۱ عین receipt قبلی ماندند. suite کامل۵۴۷۹تستی و
HTTP/SQLite۴۵۷/۴۵۷ همان شواهد C2j برای source اجرایی یکسان‌اند، نه اجرای دوباره.
[شواهد و شرط ادامه](../docs/core-progress.md#post-c2j-checkpoint)،
[رسید audit](../docs/receipts/core-quality-checkpoint-2026-10-16.json).
قدم بعدی کیفیت: review انسانی relevance، بدنه/caveat و usefulness خروجی‌های
موجود؛ سپس فرضیهٔ تازه و config/protocol ثبت‌شده روی dev. C5 پیش از API تازه
به مدرک provider نیاز دارد. هیچ تغییر در RAG/UI/tracker تیم، corpus/exclusion،
gold، default یا ledger انجام نشد؛ halt/سهhold و تمام IDهای بسته حفظ‌اند.
این توقف موقتِ توسعه است؛ E1/E2/R4/T4/C5 و ارزیابی نهایی بازند.

- [x] **پاک‌سازی Git — ۱۶ اکتبر؛ با مجوز ساسان، بدون PR تازه.**
  ۴۸branch محلی و۶۱branch ریموت فقط پس از اثبات قرارداشتن کامل در main حذف
  شدند؛ دوworktree تاریخی بدون تغییر ذخیره‌نشده جمع شدند. main تنها branch
  محلی است؛ تاریخچه و receiptها در main و backup محلی Git محفوظ‌اند.
  [PR #43](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/43) باdiff
  خالی بسته شد؛ baseline/build/review در #45/#48/#55 تحویل شده بود.
  [PR #50](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/50) بدون
  merge بسته شد: مسیر متفاوت و تست‌شدهٔ #58/#59 جایگزین آن intent شده؛ کد
  PR50 ادغام یا معادلِ main اعلام نمی‌شود. سه branch ریموت ادغام‌نشده
  `feat/e3-eval-runner`،`feat/rag-baseline-3cases` و`fix/rag-relevance-ranking`
  حفظ شدند. کار تازه ازmain روز شروع شود؛ R4/E1/E2/T4/C5 و کیفیت نهایی همچنان
  شروط قبلی را دارند. کدِ source تست‌شدهٔ۵۴۷۹تستی تغییر نکرد؛ halt/سهhold،
  ledger،corpus/exclusion و pinها ثابت‌اند. این تیک housekeeping است، نه اتمام پروژه.

- [x] **T4a — review و merge رسیدهای پاک‌سازی‌شدهٔ بهنام؛ ساسان.**
  [PR #66](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/66) با
  head`0d21450` به main با`c69b0b4` رسید؛ دو JSON اصلی بدون تغییر حفظ‌اند.
  [پذیرش و محدودیت‌ها](../docs/pr66-review.fa.md)،
  [رسید review](../docs/receipts/pr66-final-review-2026-10-16.json).
  مشاهدهٔ دستی: قطع ACK پس از commit، Retry ازUI و Actionهای۰→۱→۱→۱؛ فقط
  backend آفلاین/synthetic. ۱۷۶ تست مرتبط محلی پاس؛ merge فقط همان دو JSON
  را اضافه کرده و source تست‌ها با suite قبلی۵۴۲۴تستی یکسان است، نه اجرای تازهٔ
  آن suite. fault pin دقیق ندارد؛ بازشدن Chrome پرونده/session تازه ساخته، پس
  recovery درخواست تأییدنشده در session تازه ثابت نیست. T4 کلی، failure/outcome
  و handoff ارزیابی بازند؛ CI به علت Billing شروع نشده؛ halt/سهhold حفظ‌اند.

- [x] **C2j — validation یکسان helperهای پاسخ نسخه؛ ساسان، تحویل آفلاین.**
  [protocol پیش از کد](../experiments/intake_validation_v1/protocol-v1.json)،
  [۱۶ baseline معتبر](../experiments/intake_validation_v1/valid-baseline-v1.json)
  و [مقایسهٔ آفلاین](../experiments/intake_validation_v1/comparison-v1.json).
  هر دو helper pending/approved با همان `detached_contract` پیش از dump
  بررسی می‌شوند؛ top-level/nested extra و دادهٔ خصوصی قبل از extraction با
  خطای ثابت`IntakeRejected("InvalidInput")` رد می‌شوند و ورودی تغییر نمی‌کند.
  ۵۵ تست تازه در baseline،۲۹fail/۲۶pass و پس از اصلاح۵۵pass؛۱۶ خروجی و transition
  معتبر دقیقاً ثابت‌اند. تست متمرکز با موارد قبلی۱۶۶pass؛ روی source ثابت
  `f780ca8`،۵۴۷۹pytest،Ruff۳۵۷فایل،سهdemo وHTTP/SQLite۴۵۷/۴۵۷ باrestart پاس.
  [راهنما](../docs/intake-validation.fa.md) و
  [verification](../experiments/intake_validation_v1/verification-v1.json)؛ review
  جدا۶۷تست را تکرار کرد و blocker ندارد. shared validator/contract، extraction،
  revision/dedup و authority tracker ثابت؛ API صفر،۱۹pin وledger ثابت، halt/سهhold
  محفوظ. hardening دو مرز درون Python است، نه auth یا بهبود مدل/RAG/test؛ فایل‌های
  RAG/UI/tracker تیم تغییر نکرده‌اند. CI پاس و Windows/browser تازه ادعا نمی‌شود.
  کد و شواهد در [PR #69](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/69)؛
  وضعیت انتشار همان PR مرجع است و مصرف تیم از `origin/main` باشد.

- [x] **C4l/E2y — context فعلی برای advisor انتخاب شاهد؛ ساسان، تحویل آفلاین.**
  [ثبت پیش از پیاده‌سازی](../experiments/core_selection_context_v1/protocol-v1.json):
  [کد و اتصال](../docs/selection-context.fa.md)،
  [packet و baseline](../experiments/core_selection_context_v1/README.md) و
  [replay۸۱/۸۱](../experiments/core_selection_context_v1/replay-v1.json).
  context خصوصی با کل CaseState/request/conversation bind شد؛ اصلاح موضوع،
  A→B→A، پاسخ کوتاه نسخه و رد context قدیمی/دست‌کاری‌شده تست شدند. نام fact و
  label به‌تنهایی امتیاز نمی‌سازند؛ همهٔ valueهای USER فعال حفظ‌اند. ۲۴digest
  حالت قبلی دقیقاً ثابت؛۸۰pytest متمرکز پاس. در fixture تألیفی، منبع موضوع فعلی
  از دوم به اول رفت، اما موضوع قدیمی در shortlist باقی می‌ماند؛ negation/synonym
  هنوز محدودیت‌اند. مدل/API/retrieval/default تغییر نکرده؛ halt/سهhold حفظ‌اند.
  [verification](../experiments/core_selection_context_v1/verification-v1.json):
  روی source ثابت`50a3f8d`،۵۴۲۴pytest،Ruff۳۵۶فایل،سهdemo وHTTP/SQLite۴۵۷/۴۵۷
  باrestart پاس؛ review جدا۱۲۳تست را تکرار کرد و blocker ندارد. replay قبلی
  ۶۲/۶۲ نیز عین رسید قبلی ماند؛ ledger و۱۹pin فعلی ثابت‌اند. تیک تحویل این
  کنترل اختیاری است، نه کیفیت مدل/RAG/test یا پایان C5. CI پاس ادعا نمی‌شود؛
  انتشار با مجوز صریح تست محلی ساسان است. PR۶۶ بهنام در آن تحویل جدا ماند؛
  پذیرش بعدی آن در T4a بالا ثبت شده است.
  کد، شواهد و راهنمای اتصال در [PR #67](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/67)؛
  وضعیت انتشار همان PR مرجع است و مصرف تیم از `origin/main` باشد.

- [x] **C4k/E2x — انتخاب شاهد کامل و بررسی فقط‌خواندنی C5؛ ساسان، تحویل آفلاین.**
  [ثبت پیش از پیاده‌سازی](../experiments/core_evidence_selection_v1/protocol-v1.json):
  [نتیجه/اتصال](../docs/evidence-selection.fa.md) و
  [packet و verification](../experiments/core_evidence_selection_v1/README.md).
  unit اختیاریِ section کامل، همراه بدنه/code و subtree؛ heading خالی از body
  answer نیست. همهٔ۱۶ default context/messages/render عین baseline ماندند.
  هر۱۰ plan نگهداری‌شده، سه binding ردشده و۲۱ خروجی خام ناموجود حفظ‌اند؛ هفت
  projection تألیفی، انتخاب تازهٔ مدل نیستند. body/caveat غایب Enum در بازپخش
  کامل شد، اما draft۱۴۵۹→۵۹۶۲ و median همان هفت خروجی۱۴۵۹→۵۰۷۳ شد؛ نقل نامرتبط
  همچنان ممکن است. lexical shortlist فقط advisory است؛ semantics/usefulness
  تأیید نشده، guide fixture-only و تیک پایان کیفیت/RAG/test نیست.
  ۶۲ کنترل replay،۱۱۰ تست جدید،۶۴ context واقعی engine/۳۲run با repair/refine و
  سقف قدیمی؛ بیشینه ورودی۲۷۳۶۶. ۵۳۴۴pytest،Ruff۳۵۲فایل،سهdemo و مسیر قبلی
  HTTP/SQLite۴۵۷/۴۵۷ با restart پاس؛ section mode در engine تست شده و factory/UI
  خودکار فعالش نمی‌کنند. دو ایراد جدید fence/body و auditor framing پیش از
  freeze رفع شدند؛ مشاهدهٔ اول و amendment حفظ‌اند؛ hosted CI پاس ادعا نمی‌شود.
  هر سه uncertain با۳۶ کنترل read-only بررسی شدند؛ ledger۷۱۸row/۱۴جدول، سهhold
  جمعاً$0.0301376،halt/سقف و۱۹ فایل محافظت‌شده ثابت‌اند؛ C5 به مدرک provider نیاز
  دارد. API/corpus/exclusion/gold/shared contracts و فایل‌های UI/tracker/RAG عوض نشدند.
  کد و شواهد در [PR #65](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/65)
  پس از review نهایی به main با`efaf02a` merge شدند؛
  [رسید merge و تطابق تست محلی](../experiments/core_evidence_selection_v1/merge-review-v1.json).

- [x] **انتشار محلی PR54/57/58؛ ساسان.** هر سه به‌ترتیب به main رسیدند؛
  source نهایی `3cbbdd3` همان tree تحویل PR58 است. اجرای کامل ثابت روی همین
  main:۴۱۵۰ تست پاس؛ [رسید انتشار](../experiments/local_release_2026_10_15/verification-v1.json).
  Actions همچنان به علت Billing اجرا نشده؛ اجرای تازهٔ Windows ادعا نمی‌شود.
- [x] **C4h6 — سؤال همراه با زمینهٔ مستند موجود؛ ساسان، تحویل محدود و opt-in.**
  [ثبت پیش از کد/API](../experiments/core_ask_background_v1/protocol-v1.json).
  فقط منابع انتخاب‌شده با نسخهٔ دقیق USER، بدون conflict، بعد از سؤال غیرنسخه‌ای؛
  متن کامل و qualified، با حفظ سؤال و fallback به سؤال در صورت عبور از سقف.
  [نتیجه و محدودیت‌ها](../experiments/core_ask_background_v1/README.md): شش job
  و هر۱۲ turn حفظ‌اند؛۱۱ fresh و یک stale، پنج route کامل از شش. A در هر دو
  تکرار کنار سؤال callback، متن مستند۱٫۵۰ را واقعاً released کرد؛ همان plan
  در OFF فقط۱۰۸ کاراکتر سؤال و در ON متن۷۸۷۰ کاراکتری دارد. اثر نمایش است،
  usefulness انسانی ثابت نشده و طول متن نیاز به review دارد. B همان راهنمای
  جزئی icon۱٫۳۹ را حفظ کرد؛ یک text_input بی‌ربط در summary اولیه هم دیده شد.
  Enum هنوز fix ندارد؛ یک correction پس از retrieve_more خروجی JSON نامعتبر
  داشت، پیشنهاد قبلی stale و approval آن۴۰۹ بود. schema خام۱۳/۱۴؛ این اجرا
  نسبت به R4c با۶/۶ route، بهبود پایداری کلی را نشان نداد. هزینه۱۴ send برابر
  تخمین$0.012407340؛۳۳۲۳ کنترل native/هزینه پاس،۴۷۹ reservation قبلی و۱۴ جدول
  حفظ؛ شش scope بسته و۱۰ slot مصرف‌نشده claimed. این‌ها همان سه dev دیده‌شده‌اند؛ test نهایی نیست.
- [x] **R4d/C2i — profile قابل اتصال retrieval؛ ساسان.**
  [راهنمای اتصال](../docs/candidate-live-profile.fa.md): profile اختیاری
  `candidate_relevance_v1` به engine هر دو مسیر API حافظه‌ای/runner و HTTP/SQLite
  می‌رسد؛ native پیش‌فرض ثابت است. wrapper runner نیز metadata را حفظ می‌کند.
  read واقعی۲۵ کاندیدا، نسخهٔ فعال پیش از cap، budget کامل۱۲۰۰۰، correction،
  approval متن دقیق و restart/retry با همان tracker تست شده‌اند. اجرای API تازه
  از named profile حافظه‌ای/runner بوده؛ provider ماک در پذیرش SQLite، live SQLite
  یا مرورگر تازه حساب نمی‌شود. [verification](../experiments/core_ask_background_v1/verification-v1.json):
  ۴۳۲۲pytest،Ruff۳۰۵فایل،سهdemo وHTTP/SQLite۴۵۷/۴۵۷ پاس؛CI اجرا نشده است.
  دو کنترل نوبت سوم، حفظ background در SQLite و عدم مصرف آن به‌عنوان متن قبلی
  دستیار در مدل، حفظ USERhistory و توقف بزرگ‌بودن پیش از هزینه را بررسی کردند.
  contracts/ports و فایل‌های UI/tracker تیم تغییر نکرده‌اند؛ E1/E2/T4/R4 نهایی بازند.
  انتشار هر دو task در [PR #59](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/59)
  مستقیماً با پایهٔ main است؛ review کد/گزارش و gate محلی طبق مجوز فعلی ثبت‌اند.

- [x] **C4h7 — JSON و نمایش کوتاه؛ ساسان، تحویل آزمایش و اتصال.**
  [رفتار و flags](../docs/json-readability.fa.md)،
  [protocol پیش از کد](../experiments/core_json_readability_v1/protocol-v1.json) و
  [رسید](../experiments/core_json_readability_v1/README.md): canary دو نوبتی پاس؛
  سپس دو دور متوازن روی همان سه dev/index۱۸/۳۶، دوازده job/۲۴نوبت.
  raw JSON و expansion هر دو arm۱۲/۱۲، پیشنهاد تازه۱۲/۱۲ و route۶/۶؛ بنابراین
  برتری نسبی JSON mode ثابت نشده. تمام۲۶نوبت با canary تازه‌اند؛ هیچ failure
  یا نوبت برنامه‌ریزی‌شده حذف نشده. renderer کوتاه روی همان plan: سؤال callback
  ۷۸۷۰→۱۲۲۰؛ summary/sourceها کامل، ولی passageهای API دیگر در سؤال منتشر
  نمی‌شوند. پاسخ button۴۹۹۹ و quote icon حفظ؛ Enum هنوز generic و بدون cause/fix.
  هیچ quote بریده یا متن فنی تازه تولید نمی‌شود؛ گزارش کامل USER در summary
  می‌ماند. تغییر rationale فقط جملهٔ ثابت محل نمایش است. هر دو flag خاموش
  پیش‌فرض‌اند و USER نمی‌تواند فعالشان کند؛ usefulness انسانی null.
  ۲۶send، هزینه$0.023094885؛۵۴۶۶کنترل native/ledger/canonical پاس،۴۹۳reservation
  قبلی/۱۴جدول/holdها/halt محفوظ؛۷scope بسته و۲۶slotباقیclaimed. CI اجرا نشده؛
  ۴۵۰۶pytest،Ruff۳۱۲فایل،سهdemo وfixtureHTTP/SQLite۴۵۷/۴۵۷ محلی پاس‌اند.
  این تیک پایان آزمایش/اتصال است؛ پایان کیفیت مدل، RAG یا test نهایی نیست.
  تحویل در [PR #60](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/60)
  به main است؛ review نهایی کد/رسید/گزارش، بدون blocker ثبت شده است.

- [x] **C4h8 — کیفیت Enum با کنترل دسترسی به شواهد؛ ساسان، تحویل آزمایش.**
  [نتیجه و مرز اتصال](../docs/enum-evidence-quality.fa.md)،
  [protocol پیش از پیاده‌سازی](../experiments/core_enum_evidence_v1/protocol-v1.json) و
  [روش/رسیدها](../experiments/core_enum_evidence_v1/README.md).
  راهنمای رسمی custom-classes در review انسانی عمداً direct-answer excluded است؛
  index۱۸/۳۶، exclusion، fixture و gold اصلی حفظ شدند. مقایسهٔ تازه فقط
  fixture کنترل‌شدهٔ همان سه dev است: شواهد generic قبلی در برابر افزودن دو
  بخش کامل و hash-pinned راهنما برای Enum. این سند answer-linked است و وارد
  corpus واقعی RAG نشد. دو دور متوازن،۱۲job/۲۴نوبت/۲۴send؛هر دو حالت۱۲/۱۲fresh
  و۶/۶route عملیاتی. در draftهای Enum توضیح هویت۰/۴→۳/۴ و الگوی کامل module
  با caveat۰/۴→۱/۴؛initialها منتشر نشدند، correctionهای واقعاً released برای
  هر یک از این دو نوع راهنما۱/۲ در برابر۰/۲اند. این‌ها یک Issue در دو تکرارند،
  نه چهار case مستقل. هیچ proposal هر دو بخش مکمل را یکجا نیاورد؛generic+oneguide
  و متن۱۴۰۵۹/۱۴۴۹۴کاراکتری محدودیت‌اند. هیچ runtime fix یا applicability قطعی
  ۱٫۳۱ ثابت نشده و enumCoercion فقط widget scope دارد؛usefulness انسانیnull.
  شکست آفلاین۲۰۰۱۵>۲۰۰۰۰ حفظ شد؛amendment پیش از API، capacity موجود را برای
  هر دو حالت فعال کرد، بدون بریدن منبع/بالابردن سقف. در history واقعی سقف C
  برابر۸baseline/۲guide بود. هزینه$0.014651340؛۱۶۲۷کنترل source/ledger پاس،
  ۵۱۹reservation قبلی/۱۴جدول/holdها/halt محفوظ؛۶scope بسته،۲۴slotباقیclaimed.
  ۴۶۱۱pytest،Ruff۳۱۷فایل،سهdemo وfixtureHTTP/SQLite۴۵۷/۴۵۷ محلی پاس‌اند؛CI
  اجرا نشده. این تیک پایان آزمایش/ابزار fixture است؛پایان کیفیت Enum/RAG/test نیست.
  تحویل در [PR #61](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/61)؛
  review نهایی کد/رسید/گزارش بدون blocker، اصلاح metadata نسخهٔ worksheet و
  بررسی دوبارهٔ۱۹فایل محافظت‌شده ثبت شد. Actions روی head بازبینی‌شده پیش از
  شروع jobها به علت Billing متوقف شد؛ publication طبق مجوز review/test محلی است.

- [x] **C4h9 — انتخاب شاهد مکمل و خوانایی؛ ساسان، تحویل آزمایش با نتیجهٔ منفی.**
  [protocol پیش از پیاده‌سازی/API](../experiments/core_complementary_sources_v1/protocol-v1.json)
  ثبت شد؛ مقایسه تمام شد و نتیجه منفی بود. هر دو arm همان شواهدِ دارای guide را گرفتند؛ فقط
  SYSTEM reminder عمومی و اختیاری فرق دارد. renderer و داده‌های RAG ثابت‌اند.
  معیار اصلی انتخاب/نمایش هر دو بخش کامل و مکمل با caveat بود؛ کاهش طول به‌تنهایی
  امتیاز کیفیت نیست. baseline تازه نشان داد با وجود دو بخش مفید، همچنان
  generic+oneguide انتخاب می‌شود. تعداد route یا answer هدف
  کیفیت نیست؛ توضیح و قدم بعدی مستند باید در متن کاربر بیاید. راهنمای excluded
  صرفاً fixture می‌ماند؛ تغییر default یا افزودن framework بدون شواهد انجام نشود.
  در اجرای تازه، هر دو حالت۴/۴Enum همان generic+Enum و۱۴۴۹۴کاراکتر را داشتند؛
  پوشش مشترک هر دو بخش۰/۴، پس هدف کیفیت پاس نشد و flag توصیه نمی‌شود.
  [receipt،review و هزینه](../experiments/core_complementary_sources_v1/README.md)
  حفظ‌اند:۲۴send/$0.016245240،۱۷۷۰کنترل source/cost و۱۱۲۶کنترل مکانیکی semantic
  پاس. تیک پایان آزمایش است؛ هدف کیفیت پاس نشده و review انسانی باز است.

- [x] **C4h9b — تشخیص حساسیت به ترتیب منابع؛ ساسان، تحویل یک آزمایش محدود.**
  [protocol پیش از پیاده‌سازی/API](../experiments/core_source_order_v1/protocol-v1.json).
  همان pool کامل و همان prompt در هر دو حالت؛ فقط در supplier آزمایش، اولین
  رکورد به انتها می‌رود، برای همهٔ caseها و بدون شرط source/case ID یا محتوا.
  [نتیجه و مرزها](../docs/complementary-sources.fa.md): در Enum پوشش مشترک۰/۴→۱/۴،
  فقط یک initial منتشرنشده۱۴۴۹۴→۷۰۹۹؛ correction دوباره به۱۴۴۹۴ برگشت.
  پوشش مشترک correctionهای واقعاً released در هر دو حالت۰/۲ است؛ بهبود پایدار
  ثابت نشد. A نیز انتخاب inventory وابسته به موقعیت داشت؛ سؤال لازم حفظ شد.
  هدف تشخیص اثر ترتیب بود، نه ranking بهتر. این شاخه بسته است؛ permutation یا
  prompt بعدی برای گرفتن نمره بهتر اجرا نشود. exclusion،gold،RAG و runtime ثابت‌اند.
  [receipt و هزینه](../experiments/core_source_order_v1/README.md):۲۴send/$0.015791160،
  ۱۸۵۸کنترل cost/source پاس؛ هر۵۶۷reservation قبلی/۱۴جدول حفظ،۶scope بسته،
  ۲۴slotباقی claimed؛ holdها/halt/سقف ثابت. [verification](../experiments/core_source_order_v1/verification-v1.json):
  ۴۸۹۶pytest،Ruff۳۲۹فایل،سهdemo وfixtureHTTP/SQLite۴۵۷/۴۵۷ پاس؛ CI سبز ادعا نمی‌شود.
  تحویل هر دو آزمایش در [PR #62](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/62)؛
  [review انتشار](../experiments/core_source_order_v1/publication-review-v1.json)
  روی head`7cfa066` بدون blocker، با همان Python تست‌شده است. هر دو job Actions
  همین head قبل اجرای step به علت Billing متوقف شدند؛ workflow/protection تغییر نکرده‌اند.

- [x] **C4i/E2v — dev گسترده‌تر و توان توضیح مستند؛ ساسان، تحویل مطالعه با نتیجهٔ منفی.**
  [protocol پیش از کد/API](../experiments/core_broader_dev_v1/protocol-v1.json):
  مقایسهٔ مسیر موجود `AnalysisResult + compiled_rules` با `GroundedPlan`، بدون
  prompt/framework/renderer تازه و بدون بازکردن شاخهٔ بستهٔ C4h9. چهار خانوادهٔ
  مکمل #4713،#5618،#7206،#9487 جدا از رزروهای۱۵/۱۵ محمدحسن‌اند؛ همهٔ شش report
  غربال‌شده در exposure ثبت می‌شوند. این انتخاب، split نهایی را freeze نمی‌کند.
  هفت خانواده،۱۶snapshot جاری و دو تکرار متوازن؛۶۴invocation برنامه‌ریزی‌شده،
  همه proposal-only، بدون approval/release/action؛ موفقیت route
  ادعا نمی‌شود. ورودی فعلی، شواهد کامل و سؤال‌های ثبت‌شده در هر دو حالت یکسان‌اند.
  guide excluded فقط در condition کنترل‌شدهٔ Enum می‌ماند؛ condition بدون guide
  باید همچنان کمبود سند را از اطلاعات معلوم کاربر جدا کند. معیار موفقیت، توضیح
  مستند همراه قدم بعد و caveat است؛ کوتاه‌شدن یا answer label به‌تنهایی کافی نیست.
  [اصلاح bound پیش از هزینه](../experiments/core_broader_dev_v1/bound-amendment-v1.json)
  سقف موجود۳۲۷۶۸ را حفظ کرد؛ registration اولیه۴۹۱۵۲ نامعتبر بود و حذف نشده است.
  [خطای آماده‌سازی native](../experiments/core_broader_dev_v1/preparation-first-failure-v1.json)
  نیز حفظ شد: Chroma هنگام read دو فایل ذخیره‌سازی را بازنویسی کرد؛۱۷hash تاریخی
  ثابت ماند و ادعای حفظ هر۱۹byte نداریم. [review مستقل](../experiments/core_broader_dev_v1/index-recovery-review-v1.json)
  ۱۸۲کنترل منطقی شامل کل۱۸source/۳۶chunk/metadata/vector/exclusion را برابر manifest
  قبلی یافت. [epoch جدید آماده‌سازی](../experiments/core_broader_dev_v1/preparation-amendment-v1.json)
  قبل هر method/API با byteهای جاری pin می‌شود و تمام queryها فقط روی copy‌اند؛
  رسیدها، case/gold، manifestهای قدیمی و hold/halt ledger بازنویسی نمی‌شوند.
  [نتیجه](../docs/broader-dev-quality.fa.md):۶۴invocation روی۱۶snapshot اجرا شد؛۷۵send،۶۰پیشنهاد
  pending و۴`ModelOutputInvalid`، صفرapproval/release/action. Enum با guide در
  compiled کوتاه‌تر شد (median۷۱۸٫۵ در برابر۱۴۴۹۴)، اما شرط کامل ازپیش‌ثبت‌شده
  **۰/۴ در هر دو مسیر** است؛ ادعای علت، کاربرد نادرست widget coercion و نسخهٔ
  بی‌پشتوانه اجازهٔ پیشنهاد این مسیر را نمی‌دهند. کوتاه‌شدن، ارتقای کیفیت نیست.
  تمام candidateهای parsed و failureها در [review](../experiments/core_broader_dev_v1/semantic-review-v1.json)
  نگه داشته می‌شوند؛ usefulness انسانی هنوزnull، مطالعه fixed evidence و غیرtest است.
  [هزینه](../experiments/core_broader_dev_v1/cost-review-v1.json):۳۰۲۷کنترل پاس،
  $0.074765295 تازه،۵۹۱reservation قبلی/۱۴جدول محفوظ؛۱۶scope بسته و۵۳slot
  استفاده‌نشدهclaimed، صفرuncertainty تازه، hold/halt/سقف ثابت. [verification](../experiments/core_broader_dev_v1/verification-v1.json):
  ۴۹۸۱pytest،Ruff۳۳۷فایل،سهdemo وHTTP/SQLite۴۵۷/۴۵۷ پاس؛ hosted CI پاس ادعا نمی‌شود.
  default،factory،prompt،renderer،قرارداد عمومی و مالکیت کار بچه‌ها تغییر نکرده‌اند.

- [x] **C4j/E2w — کنترل منبع و USER؛ ساسان، تحویل آزمایشی با هدف کیفیت ناموفق.**
  [protocol پیش از پیاده‌سازی/API](../experiments/core_claim_boundary_v1/protocol-v1.json)
  و [ماتریس۱۶وضعیت](../experiments/core_claim_boundary_v1/acceptance-matrix-v1.json):
  مقایسهٔ تازهٔ compiled با plan خصوصیِ انتخاب passage و fact فعال USER؛ تمام
  surfaceها core-rendered و بدون متن فنی آزاد، cause/fix یا تغییر fact/check از مدل.
  [قرارداد و اتصال](../docs/claim-source-boundary.fa.md)،
  [رسید/تمام خطاها و review](../experiments/core_claim_boundary_v1/README.md).
  ورودی کامل، exclusion، قراردادهای عمومی و single-agent ثابت‌اند؛ exact quote
  اثبات relevance/entailment نیست. از۶۴invocation،۳۷بازدید،۲۲pending،۱۵error و۲۷
  بازدیدنشده حفظ‌اند؛compiled۱۵/۱۸ و مسیر جدید۷/۱۹ پیشنهاد دادند. Enum جدید
  identity+عنوان module را آورد ولی بدنه/caveat را نیاورد؛ هدف مشترک پاس نشد.
  دو انتخاب منبع نامعتبر withheld مسدود شدند؛ این دو error پاسخ مفید محسوب نمی‌شوند.
  ۵۲send شامل۵۱settled/$0.051594510 و یک connect_timeout با هزینهٔ نامعلوم بود؛
  hold تازه$0.0067584،جمع سهhold$0.0301376،halt/سقف قبلی محفوظ. کمپین بسته است،
  هیچ ID آن از نو استفاده نشود؛۲۸slotتخصیص‌یافتهunusedclaimed و۴۸slotاصلاًتخصیص‌نیافته.
  ۲۳۵۵کنترل هزینه/source و۶۰۵کنترل custody پاس؛ قضاوت انسانیusefulness خالی است.
  ایراد قطعی schema شرطی/feedback مبهم پس از API جداگانه آفلاین اصلاح شد؛ نتیجهٔ
  آنلاین به آن نسبت داده نمی‌شود. [verification](../experiments/core_claim_boundary_v1/verification-v1.json).
  روی source نهایی `9ad8dcb` هر۵۲۳۴pytest پاس،Ruff۳۴۶فایل،سهdemo و پذیرش تازهٔ
  HTTP/SQLite۴۵۷/۴۵۷ با restart پاس؛review جداگانه۲۵۳تست را تکرار کرد وblockerنداشت.
  Actions به‌خاطر Billing پاس ادعا نمی‌شود؛ انتشار طبق مجوز فعلی review/test محلی است.
  تیک پایان تحویل کنترل/آزمایش است؛ تنظیم پیش‌فرض، کیفیت Enum یا test نهایی بسته نیست.

- [ ] **C4j-follow-up — پاسخ مفید با انتخاب کامل شاهد و پایداری plan؛ ساسان.**
  ابتدا وضعیت request نامعلوم واقعاً روشن شود؛ ledger/hold/halt پاک یا دور زده نشود.
  review انسانی خروجی‌ها و شواهد dev موجود، سپس تصمیم دربارهٔ راه قابل‌آزمایش بعدی؛
  جواب دارای بدنهٔ راهنما و caveat لازم باشد. اصلاح آفلاین diagnostics هنوز مقایسهٔ
  API ندارد؛ نه نقل نامرتبط، نه error و نه «همه ارجاع» موفقیت کیفیت نیست.

- [ ] **داوری انسانی تنظیم منتخب و freeze مشترک؛ محمدحسن با ساسان.**
  انتخاب نرم‌افزاری `grounded_candidate_v1` در C4r انجام شده؛ review کیفیت همین
  ترکیب، usefulness، precision منابع و محدودیت Enum هنوز لازم است. pin مشترک
  build/gold/config پیش از test، مطابق ترتیب E2ad، انجام شود.
  قالب صحیح و route کامل جای داوری ادعا/نسخه/ضرورت سؤال را نمی‌گیرند.

کارهای مستقل اعضا برای نسخهٔ نهایی (پیش از شروع branch خود را از main به‌روز کنید):

| نفر | تحویل بعدی | شرط پایان |
| --- | --- | --- |
| حسن | build نهایی PR91 با frozen95 تحویل و مستقلاً بازتولید شد؛ gate ساخت بسته است. برای binding نهایی با محمدحسن همان receipt v3 را مبنا بگیر | v1/v2 را حفظ کن؛ rebuild یا تغییر ranking بعدی فقط با نسخهٔ تازه و هماهنگی freeze؛ test/gold باز نشوند |
| محمدحسن | دو بندdev درPR87 تأیید شده؛ PR88 custody و freezeمنابع PR89 ثبت‌اند. اکنون nativegold/packet با pinهای پذیرفته‌شدهٔ v3، family/coverage و ثبت نسخه‌دار core v2 برای review نهایی | exposure/تصمیمheld-out فقطباخودت؛ core فایل‌ها را باز نکرده. v1 pendingnote را درجا عوض نکن؛ ثبت جدید برای v2. support/usefulness و initial/correction جدا؛ C5/testنهایی باز |
| بهنام | PR82/84 و capture مستقل C4t آماده‌اند؛ رویmainجدید Open saved case را در Windows یک مرور دستی کن: pending پس از بستن UI، وضعیت فعلی بعد restart و عدم Action تکراری؛ source/command/محدودیت را در گزارش evaluation بده | مسیر بازکردن باID فقطGET و اکنون نرم‌افزاری آزموده شده؛ draft/ReviewOperation گم‌شدهٔ session قبلی بازیابی نشده. outcome قبلی هنوز در ورودی reasoning نیست؛ تصمیم scripted مساوی را کیفیت/یادگیری اعلام نکن؛ token/DB خصوصی منتشر نشود |
| ساسان | C4u تحویل: اتصالprofilev2 به actualfactory/API/SQLite/runner، بازتولید build و devavailability،۹۲۲تست وreview مستقل. receiptv3 نیز مستقلاً بازتولید و pinهایش تأیید شد؛ feature مستقل ضروری دیگری نیست | v1/config/vocabulary و داده‌های قدیمی ثابت؛ نه liveباhalt، نه reuse scopeبسته. نیاز C5 به مدرکprovider؛ freeze نهایی و کیفیت با مالکeval |

**قاعدهٔ انتشار فعلی — ۱۵ اکتبر، با دستور صریح ساسان:** منتظر رفع Billing
نمی‌مانیم. برای انتشار، review و تست محلی روی source ثبت‌شده، پذیرش اتصال و
محدودیت‌های پلتفرم را ضمیمه می‌کنیم؛ Actions همچنان blocked است و CI سبز ادعا
نمی‌کنیم. این قاعده جای شرط انتظار CI در یادداشت‌های قبلی را می‌گیرد؛ workflowها،
ledger، holdها، halt و receiptهای تاریخی تغییر نمی‌کنند. branch هر نفر پیش از
کار از `origin/main` به‌روز شود؛ کارهای E1/E2، R4، T4 و ارائه همچنان شاهد جدا می‌خواهند.

- [x] **R4c/C4h5 — رساندن منابع مرتبط و مقایسهٔ محدود؛ ساسان، کمک مستقل به RAG.**
  [protocol](../experiments/retrieval_relevance_v1/protocol-v1.json) و
  [رفتار و اتصال](../docs/retrieval-relevance.fa.md): PR50 حسن درhead`1a18749`
  تغییری نکرده؛ کار روی branch جدا، بدون تغییر branch/index/corpus اوست.
  برای خروجی نهایی۵، تا۲۵ کاندیدا می‌گیریم؛ ranking عمومی API/واژه‌ها و
  فیلتر نسخهٔ فعال USER پیش از cap نهایی اعمال می‌شوند. همهٔ گزینه‌ها opt-in اند.
  [بودجهٔ رکورد کامل](../experiments/retrieval_relevance_v1/whole-record-budget-amendment-v1.json)
  پس از مشاهدهٔ overflow آفلاین و پیش از API ثبت شد؛ متن منبع بریده نمی‌شود.
  replay روی index واقعی در۱۱ state، با packing هر۱۱ را زیر سقف نگه داشت.
  [مقایسهٔ تازه](../experiments/retrieval_relevance_v1/README.md) با flagهای core
  مشترک: route کامل۵/۶ در baseline و۶/۶ در نسخهٔ جدید؛ fresh از۱۰ به۱۲ رسید.
  هر۲۴ نوبت، شامل۲۲ fresh، یک empty و یک unvisited محفوظ‌اند. schema خام معتبر
  ۱۴/۱۵ در baseline و۱۲/۱۲ در نسخهٔ جدید؛ هیچ length/input/render overflow نبود.
  راهنمای مستند button۱٫۳۹ در هر دو تکرار به کاربر رسید، در baseline صفر از دو؛
  پاسخ جزئی برای همان یک case است. multiselect به مدل رسید ولی سؤال callback
  همچنان لازم بود؛ Enum هنوز علت/fix اثبات‌شده ندارد. usefulness انسانی null است.
  ۲۷ send با تخمین$0.026391915؛۳۹۱۲ کنترل هزینه/provenance پاس، همهٔ۴۵۲ reservation
  قبلی و۱۴ جدول، hold/halt/سقف محفوظ‌اند. شش scope بسته و۲۱ slot باقی claimed شدند.
  بودجهٔ bundle حداکثر۱۱۷۵۱/۱۲۰۰۰ byte بود. این تیک تحویل آزمایش است؛ RAG/eval
  نهایی بسته نشده‌اند و پیش‌فرض‌ها خاموش‌اند.
  انتشار در [PR #58](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/58)،
  پس از ادغام PR54/57، روی main `3cbbdd3` رسید؛
  [verification محلی](../experiments/local_release_2026_10_15/verification-v1.json)
  و blocked بودن CI ثبت‌اند. PR50 و branch حسن دست‌نخورده‌اند؛ این کار به merge آن وابسته نیست.

- [x] **C4h2 — repair query تکراری و مقایسهٔ محدود؛ ساسان.**
  [ثبت قبل از تغییر](../experiments/core_repeat_repair_v1/protocol-v1.json) و
  [قرارداد رفتار](../docs/repeat-query-repair.fa.md): گزینه پیش‌فرض خاموش است؛
  همان دو attempt، بدون retrieval/مدل اضافی یا اعتماد به `queries_used`.
  بازپخش سه plan واقعی قبلی با fallback تألیفی۴۲/۴۲ پاس است؛ کیفیت مدل نیست.
  [مقایسهٔ واقعی](../experiments/core_repeat_repair_v1/README.md)،۲ دور و۶ pair
  با ranking/index ثابت۱۸/۳۶: مسیر کامل۲/۶ درOFF و۴/۶ درON؛ پیشنهاد تازه۷ و۹.
  دو query تکراری به ارجاع موجه تبدیل شدند؛ صفر پاسخ فنی درهر دو حالت و
  ۱۲ سؤال ضروری.۳ repair واقعی،۲ موفق و۱length/provider-invalid؛ یکoverflow
  مستقل با۴source باقی است. تمام۲۴ نوبت شامل۱۶fresh/۱stale/۵empty/۲unvisited
  ثبت‌اند؛ usefulness انسانیnull وپیش‌فرض خاموش است.۲۸send، تخمین$0.032936640،
  صفرhold تازه؛۱۲۲۰ کنترل هزینه/پرووننس، تمام۳۶۴reservation قبلی و۱۴جدول محفوظ.
  scopeها بسته و۲۰slot مصرف‌نشدهclaimed؛ halt/C5 همچنانباز. تحویل تست/اصلاح
  محدود است؛ C4h کلی،R4 وevaluation نهایی بسته نشده‌اند.
  انتشار در [PR #51](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/51)
  با review مستقل و چهار CI موفق روی head`d1be786`؛ merge رویmain`17426b1`.
  [verification](../experiments/core_repeat_repair_v1/verification-v1.json):
  ۳۷۴۰pytest، Ruff و سه demo پاس؛ پذیرش آفلاین HTTP/SQLite با۴۵۷/۴۵۷
  شاملrestart/retry. آزمایش مدل این تحویل از TestClient/DummyTracker استفاده
  کرد؛ شاهد تازهٔ مرورگر/SQLite یا بهبود پاسخ فنی محسوب نمی‌شود.

- [x] **C4h3 — ظرفیت source و مقایسهٔ محدود؛ ساسان، بدون بهبود live اثبات‌شده.**
  [روش و receiptها](../experiments/core_source_capacity_v1/README.md) و
  [رفتار واقعی](../docs/source-capacity.fa.md): گزینهٔ پیش‌فرض خاموش؛ فقط کاهش
  maxItems موجود، بدون متن اضافی، بریدن quote یا تماس سوم. روی شکست قبلی،
  سقف امن۳ به دست آمد؛ در۱۵۸context تاریخی رشد ورودی صفر بود.
  live تازه روی همان index۱۸/۳۶: OFF وON هر دو۴/۶ route و۸fresh،۵ سؤال و۳ ارجاع؛
  صفر پاسخ فنی. فقط۲call یک correction واقعاً سقف متفاوت داشت؛ overflow در
  هیچ arm رخ نداد، پس کاهش failure یا افزایش کیفیت از این اجرا ثابت نشد.
  همهٔ۲۴نوبت شامل۱۶fresh،۴empty و۴unvisited محفوظ؛ دوlength، schema وsource-mismatch
  باقی‌اند.۲۸send، تخمین$0.032721150، صفرhold تازه؛۱۲۲۵کنترل هزینه/provenance،
  حفظ۳۹۲reservation قبلی و۱۴جدول؛۶scope بسته و۲۰slot مصرف‌نشدهclaimed.
  halt/C5 وtest نهایی بازند. این تیک تحویل آزمایش است، نه آمادگی نهایی core.

- [x] **E2r — بستهٔ داوری C4h2/C4h3؛ ساسان، کمک محدود به محمدحسن.**
  [workbench](../docs/evaluation-workbench.fa.md) اکنون هر دو receipt را می‌پذیرد؛
  criterion اصلی native با hash به method وصل است و با gold ثابت fixture
  جایگزین نمی‌شود. شکست‌ها وunvisitedها هم نمایش داده می‌شوند؛ sidecarها برای
  داوری انسانی خالی‌اند. schema ارزیابی/UI/tracker ومالکیت محمدحسن عوض نشده‌اند.

- [x] **C4h4 — قرارداد خروجی کوتاه و مقایسهٔ ثبت‌شده؛ ساسان.**
  [protocol قبل از تغییر](../experiments/core_compact_plan_v1/protocol-v1.json)،
  [رفتار واقعی](../docs/compact-plan-wire.fa.md) و
  [شرط review پیش از مدل](../experiments/core_compact_plan_v1/semantic-review-preparation-v1.json):
  index منبع و fieldهای لازم هر decision، با flag پیش‌فرض خاموش؛ قرارداد عمومی،
  hash کامل request، renderer، approval و سقف دو attempt محفوظ‌اند.۱۶۱تست هدفمند
  پاس؛ [مقایسهٔ دو دور](../experiments/core_compact_plan_v1/README.md)
  روی همان سه dev/index۱۸/۳۶ وranking ثابت انجام شد: schema نامعتبر۳/۱۸ درbaseline،
  صفر/۱۴ درcompact؛ binding هر۱۴انتخاب درست. مسیر کامل۴/۶به۵/۶، ولیfresh هر دو۱۰.
  ۱۲سؤال،۵ارجاع و۳label پاسخ، بدون پاسخ فنیِ مسئله؛ usefulness انسانیnull.
  همه۲۴نوبت، شامل۲۰fresh/۱stale/۲empty/۱unvisited محفوظ‌اند. یکrefinement سقف ورودی
  را رد کرد؛ projection هر دو قالب روی همانrequest بیش‌ازسقف است. length درهیچarm
  رخ نداد، پس کاهش length ثابت نشده.۳۲send، تخمین$0.034834305؛۱۶۷۱کنترل هزینه،
  حفظ۴۲۰reservation قبلی و۱۴جدول، صفرhold تازه؛۶scope بسته و۱۶slotباقیclaimed.
  پیش‌فرض خاموش؛ این تیک تحویل آزمایش است، نه کیفیت نهایی core/RAG.
  wire خام و expansion جدا ثبت می‌شوند؛ schema/route با پشتیبانی ادعا و usefulness
  یکی نیست. خروجی ناقص salvage نمی‌شود. regression کامل۴۰۰۶pytest،Ruff،سهdemo
  وپذیرشHTTP/SQLite۴۵۷/۴۵۷ پاس‌اند؛CI به‌علت سهمیهٔActions هنوز اجرا نمی‌شود.
  انتشار در [PR #57](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/57)،
  پس از merge54 به main retarget و همان‌جا merge شد؛ انتشار فعلی با استثنای
  محلیِ ثبت‌شده در بالای plan و رسید main `3cbbdd3` انجام شده است.

- [ ] **R4b — review اصلاح ranking حسن؛ مالک اصلاح حسن.**
  [PR #50](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/50)
  در head`1a18749` آمادهٔmerge نیست؛ [شواهد review](../experiments/rag_pr50_review/README.md):
  newest-first شاهد نسخهٔ فعلی را کنار می‌زند، over-fetch ذکرشده پیاده نیست،
  معنای `since_version` با exact applicability یکسان فرض شده و format محلی هنوز fail است.
  lint رفع شده؛ GitHub به علت Billing اصلاً jobها را شروع نکرده است.
  بازپخش۲۴query روی index واقعی۱۸/۳۶، همان membership قبلی را داد؛ over-fetch
  هنوز وجود ندارد.۹۶/۹۶ صرفاًquery-control بدون خواندن index است.
 ۹۱ تست موجود پاس ولی regression را پوشش نمی‌دهند. Hassan branch تغییر نکرد؛
  native receipt، کنترل نسخهٔunknown/قدیمی/correction وrelevance لازم است.
  **به‌روزرسانی حسن ۱۶ اکتبر:** adapter در PR50 اصلاح نمی‌شود و کنار می‌رود؛ مسیر R4c
  روی main (`query_relevance_v1`، multiplier۵، scope دقیق نسخهٔ USER قبل از cap، packing
  ۱۲۰۰۰byte) هر سه ایراد را برطرف می‌کند. [رسید و review](../experiments/r4b_version_ranking/README.md)
  روی همان۲۴ query آرشیوی dev (۸ state) و index ثبت‌شدهٔ۱۸/۳۶: backend در PR50/native پنج و
  در R4b بیست‌وپنج کاندیدا گرفت؛ button۱٫۳۹ و multiselect۱٫۵۰ فقط در R4b و fragment۱٫۵۰
  در هر سه به مدل رسیدند؛ version_unsafe صفر. ۱۶ تست تازه برای نسخهٔ unknown/قدیمی/فعلی/
  correction و `since_version`. شواهد لازم۱/۵ در PR50/native و۳/۵ در R4b؛ off_topic از۸ به۵
  (برچسب‌ها پیش‌نویس دستیار با تأیید حسن، نه review مستقل). chunk key-identity در
  widget-behavior (۱٫۵۰تا۱٫۵۵) در R4b کاندیدای۱۶و۲۳ از۲۵ است و به مدل نمی‌رسد؛
  bundleهای مربوط۲و۴hit دارند، پس نسبت‌دادن حذف به cap پنج درست نیست. محدودیت
  packing بایتی/ترتیب و relevance باید جدا بررسی شود؛ گام بعد فقط روی dev است.
  exclusion حفظ: build فقط docs، صفر Issue/comment، بدون
  custom-classes/release note؛ با `index_exclusion` نهایی split-e1-v1 هم چک شد. هیچ case یا
  query از test استفاده نشد. availability است، نه کیفیت پاسخ؛ کد adapter/engine/index
  تغییر نکرد. PR50 قبلاً بدون merge بسته شده؛ پذیرش receipt و اصلاح ایمنی بازپخش
  PR72 تیک جدا دارد و پایان R4 نیست.
  کار core مستقل از این اصلاح ادامه دارد. محمدحسن review سه dev را درPR55 و
  rubric پیش‌نویس را درPR56 رویmain رسانده؛ اکنون PR70–76 هر۳۱fixture را ثبت
  کرده‌اند. usefulness، native gold، vocabulary نهایی و freeze هنوز با اوست.
  کمک ساسان محدود به اتصال وreviewpack است.

- [ ] **R4e — version prefilter و benchmark دسترسی dev؛ حسن.**
  روی corpus نهایی (۴۳ نسخهٔ هر docstring)، ۴ تا ۱۷ از ۲۵ کاندیدا نسخه‌های تکراری همان متن بودند
  و scope بعد از top-k فقط ۰ تا ۳ کاندیدای مجاز باقی می‌گذاشت؛ docstringهای multiselect/fragment
  ۱٫۵۰ کیس A کنار می‌رفتند. گزینهٔ opt-in `retrieval_version_prefilter` همان قاعدهٔ scope را
  پیش از top-k به‌صورت filter بومی می‌فرستد (بدون rebuild؛ هم‌ارزی filter و scope روی هر دو corpus
  تست شده). [benchmark و نتایج](../experiments/r4e_version_prefilter/README.md) روی ۱۶ کیس dev:
  passage لازمِ داخل کاندیداها ۵→۱۰ و رسیده به مدل ۲→۴ از ۱۶. segmentation، embedding بزرگ‌تر،
  BM25، ranking دیگر، backfill API و بودجهٔ بزرگ‌تر اثری نداشتند. پیش‌فرض‌ها، profile و live
  دست‌نخورده‌اند؛ اتصال به profile تصمیم core است. availability است، نه کیفیت پاسخ.

- [ ] **T4 — گزارش PR52 و رسیدهای PR66 review شدند؛ بخش‌های نهایی هنوز بازند.**
  [گزارش روی commit ثابت`8420a3b`](https://github.com/Iran-110/QueraAgenticAI-FinalProject/blob/8420a3beed37e6bc79504487cd44724a40a30d79/docs/two-case-ui-sqlite-smoke-2026-10-14.md)
  اکنون در [PR #52](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/52)
  بازبینی شد؛ branch او تغییر نکرد. اجرای دستی
  Windows، آفلاین/scripted و رویsource`f8b3106` بوده، نهmain`17426b1`.
  correction، سؤال پس از correction، stale409، Edit/Reject، جداسازی دو case،
  restart backend و یکaction پس از replay تأییدشده را گزارش می‌کند.
  این‌ها گزارش اپراتورند؛ JSON و screenshot در PR52 ضمیمه نبودند.
  retry در گزارش PR52 ازAPI بود. سپس [T4a/PR66](../docs/pr66-review.fa.md)
  دو JSON پاک‌سازی‌شده و مشاهدهٔ lost-ACK/Retry ازUI را اضافه کرد؛ اصل receiptها
  حفظ‌اند. pin دقیق اجرای fault و recovery عملیات تأییدنشده در session تازه
  هنوز ثبت نشده‌اند؛ backend durability جای آن recovery نیست. token/DB منتشر نشود.
  tool failure، مصرف outcome در تصمیم بعد و handoff ارزیابی همچنان بازند؛
  T4 تیک نمی‌خورد و این گزارش، کیفیت مدل/RAG را نشان نمی‌دهد.
  **به‌روزرسانی ۱۷ اکتبر:** PR82/84 و C4t شواهد خطا/replay و ورودی واقعی را
  اضافه کردند؛ U4a بازکردن وضعیت ثبت‌شده با ID در session تازه را با AppTest
  و restart پردازش backend می‌آزماید. بازیابی draft یا ReviewOperation
  ارسال‌نشده از session قبلی پیاده نشده است؛ outcome قبلی در reasoning نیست.
  [وضعیت و مرز تازه](../docs/saved-case-reopen.fa.md) و
  [رسید مشترک](../docs/receipts/team-closeout-2026-10-17.json) جای ادعای بستن
  کامل T4 یا بازتولید مستقل تست قدیمی Windows را نمی‌گیرند.

تحویل C4h1/E2p/E2q در [PR #49](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/49)
با head`344b260`، review مستقل وچهار CI موفق، رویmain با`f78c6e9` منتشر شد.
نتیجهٔ منفی آزمایش وhold/haltها حفظ‌اند؛ از آن بهبود کیفیت ادعا نمی‌شود.

- [x] **E2p — ابزار review خروجی واقعی؛ ساسان، کمک موقت به محمدحسن.**
  [راهنما](../docs/evaluation-workbench.fa.md): صفحهٔ محلی با پیام مصرف‌شده،
  تمام output surfaceها، factهای فعال، sourceهای واقعی و template خالی برای
  داوری. C4g همهٔ۲۴ نوبت را نگه می‌دارد:۲۳ رسیده،۱۷ پیشنهاد تازه،۶ بدون پاسخ
  تازه شامل۲ stale و۱ نوبت اجرا‌نشده. C4h متوقف‌شده هم۲۴ نوبت را نگه می‌دارد:
  ۱۶ رسیده،۱۰ پیشنهاد تازه،۶ بدون پاسخ تازه شامل۴ stale و۸ اجرا‌نشده.
  scope/hash و duplicate review کنترل می‌شوند؛ fixed oracle با native evidence
  یکی نیست. usefulness انسانی خالی است؛ E1/E2 نهایی یا۳۰ case بسته نشده‌اند.

- [x] **C4h1 — آزمایش راهنمای محدودیت query و اندازهٔ source؛ ساسان، نتیجهٔ منفی.**
  [ثبت قبل از تغییر و اصل نتایج](../experiments/core_resource_guidance_v1/README.md):
  همان۱۸ source/۳۶ chunk در هر دو arm، بدون تغییر ranking حسن؛۲۱ send با
  تخمین$0.024946020،۴ pair از۶ ثبت‌شده. هر arm فقط۱ مسیر کامل از۴ مسیر
  واقعاً اجراشده داشت؛۴ job آینده اجرا نشدند. راهنمای اختیاری برتری ثابت نکرد
  و پیش‌فرض خاموش است. یک refinement جدید با راهنما۳۳۰۷۵ و بدون آن۳۲۰۶۵
  byte همراه margin بود؛ guard۳۲۷۶۸ جلوی send را گرفت. اصل Usage آن attempt
  unrecorded/null ماند و campaign طبق شرط حسابداری متوقف شد؛ resume نداریم.
  چهار scope بسته،۱۱ slot مصرف‌نشده permanently claimed،۱۶ slot آینده تخصیص
  نیافته؛ تمام۳۴۳ reservation قبلی و schema/۱۴ جدول،دو hold و halt حفظ‌اند.
  [review حسابداری V2](../experiments/core_resource_guidance_v1/cost-review-v2.json)
  ۸۸۲/۸۸۲ است؛ V1 با یک انتظار اشتباه دربارهٔ method-v1/v2 محفوظ است.

- [x] **E2q — تشخیص attempt متوقف‌شده پیش از reservation؛ ساسان، آفلاین.**
  [اصلاح محدود پس از مشاهده](../experiments/core_resource_guidance_v1/pre-dispatch-accounting-amendment-v1.json):
  فقط typed ContextLimitExceeded از gateway واقعی با نبود reservation و هر
  transport marker پیش/پس، برای اجراهای آینده skipped_before_reservation با
  هزینه صفر ثبت می‌شود. حالت مبهم یا hold واقعی صفر نمی‌شود.۲۸ کنترل جدید
  و۸۸ regression پاس؛ receipt/campaign قبلی تغییر نکرد و هیچ API تازه برای
  این fix مصرف نشد. صفر send در کنترل HTTP، صفر route کامل بود؛ کیفیت نیست.

[بررسی انتشار این تحویل](../experiments/core_resource_guidance_v1/verification-v1.json):
۳۶۴۹pytest،Ruff روی۲۶۸ فایل،سه demo وپذیرشHTTP/SQLite۴۵۷/۴۵۷ باrestart/retry
پاس‌اند؛ CI همان head وreview نهایی شرط انتشار است. E1/E2/R4/T4/E4/E5/C5
با این تحویل بسته نشده‌اند و کار اعضا ادامه دارد.

- [x] **C4g / R4a — build نسخه‌دار و آزمایش سه dev با index واقعی؛ ساسان، کمک به RAG حسن.**
  انتشار و review در [PR #48](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/48)؛
  [protocol قبل از اجرا](../experiments/dev_rag_coverage_v1/protocol-v1.json) و
  [رسید/محدودیت‌ها](../experiments/dev_rag_coverage_v1/README.md): profile بسته۱۸/۳۶،
  چهار source رسمی و۴۶ reservation؛ پذیرش۸۹/۸۹، دو build مستقل یکسان و حفظ تمام
  chunkها/snapshotهای قدیمی۱۴/۳۰. این تیک تحویل محدود است، R4/کیفیت نهایی نیست.
  دو دور balanced با source ثابتa6c7f8c؛۲۹ call، تخمین$0.032363430، صفر hold تازه،
  شش scope بسته و۱۹ slot مصرف‌نشدهclaimed. ۶۲۹ کنترل حسابداری، همهٔ۳۱۴ ردیف
  reservation قبلی و ردیف‌های۱۴ جدول/schema محفوظ؛ C5/halt/دو hold قبلی بازند.
  route قدیم۴/۶ و جدید۲/۶؛ بهبود کیفیت از افزایش corpus ثابت نشد. fragment1.50
  رسید ولی button1.39/multiselect اضافه‌شده در bundle مدل نیامد؛ پنج RepeatedQuery
  و یک Enum overflow در دو attempt حفظ‌اند.۱۷ proposal تازه/دو مشاهدهٔ stale جدا،
 ۳۲ hit نسخهٔ ناسازگار/نامعلوم حذف، سه plan نامعتبر و repairها حفظ؛ usefulness
  انسانیnull.۳۵۱۵pytest و HTTP/SQLite۴۵۷/۴۵۷ و demos/Ruff پاس؛ CI head شرط انتشار.
  head1c01442 دو Linux و یک Windows پاس؛ Windows دیگر در سقف۲۰ دقیقه نزدیک
  انتهای suite cancel شد. هیچ assertion fail یا gate حذف نشد؛ بودجهٔ job۳۰ دقیقه شد.

- [ ] **C4h — رفع بن‌بست query و انتخاب source در حد خروجی؛ ساسان.**
  آزمایش C4h1 فقط prompt guidance بود و مسئله را حل نکرد. C4h2 بالای همین
  فایل،history خودcaller وfallback را باگزینهٔخاموش پیش‌فرض ودو attempt
  تحویل داده؛ دو ارجاع تازهٔ واقعی داشت، ولی پاسخ فنی اضافه نشد. قدم بعد
  C4h3،کفایت واندازهٔ انتخاب source است؛ guard engine وquote کامل محفوظ‌اند.
  repair درattempt دوم ظرفیت retrieval سپس model سوم نمی‌دهد؛ route کامل‌تر
  باescalation بیشتر، به‌تنهایی بهبود کیفیت نیست. baseline/شکست‌های قبلی محفوظ‌اند.
  کار حسن در R4: ranking/backfill نسخه و relevance این queryهای واقعی؛ source-ID
  یا gold filter برای بالا بردن نتیجه ممنوع. محمدحسن human review/split و بهنام
  smoke دستی UI/SQLite را ادامه دهند؛ این کارها با C4g بسته نشدند.

- [x] **C4f — مقایسهٔ محدود مدل و بهبود انتخاب منبع؛ ساسان.**
  انتشار و review در [PR #47](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/47)؛
  ۳۳۴۶ pytest، Ruff و HTTP/SQLite ۴۵۷/۴۵۷ با restart/retry پاس.
  [روش ثبت‌شده](../experiments/core_quality_followup/README.md): همان سه dev و
  oracle قبلی؛ دو دور paired سقف ۱۰۲۴/۲۰۴۸، و مقایسهٔ reminder روی شش وضعیت
  سالم/خصمانه. source-gap investigation جدا روی ۱۷ کنترل archived از ۴ پاس
  به ۱۷ پاس رسیده؛ پاسخ‌های قدیمی و نمرهٔ ۷/۹ بازنویسی نمی‌شوند.
  [راهنمای اتصال و هزینه](../docs/core-quality-followup.fa.md): مجوز تازهٔ ساسان
  برای finite quarantine-set، با هر دو hold و تمام revocationهای قبلی، halt
  عمومی و سقف $4.50 محفوظ. این reconciliation نیست؛ خطای نامعلوم تازه کل
  آزمایش را می‌بندد. دو epoch واقعی، ۶۴ call با تخمین $0.041621580 و بدون
  hold تازه؛ تمام sourceها هنگام اجرا ثابت. مقایسهٔ cap هر دو ۶/۶ بود، برتری
  ۲۰۴۸ اثبات نشد. در دو تکرار همان challenge، baseline دو بار quote مهاجم
  را انتخاب کرد و reminder صفر بار؛ در clean، متن مفید button در draft کاربر
  صفر از دو در برابر دو از دو، با حفظ source برای maintainer در هر دو arm.
  usefulness انسانی null و نمرهٔ composite تفسیر دستیار است. تمام ۴۸ proposal
  و ۶۴ prompt بررسی شده؛ پنج first attempt نامعتبر/repair محفوظ‌اند. ۱۰ scope
  بسته و ۳۲ slot استفاده‌نشده claimed باقی‌اند. C5، RAG واقعی و test نهایی
  هنوز بازند؛ defaultها ثابت‌اند. CI همان head و review شرط انتشار است.
  یک Windows با همین تغییرات پاس و دیگری در سقف ۱۰ دقیقه cancel شد؛ تمام
  checkها حفظ و سقف job بیست دقیقه شد تا head نهایی کامل بررسی شود.

- [x] **C4e — اندازه‌گیری محدود پایداری و برش خصمانهٔ آفلاین؛ ساسان.**
  انتشار و review در [PR #46](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/46)؛
  ۳۲۰۴ تست، HTTP/SQLite ۴۵۷/۴۵۷ و restart/retry پاس؛ CI همان head شرط merge است.
  [protocol](../experiments/core_stability_adversarial/stability-protocol-v1.json)
  قبل از مدل ثبت شد؛ سه دور کامل، دور چهارم پس از ۲ job از ۶ با خطای provider
  متوقف شد. [اصل receipt و review](../experiments/core_stability_adversarial/README.md):
  در سه دور کامل B سه route از ۹ و C هفت از ۹؛ با دور چهارم ناقص B سه از ۱۰
  و C هشت از ۱۰. ۱۰ paired input اولیه یکسان‌اند؛ ترتیب متوازنِ چهار دور
  کامل اجرا نشد. ۴۲ transport attempt، ۴۱ settled با تخمین $0.025141875 و
  یک hold تازه $0.0033792؛ ۴ job اجرا نشده‌اند، نه موفق. دو پاسخ Enum با
  `ProviderResponseInvalid` و خروجی ۱۰۲۴ token شکست محسوب شدند؛ علت دقیق
  truncation ثابت نشده. ۲۵ proposal، ۲۰ سؤال ضروری، ۳ پاسخ محدود button؛
  کفایت سخت‌گیرانهٔ ۲ پاسخ Enum کامل اثبات نشد و usefulness انسانی null است.
  ۱۴ qualification اولیه نسخهٔ نامعلوم را تأییدشده خواندند؛ [fix مستقل catalog](../experiments/core_stability_adversarial/catalog-version-truth-receipt-v2.json)
  همان ۱۰ کنترل archived را از ۳ پاس/۷ شکست به ۱۰ پاس رساند؛ نتیجهٔ live
  بازنویسی یا دوباره نمره‌گذاری نشده و fix با API تازه آزمایش نشده است.
  برش خصمانه پس از توقف فقط آفلاین است: ۶ کنترل سالم و ۳ counterexample؛
  انتخاب شاهد قدیمی و answer با conflict رد شدند، quote منبع مهاجم با hash
  معتبر پذیرفته شد و شکست semantic ثبت شد. این‌ها کیفیت RAG/test یا بستن
  bonus نیستند. tracker/UI/RAG/قراردادهای مشترک تغییر نکرده‌اند؛ دو انتظار
  تست اتصال برای catalog جدید اصلاح و اصل کنترل‌های تاریخی حفظ شده‌اند.

- [ ] **C5b — تطبیق درخواست نامعلوم تازهٔ C4e؛ ساسان.**
  [بستهٔ reconciliation](../experiments/core_stability_adversarial/stability-cost-reconciliation-v1.json)
  شناسهٔ محلی و بازهٔ UTC را دارد. HTTP status، model و usage دریافت نشده‌اند؛
  بدون رسید provider، صفر بودن هزینه فرض نمی‌شود. سه scope بسته و چهارمی
  با `NewUncertainty` revoke شد؛ grant قدیمی نیز طبق guard موجود revoke است،
  hold قبلی $0.02 و hold تازه باقی‌اند، pending صفر و halt پابرجاست.
  پروتکل live قبلی بسته می‌ماند؛ ledger reset یا parent تازه برای دورزدن این
  وضعیت ساخته نمی‌شود. C4f با مجوز تازهٔ انسانی و scope مستقلِ محدود، هر دو
  hold را حفظ می‌کند؛ reconciliation و halt عمومی همچنان بازند. smoke بهنام مستقل است.

- [x] **C4d — آزمایش محدود سه dev و اصلاح تصمیم‌های GroundedPlan؛ ساسان.**
  انتشار در [PR #45](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/45)؛
  ۳۱۳۹ تست محلی و HTTP/SQLite ۴۵۷/۴۵۷ پاس، CI همان head شرط merge است.
  [ورودی/known/unknown و oracle قبل از مدل](../data/evaluation/dev-three-v1/scenario-review-v1.json)
  و [receiptها و مقایسه](../experiments/dev_three_baseline/README.md) ثبت‌اند.
  A catalog معمول: ۲ خروجی معتبر از ۸، صفر مسیر کامل از سه؛ B vocabulary:
  ۳ از ۷ و یک مسیر؛ C guidance اختیاری decision/فیلد: ۸ از ۸ و سه مسیر.
  پنج state مشترکِ اولین attempt، request hash یکسان دارند؛ repair و refinement
  بعدی یکسان نیستند. Enum پاسخ مستند داشت ولی handoff صریحِ source gap کم بود؛
  نتیجهٔ اصلی حفظ است و replay اصلاح اختیاری renderer جدا گزارش می‌شود؛ پیش‌فرض تاریخی ثابت است.
  ۴۱ کنترل mode از ۲۰ پاس/۲۱ شکست به ۴۱ پاس، و ۱۷ کنترل config/HTTP از
  ۵ پاس/۱۲ شکست به ۱۷ پاس رسیدند؛ شکست اولیهٔ suite حفظ شده. این اعداد
  کیفیت عمومی، حل Issue یا test نهایی نیستند. ۲۳ send، تخمین $0.013688565؛
  سه scope بسته، cap/hold/halt و grant قبلی حفظ، C5 باز. index واقعی با مدل
  mock، ۷۳/۷۳ و دو build همسان/۴۰ query؛ همین ۱۴ docs/۳۰ chunk و vectors محلی،
  بدون پوشش تازهٔ نسخه‌های fixture. [راهنما](../docs/dev-three-baseline.fa.md).

- [ ] **E1a — سه dev پذیرفتهٔ انسانی؛ split نهایی با محمدحسن.**
  خانواده‌های #12782/#12629، #9770 و #8129/#2379/#8180 exposed و answer-informed؛
  صفر test تازه. chronology/duplicate خارجی و review usefulness هنوز باز.
  [manifest فعال این آزمایش](../data/evaluation/dev-three-v1/split-manifest.json)
  جداست؛ manifest تاریخی pilot برای بازتولید تغییر نکرده. routeها را می‌توان
  در runner موجود مصرف کرد؛ جواب نسخه فقط پس از همان سؤال released وارد شود.
  این کمک جای باقی ۱۵ dev/۱۵ test یا E1–E5 را نمی‌گیرد.
  [review انسانی caseها](../data/evaluation/dev-three-v1/case-review-v1.json)
  (پیش‌نویس دستیار، تأیید/اصلاح محمدحسن ۱۵ اکتبر، ساخته‌شده با
  `scripts/prepare_case_review.py`): هر سه برای dev پذیرفته؛ خانواده‌ها کامل‌تر شدند:
  #12629/#12782/#13022، #9770 به‌همراه #7300/#8734/#14297، و #8129/#2379/#8180
  به‌همراه #4909/#6985/#7419. مسیر جدید سند custom-classes باید به exclusion اضافه شود.
  release note۱٫۵۰ تغییر مشخص multiselect را می‌گوید؛ widget-behavior فقط rollout
  تدریجی۱٫۵۰تا۱٫۵۵ را می‌گوید. متن دقیق باید به مدل برسد؛ عضویت درallowlist کافی
  نیست. [review و شرط prospective ساسان](../docs/pr55-evidence-review.fa.md)
  برای اجرای تازه ثبت شد؛ gold/receipt تاریخی دست‌نخورده‌اند.
  usefulness خروجی مدل هنوز باز است.

کار جاری حسن: از build بستهٔ۱۸/۳۶ تحویل C4g جلو برود و relevance،ranking نسخه
و backfill را با queryهای واقعاً ثبت‌شده قبل/بعد بسنجد؛ چهار source اضافه شده‌اند
ولی membership به معنی رسیدن source به مدل نیست. برای همین سه dev منتظر
manifest تازه نماند؛ final split و exclusion انسانی جداست. PR #43 در آخرین
HEAD بررسی‌شدهٔ `3f9e7b1` بدون diff بود. محمدحسن review سه dev وdraft rubric را
منتشر کرده؛ ساسان ابزار review و اندازه‌گیری را جلو برده، ولی usefulness انسانی،
ثبت exclusion تکمیلی و باقی۱۲ dev/۱۵ test همچنان بازند. بهنام smoke دستی دو-case روی
main تازه را با Edit/Reject،correction،approval قدیمی وrestart/retry ادامه دهد؛
هر blocker UI/API را ثبت کند تا ساسان بردارد. تغییر ranking/tracker در این
تحویل انجام نشده و source/oracle/corpus قدیمی ثابت‌اند.

- [x] **C4c — vocabulary سؤال‌های caller در factory معمول؛ ساسان، محدود آفلاین.**
  انتشار و CI نهایی در [PR #44](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/44) است.
  [ثبت قبل از اصلاح](../experiments/user_gap_configuration/protocol-v1.json):
  ۲۱ کنترل، چهار state از همان خانوادهٔ exposed و سه سؤال بازبینی‌شده.
  مسیر معمول فقط gap نسخه را داشت؛ تنظیم اختیاری `AGENT_USER_GAP_CATALOG`
  باید vocabulary موجود را به factory برساند، فقط برای unknown صریح و بدون
  تکرار fact فعال USER. source catalog، قراردادها و فایل‌های اعضا ثابت‌اند.
  [مقایسهٔ واقعی Git و review](../experiments/user_gap_configuration/README.md):
  همان ۲۱ کنترل از ۹ pass/۱۲ fail به ۲۱ pass رسیدند؛ دوازده مورد مربوط به
  configuration و اتصال HTTP هستند، نه دوازده تصمیم مدل. تست کامل ۲۸۸۱، Ruff
  روی ۲۱۰ فایل، سه demo و پذیرش HTTP/SQLite ۴۵۷/۴۵۷ همراه restart پاس‌اند.
  [راهنمای اتصال](../docs/user-gap-configuration.fa.md): unknownها باید صریح در
  UI/API ثبت شوند؛ vocabulary خودکار کمبود را کشف نمی‌کند. factory بدون تنظیم
  اضافی همان رفتار قبلی را دارد. source catalog و قراردادها تغییر نکرده‌اند.
  ledger/halt/grant قبلی محفوظ‌اند؛ pair مدل با remaining grant کامل تأمین
  نمی‌شود، پس برای این اصلاح اجرای paid انجام نمی‌دهیم.

قدم اتصال محمدحسن: برای dev caseها نام gapهای لازم را در unknowns و جواب‌ها را
با همان نام در reported_facts ثبت کند؛ vocabulary سؤال‌ها را قبل از اجرای
مدل review و در config خصوصی freeze کند. فرم UI موجود این ورودی را دارد؛
نسخهٔ معلوم یا callback دریافت‌شده دوباره پرسیده نشود. این کار جای E1/E2 یا
rubric و داوری usefulness نیست. task بهنام برای smoke دستی C2h همچنان پابرجاست.

- [x] **C2h — سؤال‌های mock مطابق facts فعلی؛ ساسان، تحویل محدود آفلاین.**
  انتشار و CI نهایی در [PR #42](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/42) است.
  [ثبت، نتیجه و review](../experiments/offline_corrections/README.md): همان ۱۹
  کنترل V2 روی source قدیم پنج pass/چهارده fail و روی `090c1e5` نوزده pass
  دارند. V1 و شکست assertion ظاهری UI حفظ‌اند؛ V2 فقط «Approve فعال نباشد» را
  به‌جای الزام وجود دکمهٔ disabled ثبت می‌کند. فقط backend بدون index و scripted
  در `ask/ask_version` اصلاح شد: نسخهٔ نامعلوم سؤال canonical؛ نسخهٔ معلوم
  سؤال widget؛ اطلاعات کافی با شاهد synthetic ناکافی، ارجاع. guard core پابرجاست.
  AppTest، پاسخ کوتاه پس از approval، correction، 409 برای approval قدیمی،
  replay و retry در سه process تازه پاس‌اند؛ تست کامل ۲۸۶۰ و HTTP/SQLite
  ۴۵۷/۴۵۷ پاس است. [راهنمای ادامه](../docs/offline-scripted-corrections.fa.md):
  replay رخداد ناموفق قبلی همان نتیجه را نگه می‌دارد؛ ادامه با turn تازه.
  هزینه صفر؛ کیفیت مدل/RAG یا بستن T4/U3/E5 از این نتیجه گرفته نمی‌شود.

قدم کوچک بعدی بهنام: main تازه را بگیرد و smoke دو-case خودش را از UI با پیام
جدید تکرار کند؛ correction و سؤال بعدی، Edit/Reject جدا، approval قدیمی و
restart/retry با envelope دقیق ثبت شوند. هر review موفق یک action مورد انتظار
دارد؛ retry همان review نباید action اضافه کند. گزارش اصلی #40 تغییر نکند؛
نتیجهٔ تازه با PR، command و receipt جدا بیاید. محمدحسن اگر در UI blocker دید
به او کمک کند؛ مسئولیت dev/test/rubric و corpus نهایی اعضا پابرجاست.

### تحویل‌های قبلی و موارد اتصال باز

تحویل مستقل تازهٔ ساسان **C4b — حفظ تعارض اعلام‌شده در refinement/repair** در
[PR #41](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/41) است.
[مقایسهٔ اصل کد قدیم و جدید](../experiments/conflict_continuity/README.md) با
۱۴ کنترل ثبت‌شده پیش از fix: روی `03225e2` هفت pass/هفت fail و روی source تمیز
`8cc41bf` چهارده pass/صفر fail. سه answer نامجاز دیگر به approval نمی‌رسند؛
چهار ask/escalate مجاز، status حل‌نشده را برای maintainer حفظ می‌کنند و quoteها
فقط از bundle جاری‌اند. حذف منبع یا هشدار «حل شد» رفع تعارض نیست. marker فقط
gap منبع است؛ اطلاعاتی که کاربر می‌تواند روشن کند سؤال جدا دارد.

[راهنمای اتصال C4b](../docs/conflict-continuity.fa.md): status فقط در همان
run/case/revision نگه داشته می‌شود؛ هیچ quote قدیمی cache نمی‌شود. handoff باید
request واقعی planner پس از افزودن marker را capture کند. قراردادهای مشترک و
ماژول‌های اعضا عوض نشده‌اند؛ catalog پیش‌فرض هنوز تعارض را خودکار تشخیص نمی‌دهد.
تست کامل ۲۸۴۱ pass، ۴۴ regression تازه، Ruff و سه demo پاس؛ پذیرش جداگانهٔ
HTTP/SQLite ۴۵۷/۴۵۷ و restart پاس است. [receipt و review مستقل assistant](../experiments/conflict_continuity/README.md)
ثبت‌اند؛ CI نسخهٔ انتشار در PR مرجع بررسی شود. این کنترل تألیفی/آفلاین یک
خانوادهٔ exposed است، هزینهٔ API صفر، case مستقل اضافه نمی‌کند و کیفیت مدل/RAG
را ثابت نمی‌کند. E1/E2/R4/E4/E5/C5 و برآورد حدود ۷۵٪ تغییری نکرده‌اند.

[گزارش دو-case بهنام، PR #40](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/40)
پس از review و CI Linux/Windows با `78901d7` روی main است؛
[گزارش مشاهدهٔ دستی](../docs/two-case-ui-sqlite-smoke-2026-10-13.md) correction،
رد approval قدیمی، یک approval و replay بعد از restart backend را ثبت می‌کند.
این رسید خودکار/کیفیت مدل نیست؛ browser session باز ماند و Edit/Reject جدا
اجرا نشده‌اند. run scripted پس از correction با `KnownFactMarkedMissing` متوقف
شد، پس تصمیم follow-up موفق یا بستن T4/U3/E5 را از آن نتیجه نمی‌گیریم.

تحویل قبلی ساسان **C4a — انتخاب واقعی مدل روی شواهد ثابت** در
[PR #39](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/39) است؛
از main `80f9913` شروع شد. [بستهٔ شواهد و محدودیت‌ها](../experiments/controlled_model_baseline/README.md)
اصل preregistration، receipt و review جدا دارد. baseline روی `8b16f2c` پس از
CI لینوکس/ویندوز اجرا شد: ۳ send واقعی، ۲ سؤال callback قابل بررسی، یک
`ProviderResponseInvalid` و ۳ condition اجرا‌نشده از ۶ مورد. هزینهٔ تخمینی
$0.002005245 و hold تازه صفر؛ هزینهٔ حساب واقعی unknown است.

[follow-up تازهٔ سقف خروجی](../docs/controlled-output-cap-followup.fa.md) فقط
همان نسخهٔ نامشخص را با همان ورودی/prompt/model و یک send مجاز ثبت می‌کند؛
خروجی ۳۸۴ به ۵۱۲، reserve ورودی ۱۵۳۶۰ و رزرو $0.002872320 در باقی‌ماندهٔ
grant قبلی $0.002909545 جا شد. روی `07d759f` پس از
[CI Linux/Windows](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38445395851)
یک send، یک سؤال ضروری نسخه، `finish_reason=stop` و ۳۸۵ token خروجی داشت؛
کاربرد هر پنج source تأییدنشده ماند. مقایسهٔ همان ورودی فقط تکمیل عملیاتی
۰ به ۱ است؛ علت خطای قبلی و افزایش کیفیت ثابت نشده. baseline اصلی همچنان
۲ proposal از ۶ condition و سه کنترل آخر در live اجرا نشده‌اند.
جمع دو epoch چهار send با $0.002845260 تخمینی، hold تازه صفر؛ grant قدیمی
$0.00206953 باقی دارد و رزرو کامل اجرای دیگر در آن جا نمی‌شود. halt/hold
قبلی حفظ‌اند؛ baseline و reviewer تغییر نکرده‌اند و retry خودکار نداریم.

این‌ها variationهای exposed یک خانواده‌اند، نه شش Issue مستقل، RAG واقعی
یا test نهایی؛ catalog و conflictها دستی‌اند. مشکل import مستقیم core در
process تازه جدا اصلاح شد و API عمومی حفظ است؛ این علت خطای provider نبود.
تست کامل محلی ۲۷۹۷ مورد، Ruff و سه demo پاس‌اند. CI و انتشار نهایی در PR
مرجع ثبت شوند؛ branchها پس از merge با `origin/main` sync شوند.

[راهنمای C4 به تیم و agentهای کاری](../docs/team-handoff-c4.fa.md) محدودهٔ
فایل‌ها و adopt کردن را مشخص می‌کند. قراردادهای مشترک و ماژول‌های اعضا تغییر
نکرده‌اند. وظایف سه dev case/corpus/smoke تیم پابرجاست؛ E1/E2/R4/E4/E5/C5 بازند.

انتشار #37 روی main `109f59e` و [CI Linux/Windows](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38406080389)
پاس شد. تحویل مستقل ساسان **C2g** در [PR #38](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/38)،
[query بعد از correction](../docs/current-retrieval-context.fa.md)،
است: reasoning/history حفظ می‌شود و context اولیهٔ retrieval از factهای فعلی،
پیام اخیر و hint موضوعی جدا می‌آید. [نتیجه و اصل receiptها](../experiments/retrieval_context/README.md):
روی ده variation تألیفی، کنترل لفظی ۷۲/۹۶ به ۹۶/۹۶ و همهٔ کنترل‌های هر سناریو
۲/۱۰ به ۱۰/۱۰ رسید؛ این کیفیت مدل نیست. index واقعی ۶۰ collection read داشت.
دو send آنلاین با $0.001115400 تخمینی همان سؤال ضروری callback را انتخاب کردند؛
منبع arm جدید نسخهٔ 1.64.0 برای کاربر 1.49.0 بود. کیفیت RAG/تصمیم بهتر اثبات نشد.
سیاست موجود `exact_user_version` به backend توصیهٔ نسخهٔ فعلی، **پس از probe و
با تست آفلاین** وصل شد؛ comparison با `all` محفوظ است. این فیلتر ranking/backfill
و coverage حسن در R4 را نمی‌بندد؛ وظایف سه dev case و corpus تیم همان‌اند.

تحویل محلی C2g: ۲۷۱۴ pytest، Ruff و HTTP/SQLite با process تازه ۴۵۷/۴۵۷ پاس؛
۲۱ تست مستقل scope روی هر دو seam اتصال اجرا شد. source receipt آنلاین همان
`0b3f1cc` است و binding بعدی آفلاین در `a06925f`؛ CI انتشار نهایی در PR مرجع
است. [verification و اصل receiptها](../experiments/retrieval_context/README.md)
بهبود query را از کیفیت مدل و source جدا نگه می‌دارند.

نسخهٔ قبلی با [PR #36](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/36)
روی main `a087770` است؛ [CI انتشار Linux/Windows](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38387712898)
پاس شد. [تحویل تازهٔ مستقل](../docs/evaluation-live-routes.fa.md): runner فقط
مسیر ثبت‌شدهٔ متناسب با سؤال واقعی را اجرا می‌کند؛ factory مشترک Chroma/model،
case binding پایدار و helper امتیازهای review اضافه شده‌اند. این‌ها پذیرش
عملیاتی با mock هستند؛ rubric/fixture نهایی، کیفیت و C5 هنوز بازند.

بررسی نهایی محلی این تحویل: ۲۶۱۶ pytest، Ruff و سه demo پاس؛ AppTest صفحهٔ
واقعی با همین factory و provider mock و HTTP/SQLite تازه ۴۵۷/۴۵۷ پاس‌اند.
[مقایسهٔ ثبت‌شدهٔ runner](../experiments/evaluation_routes/README.md) روی همان
fixture و portهای mock: تکمیل مسیر قبلی ۰/۳ و مسیر شاخه‌ای ۳/۳؛ baseline
هیچ check مکانیکیِ fail نداشت، اما ادامهٔ درست گفتگو را کامل نمی‌کرد.
این بهبود عملیاتی است؛ کیفیت مدل/RAG یا سه case مستقل نیست. CI و publication
نسخهٔ نهایی در PR ثبت شوند؛ [verification محلی](../experiments/evaluation_routes/verification-v3.json)
و اصلاحات audit نسخه‌های V1/V2/V3 حفظ‌اند؛ اصل receiptها بازنویسی نشوند.

هدف امشب درخواست ساسان است، نه تأیید زمان اعضا. اول یک برش dev قابل بررسی
بسازیم، سپس تمام الزام‌ها را ببندیم؛ سه case جای ۳۰ case را نمی‌گیرد.
هر تحویل PR، دستور اجرا و receipt داشته باشد؛ اگر امروز نمی‌رسد، blocker و
قسمت قابل تقسیم همان روز اعلام شود. فردا ارائه/bonus پس از روشن شدن وضع
بخش الزامی بررسی شود. branchها از `origin/main` sync شوند؛ تغییر plan با PR
منتقل می‌شود و از لپ‌تاپ دیگر فوری دیده نمی‌شود.

| مالک / محدودهٔ فایل | کار مشخص این برش | شرط پذیرش و ادامه |
| --- | --- | --- |
| ساسان — core، `evaluation/runner.py`، `routes.py`، `live.py`، `semantic_review.py`، `live_backend.py` | اتصال مسیرها، receipt معتبر، case/revision/retry و helper review؛ review/انتشار این تحویل؛ بعد baseline واقعی dev | تست‌های آفلاین و CI؛ baseline با config ثابت و protocol قبلی؛ خرج فقط ضروری/ثبت‌شده با همان ledger و علت C5 محفوظ. هم‌زمان این فایل‌ها توسط اعضا ویرایش نشوند |
| محمدحسن — `data/evaluation/dev/`، `test/`، manifest، rubric و UI | [packet سه dev آماده](../data/evaluation/dev-three-v1/split-manifest.json) را review/adopt کند؛ chronology، خانواده‌ها/exposure، oracle و rubric را با حسن ببندد | fixtureها قبل از run ثبت شده‌اند؛ ادامهٔ تألیفی و exposure صریح است. review مستقل original و edit جدا، usefulness انسانی؛ سپس تکمیل ۱۵ dev/۱۵ test و حداقل ۱۰ multi-turn، پنج test. E1/E2 هنوز بازند |
| حسن — retrieval، corpus و exclusion | برای همان سه dev case، شاهد مرتبط و نسخه‌دار یا unknown صریح معرفی کند؛ linkage/exclusion خانواده‌ها را با محمدحسن ببندد؛ top hit نسخهٔ 1.64 برای کاربر 1.49 را با ranking/filter/backfill و coverage منابع dev بررسی کند | URL/revision/hash/span/نسخه و coverage لازم/مفقود؛ خود case/comment/outcome/duplicate و جواب مستقیم از index خارج؛ build نهایی نسخه‌دار و receipt retrieval روی dev. فیلتر core منبع جایگزین نمی‌آورد؛ docs pilot فعلی برای ادعای کیفیت کافی نیست |
| بهنام — tracker/tools و شاهد T4 | یک receipt دو-case از UI موجود تا API/SQLite: approve/edit/reject، correction، approval قدیمی، restart/retry و جابه‌جایی case | action تکراری صفر و revision درست؛ PR با command/receipt روی main تازه. tracker موجود را استفاده کند؛ startup مدل عمومی در C5 halt مسدود است، smoke آفلاین مستقل انجام شود |

پس از این برش، ساسان baseline/model comparison ثبت‌شده را اجرا می‌کند؛
خانواده‌های test فقط پس از freeze و بدون tuning اجرا شوند. هیچ case، نمرهٔ
انسانی، corpus نهایی یا حل halt از طرف افراد تأییدشده فرض نمی‌شود.

بازبینی بخش الزامی پس از #37، بدون bonus: **حدود ۷۵٪، برآورد مهندسی و نه نمرهٔ کیفیت**.
برآورد قبلی ۷۰٪ بود؛ آماده‌شدن routeها/factory/helper موجب این تغییر است،
نه افزایش تعداد pytest یا اثبات کیفیت مدل. dev مستقل همچنان ۱ و test صفر است.
[مسیر کوتاه تکمیل و حدود شواهد](../docs/delivery-readiness-2026-10-13.fa.md):
اولویت با caseهای مستقل، corpus/exclusion نهایی، baseline واقعی dev و test
بدون tuning است. infra آماده‌تر است؛ تست‌های آفلاین این کارها را نمی‌بندند.

گام مستقل تازه: cleanup runner اصلاح شده؛ [۱۵/۱۵ candidate metadata](../data/evaluation/candidates/reservations-v1.json)
و gate مکانیکی `frozen_final_v1` آمادهٔ بازبینی‌اند. candidateها هنوز case نهایی
نیستند، partial exclusion هنوز به corpus نهایی اعمال نشده و E1–E5 بازند.
runner در حالت final کل bundle و evidenceهایش را قبل از live factory بررسی
می‌کند؛ branchهای adaptive در تحویل تازه پیاده‌اند و semantic helper judgment
caller را ثبت می‌کند؛ scoring مستقل و freeze هنوز باقی‌اند. [protocol اتصال واقعی دو turn](../experiments/grounded_http_acceptance/connected-live-protocol-v1.json)
با index موجود، correction و ledger اصلی ثبت می‌شود؛ اجرا و نتیجه جدا گزارش
می‌شوند. مجوز API جدید کاربر شامل آزمایش ضروری است؛ سقف تیم و halt/hold قبلی
حفظ می‌شوند. هیچ پیام تیمی از این مرحله ارسال نشده است.

اجرای واقعی همین مرحله روی `fbac1b4` انجام شد؛ [receipt و review](../experiments/grounded_http_acceptance/connected-live-README.md):
۲ send، $0.001104015 تخمینی؛ correction، proposal تازه، retry و ساخت دوبارهٔ
API پایدار پاس‌اند. در هر دو turn مدل سؤال callback لازم را انتخاب کرد؛ fix یا
حل Issue ادعا نشد. source نسخهٔ نامعلوم و relevance محدود داشت؛ R4 و C4 بازند.
ناسازگاری انتظار Python با `context_changed=true` در review ثبت شده و اصل
protocol حفظ شده است. ۱۵/۱۵ metadata همچنان candidate است؛ dev واقعی ۱ و test
واقعی ۰. خرج بیشتر پس از case/rubric و یک مقایسهٔ dev ثبت‌شده انجام شود.

بررسی محلی پس از receipt: ۲۴۲۴ pytest، mapper ۱۳۲/۱۳۲، core/SQLite ۴۹/۴۹،
HTTP/SQLite با interpreter تازه ۴۵۷/۴۵۷ و replay روی دو index موجود ۷۰/۷۰.
این‌ها عملیاتی‌اند. گسترش تست‌های Windows، خواندن seed با encoding پیش‌فرض
در یک تست تازه را آشکار کرد؛ UTF-8 صریح اصلاح شده و پذیرش CI نسخهٔ نهایی
پیش از merge لازم است. جزئیات در verification همان packet ثبت می‌شوند.

| بخش | چیزی که داریم | چیزی که هنوز اثبات نشده |
| --- | --- | --- |
| core — ساسان | قراردادها، correction و GroundedPlan؛ C2a سرویس core و C2d اتصال HTTP به SQLite موجود با outcome اتمیک و approval دقیق؛ HTTP پایدار #30 روی main؛ UI و index محلی در [U3a/P4a، PR #32](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/32) پیاده و با تست‌های مستقل پذیرفته شده‌اند | corpus/index نهایی، اتصال مدل و کیفیت تصمیم روی caseهای ندیده؛ C5 halt |
| داده — آماده‌سازی اولیه ساسان؛ ادامه با حسن | seed اولیه در `streamlit-data-for-dev-test/`: ۲۴۰ Issue، ۱۱۷۸ comment، ۵۶ متن Markdown و ۱۱۷۲ API record؛ adapter حسن و اصلاح اتصال ساسان با #27 و #23 روی main در `ec1a1f0`؛ mapper واقعی ۱۳۲/۱۳۲؛ [بازبینی #35](../experiments/retrieval_acceptance/pr35/README.md) رسید reference را از mapper و index واقعی جدا می‌کند؛ build pilot ۱۴ docs/۳۰ chunk | provenance تمام corpus، segmentation و exclusion نهایی؛ کیفیت retrieval واقعی و split مستقل |
| UI/API — محمدحسن | structured input و review کامل در #13/#21، case switching؛ UI پیش‌فرض memory/scripted؛ مسیر opt-in SQLite/index، auth و retry دقیق در U3a وصل شده | تنظیم نهایی index/model و auth محصول؛ recovery بعد پایان کامل session مرورگر |
| tracker/tools — محمد بهنام | SQLite #19/#20 روی main؛ state/revision/correction/authenticated review؛ اتصال C2d با ساسان outcome/snapshot/ABA و HTTP restart/retry را پاس کرده | شواهد evaluation نهایی T4 و تنظیم محصول؛ binding UI آفلاین پاس شده، action comment محلی است |
| evaluation — محمدحسن | یک dev چهار‌نوبتی، manifest پیش‌نویس، runner #15 و scenarioهای عملیاتی #18 | ۱۵ dev و ۱۵ test، rubric و split freezeشده، اجرای واقعی و داوری کیفیت؛ سناریوهای synthetic جزو ۳۰ case نیستند |

تغییرات جدید core از طریق [PR #7](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/7) با merge commit `85b6027` به `main` رسیدند. [گزارش V8](../docs/controlled-core-v8.fa.md)، [گزارش V9](../docs/controlled-core-v9.fa.md) و [قرارداد GroundedPlan](../docs/extractive-core.md) شواهد این milestone هستند. ۱۴۱۴ تست آفلاین در milestone محلی و ۱۴۲۸ تست همراه API/UI در CI ترکیب PR با main پاس شدند؛ نتیجهٔ RAG واقعی یا test نهایی نیست. GroundedPlan اختیاری است و پیش‌فرض production تغییر نکرده.

### قدم جاری پس از پذیرش HTTP/SQLite — ۲۰۲۶-۱۰-۱۳

[PR #27](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/27) با `4162079`
به `feat/rag-module` و بعد [PR #23](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/23)
با `ec1a1f0` به main merge شدند. هر دو CI روی head تازهٔ #23 پاس شدند؛
[CI انتشار main](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38225492349)
نیز ۱۸۹۱ تست، Ruff و replayهای آفلاین را پاس کرد.
[receipt تازهٔ main](../experiments/retrieval_acceptance/results-main-ec1a1f0.json)
در checkout تمیز: ۱۴ case / ۱۳۲ check؛ ۹۵ تست مرتبط و ۴۹ check مستقل
core/SQLite دوباره پاس شدند. کد و fixture با اجرای تمیز `326480d` یکسان‌اند؛
[شواهد انتشار](../experiments/retrieval_acceptance/release-main-ec1a1f0.json)
و [حدود پذیرش](../docs/rag-adapter-acceptance.fa.md) ثبت‌اند.
انتشار R3 فقط port آفلاین را بست. پس از آن #29 روی main `cddef782` منتشر شد؛ مسیر پایدار HTTP/SQLite در #30 روی main `6e719e9` منتشر شد؛ [receipt ۴۵۷/۴۵۷](../docs/persistent-http.fa.md). اصلاح Windows بهنام در [PR #31](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/31) با `877601c` روی main است و [CI آن](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38314737701) پاس شد. اتصال UI/index محدود در [U3a/P4a](../docs/offline-ui-index-pilot.fa.md) آزمایش شده؛ [receipt روی source تمیز `c14314f`](../experiments/ui_review_acceptance/verification-c14314f.json): ۲۲۱۸ pytest، UI baseline ۲/۶ و نسخهٔ جدید ۶/۶، Chroma واقعی ۱۴ source / ۳۰ chunk، HTTP پایدار ۴۵۷/۴۵۷. این اعداد پذیرش عملیاتی‌اند؛ corpus/index نهایی و کیفیت مدل همچنان بازند.

| نفر / task | قدم بعدی | خروجی لازم برای پذیرش |
| --- | --- | --- |
| حسن — R1/R2/R4 و بخش index در P4 | از profile و builder موجود شروع کند؛ با محمدحسن exclusion خانواده‌ها را از manifest E1 بگیرد، corpus/index نهایی نسخه‌دار بسازد و retrieval را روی dev بررسی کند | PR با provenance، segmentation و coverage؛ exclusion خود case، جواب، comment و duplicateها؛ snapshot/hash و دستور build تازه؛ sourceهای لازم/مفقود و version scope روی dev، بدون tuning روی test؛ `index_data` قدیمی هنوز مسدود است |
| محمدحسن — E1/E2/U3 | خانواده‌ها و rubric را پیش ببرد؛ مسیر runnable U3a را برای تنظیم/evaluation نهایی به کار بگیرد | manifest dev/test برای حسن؛ smoke مرورگر واقعی؛ source support و سؤال ضروری با داوری مستقل؛ AppTest و payload retry در U3a پاس‌اند |
| محمد بهنام — T4، مشترک با U3 | اتصال C2d را review و تنظیم database/credential را با محمدحسن جمع کند | همان receipt restart/retry/rollback؛ وضعیت ابزار در evaluation و پیکربندی نهایی؛ tracker دوم یا reset نساختن |
| ساسان — C2f/C4/C5، مشترک با P4 | اتصال GroundedPlan در [C2f/PR #34](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/34)؛ پذیرش snapshot نهایی حسن و ارزیابی تصمیم با معیار E2 | receiptهای آفلاین و probe محدود موجود؛ C5 هنوز halt دارد، live عمومی مجاز نیست؛ corpus نهایی و baseline کیفیت مدل جدا باقی‌اند |

[PR #35](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/35) رسید اصلی حسن را بدون تغییر حفظ می‌کند؛ آن رسید `reference_fixture_adapter` است، نه index. [build و replay جدا روی index موجود](../experiments/retrieval_acceptance/pr35/README.md) با همان adapter/core/tracker انجام می‌شود. دو build تازه manifest/snapshot یکسان دارند؛ [verification](../experiments/retrieval_acceptance/pr35/verification-82c39a9.json): mapper واقعی با backend ثابت ۱۳۲/۱۳۲، replay روی همان index موجود ۷۰/۷۰ با ۲۸ query Native و suite تمیز ۲۲۹۸ تست. rule محدود Git، byteهای seed را با `autocrlf=true/false` حفظ می‌کند. این شواهد P4a محدود را تقویت می‌کند؛ R1 نهایی، R2، R4 و E1/E2 همچنان بازند. وضعیت انتشار و CI همان PR مرجع است.

اتصال محدود [PR #32](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/32) روی main با `2ce25ab` منتشر شد؛ CI لینوکس و Windows روی [head شاخه](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38316532488) و [ترکیب PR](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38316540401) سبز است. کد و checklist همین نسخه مبنای اتصال تیم است. هیچ‌کدام از تیک‌های U3a/P4a، R2/R4 یا E1–E5 را نمی‌بندد. هر نفر branch خود را با `origin/main` sync کند؛ تغییر checklist با PR و شاهد انجام کار منتقل شود.

انتخاب caseها و کار API می‌توانند هم‌زمان جلو بروند. برای E1، seed در repo
موجود است؛ منتظر ZIP یا index نمانیم. caseها، جواب‌ها و duplicateهای خانوادهٔ
ارزیابی وارد corpus مجاز نشوند؛ #12782/#12629 همچنان exposed dev هستند.

## قدم مشترک بعدی: یک case چندمرحله‌ای از dev

### درخواست تحویل قبلی — ۲۰۲۶-۱۰-۱۰

این‌ها درخواست هماهنگ‌کننده برای یک برش کوچک از pilot هستند؛ به معنی تأیید
زمان‌بندی توسط اعضا یا بسته‌شدن taskهای اصلی نیستند. اگر خروجی امروز نمی‌رسد،
همان روز blocker و قسمت قابل واگذاری اعلام شود تا تقسیم کنیم یا ساسان آن قسمت
را بردارد. تحویل هر نفر یک branch/PR و دستور اجرای نمونه یا تست مربوط است.

| نفر | خروجی قابل تحویل امروز | شاهد حداقلی |
| --- | --- | --- |
| حسن — P4/R3 | adapter `search(RetrievalRequest)` برای همین case با EvidenceBundle و metadata کامل؛ فعلاً fixture کافی است | snapshot/ID/URL/span/commit/نسخهٔ منابع؛ آخرین bundle پس از refinement |
| محمد بهنام — P3/T1–T3 | برش state/revision و pending approval برای همین case، با محل persistence مشخص | correction مجوز قبلی را باطل کند؛ retry event/action تکراری نسازد؛ هر کنترل هنوز ناقص، صریح ثبت شود |
| محمدحسن — P1/U2/E2 | ورودی fact/correction و نمایش کامل review به API وصل شود؛ همین fixture شروع pilot باشد | یک اجرای پیام/جواب سؤال/اصلاح/approve یا reject؛ برای split و caseهای ارزیابی، وضعیت واقعی و فایل manifest اولیه گزارش شود |

تکمیل index نهایی، همهٔ ۳۰ case یا evaluation نهایی، شرط این تحویل کوچک نیست.

### قدم قبلی پس از بازبینی — ۲۰۲۶-۱۰-۱۱

اصلاحات runner/UI و نسخهٔ تازهٔ همین plan در
[PR #21](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/21) ثبت شده‌اند؛
وضعیت انتشار و CI همان PR مرجع است. اصلاح tracker در
[PR #20](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/20)
به branch بهنام merge شد (`6628758`) و سپس
[PR #19](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/19)
به main رسید (`464e55e`). [CI branch tracker](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38150131745)
و [CI بازبینی fix](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38150134843)
روی `6628758` پاس‌اند؛ [CI انتشار main](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38150252419)
هم روی `464e55e` پاس شد.

PRهای #13، #14، #15، #17 و #18 روی main هستند؛ runner هنوز کیفیت مدل را
امتیاز نمی‌دهد و API از DummyTracker استفاده می‌کند. [بازبینی اتصال](../docs/team-integration-review-2026-10-11.fa.md)
نتیجهٔ تست‌ها و اصلاحات مرزی را ثبت می‌کند. درخواست تحویل امروز، یک برش کوچک
از pilot است؛ زمان‌بندی قطعی اعضا نیست. تحویل یک branch/PR، دستور اجرا و شاهد
باشد؛ اگر وابستگی مانع است، blocker و بخش مستقل همان روز ثبت شود:

| نفر | قدم امروز | خروجی قابل بررسی | اگر وابستگی مانع بود |
| --- | --- | --- | --- |
| ساسان — C2a/C3 | [CoreTurnService و pilot مستقل](../docs/core-turn-service.fa.md) آماده‌اند؛ اتصال API را با محمدحسن و بهنام بررسی کند | receipt/replay، context چندنوبتی، full-state guard و ACK دقیق؛ ۴ turn و ۴۹ check عملیاتی | تا adapter API آماده شود، همین سرویس با SQLite و fixture اجرا شود؛ journal/CAS lifecycle هنوز بازند |
| محمد بهنام — T4/P3 با U3 | با محمدحسن مسیر API را به تنها مرجع state یعنی SQLite وصل کند | replay پیش از مدل، review_id ثابت و hash دقیق؛ restart/retry/rollback و دو پرونده مستقل | اگر مرز API/auth آماده نیست، عملیات و کدهای خطای لازم را با fixture مشترک تحویل دهد |
| محمدحسن — E1/E2/U3 | دریافت ZIP را تأیید و انتخاب خانواده‌ها را شروع کند؛ schema/rubric و branch سؤال‌ها را با core هماهنگ کند | manifest پیش‌نویس خانواده‌ها برای حسن؛ یک dev با مسیرهای معتبر؛ review جدا برای original و edited/released | اگر ZIP نرسیده، blocker تحویل را ثبت و schema/branchها را روی dev موجود جلو ببرد؛ منتظر index نماند |
| حسن — R1–R3/P4 | backend موجود PR #23 را با main sync و CI را سبز کند؛ adapter قرارداد core را روی همان backend اضافه کند | EvidenceBundle با snapshot/نسخه/span، سقف کلی top_k و dedup؛ allowlist کوچک و exclusion dev پیش از index | تا E1 نهایی، collection/embedding ساختگی و docs مجاز pilot را تست کند؛ corpus نهایی هنوز باز بماند |

بازبینی اولیهٔ [PR #23 و شرط تحویل R3](../docs/rag-handoff-review-2026-10-11.fa.md)
روی `c0d450a`: backend اولیه push شده، ولی port هنوز خروجی خام Chroma می‌دهد؛
probe آفلاین با collection ساختگی در core به `RetrievalResultInvalid` و صفر
فراخوانی مدل رسید. metadata commit/location و chunkهای بزرگ باید پیش از اتصال
اصلاح شوند؛ [CI همان head](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38157755729)
با ۳۱ finding در Ruff متوقف شد. R1/R2/R3/P4 بازند. بازبینی محدود core در
`37ce74a` ایراد تازهٔ قابل بازتولیدی پیدا نکرد؛ ۱۷۹۶ تست و pilot چهار‌نوبتی
با ۴۹ check، شاهد آمادگی آفلاین C2a هستند. این milestone کیفیت RAG/مدل نیست.

بازبینی پیشین، پیش از push اصلاحی — ۲۰۲۶-۱۰-۱۲: head #23 در `bdb7c53` بود. CI قبلی سبز شده،
ولی `adapter.py`، `retriever.py`، `data_scripts/chunking.py` و `data_scripts/data_loader.py` صفر بایت بودند؛ پس
آن CI شاهد پذیرش adapter نبود. seed کوچک و README در branch حسن موجود بودند.
در آن milestone کدها به push دوباره نیاز داشتند؛ R1/R2/R3/P4 باز بودند. [ثبت pinned head](../experiments/retrieval_acceptance/candidate-bdb7c53.json).

push تازهٔ حسن در `b571080` چهار فایل را برگرداند؛ پذیرش روی همان کد مشکل
namespace، حذف commit/span، clipping متن و snapshot را بازتولید کرد. ساسان با
اجازهٔ کاربر اصلاح محدود R3 را در branch جدا انجام داد؛ import استاندارد، حفظ
metadata/text، snapshot تنظیم‌شده و checkهای collection، filters و خطای امن اضافه
شدند. [binding و دستور واقعی](../docs/rag-core-acceptance.fa.md) اکنون mapper خود
adapter را آزمایش می‌کند؛ smoke اولیه ۱۳۲/۱۳۲ پاس است. fixture و تصمیم‌های
ثبت‌شده تغییر نکرده‌اند؛ مشاهدهٔ queryهای refinement از فرض یک read به بررسی
round فعلی اصلاح شد و mutation مستقل دارد. [receipt تمیز و مقایسهٔ pinned baseline](../docs/rag-adapter-acceptance.fa.md)
روی `326480d` ثبت شد؛ ۱۸۹۱ تست کامل و Ruff پاس‌اند. اصلاح با #27 و #23 منتشر شد؛
receipt تازهٔ main در بخش جاری بالاست. R1/R2/R4 و retrieval از index واقعی بازند.

سهم مستقل تازهٔ core، **C2b**، [kit پذیرش اتصال](../docs/rag-core-acceptance.fa.md)
است: fixture پیش از اجرا ثبت شد؛ همان factory با تست port و چهار turn
`CoreTurnService`/SQLite اجرا می‌شود. ۱۳۲/۱۳۲ check مرجع پاس؛ mutationهای
metadata، query، سقف نتیجه، snapshot، quote و evidence قدیمی رد شدند.
backend ثابت اکنون به seam کد واقعی حسن تزریق و همین protocol روی main اجرا
شده؛ نتیجهٔ fixture کیفیت RAG یا test نهایی نیست. API/persistence، index و
exclusion نهایی همچنان taskهای مستقل تیم‌اند.

healthcheck پیش از push بعدی RAG — ۲۰۲۶-۱۰-۱۲: main در `febaefa` تمیز و
با remote یکسان بود؛ [CI همان main](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38182028171)
۱۸۲۸ تست و replayهای ثبت‌شده را پاس کرد. ۱۱۸ تست مرتبط core/SQLite/acceptance
دوباره پاس شدند؛ fixture و هر ۴۷ fingerprint کد با receipt نهایی برابرند و
لینک‌های اتصال سالم‌اند. review مستقل core blocker تازه‌ای پیدا نکرد.
سقف query درخواست core با تعداد خواندن‌های داخلی backend فرق دارد؛ راهنمای
C2b این مرز را روشن می‌کند و هزینه/کارایی RAG همچنان R4 است. تغییر production
لازم نشد. قدم بعد، کد قابل اجرای R3/P4، اتصال API/SQLite با U3/T4 و freeze
caseها/exclusion با E1/R2 است؛ C5 نیز به مدرک provider وابسته است.

انتخاب caseها لازم نیست منتظر index بماند. seed اولیه همراه manifest با #23
در `streamlit-data-for-dev-test/` به main رسید؛ انتخاب E1 از همین فایل‌ها ممکن است.
این انتشار، تأیید دریافت ZIP در پی‌وی نیست. schema و [rubric پیشنهادی core](../docs/evaluation-rubric.md) هنوز
نیاز به پیاده‌سازی و freeze توسط مالک evaluation دارند؛ checkbox کیفیت باز است.

سهم core و fixture با [PR #11](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/11)
به `main` رسید (`edea31c`) و [CI انتشار](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38045540320)
پاس شد. قبل از اتصال، تغییرات محلی را حفظ کنید، `git fetch origin` بزنید و
branch کاری خودتان را از `origin/main` به‌روز کنید. همین نسخه مبنای pilot تیم است.

fixture پایهٔ این تحویل، [case چهار‌نوبتی C3](../experiments/review_handoff/case-current-state-latest-evidence.json)
است؛ [فرمان replay و محدودیت‌ها](../experiments/review_handoff/README.md) و
[قرارداد ورودی/خروجی اتصال](../docs/integration.md#complete-proposal-handoff-c3)
کنار آن‌اند. label و oracle فقط برای بررسی‌اند؛ وارد ورودی مدل یا index نشوند.

- [x] **P1 — محمدحسن:** یک case از dev معرفی کند؛ ورودی شروع، follow-upها، اصلاح اطلاعات و تصمیم‌های قابل قبول را قبل از اجرا در fixture ثبت کند. اگر ادامهٔ گفتگو ساخته شده، آن را از گفتگوی واقعی جدا علامت بزند. case `dev-pilot-12782` (خانوادهٔ #12782/#12629، فقط dev) در [`data/evaluation/dev/pilot-12782.json`](../data/evaluation/dev/pilot-12782.json) با commit `3e0a86a` پیش از اولین اجرا ثبت شد ([PR #14](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/14))؛ follow-upها developer-authored علامت خورده‌اند و شواهد همان excerptهای رسمی C3 با SHA ثبت‌شده‌اند. runner `uv run python -m agent_app.evaluation.pilot data/evaluation/dev/pilot-12782.json` همان API رابط را آفلاین اجرا می‌کند: پیام، approve سؤال نسخه، پاسخ bind‌شدهٔ `1.50.0`، correction به `1.49.1` که proposal قبلی را stale می‌کند (approve قدیمی 409)، edit و approve نسخهٔ ویرایش‌شده، withdrawal و reject بدون ارسال، و replay همان event. [receipt](../data/evaluation/receipts/pilot-12782-v1.json): ۴۸ از ۴۸ check پاس. agent اسکریپتی است و storage حافظه‌ای؛ این receipt کیفیت تصمیم، RAG یا tracker پایدار را نشان نمی‌دهد.
- [x] **P2 — ساسان؛ مسیر آفلاین core/API:** اطلاعات صریح HTTP به UserTurn معتبر وصل شد؛ correction/withdrawal/تغییر محیط، factهای قدیمی و inference/ref را کنار می‌گذارند. reply فقط به سؤال canonical تأییدشده و همان case/revision/proposal متصل است. [fixture هفت‌نوبتی و receipt](../docs/user-intake-pilot.fa.md)، replay/old approval و baseline چهار regression قابل بررسی‌اند. این تیک adapter با storage حافظه‌ای را پوشش می‌دهد؛ UI واقعی و transaction پایدار با U2 و T2/T3 تکمیل می‌شوند. متن آزاد به‌تنهایی fact تأییدشده نیست.
- [x] **P3 — tracker بهنام؛ اتصال آفلاین HTTP با ساسان.** همان پرونده و proposal با revision معتبر حفظ و approval قدیمی/قبل edit رد می‌شود؛ review دقیق پس از restart receipt/action قبلی را می‌دهد و comment محلی فقط یک بار ثبت می‌شود. [پذیرش C2d و crash/rollback](../docs/persistent-http.fa.md) شاهد است؛ این تیک pilot عملیاتی محلی است، نه اتصال frontend/index/model یا ارزیابی کیفیت.
- [ ] **P4 — حسن؛ اصلاح اتصال با ساسان:** mapper واقعی اکنون با collection ثابت از همان case عبور می‌کند؛ [receipt تمیز ۱۳۲/۱۳۲](../docs/rag-adapter-acceptance.fa.md) شامل چهار turn با SQLite است. بعد از آماده شدن corpus مجاز، همان قرارداد روی index واقعی اجرا شود؛ این قسمت هنوز باز است.

**شرط پایان pilot آفلاین:** ورودی، سؤال تأییدشده، پاسخ کاربر، correction، revisionها، evidence فعال/کنارگذاشته‌شده و proposal در trace قابل بازبینی باشند. ماژول tracker مستقل آماده است؛ تا مسیر API/UI با persistence و recovery تأیید نشده، receipt رابط فقط «pilot با fixture و storage حافظه‌ای» است.

**شرط پایان اتصال واقعی:** همان مسیر با retrieval واقعی و tracker پایدار اجرا شود؛ reject و edit، approval قدیمی، retry یک event/action و restart بررسی شوند؛ نتیجهٔ ابزار در state و تصمیم بعدی دیده شود. اجرای مدل واقعی فقط پس از حل توقف ledger و با سقف هزینهٔ ثبت‌شده مجاز است. آماده بودن pilot آفلاین به معنی رسیدن به این مرحله نیست.

## checklist هر نفر

راهنمای نقش‌ها: [حسن](member_1_todo.md)، [ساسان](member_2_todo.md)، [محمد بهنام](member_3_todo.md)، [محمدحسن](member_4_todo.md). وضعیت taskها فقط در همین checklist ثبت شود؛ فایل‌های نقش، راهنمای ارجاع به آن‌اند.

### حسن — داده و RAG

- [ ] **R1 — بازبینی seed و provenance.** seed و manifest در `streamlit-data-for-dev-test/` روی main موجودند؛ تعدادها، روش انتخاب، URL/تاریخ، commit و نسخهٔ اسناد را تا corpus/index بازبینی و ثبت کند. دامنهٔ اولیه Session State، widgets، callback/rerun است؛ همهٔ Streamlit را نمایندگی نمی‌کند. body فعلی Issue ممکن است بعداً ویرایش شده باشد.
- [ ] **R2 — کنارگذاری خانواده‌های ارزیابی، قبل از index نهایی.** فهرست dev/test از E1 را بگیرد؛ خود Issue، commentها، outcomeها، duplicateها و docs حاوی جواب مستقیم همان case را بررسی کند. خروجی: corpus allowlist، exclusion manifest و گزارش بررسی linkage/duplicate؛ candidate مرتبط به معنی duplicate قطعی نیست.
  **به‌روزرسانی حسن ۱۷ اکتبر — build پس از freeze (v3):** rebuild با `split-manifest-frozen-v1.json`؛ exclusion
  ۹۵ Issue ([exclusion-v2](../experiments/final_corpus_v1/exclusion-v2.json))، همان ۱۲۲۸ منبع/۱۸۲۷ chunk و
  allowlist. [رسید v3](../experiments/final_corpus_v1/build-receipt-v3.json): snapshot
  `docs-pilot-20ab0d69…`، index manifest `933682e5…`، exclusion `1e9f0469…`؛ build تکرارپذیر،
  snapshotهای ۱۴/۱۸ منبعی بدون تغییر، صفر سند ممنوعه. pinهای v1/v2 و index قبلی دست‌نخورده‌اند.
  ثبت native gold روی این pinها با محمدحسن.
  **به‌روزرسانی حسن ۱۷ اکتبر — build نهایی (E2ad):** protocol سوم `docs-api-release-final-v1`
  کنار دو پروفایل قبلی؛ snapshotهای ۱۴ و ۱۸ منبعی از ورودی فعلی بدون تغییر. منابع بسته: ۴۷ صفحهٔ
  docs، ۹ release note (نوع `release_note`، بدون نسخهٔ استنتاجی) و ۱۱۷۲ رکورد API با نسخهٔ دقیق
  (۴۳ نسخه)؛ ۱۲۲۸ منبع و ۱۸۲۷ chunk. راهنمای custom-classes در کد و allowlist رد می‌شود.
  [exclusion](../experiments/final_corpus_v1/exclusion-v1.json) از `index_exclusion` همان۹۰ Issue
  split-e1-v1؛ صفر Issue/comment index شده؛ فقط metadata manifest خوانده شد، نه test.
  [دستور build، allowlist و رفع blocker اتصال](../experiments/final_corpus_v1/README.md): هر search
  ۲۲ بار کل storage را verify می‌کرد (۴٫۲/۵٫۱ ثانیه روی Chroma واقعی). برای صرفه‌جویی در وقت و
  نزدیک بودن deadline، تصمیم با خود حسن بود: یک verify کامل قبل و یک بعد از هر search با
  `read_session`؛ ردیف‌های برگشتی همچنان تک‌تک چک می‌شوند و تغییر storage در پایان search رد
  می‌شود. نتیجه روی Windows: ۰٫۴۹/۰٫۴۷ ثانیه در هر search، همان snapshot و pinها؛ ۱۵۰ تست مرتبط
  شامل همهٔ تست‌های mutation در Chroma واقعی پاس. ranking/packing جدا. بعد از freeze، exclusion
  تازه و rebuild.
- [x] **R3 — adapter بازیابی؛ کد پایه حسن، اصلاح اتصال ساسان.** `search(RetrievalRequest)` با snapshot تنظیم‌شده، سقف کلی top_k و metadata صریح/unknown پیاده است؛ mapper واقعی همراه constructor/backend واقعی با collection ثابت، [۱۴ case و ۱۳۲ check](../docs/rag-adapter-acceptance.fa.md) را پاس کرد. پس از refinement آخرین bundle در handoff است؛ alias یا اصلاح خروجی در binding نداریم. با #27 و #23 منتشر شد و [receipt تمیز main `ec1a1f0`](../experiments/retrieval_acceptance/results-main-ec1a1f0.json) پاس است. این تیک فقط port آفلاین را می‌بندد؛ index/corpus/کیفیت RAG در R1/R2/R4/P4 بازند.
- [ ] **R4 — آزمون بازیابی روی dev.** سند کامل/ناقص، نسخهٔ نامعلوم/متفاوت، conflict و خطای retrieval را بررسی کند؛ relevance و پوشش منابع را جدا از کیفیت متن مدل ثبت کند. [مشاهدهٔ واقعی C2g](../experiments/retrieval_context/README.md): query تمیز هم `text_input` نسخهٔ 1.64.0 برای مسئلهٔ multiselect کاربر 1.49.0 آورد؛ gate core ranking/backfill ندارد. خروجی: تست adapter و receipt بازیابی با snapshot/config مشخص، منابع مرتبط multiselect/fragment و رفتار پس از رد نسخهٔ نامرتبط.

وابستگی: R1 و fixture مربوط به P4 اکنون مستقل قابل انجام‌اند؛ R2 و index نهایی به E1 وابسته‌اند. مدل یا embedding پولی از ledger و سقف مشترک عبور می‌کند.

### ساسان — core و قرارداد اتصال

- [x] **C1 — انتشار و اتصال نسخهٔ مشترک core.** commitهای V8/V9 و راهنمای اتصال در [PR #7](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/7) منتشر شدند؛ [CI روی commit 8cf56d8](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38033908496) پاس شد. ۱۴۱۴ تست محلی و Ruff هم پاس‌اند؛ مقایسهٔ baseline در گزارش‌های V8/V9 ثبت است. [CI ترکیب PR با main](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38033931700) هم با ۱۴۲۸ تست پاس شد؛ PR با اجازهٔ ساسان به main merge شد (`85b6027`).
- [x] **C2a — coordinator مستقل core با tracker موجود.** [CoreTurnService و دستور اجرا](../docs/core-turn-service.fa.md): original-event replay و receipt عقب‌افتاده پیش از factory متوقف؛ پیام‌های کاربر برای reply کوتاه حفظ؛ facts فعال مرجع؛ full-state freshness؛ handoff کامل و read دقیق ACK. [تست سرویس](../tests/test_core_turn_service.py)، [context](../tests/test_core_conversation.py) و [freshness](../tests/test_engine_freshness.py) با SQLite واقعی و portهای تألیفی شاهدند؛ pilot موجود چهار turn و ۴۹ check عملیاتی دارد. این تیک سهم مستقل core را می‌بندد، نه API، journal/resume، CAS lifecycle یا کیفیت مدل.
- [x] **C2b — kit پذیرش RAG/core با fixture.** [protocol و دستور اجرا](../docs/rag-core-acceptance.fa.md)، [fixture پیش‌ثبت‌شده `db9c2c0`](../experiments/retrieval_acceptance/fixture-v1.json) و [receipt مرجع](../experiments/retrieval_acceptance/results-fixture-v3.json): ۱۴ case، ۱۳۲ check؛ ۴ turn، ۵ retrieval و ۵ reasoning اسکریپتی با SQLite واقعی. [اجرای mapper واقعی R3](../docs/rag-adapter-acceptance.fa.md) نیز ۱۳۲/۱۳۲ پاس است؛ خطای فرض یک read برای هر query در observation pilot با mutation مستقل اصلاح شد. ترتیب ranking/query آزاد است؛ evidence قدیمی و نقص‌های port رد می‌شوند. هزینهٔ API صفر؛ index/corpus و کیفیت واقعی بازیابی/مدل همچنان خارج این تیک‌اند.
- [x] **C2c — پذیرش pilot آفلاین از HTTP.** #29 با review و CI به main `cddef782` رسید؛ حافظهٔ پیش‌فرض همچنان restart را رد می‌کند. مسیر opt-in SQLite در C2d همان fixture را با [receipt تمیز ۴۵۷/۴۵۷](../experiments/http_pilot_acceptance/results-sqlite-b7107c0.json) و پنج checkpoint با process تازه پاس کرد؛ correction، approval قدیمی/قبل edit، کل view/action و صفر بودن port در retry بررسی شدند. [گزارش و محدودیت‌ها](../docs/persistent-http.fa.md)؛ این تیک عملیات آفلاین HTTP/core/tracker را می‌بندد، نه اتصال UI/index/model یا کیفیت evaluation.
- [x] **C2d — اتصال مستقل HTTP به tracker موجود؛ ساسان.** با #30 روی main `6e719e9` منتشر شد: [factory و قرارداد](../docs/persistent-http.fa.md)، [protocol v2 ثبت‌شده در `6f0e8b5`](../experiments/http_pilot_acceptance/protocol-v2.json) و [مقایسهٔ backendها روی source یکسان](../experiments/http_pilot_acceptance/comparison-sqlite.json). همان CoreTurnService/SQLite، snapshot واحد، outcome واقعی و stage اتمیک؛ reviewer از credential سرور، review_id ثابت و hash دقیق؛ retry/restart بدون model/action اضافه. ۲۰۳۵ pytest، Ruff، crash واقعی بعد ingress/stage، rollback و ABA پاس؛ هزینه API صفر. payload/hash/auth و retry review در U3a وصل و آزمایش شدند؛ تنظیم محصول و evaluation کامل هنوز بازند.
- [ ] **C2 — اتصال ورودی چندنوبتی.** سهم core/API آفلاین در P2 انجام و [ثبت شد](../docs/user-intake-pilot.fa.md): reported_facts، checks_performed، context_changed، reply ثبت‌شده و original-event replay؛ تست correction/withdrawal/تغییر محیط پاس‌اند. U2 در #13 وصل شد و جداسازی فرم در #21 اصلاح شد؛ API/state/review آفلاین در C2d به قراردادهای T1–T3 وصل و P3 پذیرفته شد؛ binding UI و index محدود در U3a/P4a پاس شده‌اند؛ تنظیم index/model نهایی باقی است. [قرارداد recovery](../docs/persistent-core-handoff.md) بین commit event و stage proposal، replay بدون اجرای مدل و read پس از ACK نامعلوم را مشخص می‌کند؛ coordinator core در C2a پیاده شده؛ factory HTTP و outcome واقعی اکنون در C2d آمده؛ resume خودکار ساخته نشده است. سؤال مبهم یا ویرایش‌شده fact فرضی نمی‌سازد؛ retry همان event باید پیش از stale/reply check و ساخت adapter شناسایی شود. [بازبینی مرز اتصال](../docs/team-integration-review-2026-10-11.fa.md).
- [x] **C3 — قرارداد خروجی و review با fixture.** `ProposalHandoff` کل case، آخرین bundle واقعاً مصرف‌شده، تمام analysis و catalog واقعی GroundedPlan را نگه می‌دارد؛ gap کاربر/منبع، همهٔ منابع و scope نسخه قابل review هستند. منبع قبلی، تغییر case با revision یکسان، packet/متن دست‌کاری‌شده و approval پیش از edit رد می‌شوند. [PR #11](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/11)، [نتیجه و handoff](../docs/review-handoff-pilot.fa.md)، fixture ثبت‌شده `b085f7d`، helper `74e353b` و API `44d70a2` شاهدند. C3 فقط سهم core و مثال آفلاین را می‌بندد؛ نمایش U2 انجام شده و #21 تمام claimهای هر chunk را حفظ می‌کند. مسیر opt-in persistence/authentication/اجرای محلی در C2d پیاده است؛ اتصال UI به همان envelope باقی می‌ماند؛ review معنایی و approval جدا هستند.
- [ ] **C4 — baseline برای pilot متصل.** baseline ورودی HTTP روی `5af98e6` چهار fail و روی adapter جدید چهار pass دارد؛ [ثبت C2](../docs/user-intake-pilot.fa.md). baseline خروجی C3 روی کد واقعی `3f22ef9` با همان چهار regression بازپخش شد؛ چهار fail و روی نسخهٔ جدید چهار pass، همراه [case چهار‌نوبتی و محدودیت](../docs/review-handoff-pilot.fa.md). پس از اتصال P3/P4، مقایسهٔ تصمیم واقعی ادامه یابد؛ baseline نرم‌افزار جای کیفیت مدل/RAG/test نیست. receiptهای تاریخی حفظ شده‌اند؛ انتخاب Issue فعلی answer-informed و exposed است.
- [x] **C4a — harness و prefix محدود انتخاب واقعی مدل؛ ساسان.** [بستهٔ نتیجه و review](../experiments/controlled_model_baseline/README.md) runtime/reviewer جدا، ID خنثی و catalog مربوط به bundle فعلی دارد. شش variation یک خانوادهٔ exposed، mock شش‌مسیره و baseline واقعی prefix ثبت شد: ۳ send، ۲ proposal، یک خطا و سه terminal skip؛ follow-up جدا با همان prompt فقط یک سؤال نسخهٔ کامل داد. کل چهار send $0.002845260 تخمینی؛ منابع/کل پاسخ/سؤال، هزینه و محدودیت‌ها review شده‌اند، نمرهٔ انسانی null است. این تیک تحویل محدود را می‌بندد؛ baseline شش‌حالته کامل نشده و C4 مستقل/RAG/test نهایی بازند؛ correction/conflict/stale در live این packet اجرا نشدند.
- [x] **C4b — تداوم تعارض اعلام‌شده پس از refinement؛ ساسان، تحویل محدود آفلاین.** [protocol، مقایسه، receipt و review](../experiments/conflict_continuity/README.md): همان ۱۴ کنترل روی اصل `03225e2` هفت pass/هفت fail و روی `8cc41bf` چهارده pass. سه answer خطرناک مسدود، چهار ask/escalate مجاز با status حل‌نشده و فقط quote جاری؛ ۲۵ کنترل lifecycle/boundary و پنج تست HTTP با provider mock نیز پاس‌اند. repair مجاز status را حفظ و stop نهایی scope را آزاد می‌کند؛ run/case/revision بعدی تازه است. approval/retry/restart امن و request واقعی handoff بررسی شده‌اند. این تیک فقط این رفتار software را می‌بندد؛ تشخیص خودکار تناقض، مدل/RAG واقعی، C4 مستقل و test نهایی بازند؛ هزینه صفر و fixtureهای تاریخی بدون تغییر.
- [ ] **C5 — رفع علت halt پیش از live.** هویت مدل، usage و هزینهٔ مورد اختلاف با مدرک provider تطبیق داده شود؛ uncertainty و ledger پاک یا reset نشوند. شرط پایان: علت توقف مستند، وضعیت ledger و مجوز/سقف باقی‌مانده روشن باشند؛ فقط آن‌وقت pilot کوچک ثبت‌شده اجرا شود. [بررسی تازهٔ هر سه uncertain در C4k](../experiments/core_evidence_selection_v1/c5-readonly-report.fa.md) با۳۶کنترل read-only، همان۷۱۸reservation،۱۴جدول و SHA را حفظ کرد؛ HTTP200 اولی، خطای transport نامشخص دومی وconnect_timeout سومی، model/usage/charge قطعی یا zero-charge را ثابت نمی‌کنند. settled محلی$0.599798760 وholdها$0.0301376اند؛ مدرک provider/account-wide هنوز کم است و هیچsettle/release/unhalt اجرا نشد.

برای C2/U3 از سرویس C2a استفاده شود؛ coordinator core دیگر فقط helper تستی نیست. factory HTTP/auth و outcome پایدار C2d روی main است؛ binding frontend آفلاین U3a و index محدود P4a آماده‌اند؛ محمدحسن/بهنام تنظیم محصول و smoke مرورگر را نهایی کنند. readهای سرویس به‌تنهایی CAS lifecycle نیستند؛ C2d اکنون در transaction اولین root proposal هر revision و outcome را کنترل می‌کند و مسیر ABA قبلی را می‌بندد. resume خودکار وجود ندارد. [packet تازهٔ C5](../docs/live-reconciliation-2026-10-11.fa.md) با خواندن read-only و hash ثابت ledger ثبت شد؛ مدرک provider همچنان کم است.

وابستگی: سهم مستقل ورودی P2 و خروجی C3 با fixture انجام شده و U2 به API وصل است؛ port آفلاین R3 نیز روی main پذیرفته شد. قدم بعد retrieval از index ثابت (P4/R1/R2/R4)، وصل کردن UI به state/approval پایدار C2d و split/rubric/runner محمدحسن (E1–E3) است. تک agent مبناست؛ اضافه کردن agent/framework نیاز به شکست واقعی و مقایسهٔ مستند دارد.

[بازبینی آمادگی core](../docs/core-readiness-audit.fa.md) دو regression تازه را
روی `254e6542` با دو fail و بعد از `68dec4f` با دو pass ثبت می‌کند. مسیر gateway
موجود تا review نیز با MockTransport و ledger موقت بررسی شده؛ این شاهد اتصال
آفلاین است و C4/C5 یا کیفیت مدل را نمی‌بندد. تحویل کوچک بالا ورودی ادامهٔ
pilot مشترک است، نه درخواست بازسازی بخش‌های دیگر توسط core.

بازبینی ۱۱ اکتبر C2/C3/E3: نه regression روی `6131091` fail و پس از اصلاح
pass شدند؛ شناسه و پروندهٔ درست، accounting درخواست، حفظ review، جداسازی فرم
و نمایش همهٔ claimهای یک chunk. [شواهد و محدودیت‌ها](../docs/team-integration-review-2026-10-11.fa.md).
این baseline منطق اتصال است؛ C4 برای تصمیم مدل همچنان باز می‌ماند.
سهم تازهٔ C2 در [۱۱ تست خطای core/SQLite](../tests/test_core_tracker_failure_boundaries.py)
ثبت شد: ورودی superseded پیش از read، correction حین reasoning/قبل stage،
قطع اجرا قبل مدل و بعد مدل/قبل stage، بازیابی دقیق ACK، rollback پس از INSERT
و event/review همزمان. همراه ۱۶ تست tracker، ۲۷ تست هدفمند پاس‌اند؛ full suite
انتشار #21 روی `94b60e1` نیز ۱۷۲۱ تست و Ruff پاس داشت. helperهای recovery در این
فایل تاریخی فقط harness تست‌اند؛ نسخهٔ قابل استفادهٔ core اکنون C2a است و
مسیر opt-in coordinator/outcome واقعی API اکنون در C2d آمده؛ UI و تنظیم index/model با U3/T4 بازند.
receipt تازهٔ [runner v3](../data/evaluation/receipts/offline/core-boundary-review-2026-10-11-v3.json)
روی `37ab853`: ۱۳۶ check در ۱۱ turn، یک dev و دو scenario، صفر fail؛ همهٔ
handoffها و متن released محفوظ‌اند. ترکیب اصلاحات با SQLite در checkout
آزمایشی ۱۷۱۰ تست پاس کرد؛ API هنوز memory است و E2/C4/C5 باز می‌مانند.

### محمد بهنام — tracker و ابزارها

- [x] **T1 — ماژول مستقل SQLite: state پایدار.** CaseState، revision، history، pending proposal و نتیجهٔ اقدام‌ها ذخیره و بازیابی می‌شوند؛ دو پرونده مستقل و ادامه پس از restart تست شده‌اند. read_case در #20، state/pending/history را از یک snapshot می‌خواند. regression همزمانی و fixture موجود P1 با SQLite همراه ۱۴ تست قبلی، ۱۶ pass دارند. این تیک ماژول مستقل را می‌بندد؛ HTTP/P3 در C2d نیز پذیرفته شد، binding UI آفلاین در U3a پاس شده؛ تنظیم محصول و evaluation هنوز بازند.
- [x] **T2 — ماژول مستقل SQLite: رخداد و revision.** event ID و hash ورودی پیش از stale/reply check بررسی می‌شوند؛ replay receipt قبلی را می‌دهد و محتوای متفاوت با همان ID رد می‌شود. commit state/event و invalidation approval اتمیک‌اند و read سازگار موجود است. خواندن state پس از commit در coordinator واقعی HTTP با C2d پیاده و restart/retry آن پذیرفته شد؛ binding UI آفلاین در U3a پاس شده.
- [x] **T3 — ماژول مستقل SQLite: approval و اجرای اقدام محلی.** reviewer معتبر و همان case/revision/proposal/hash کنترل می‌شوند؛ reject اقدامی ندارد، edit پیشنهاد و approval تازه می‌خواهد، correction مجوز قبلی را باطل می‌کند. retry/restart همان review نتیجهٔ قبلی و یک action محلی می‌دهند؛ rollback و concurrent review تست شده‌اند. authentication مرز HTTP در C2d پیاده است؛ credential و envelope client/UI در U3a وصل و تست شدند؛ review معنایی مجوز اجرا نیست.
- [ ] **T4 — شواهد عملیاتی pilot و evaluation.** برای retry/restart/stale/reject/edit/خرابی ابزار receipt بدهد، نتیجهٔ ابزار در وضعیت و تصمیم بعدی مصرف شود و دستور reset واقعی tracker را مستند کند. تست pytest این بخش و log امن با خودش؛ محمدحسن این شواهد را در گزارش evaluation استفاده کند.
  - شواهد محلی Windows در ۲۰۲۶-۱۰-۱۲: ۲۷ تست tracker/failure، ۷۷ تست SQLite/API/crash، ۳۳ تست HTTP runtime و پذیرش HTTP/SQLite با ۴۵۷/۴۵۷ check (restart=true) پاس شدند. [گزارش و دستور reset توسعه](../docs/tracker-t4-operational-evidence.md)، [اصلاح harness ویندوز در PR #31](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/31). binding آفلاین UI/auth/retry در [PR #32](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/32) پیاده و تست شده؛ وضعیت انتشار همان PR مرجع است. تنظیم credential محصول، smoke مرورگر و مصرف outcome در evaluation بازند؛ T4 تیک نمی‌خورد.
  - گزارش دستی تازه روی branch`test/mohammadbehnam-latest-two-case-smoke`، commit`8420a3b`، در وضعیت فعلی بالای این فایل ثبت شد: اجرای تاریخی روی`f8b3106` با API retry؛ انتشار receipt، browser/session recovery، lost-ACK از UI و باقی شواهد T4 هنوز بازند. از این گزارش تکرار تمام smokeها لازم فرض نمی‌شود؛ ابتدا receipt همان اجرای ثبت‌شده منتشر و فقط شکاف‌های باقی‌مانده تکمیل شوند.

شاهد T1–T3: [source ماژول](../src/agent_app/tracker/sqlite_tracker.py)، [۱۶ تست tracker](../tests/test_sqlite_tracker.py)، [pilot آفلاین](../scripts/tracker_pilot.py) و [قرارداد و دستور اجرا](../docs/sqlite-tracker.md). [PR #20](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/20) با `6628758` به branch بهنام و سپس [PR #19](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/19) با `464e55e` به main merge شدند؛ suite branch tracker با ۱۶۹۰ تست و CI انتشار main پاس‌اند. پذیرش مستقل اولیه U3/T4 را نمی‌بست؛ اکنون HTTP/P3 با C2d پذیرفته شد و binding UI/evaluation باقی است. [گزارش بازبینی](../docs/team-integration-review-2026-10-11.fa.md).

وابستگی: ماژول T1–T3 با قراردادهای فعلی موجود است؛ برای T4/UI، ورودی UserTurn، proposal دقیق، review envelope و outcome از مسیر C2d موجود است؛ binding frontend و شواهد evaluation تکمیل شوند. اقدامات فقط روی tracker محلی‌اند.

### محمدحسن — UI، caseها و evaluation

- [x] **U1 — prototype آفلاین.** Streamlit و FastAPI روی main، انتخاب scenario ساختگی و review پیشنهاد موجودند. این checkbox فقط همین prototype را پوشش می‌دهد؛ storage حافظه‌ای و فیک بودن retriever/reasoner همچنان صریح نمایش داده شوند.
- [x] **U2 — ورودی و نمایش کامل.** پیام، اطلاعات صریح/اصلاح‌شده و نتیجهٔ check به قرارداد C2 وصل شوند؛ facts فعال و superseded، unknownها و کل پیشنهاد، summary، منابع و scope نسخه به reviewer نمایش داده شوند. تغییر پرونده pending قبلی را stale کند؛ edit دوباره review/approval بخواهد. انجام‌شده در [PR #13](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/13): هر پیام event با `turn_id` پایدار و `expected_revision` می‌فرستد و retry همان payload را دوباره می‌فرستد؛ فرم fact/correction/withdraw، check، unknown و تغییر محیط؛ پاسخ کوتاه نسخه فقط به سؤال canonical تأییدشده (`awaiting_reply`) با سناریوی آفلاین `ask_version`؛ جدول facts فعال/superseded، receipt آخرین ورودی، و برای reviewer همهٔ سطوح analysis، همهٔ منابع (cited و uncited) با version scope، gapها و conflict groupها وقتی موجودند. شاهد: `tests/test_ui.py` و `tests/test_ui_client.py`. محدودیت: storage حافظه‌ای و adapterهای ساختگی؛ اتصال واقعی U3 است.
- [ ] **U3 — اتصال واقعی UI/API.** انتخاب mock از تنظیم retriever/model/tracker واقعی جدا باشد؛ error و توقف قابل فهم نمایش داده شوند. تست API و smoke test UI، case switching و approval/reject/edit با خودش؛ persistence و مجوز اجرا به tracker سپرده شود. وضعیت: انتخاب‌گر پرونده در نوار کناری اضافه شد (فهرست پرونده‌های همین session با وضعیت هر کدام، تعداد پرونده‌های منتظر review، پیام ارسال‌نشده متصل به پرونده خودش)؛ تست در `tests/test_ui.py`. ماژول T1–T3 و port آفلاین R3 روی main موجودند؛ factory پایدار HTTP/core و outcome C2d با #30 روی main است. U3a credential maintainer، review_id/hash اصلی و retry per-case را وصل کرده؛ P4a index کوچک واقعی با embedding محلی دارد. تنظیم نهایی index/model، smoke مرورگر واقعی و evaluation همچنان باقی است.
- [ ] **E1 — انتخاب و freeze caseها.** حداقل ۱۵ dev و ۱۵ test در سطح خانوادهٔ Issue؛ حداقل ۱۰ سناریوی چندنوبتی که حداقل ۵ تای آن‌ها در test باشند. manifest خانواده‌ها و شناسهٔ نسخهٔ split به حسن داده شود. کیس‌های توسعهٔ قبلاً دیده‌شده مثل 12782 و duplicate آن 12629، test مستقل نیستند؛ فهرست exposure بسته هم بازبینی شود. وضعیت جاری: [packet سه dev](../data/evaluation/dev-three-v1/split-manifest.json)، سه خانوادهٔ exposed و صفر test، هنوز draft و بدون freeze نهایی؛ [راهنمای review و chronology](../docs/dev-three-baseline.fa.md). [manifest تاریخی pilot](../data/evaluation/split-manifest.json) با یک dev و صفر test برای حفظ receiptهای قدیمی تغییر نکرده؛ پروندهٔ #12782 در این دو packet یک case است و دوبار شمرده نمی‌شود. seed اولیه در `streamlit-data-for-dev-test/` با #23 روی main موجود است؛ باقی خانواده‌ها از همان داده‌ها انتخاب شوند. انتخاب اولیه منتظر R1 یا index نمی‌ماند؛ provenance و linkage با حسن پیش از freeze بررسی می‌شوند. انتخاب خانواده‌ها (۱۵ اکتبر، تأیید محمدحسن): [manifest `split-e1-v1`](../data/evaluation/split-e1-v1/split-manifest.json) با ۱۶ خانوادهٔ dev و ۱۵ خانوادهٔ test؛ از ۲۴۰ Issue موجود در seed با `scripts/screen_evaluation_candidates.py` غربال شد و ۱۳ کاندید ضعیف رزرو قبلی (feature request بدون جواب مستند، Issueهای قبل از 1.22 یا API منسوخ) جایگزین شدند. خانواده‌ها با cross-reference و رویدادهای duplicate در GitHub بررسی و محافظه‌کارانه گسترش یافتند؛ هیچ خانواده‌ای بین dev و test مشترک نیست و هیچ Issue دیده‌شده در توسعه در test نیست. #12165 به dev منتقل شد چون با خانوادهٔ exposed #12629 به umbrella #11277 ارجاع دارد. فهرست `index_exclusion` برای حسن آماده است. هفت fixture چندنوبتی test با rubric v1 ثبت شد (`data/evaluation/split-e1-v1/test/`، شواهد ثابت `evidence-test-v1.json`): همراه سه dev-three، ۱۰ سناریوی چندنوبتی که ۷ تای آن در test است؛ runner آفلاین scripted ۷/۷ case، ۱۴ نوبت و ۱۷۲/۱۷۲ check (کیفیت مدل نیست). هشت fixture باقی‌ماندهٔ test (تک‌نوبتی، شواهد `evidence-test-b-v1.json`) هم ثبت شد؛ هر ۱۵ case test اکنون fixture و gold دارند و runner آفلاین ۱۵/۱۵ case، ۲۲ نوبت و ۲۶۰/۲۶۰ check را پاس می‌کند (scripted، کیفیت مدل نیست). #17011 به خانوادهٔ #17112 اضافه شد. سیزده fixture dev باقی‌مانده هم ثبت شد (`data/evaluation/split-e1-v1/dev/`، شواهد `evidence-dev-v1.json`)؛ همهٔ ۳۱ case (۱۶ dev، ۱۵ test) fixture و gold دارند و runner آفلاین روی کل split ‏۳۱/۳۱ case، ۴۵ نوبت، ۱۴ مسیر چندنوبتی (۷ در test) و ۵۳۳/۵۳۳ check پاس است (scripted، کیفیت مدل نیست). #9171 به خانوادهٔ #9180 اضافه شد. gold هر ۱۵ case test را محمدحسن در ۱۶ اکتبر روی کارت‌های خلاصه review و تأیید کرد ([نتیجه](../data/evaluation/split-e1-v1/test-card-review-v1.json)؛ ۱۵/۱۵ درست، case 02 پس از توضیح). مبنای این review خلاصهٔ رفتار مورد انتظار است، نه thread کامل GitHub یا تک‌تک فیلدهای gold. review نمونه‌ای ۵ case dev (یکی از هر نوع رفتار) هم انجام شد ([نتیجه](../data/evaluation/split-e1-v1/dev-spot-check-v1.json)؛ ۵/۵ درست). یکی از case‌ها (dev-case-n، #12740) با تذکر داور اصلاح شد: پیام v1 به‌غلط می‌گفت screenshotها کد ندارند؛ v2 آن را درست می‌کند و تصمیم «پرسیدن کد به‌صورت متن» می‌ماند چون agent فقط متن می‌خواند. تأیید vocabulary سؤال‌های جدید و freeze هنوز باز است.
- [ ] **E2 — fixture و rubric پیش از اجرا.** case_id، منبع/زمان، ورودی قابل مشاهده در شروع، پاسخ‌های بعدی به‌ترتیب، factهای معلوم، gap کاربر/منبع، منابع مجاز، تصمیم‌های قابل قبول و انتظار عملیاتی ثبت شوند. جواب/label/gold برای runner/reviewer است و وارد پیام مدل یا index نمی‌شود. schema با ساسان هماهنگ شود؛ مسیر موجود `data/evaluation/` مبنا باشد. placeholder قبلی `dev_cases.json` حذف شد؛ پیش‌نویس schema در [`data/evaluation/README.md`](../data/evaluation/README.md) و نخستین fixture آن (P1) ثبت شده‌اند. هماهنگی schema با ساسان هنوز باز است. [rubric v1](../docs/evaluation-rubric-v1.md) (`e2-rubric-v1`، ۱۵ اکتبر) پیش‌نویس ساسان را مبنا می‌گیرد و خواسته‌های او را اضافه می‌کند: بررسی همهٔ ادعاهای مهم با متن و نسخهٔ منبع حتی بیرون citation، نمرهٔ جدای پیشنهاد مدل و متن edited/released، gap کاربر/منبع با ادامهٔ مورد انتظار برای هر نوع سؤال، و gold جدا برای شواهد ثابت و index واقعی. هنوز freeze نشده؛ پشتیبانی runner از gold چندشرطی پیاده نشده است.
  یادداشت تاریخی پوشش سؤال (۱۶ اکتبر، head اولیهٔ PR78، پیش از E2aa): [`question-coverage-v1.json`](../data/evaluation/split-e1-v1/question-coverage-v1.json) شاخه‌های ask هر ۳۱ fixture را با vocabulary ثابت dev و همان قاعدهٔ core (سؤال نسخهٔ داخلی تا fact نسخهٔ USER نیامده؛ سؤال vocabulary فقط با نام در unknowns فعلی case) تطبیق می‌دهد. dev: هر ۱۱ شاخه در دسترس‌اند (۵ نسخه، ۶ vocabulary). test: ۲ از ۷ شاخه سؤالی می‌خواهند که در vocabulary نیست؛ این محدودیت سیستم گزارش می‌شود و سؤالی از روی test اضافه نشده. سؤال نسخه در ۴ turn dev و ۲ turn test که ask در gold پذیرفته نیست هم در دسترس است (ریسک سؤال غیرلازم). بخش test فقط شمارش است؛ در دسترس بودن سؤال اثبات انتخاب درست مدل نیست.
  **اصلاح E2aa:** v1 بالا برای حفظ تاریخچه است؛ projection عمومی آن سه counterexample داشت. [v2 فقطdev](../data/evaluation/split-e1-v1/question-coverage-dev-v2.json) با transition/catalog واقعی، همان۱۱ask و۴extraoffer را بازتولید کرد. summary تاریخی test در این اصلاح دوباره اجرا یا تأیید نشده است؛ گزارش نهایی آن با مالک evaluation و بدون تنظیم vocabulary از روی test است.
  یادداشت v2 سه dev (۱۶ اکتبر): [`dev-three-v2`](../data/evaluation/dev-three-v2/README.md) سه case قبلی را برای `e2-rubric-v1` و شواهد ثابت دوباره ثبت می‌کند (fixture_id تازه، خانوادهٔ کامل، `required_sources`، و در case-b یک ادعای غیرقابل قبول و قاعدهٔ «پیشنهاد بی‌منبع فقط با برچسب صریح»). تصمیم‌ها، gapها، routeها و evidence همان v1؛ v1 و receiptهایش دست‌نخورده‌اند. [review انسانی](../data/evaluation/dev-three-v2/gold-review-v1.json): ۸ از ۸ پس از توضیح ساده‌تر سه کارت «مطمئن نیستم» درست؛ محدودیت ثبت‌شده: سؤال callback در case-a نوبت پاسخ ندارد. manifest split-e1-v1 حالا v2 را pin می‌کند و blocker rubric حذف شد؛ [گزارش پوشش dev v3](../data/evaluation/split-e1-v1/question-coverage-dev-v3.json) با v2 فقط در hash manifest فرق دارد. آفلاین ۷۹/۷۹، هزینه صفر.
  یادداشت native gold dev (۱۶ اکتبر): [ثبت فعال v2](../data/evaluation/split-e1-v1/native/native-registration-dev-v2.json) در E2ac،۱۴fixtureقبلی و۲اصلاح نسخه‌دار escalation را انتخاب می‌کند. [review انسانی v1](../data/evaluation/split-e1-v1/native/native-dev-gold-review-v1.json) و تمام byteهای قدیمی محفوظ‌اند؛ تأیید انسانی دو بند جدید (۱۷ اکتبر، mhg، هر دو درست؛ assistant-informed) در [sidecar جدا](../data/evaluation/split-e1-v1/native/native-dev-e2ac-human-confirmation-v1.json) ثبت شد و byteهای اصلاح/registration دست نخوردند. [شرح و رسید](../docs/native-dev-gold-amendment.fa.md): آفلاین scripted تازه۱۶case/۲۳turn/۲۷۳check پاس، نه کیفیت مدل. passage/نسخه/support جدا review می‌شوند؛ نبود match خودکار ارجاع درست نیست. pinبیلد همچنان pending؛ native gold مربوط بهtest جدا و فقط با صاحبeval است.
  یادداشت native gold test (۱۶ اکتبر): مالک evaluation ثبت ۱۵ fixture بومی و review انسانی و اجرای scripted آفلاین ۲۶۰/۲۶۰ را گزارش کرده است؛ این‌ها ارزیابی کیفیت مدل یا تأیید مستقل core نیستند. این داده‌ها held-out هستند و فقط custody/metadata آن‌ها در review توسعه بررسی می‌شود؛ هیچ pytest تازه‌ای آن‌ها را نمی‌خواند. pinها pending_final_build هستند. جزئیات case و اصلاح gold باید فقط در artifact خصوصیِ صاحب evaluation بماند. تصمیم eligibility پس از exposure محدود PR83 (۱۷ اکتبر، mhg) در فایل held-out ثبت شد؛ ترکیب ۱۵ test تغییر نکرد و گزارش نهایی یک تحلیل حساسیت دارد. توضیح PR83 هم به جمع‌بندی کلی تغییر کرد.
  یادداشت freeze (۱۷ اکتبر): [freeze split-e1-v1](../data/evaluation/split-e1-v1/freeze/README.md) با review انسانی mhg (assistant-informed) ثبت شد: rubric `e2-rubric-v1`، ۳۱ خانواده (۱۶ dev/۱۵ test)، ۱۹ Issue exposed بدون هیچ‌کدام در test، exclusion از ۹۰ به ۹۵ (پنج گزارش C4i)، اعلامیهٔ corpus با ۱۲۲۸ منبع و vocabulary فقط-dev. draft manifest دست نخورد. باقی: rebuild حسن با `build-receipt-v3`، native gold v3 با pinها، packet `frozen_final_v1` و preflight.
- [ ] **E3 — runner قابل تکرار.** caseها از fixture اجرا شوند؛ turn بعدی در زمان درست آشکار شود و case/revision/proposal و config/snapshot، latency و هزینه ثبت شوند. replay منطقی بدون API و اجرای کیفیت با مدل واقعی خروجی جدا داشته باشند. schema/runner و API/UI pytest با خودش؛ برای قراردادها از ساسان کمک بگیرد. وضعیت: runner آفلاین `agent_app.evaluation.runner` آماده است: caseهای یک split را turn به turn اجرا می‌کند، case/revision/proposal، git commit، hash fixture، config/snapshot، latency، تلاش مدل، دور retrieval، step، هزینه و token را ثبت می‌کند و receipt حالت offline و live را در مسیرهای جدا نگه می‌دارد. [receipt آفلاین dev](../data/evaluation/receipts/offline/dev-2026-10-10.json). ([PR #15](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/15)) مسیر live با HTTP intercepted و BudgetLedger موقت آفلاین تست شده؛ provider و ledger اصلی استفاده نشده‌اند. #21 receipt کامل، accounting درخواست و محافظ branch نامتناسب را اضافه می‌کند؛ تکمیل E3 هنوز به adapter U3، branchهای گفتگو و validation ثبت‌شده نیاز دارد. سناریوهای عملیاتی ساختگی برای خرابی ابزار (retrieval، یک خطای مدل با retry در سقف دو تلاش، دو خطا و توقف) و جابه‌جایی میان دو پرونده در `data/evaluation/scenarios/` پیش از اجرا ثبت شدند؛ اجرای اول ۸۱ از ۸۲ پاس شد چون انتظار ثبت‌شده کد توقف را اشتباه پیش‌بینی کرده بود (engine آخرین خطای adapter یعنی `ReasoningUnavailable` را گزارش می‌کند)؛ receipt آن حفظ و نسخهٔ v2 با همان یک تغییر ثبت شد. این سناریوها جزو ۳۰ case ارزیابی نیستند.
- [ ] **E4 — baseline و تنظیم فقط روی dev.** کیفیت تصمیم/پشتیبانی ادعاها/ضرورت و پاسخ‌پذیری سؤال، retrieval، صحت عملیات و هزینه/latency جدا سنجیده شوند. تغییرات روی ورودی یکسان مقایسه و نسخهٔ code/prompt/corpus/model freeze شود. نمونهٔ قضاوت انسانی ثبت شود؛ JSON معتبر یا نظر همان مدل تنها شاهد کیفیت نیست.
  یادداشت E4 (۱۶ اکتبر): نخستین داوری انسانی خروجی واقعی مدل ثبت شد: [`human-output-card-review-v1.json`](../experiments/dev_rag_coverage_v1/human-output-card-review-v1.json). ۱۷ پیشنهاد تازهٔ C4g در۷گروه case/turn/decision/draft بررسی شدند؛ متن سؤال دو گروه یکسان است و۶متن یکتا داریم. تصمیم۶گروه قابل قبول ویک گروه نامطمئن؛ usefulness دو گروه۲وپنج گروه۱ است:۱٫۲۹به‌ازای گروه و۱٫۴۷باوزن۱۷پیشنهاد. [پذیرش و توضیح واحد شمارش](../docs/pr77-review.fa.md) نمره‌های اصلی را تغییر نمی‌دهد. هر۱۷binding/handoff وhashreceipt تطبیق داده شد؛ export خصوصی وpacket وابسته‌به‌مسیر کاملاً بازتولید نشده‌اند. support بررسی نشده وE4باز است؛ اینdevexposed است، نهtestنهایی. نشانگر `\u000d` درcase-c ازCRLFوescape renderer است، نه خطای مدل.
  یادداشت C4j (۱۶ اکتبر): [`assistant-informed-output-review-v1.json`](../experiments/core_claim_boundary_v1/assistant-informed-output-review-v1.json) ۲۲ پیش‌نویس موجود C4j را با تصمیم و usefulness محمدحسن ثبت می‌کند. داور پس از خواندن ترجمه و رفتار مورد انتظار، ارزیابی دستیار را باز کرد؛ ۱۹ دلیل متن دستیار است و همهٔ نمره‌ها در بازهٔ پیشنهادی دستیارند، پس این **نمرهٔ مستقل انسانی نیست** و worksheet اصلی دست نخورده (فیلدهای انسانی null). نتیجهٔ توصیفی: سؤال‌ها ۷/۷ قابل قبول (میانگین ۱٫۸۶)، answerها ۱/۱۴ قابل قبول (میانگین ۰٫۵)؛ روش A میانگین ۱٫۲ و روش B ۰٫۴۳. ۴۲ ردیف بدون پیش‌نویس نمره ندارند.
- [ ] **E5 — test و گزارش نهایی.** بعد از E1–E4 و اتصال واقعی، test بدون tuning اجرا شود؛ شکست‌ها، موارد حل‌نشده و اطلاعات ناقص همراه trace گزارش شوند. شواهد RAG از حسن، tracker از بهنام و core از ساسان جمع شود؛ مالک اجرای evaluation و گزارش محمدحسن است.
- [ ] **E6 — bonus و ارائه.** فقط پس از مسیر اصلی، Adversarial Testing با دامنهٔ توافق‌شدهٔ منتور و مقایسهٔ منصفانه اجرا شود؛ اسلاید و README با رفتار و هزینهٔ واقعی هماهنگ شوند.

وابستگی: E1/E2 با fixture اکنون قابل انجام‌اند؛ U2 انجام شده و port آفلاین R3 موجود است. E1 قبل از R2، E4 قبل از E5، و ادامهٔ U3 به P4، اتصال P3/T4 و C2 وابسته است. test برای انتخاب مدل، prompt، retrieval یا architecture استفاده نشود.

یادداشت بازبینی E2/E3: [rubric پیشنهادی](../docs/evaluation-rubric.md) با `AnalysisResult` و `ProposalHandoff` سازگار است؛ evidence_links به‌تنهایی اثبات پشتیبانی تمام ادعاها نیست. تا داوری مستقل، `live` فقط نوع اجراست و quality_claim باید false بماند. gold/expected مسیر offline را با مسیرهای معتبر live یکی نکنیم؛ manifest/corpus frozen و پاسخ‌های شرطی چندنوبتی هنوز کار E1–E3 هستند. receiptهای قبلی حفظ شوند.


### برش مستقل تازه — U3a / P4a، ساسان با ماژول‌های موجود تیم

- [x] **R1a — profile قابل بازتولید seed.** [script و receipt](../experiments/corpus/seed-profile.json)، ۲۸ تست: ۱۴ فایل package، schema/grain/hash/joins؛ نسخه‌های هم‌متن مستقل، split draft و candidateهای خانواده صریح. این تیک تأیید corpus نهایی نیست.
- [x] **P4a — index کوچک docs-only و اتصال واقعی.** [allowlist ثبت‌شده](../experiments/corpus/pilot-allowlist.json)، ۱۴ source و ۳۰ chunk؛ hash/span/commit و نسخه حفظ؛ همهٔ Issue/comment/release notes/evaluation خارج. Chroma واقعی با vector lexical محلی، pin مستقل snapshot و guard محتوا/نتیجه؛ ۶۰ تست شامل mutation موقت حین query. builder قدیمی نهایی همچنان بسته است؛ R2/R4 بازند.
- [x] **U3a — UI به backend پایدار و retry review.** [راهنمای اجرا](../docs/offline-ui-index-pilot.fa.md)، ۱۰۰ تست UI/client شامل ۲۴ regression قبلی؛ operation ثابت قبل POST، همان hash و متن نمایشی معتبر، credential خصوصی session، correction/case switching و ACK نامعلوم. baseline کنترل‌شده client/API قبلی ۲/۶، نسخهٔ جدید ۶/۶؛ نمرهٔ کیفیت نیست.
- [x] **C2e — اتصال U3a/P4a به core/SQLite.** client واقعی از TCP و دو interpreter تازه، index واقعی و همان DB؛ retry فقط receipt/action اصلی. AppTest واقعی صفحه نیز سرچ docs، question/approval، reply و correction را اجرا کرده. این scope مرورگر واقعی یا recovery بعد پایان session UI نیست.
- [x] **C2f — GroundedPlan در HTTP پایدار، پذیرش محدود.** کد و شواهد در [PR #34](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/34)؛ وضعیت انتشار و CI همان PR مرجع است. [protocol ثبت‌شده پیش از اجرا](../experiments/grounded_http_acceptance/protocol-v1.json) و [دستور اتصال/حدود](../docs/grounded-persistent-pilot.fa.md): همان fixture exposed چهارمرحله‌ای، gateway جعلی و ledger موقت؛ baseline `3c92b12` ده کنترل از دوازده و نسخهٔ جدید دوازده از دوازده. بهبودها label درست و cleanup هر run هستند؛ baseline از قبل injection را اجرا می‌کرد. اصلاح نسخه، شاهد آخرین round، approval قدیمی، restart/retry و edit/reject پاس‌اند؛ AppTest و TCP با index واقعی نیز پاس شدند. [probe واقعی ثبت‌شده](../experiments/grounded_http_acceptance/live-result-0b962de.json) فقط یک درخواست توسعه و سؤال نسخه بود، هزینهٔ تخمینی $0.000650430؛ [review جدا](../experiments/grounded_http_acceptance/live-review-0b962de.json). این کیفیت مدل/RAG یا test نهایی نیست؛ ID دقیق serving model در receipt اول نامشخص است و C5 halt/hold قبلی حفظ شده است.
- [x] **C2g — context فعلی retrieval و binding کنترل نسخه.** [protocol، receipt و حدود](../experiments/retrieval_context/README.md): تاریخچهٔ reasoning خام حفظ، query اولیه از facts فعال/پیام اخیر/topic جدا؛ ده variation تألیفی با همان baseline، همهٔ کنترل‌های query ۲/۱۰ به ۱۰/۱۰. دو send آنلاین همان سؤال callback را انتخاب کردند و منبع نامرتبط نسخهٔ 1.64 برای کاربر1.49 را آشکار کردند؛ افزایش کیفیت تصمیم/RAG ادعا نمی‌شود. forwarding سیاست موجود `exact_user_version` به HTTP و انتخاب آن در backend توصیهٔ نسخهٔ فعلی، پس از probe با ۲۱ تست آفلاین پذیرفته شد؛ default `all` برای comparison باقی است. فیلتر ranking/backfill نیست و corpus/داوری/test نهایی را نمی‌بندد.

مسیر تک agent است؛ پیش‌فرض pilot هنوز scripted است و `grounded_fake_gateway` اتصال gateway جعلی را فعال می‌کند. policy آفلاین محافظه‌کار است: نسخهٔ نامعلوم سؤال، نسخهٔ معلوم ارجاع؛ هزینهٔ API این launcher صفر است. probe واقعی جداگانهٔ C2f یک درخواست با هزینهٔ تخمینی $0.000650430 داشت؛ C5 halt حفظ شده. [بررسی نهایی](../experiments/grounded_http_acceptance/verification-89a0aec.json) و [smoke مرورگر](../experiments/grounded_http_acceptance/browser-receipt-89a0aec.json): ۲۲۸۳ تست پاس، correction در همان case و یک action. defect label متغیر case اصلاح شد؛ auth محصول و recovery کامل session هنوز بازند. معیار claim/source و کیفیت retrieval با داوری مستقل روی dev و سپس test سنجیده می‌شوند. [حدود دقیق و دستورها](../docs/grounded-persistent-pilot.fa.md).

## نسبت case، corpus، UI و pytest

- **case ارزیابی:** یک مسئلهٔ انتخابی با ورودی اولیه و ادامهٔ گفتگوست. متن شروع به agent داده می‌شود، حتی وقتی آن Issue داخل corpus نیست. نگه‌داشتن جواب یا duplicate همان مسئله در index، توان بررسی مسئلهٔ تازه را اندازه نمی‌گیرد.
- **corpus RAG:** docs و Issueهای مجاز دیگر برای استدلال و شواهد مشترک‌اند؛ همهٔ Issueها حذف نمی‌شوند. اگر پس از کنارگذاری شاهد کافی نبود، پاسخ مستند محدود، سؤال ضروری، retrieval بیشتر یا ارجاع طبق rubric می‌تواند قابل قبول باشد؛ پاسخ قطعی تحمیل نمی‌کنیم.
- **UI:** ورودی آزاد مسئله دارد و به ۳۰ case محدود نمی‌شود. این ۳۰ case مجموعهٔ ارزیابی‌اند. prototype فعلی خروجی scripted scenario می‌دهد؛ رفتار مدل دربارهٔ متن جدید فقط پس از اتصال واقعی سنجیده می‌شود. انتخاب case آماده برای demo می‌تواند گزینهٔ جدا باشد.
- **fixture/runner:** caseها و gold بیرون UI نگهداری می‌شوند؛ runner همان API/adapter قراردادشده را خودکار صدا می‌زند. نمایش دستی چند case در UI جای evaluation قابل تکرار را نمی‌گیرد.
- **pytest:** تست core با ساسان، retrieval با حسن، tracker/tools با بهنام، UI/API و schema/runner evaluation با محمدحسن. تست مشترک pilot با مشارکت صاحبان اتصال و هماهنگی محمدحسن است؛ fixture/fake برای منطق مناسب است، ولی پاس شدن آن معیار کیفیت مدل/RAG نیست.

## ترتیب و شرط پایان پروژه

1. E1/E2 و بازبینی seed انجام شوند؛ adapterها و pilot ثابت می‌توانند هم‌زمان جلو بروند.
2. R2 انجام و corpus نهایی freeze شود؛ نسخهٔ split و exclusion کنار index ثبت شود.
3. pilot آفلاین و سپس اتصال واقعی با شواهد persistence/approval/retry/restart تأیید شوند.
4. baseline و بهبود روی dev مقایسه شوند؛ code، prompt، model و corpus freeze شوند.
5. test نهایی بدون tuning اجرا و گزارش کیفیت، شکست‌ها و هزینه تهیه شود؛ bonus بعد از اصل کار است.

هر checkbox زمانی بسته می‌شود که لینک commit/PR، تست، trace یا artifact شرط پایانش کنار همان task اضافه شود. تغییر owner یا قرارداد مشترک با review صاحب بخش ثبت شود. برای ساختار عمومی از [معماری](../docs/architecture.md)، [راهنمای اتصال](../docs/integration.md)، [UserTurn](../docs/user-turns.md) و [پیشرفت core](../docs/core-progress.md) استفاده کنیم؛ مستندات V8/V9 اکنون همراه core روی main هستند.

## به‌روزرسانی مشترک plan

- `main` مرجع مشترک تیم است. هرکس پیش از شروع کار، تغییرات محلی‌اش را حفظ کند، `git fetch origin` بزند و branch کاری خودش را از `origin/main` به‌روز کند. فایل plan با Git لحظه‌ای sync نمی‌شود؛ نسخهٔ تازه پس از fetch/merge دیده می‌شود.
- هر نفر taskهای خودش را در همین فایل نگه دارد؛ تغییر وضعیت یا بسته شدن checkbox همراه لینک commit/PR، تست، trace یا artifact باشد. blocker و ورودی لازم از نفر دیگر کنار همان task نوشته شود.
- تغییر کد و plan روی branch صاحب بخش ثبت و با PR به main برسد. شناسهٔ task مثل `R3` یا `U2` در توضیح PR نوشته شود؛ تغییر قرارداد مشترک با review صاحب بخش جمع شود. کار فعلی دیگران بازنویسی یا reset نشود.
- لینک PR و taskهای تغییرکرده در گروه معرفی شوند تا هماهنگ‌کننده و صاحب وابستگی باخبر شوند. برای دنبال کردن خودکار PRها، هر عضو می‌تواند اعلان‌های GitHub همان repository را فعال کند؛ صرف push شدن فایل به معنی دیده شدن آن توسط همه نیست.
- Codex/Claude هر نفر قبل از اجرا، AGENTS.md و همین plan را بخواند و از owner و شرط پایان task پیروی کند. پاس شدن mock یا pytest به‌تنهایی checkbox مربوط به اتصال واقعی یا کیفیت مدل را نمی‌بندد.

## محدودیت‌های اجرا

کل بودجهٔ تیم ۵ دلار است، شامل embedding، توسعه، evaluation و bonus. اجرای عادی live فعلاً به دلیل halt ledger متوقف است؛ ledger جدید یا reset راه ادامه نیست. کلید و raw credentials وارد log/Git/fixture نمی‌شوند. سقف هر invocation همان ۲ تلاش مدل، ۲ دور retrieval، ۲ query در هر دور و ۸ step است؛ پیشنهاد از اجرای اقدام جدا و همهٔ تغییرات عملیاتی روی tracker محلی‌اند.

### وضعیت انتشار C4h3/E2r

[بررسی محلی](../experiments/core_source_capacity_v1/verification-v1.json):۳۸۲۷pytest،
Ruff،سهdemo وHTTP/SQLite۴۵۷/۴۵۷ پاس. تغییرات در [PR #54](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/54)
رویbranch`feat/core-source-capacity` منتشر شدند. شرط انتظار CI با دستور صریح
۱۵ اکتبر ساسان جای خود را به review و verification محلی داد؛ این به معنی CI
موفق یا رفع Billing نیست. درhead`6a4bd26`، هر دوjob قبل از شروع با خطای Billing
متوقف شدند؛ اصل verification و receiptها حفظ می‌شوند.
