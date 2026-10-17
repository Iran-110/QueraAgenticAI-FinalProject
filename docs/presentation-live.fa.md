# اجرای زندهٔ محدود برای ارائه — `presentation_scoped_v1`

این مسیر جدا از backend عادی است و همان core، Chroma نهایی v3 و SQLite را
با مدل واقعی متیس وصل می‌کند. به معنی حل C5 یا نتیجهٔ ارزیابی held-out نیست.
ordinary live همچنان در halt متوقف می‌شود. سناریوی scripted در این مسیر
تصمیم مدل را تعیین نمی‌کند؛ متن ورودی آزاد است.

## مجوز و مرز اجرا

ساسان در طرح ارائهٔ ۱۸ اکتبر دو مرحلهٔ مستقل را مجاز کرده است: پذیرش/تمرین
و ارائه، هرکدام حداکثر `$0.10` و۱۴درخواست. هر مرحله سه case با۳/۲/۲نوبت دارد؛
هر نوبت همان حداکثر دو تلاش engine را دارد. مدل `gpt-4o-mini`، reserve ورودی
۳۲۷۶۸ و خروجی۱۰۲۴ است. bound قیمت ثبت‌شده برای هر slot برابر `$0.006082560`
و مجموع۱۴slot برابر `$0.085155840` است؛ هزینهٔ واقعی باید از usage تسویه شود.

نام case/run، revision و attempt پیشاپیش ثبت می‌شوند، نه متن سؤال داور.
شناسه‌های بسته یا خرج‌شده دوباره استفاده نمی‌شوند. scope فقط پس از تطبیق
hash همان protocol ثبت می‌شود؛ آماده‌سازی و startup مدل را فراخوانی نمی‌کنند.
pool تمام‌شده یا revision خارج از آن، پیش از ingress رد می‌شود. ارسال پیام
زنده علاوه بر approval نهایی، bearer خصوصی UI را هم لازم دارد.

هر سه hold قبلی و `halt=true` باقی می‌مانند. ثبت scope/مصرف تازه، فقط ردیف‌های
مجاز جدید به همان ledger اضافه می‌کند؛ بازنشانی DB یا کاهش hold نداریم.
عدم قطعیت تازه هر دو مرحله را متوقف می‌کند؛ تمدید یا scope جایگزین خودکار
وجود ندارد. C5 همچنان به مدرک provider برای درخواست‌های قدیمی نیاز دارد.

## آماده‌سازی و اجرا

از root پروژه، یک index پذیرفته‌شدهٔ v3 و یک پوشهٔ خروجی **تازه و بیرون repo**
بدهید. این دستور فقط protocolها، کپی index، baseline و شناسه‌ها را می‌سازد:

```bash
uv run python -m agent_app.presentation_session prepare --output-dir /absolute/fresh-session-folder --index /absolute/verified-v3-index
```

برای هر مرحله، بعد از review همان protocol و سقف و slotهایش، hash ثبت‌شده در
`sessions.json` را صریح بدهید. این کار طبق طرح مصوب مجوز محدود را ثبت می‌کند؛
خود دستور هیچ model call ندارد:

```bash
uv run python -m agent_app.presentation_session authorize --protocol /absolute/fresh-session-folder/rehearsal/protocol.json --expected-sha256 SHA256_FROM_SESSIONS
uv run python -m agent_app.presentation_session status --protocol /absolute/fresh-session-folder/rehearsal/protocol.json
```

token reviewer در فایل خصوصی `reviewer-token.txt` با permission۶۰۰، بیرون repo
نگه داشته می‌شود؛ کلید مدل فقط از `.env` اصلی و پس از guardهای public خوانده
می‌شود. محتوای هیچ‌کدام را در command، log، screenshot یا Git نگذارید:

```bash
uv run python -m agent_app.presentation_session serve --protocol /absolute/fresh-session-folder/rehearsal/protocol.json --dotenv "$PWD/.env" --reviewer-token-file /absolute/private/reviewer-token.txt --port 8001
```

UI جدا با `AGENT_API_URL=http://127.0.0.1:8001`، timeout صریح۹۰ثانیه، همان token
خصوصی در environment و `AGENT_PRESENTATION_CASES` به‌شکل JSON سه case همان
protocol اجرا می‌شود. مدل و کلید آن به UI داده نمی‌شوند. startupهای اصلی و
demo آفلاین قبلی تغییر نکرده‌اند.

scope تمرین و scope ارائه DB و case و شناسهٔ مستقل دارند. بعد از پذیرش و
خاموش‌کردن process تمرین، scope آن را ببندید؛ برای ارائه فقط protocol دوم
ثبت‌شده را اجرا کنید. restart مجوز یا case تازه نمی‌سازد:

