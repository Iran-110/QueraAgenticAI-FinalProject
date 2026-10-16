# گزارش توسعه و بستهٔ شواهد تحویل — ۱۶ اکتبر

**وضعیت: پیش‌نویس تحویل؛ ارزیابی نهایی کامل نشده است.** این فایل کار انجام‌شده
و شواهدش را جمع می‌کند تا بعد از دریافت نتایج نهایی تکمیل شود. درصد یا نمرهٔ
پروژه از تعداد تست و commit نتیجه نمی‌گیریم. صورت پروژه، plan تاریخی و
receiptهای قبلی تغییر نکرده‌اند.

## وضعیت امروز

| بخش | شاهد موجود | باقی‌مانده برای اعلام اتمام |
| --- | --- | --- |
| core و اتصال | correction، وضعیت فعلی کاربر، شواهد نسخه‌دار، پیشنهاد جدا از اجرا، API/UI/SQLite | انتخاب تنظیم نهایی و کیفیت پاسخ با داوری مستقل |
| صحت نرم‌افزار | source ثبت‌شدهٔ `5bbb133`: ۵۵۸۹ تست توسعه، با یک deselection صریح؛ HTTP/SQLite برابر۴۵۷/۴۵۷ | این اعداد کیفیت جواب مدل یا اجرای test نهایی نیستند |
| RAG | Chroma واقعی، buildهای pinned، کنترل نسخه و بازپخش dev | بهبود packing/relevance و freeze نهایی corpus/index/config با حسن |
| evaluation | ثبت۱۶dev/۱۵test و۱۴مسیر چندنوبتی شامل۷test در metadata؛ اجرای scripted ثبت‌شده روی۱۶dev،۲۷۳check | native gold/routes،v2 سه dev در صورت انتخاب rubric یکدست v1،vocabulary/rubric/split freeze،usefulness و ارزیابی نهایی با محمدحسن |
| tracker | approval/edit/reject، stale409،restart/retry و شاهد lost-ACK | مرزهای باقی‌ماندهٔ T4 با بهنام/محمدحسن؛ recovery درخواست تأییدنشده پس از نابودی کامل session ثابت نشده |
| هزینه | ledger و رسیدها حفظ‌اند؛ سه درخواست نامعلوم وhalt باقی است | مدرک provider و تطبیق usage/charge برای C5 |

[verification اجرایی](../experiments/evaluation_readiness_v1/verification-v1.json)
به source و artifactهای دقیق bind است. healthcheck تازه، برابری source فعلی
با همان source تست‌شده را بررسی می‌کند؛ اجرای دوبارهٔ suite کامل ادعا نمی‌شود.
test نهایی و evidence/gold آن برای این گزارش باز نشده‌اند. GitHub Billing
مانع hosted CI است؛ انتشار با review و تست محلیِ مجازشده انجام شده است.
[healthcheck تازه](receipts/deadline-healthcheck-2026-10-16.json) شامل۹۷تست
متمرکز، چهار مسیر CLI و [HTTP/SQLite تازه۴۵۷/۴۵۷](receipts/deadline-http-sqlite-2026-10-16.json)
است؛ کنترل read-only هزینه نیز۳۶/۳۶پاس است و C5 همچنان باز می‌ماند.

## سیستم چه می‌کند و چرا این ساختار انتخاب شد؟

یک agent داریم. ورودی صریح کاربر به وضعیت همان پرونده و revision تبدیل می‌شود؛
correction مقدار قبلی را بازنشسته می‌کند. retrieval شواهد می‌دهد؛ core محدودهٔ
نسخه و سقف منابع/تلاش‌ها را اعمال می‌کند. در مسیر GroundedPlan، مدل تصمیم و
منبع یا سؤال ثبت‌شده را انتخاب می‌کند و core متن مستند را می‌سازد. این ساختار
محدود، کنترل اتصال و replay را ساده می‌کند؛ framework یا agent اضافه بدون
شاهد نیاز وارد نشده است.

سؤال برای کمبود اطلاعات قابل‌پاسخ کاربر است؛ کمبود مستندات به retrieval محدود
یا ارجاع نیاز دارد. نسخه از سند به کاربر نسبت داده نمی‌شود. نقل دقیق به‌تنهایی
ارتباط منبع یا پشتیبانی همهٔ ادعاها را ثابت نمی‌کند؛ review انسانی لازم است.

پیشنهاد تا تأیید انسانی منتشر نمی‌شود. tracker همان case، revision، proposal
و متن دقیق را کنترل می‌کند. approval قدیمی رد می‌شود؛ retry باید receipt همان
عملیات را بگیرد و Action تکراری نسازد. state دو پرونده مستقل است. ابزارها فقط
روی tracker محلی اثر دارند؛ متن Issue یا source مجوز اجرا صادر نمی‌کند.

