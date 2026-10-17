# کنترل تکمیلی نسخهٔ اجرای ارائه

مسیر `presentation_release_watch_v1` یک لایهٔ اختیاری روی `presentation_scoped_v1` است. پروتکل مالی، ۲۱ فایلِ bound قبلی، مدل، ورودی provider، شناسهٔ درخواست‌ها، slotها و سقف هزینه تغییر نمی‌کنند. این لایه مجوز مالی تازه صادر نمی‌کند و halt یا holdها را حل‌شده اعلام نمی‌کند.

## چه گپی را می‌بندد؟

پروتکل اولیه ۲۱ فایل مشخص را کنترل می‌کند. بعضی dependencyهای واقعی، مانند `retrieval/retriever.py`، `tracker/sqlite_tracker.py` و `contracts.py`، جزو آن فهرست نیستند. کنترل قبلی دربارهٔ همان فهرست درست بود؛ پوشش همهٔ کد را ثابت نمی‌کرد.

در یک کپی موقت از source، تغییر واقعیِ فایل `retriever.py` کنترل قدیمی را متوقف نکرد، اما sidecar جدید آن را رد کرد. source اصلی، پروتکل و ledger جلسه در این کنترل تغییر نکردند.

sidecar جدید این موارد را به‌صورت یک مجموعهٔ بسته hash می‌کند:

- همهٔ فایل‌های Python در `src/agent_app/` و `app_pages/`، همراه با خود لایهٔ جدید؛
- `app.py`، `pyproject.toml` و `uv.lock`؛
- دو تنظیم عمومی انتخاب‌شدهٔ recipe و vocabulary.

اضافه‌شدن یا حذف فایل، تغییر bytes، symlink، hardlink و خطای خواندن یک زیرپوشه باعث رد شدن می‌شود. این کنترل، wheelهای نصب‌شده، کد native یا اصالت محتوای منابع را تأیید نمی‌کند. داده، test، فایل `.env` و کلیدها وارد inventory نمی‌شوند.

## نحوهٔ انتخاب و اجرا

بعد از review نهایی source، برای هر پروتکل یک فایل تازهٔ `release-watch.json` ساخته و hash خام آن جدا ثبت می‌شود. دستور capture فایل قبلی را جایگزین نمی‌کند. launcher فقط hashهای صریحِ فایل محلی `release-watch-config.json` را می‌خواند؛ خودش capture، rebase، funding یا scope جایگزین انجام نمی‌دهد.

ورودی `--expected-sha256` باید همان hash بازبینی‌شده باشد. مسیرهای `check` و `serve` در `agent_app.presentation_release` مقایسهٔ کامل را انجام می‌دهند. مسیر قدیمی و factory عادی همچنان رفتار و guardهای خودشان را دارند؛ استفاده از bootstrap جدید انتخابی و صریح است.

ترتیب کنترل در مسیر تازه:

1. sidecar، پروتکل اصلی و مجموعهٔ کامل source پیش از lookup کلید بررسی می‌شوند.
2. guardهای اصلیِ scope، index، تنظیمات و درخواست اجرا می‌شوند.
3. هنگام ساخت adapter دوباره inventory بررسی می‌شود.
4. پس از reservation و درست پیش از فراخوانی transport زیرین، مقایسهٔ source تکرار می‌شود.

اگر تغییر قبل از startup دیده شود، درخواست مدل و lookup credential انجام نمی‌شود. اگر تغییر بعد از reservation دیده شود، transport زیرین فراخوانی نمی‌شود، ولی gateway موجود همچنان هزینه را محافظه‌کارانه نامعلوم ثبت می‌کند و scopeها متوقف می‌شوند. این لایه ادعای refund یا صفر بودن هزینهٔ آن حالت را ندارد.

## رسید تکمیلی

`app.state.presentation_release_binding` از binding مالی/تنظیمات اصلی جداست. فایل خصوصی `release-watch-audit.jsonl` فقط hashها، مرحلهٔ کنترل و وضعیت واگذاری به transport را ثبت می‌کند؛ پیام کاربر، متن منابع، header یا credential را نمی‌نویسد.

در این مسیر، نشانگر قدیمی `http_send_started` به ورود به زنجیرهٔ transport مربوط است و به‌تنهایی اثبات بازشدن socket یا پذیرش provider نیست. برای بررسی رد شدن در guard جدید، رسید تکمیلی و `delegate_started` را هم ببینید. حتی این نشانگر نیز رسید مصرف provider محسوب نمی‌شود؛ usage و ledger جدا هستند.

## پایان امن عمر برنامه

در `PresentationRuntime.close()` قدیمی، ترتیب گرفتن lockِ owner و run می‌تواند با ثبت رسیدِ هم‌زمان چرخه بسازد. یک diagnostic موقت این ترتیب را با timeout کنترل‌شده مشاهده کرد؛ thread دائماً قفل‌شده باقی نماند. این نتیجه، خرابی shutdown معمول Uvicorn را ثابت نمی‌کند؛ Uvicorn معمولاً ابتدا درخواست‌ها را تمام می‌کند.

bootstrap جدید فقط lifespan برنامهٔ ASGI را هماهنگ می‌کند: ابتدا زیر lockِ owner ورود تازه بسته و runهای فعال کپی می‌شوند؛ سپس lock آزاد می‌شود و بستن runها بیرون event loop انجام می‌شود. بنابراین ثبت رسید می‌تواند تمام شود و بعد lifespan اصلی خارج شود. کلاس یا متد قدیمی monkeypatch نشده‌اند؛ فراخوانی مستقیم و هم‌زمان `PresentationRuntime.close()` همچنان خارج از این اصلاح است.

برای ارائه باز هم صبر کنید spinner تمام شود، سپس launcher را متوقف کنید. تغییر source، stop وسط reservation یا مصرف نامعلوم تازه مجوز ادامهٔ پرداخت نیست.

## شواهد آفلاین

- `tests/test_presentation_release_watch.py`: کنترل source موقت، startup پیش از credential، aliasها، خطای خواندن، رد شدن تغییر پس از reservation، مسیر واقعی HTTP/Chroma/SQLite با provider ماک، و خروج lifespan حین درخواست فعال.
- `tests/test_presentation_release_safety.py`: retry هم‌زمان، correction حین درخواست، خطاهای provider/accounting، شکست settlement و سقف دو تلاش.

این تست‌ها روی index و ledger موقت اجرا می‌شوند. provider واقعی، فایل testِ held-out، ledger اصلی و key خوانده نمی‌شوند. نتیجهٔ آن‌ها کیفیت مدل، موفقیت ارزیابی نهایی یا حل C5 نیست.