```bash
uv run python -m agent_app.presentation_session close --protocol /absolute/fresh-session-folder/rehearsal/protocol.json
```

## شواهد و تست

پیش از مصرف API، تست‌های `test_presentation_runtime.py`،
`test_presentation_ui_api.py`، `test_presentation_session.py` و
`test_presentation_review.py` با ledger موقت و provider ماک اجرا می‌شوند.
index واقعی موقت است؛ payloadهای test/exposure، کلید و ledger اصلی مصرف نمی‌شوند.

در اجرای واقعی، receipt خصوصی هر درخواست شامل context دقیق، evidence مصرف‌شده،
canonical plan، serving model تأییدشده و usage/cost ledger است. این فایل‌ها
پشتیبان review هستند و خودکار وارد Git یا corpus نمی‌شوند. بعد از اجرا باید
کیفیت هر ادعای مهم و سؤال را جدا بررسی کرد؛ HTTP200 یا JSON معتبر نمرهٔ کیفیت نیست.

کنترل آخر درست پیش از transport، بعد از reserve، config/source/index و همان
reservation را دوباره بررسی می‌کند. اگر ارسال/usage قطعی نباشد، نتیجهٔ آفلاین
به‌صورت خودکار جای مدل نشان داده نمی‌شود.

## نتیجهٔ پذیرش و آماده‌سازی جلسه

source ثبت‌شده `cf5fa50`، ۱۲۶۷تست مرتبط روی۴۰فایل امن و Ruff/format۴۱۳فایل
را پاس کرد؛ ۵۹کنترل تازه داخل همین شمارش‌اند. کنترل launcher بیرون repo نیز
۱۱تست دارد. audit ثبت‌شده مربوط به parent interpreter است، نه تمام subprocessها.
بستهٔ receipt، شمارش‌ها و مرزها را در
[رسید پذیرش زنده](receipts/presentation-live-acceptance-2026-10-17.json) ببینید.

پذیرش واقعی۷نوبت/۸درخواست،۳۷۱۳۰token ورودی و۴۵۹خروجی داشت؛ همه با مدل
`gpt-4o-mini-2024-07-18` و هزینهٔ تخمینی `$0.006429390` از usage تسویه شدند.
سه نوبت از مرورگر UI و چهار نوبت از client همان API ارسال شدند. correction،
409 approval قدیمی، retry پیام و review، reopen و restart واقعی backend پاس‌اند؛
هر سه پرونده برابر ماندند و retry درخواست مدل یا Action اضافه نساخت.

کیفیت جواب **جزئی** است: بخش درست type، disabled و icon دکمه در منابع مصرف‌شده
بود؛ جواب correction multiselect منابع download_button/fragments کم‌ربط انتخاب
کرد و متن‌های جواب طولانی‌اند. نقل‌قول دقیق و JSON معتبر، relevance یا حل
مسئله را ثابت نمی‌کند. این بازبینی assisted است؛ نمرهٔ انسانی نهایی نداریم.

مرحلهٔ تمرین با۸درخواست بسته شد. مرحلهٔ ارائه مستقل، با۷نوبت/۱۴درخواست و
سقف۰٫۱۰دلار، در زمان تحویل مصرف نشده است. startup و GET/reopen مدل را صدا
نمی‌زنند. ظرفیت برای سؤال آزاد داور است؛ تمرین بیشتر با backend آفلاین انجام
شود. scope خودکار تمدید نمی‌شود. global halt و سه hold تاریخی باقی‌اند؛ هزینهٔ
تخمینی محلی جای reconciliation صورتحساب provider نیست.

در این دستگاه launcher و بستهٔ قابل نمایش در
`/Users/sasan/Desktop/Agentic AI/output/presentation-2026-10-18/` قرار دارند؛
`start-live-demo.command` مسیر live را روی UI8502/API8001 باز می‌کند و
`start-live-demo.py --status` health/ظرفیت را بدون مدل گزارش می‌دهد.
دمو آفلاین8501/API8000 برای پشتیبان حفظ شده است. اجرای نمایش فقط روی loopback
است؛ `.env`، token، ledger و receipt خصوصی وارد bundle عمومی نمی‌شوند.

نشانگر خاکستری `Synthetic` از metadata قدیمی API می‌آید؛ مسیر scoped و receipt
provider واقعی را ثبت می‌کنند. این نقص label توضیح داده می‌شود؛ source فریز‌شده
برای مخفی‌کردن آن دست‌کاری نشده است. caption scoped و قیمت/مدل در receipt معیار
تشخیص اجرای واقعی‌اند. هیچ screenshot یا OCR به مدل فرستاده نمی‌شود.