## نصب، بررسی و demo پایدار

دستورها از root مخزن، با Python3.13 و uv اجرا شوند:

```bash
uv sync --locked --group dev
uv run agent-app demo --scenario refine
uv run agent-app gateway-demo --scenario repair
uv run agent-app turn-demo
uv run pytest --deselect=tests/test_prepare_case_review.py::test_split_e1_manifest_covers_every_registered_fixture
uv run ruff check .
uv run ruff format --check .
```

یک تستِ خواندن همهٔ fixtureهای held-out عمداً از فرمان توسعه کنار گذاشته شده؛
validation کامل آن با مالک evaluation است. دموها synthetic/offline هستند.
در سناریوی `error`، exit1 و `RetrievalUnavailable` رفتار مورد انتظار است.

برای نمایش UI پایدار، یک DB تازهٔ مخصوص demo انتخاب کنید؛ اگر مسیر زیر از
قبل وجود دارد، نام تازه بدهید. کلید مدل لازم نیست. در ترمینال backend با zsh:

```bash
read -rs "AGENT_REVIEWER_TOKEN?Private reviewer token: "
export AGENT_REVIEWER_TOKEN
export AGENT_TRACKER_DB="$PWD/runtime/submission-demo-v1.sqlite3"
export AGENT_PILOT_REASONING=scripted
unset AGENT_PILOT_INDEX AGENT_PILOT_SNAPSHOT
uv run uvicorn agent_app.offline_backend:application_factory --factory --host 127.0.0.1 --port 8000
```

در ترمینال UI همان token خصوصی معتبر را وارد کنید؛ طول۳۲تا۵۱۲کاراکتر ASCII
مجاز و بدون فاصله باشد. token را در پیام، log یا گزارش کپی نکنید:

```bash
read -rs "AGENT_REVIEWER_TOKEN?Private reviewer token: "
export AGENT_REVIEWER_TOKEN
export AGENT_API_URL="http://127.0.0.1:8000"
uv run streamlit run app.py --server.address 127.0.0.1
```

مسیر demo: سناریوی **Ask a follow-up question** را انتخاب و مسئله‌ای با نسخهٔ
نامعلوم ثبت کنید؛ سؤال canonical را review/approve کنید. پاسخ `1.50.0` را از
فرم **Streamlit version** بفرستید. برای correction، **Report facts and corrections**
را باز کنید؛ پیام توضیحی، نام `streamlit_version` و مقدار `1.49.0` را وارد و
**Send update** را بزنید؛ fact فعال و revision تازه را بررسی کنید. پیام آزاد
به‌تنهایی fact را اصلاح نمی‌کند. پیشنهاد فعلی را بررسی و تأیید کنید؛ backend
را با همان DB دوباره بالا بیاورید و وضعیت پرونده را بررسی کنید. پس از correction
لزومی ندارد UI دکمهٔ پیشنهاد قدیمی را نگه دارد. stale approval و retry را از
تست پذیرش HTTP نشان دهید، نه با ادعای وجود دکمهٔ مخصوص در UI:

```bash
DELIVERY_CHECK_OUTPUT="$(mktemp -d)"
uv run python scripts/http_pilot_acceptance.py --factory agent_app.testing.sqlite_http_binding:sqlite_factory --protocol experiments/http_pilot_acceptance/protocol-v2.json --output "$DELIVERY_CHECK_OUTPUT/http-sqlite.json"
```

این تست fixture آفلاین و DB موقت خود را دارد. پوشش lost-ACK از مرورگر پیچیده‌تر
از نمایش کوتاه بالاست و رسید مستقل زیر حدود آن را توضیح می‌دهد.

برای بازنشانی demo، هر دو process را متوقف و از مسیر DB تازه استفاده کنید؛
DB قبلی محفوظ می‌ماند. `runtime/budget.sqlite3` ledger هزینه است و هیچ‌وقت
برای بازنشانی tracker حذف، جایگزین یا reset نمی‌شود.

[pilot با index محلی](offline-ui-index-pilot.fa.md) و
[GroundedPlan با gateway جعلی](grounded-persistent-pilot.fa.md) مسیرهای
اختیاریِ موجودند. هیچ‌کدام نتیجهٔ تصمیم مدل واقعی را نمایش نمی‌دهند. ordinary
live با halt فعلی اجرا نمی‌شود؛ demo آفلاین جای رفع C5 یا ارزیابی نهایی نیست.

## داده و مقایسه‌های قابل دفاع

seed ثبت‌شده شامل۲۴۰Issue،۱۱۷۸comment،۵۶سندMarkdown و۱۱۷۲record API نسخه‌دار
است؛ این مجموعه با corpus واقعی RAG یکسان نیست. build dev بررسی‌شده فقط docs
دارد:۱۸source/۳۶chunk، embedding محلی lexical و بدون embedding API. خود caseهای
ارزیابی، جواب‌ها، commentها و duplicateها وارد index نمی‌شوند. exclusion فعلی
۹۰Issue بررسی شده؛ manifest هنوز draft است و build نهایی به freeze آن وابسته است.

| آزمایش | نتیجهٔ مشاهده‌شده | حد ادعا |
| --- | --- | --- |
| C2j، validation ورودی دو helper نسخه |۵۵regression:۲۹fail/۲۶pass به۵۵pass؛۱۶transition معتبر ثابت | صحت نرم‌افزار، نه بهبود جواب مدل |
| R4c/R4b روی index ثابت dev |شاهد لازم۱/۵ به۳/۵؛ off_topic۸به۵ با labelهای تأییدشدهٔ حسن | availability/relevance توسعه، نه حل مسئله یا test نهایی |
| C4i، دو مسیر پاسخ روی dev exposed |هدف کیفیت Enum در هر دو حالت۰/۴ | نتیجهٔ منفی حفظ شده؛ مسیر تازه به default تبدیل نشده |
| C4k/C4l، section/context فعلی |بدنهٔ section و اصلاح موضوع در replayهای تألیفی بهتر کنترل شدند | انتخاب تازهٔ مدل و usefulness اندازه‌گیری نشده |

برای case-a، passage پشتیبان باید در bundle واقعاً مصرف‌شدهٔ همان turn باشد؛
بودن سند در index کافی نیست. gold ثابت و native scope جدا می‌خواهند. راهنمای
answer-linkedِ excluded صرفاً fixture می‌ماند. آرشیوهای exposed و پاسخ‌آگاه،
held-out test نیستند؛ ادامه‌های تألیفی هم گفت‌وگوی واقعی حساب نمی‌شوند.

نمونه‌های قابل بازبینی:

- [اصلاح کاربر، approval و restart/retry در HTTP](../experiments/evaluation_readiness_v1/verification-v1.json).
- [رسیدهای lost-ACK بهنام و محدودیت session تازه](pr66-review.fa.md).
- [شواهد واقعی retrieval و packing](../experiments/evaluation_readiness_v1/native-acceptance-v1.json).
- [آزمایش مدل و شکست Enum](broader-dev-quality.fa.md).
- [مرز ادعا/منبع، خطاها و توقف مطالعه](claim-source-boundary.fa.md).

## هزینه، نقش اعضا و تکمیل گزارش

ledger تعیین‌شده،۷۱۸reservation دارد:۷۱۵settled با تخمین محلی
USD0.599798760 و۳uncertain باhold مجموعUSD0.030137600. این تخمین token/rate
جای invoice حساب نیست؛ هزینهٔ واقعی provider و attribution کل حساب هنوز تطبیق
نشده‌اند. سقف ledger برابرUSD4.50 و سقف کل تیمUSD5 است؛ دادهٔ نامعلوم صفر
فرض نشده و هیچ hold یا halt برای ادامه پاک نشده است. جزئیات در
[C5](../experiments/core_evidence_selection_v1/c5-readonly-report.fa.md) است.

سهم‌ها بر اساس تحویل‌ها توصیف می‌شوند، نه درصد commit: ساسان core، قراردادها
و اتصال؛ حسن داده/RAG؛ بهنام tracker و شواهد عملیاتی؛ محمدحسن UI و evaluation.
کمک‌های متقابل در PR و plan ثبت شده‌اند. درصد تلاش افراد از آمار Git قابل
استنتاج دقیق نیست.

این فایل پیش‌نویس کمکی است؛ مالک گزارش و ارزیابی نهایی E5 محمدحسن می‌ماند.
برای نسخهٔ نهایی هنوز باید artifactهای واقعی زیر اضافه شوند:

1. manifest،rubric/vocabulary،native fixture/gold/routes و corpus/index نهاییِ
   freezeشده با hash و دستور اجرای واقعی؛ مالک‌ها محمدحسن و حسن.
2. baseline و تنظیم منتخب روی dev یکسان با داوری claim/source/question و
   usefulness؛ سپس freeze code/prompt/model/config پیش از test.
3. نتیجهٔ held-out بدون tuning، شمارش شکست/نوبت‌های اجرا‌نشده و چندنوبتی‌های
   واقعاً تکمیل‌شده؛ مالک اجرا و review محمدحسن است.
4. latency،token/request،هزینه/uncertainty و شواهد provider، همراه حدود T4؛
   C5 با ساسان و صاحب حساب، شواهد عملیاتی با بهنام/محمدحسن.

بستهٔ کد و demo قابل آماده‌کردن امروز است. **اعلام پایان تمام الزامات** به
بسته‌شدن این gateها وابسته است؛ تا آن زمان این فایل پیش‌نویس توسعه می‌ماند.
bonus یا framework تازه در مسیر کوتاه تحویل امروز نیست.
