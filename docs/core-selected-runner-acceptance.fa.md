# اتصال تنظیم منتخب به runner و تصحیح review — C4s

این مرحله feature تازه‌ای برای core انتخاب نمی‌کند. تنظیم C4r، source اجرایی،
vocabulary، corpus، split و رفتار UI/API/tracker ثابت‌اند. هدف، بستن تست اتصال
factory منتخب به کل مسیر runner، سپس ثبت نتیجهٔ قابل بازتولید است؛ provider
فقط mock و index/ledger موقت‌اند. گذشتن این مسیر نمرهٔ کیفیت مدل نیست.

## پذیرش مسیر کامل runner

تست جدید [test_core_delivery_runner.py](../tests/test_core_delivery_runner.py)،
factory موجود را با `AGENT_CORE_PROFILE=grounded_candidate_v1` می‌سازد و
`runner.run(mode="live", conditional_routes=True)` را کامل اجرا می‌کند.
اینجا `live` نام mode اجرای adapter است؛ HTTP مدل با `MockTransport` قطعاً
intercept می‌شود و هیچ API پرداخت‌شده‌ای نداریم. case tracker این runner
همان `process_memory_dummy_tracker` است؛ پذیرش SQLite/restart قبلاً در C4r
ثبت شده، نه در این تست تازه.

| سناریوی ساختگی | اطلاعات و gap | انتظار ثبت‌شده |
| --- | --- | --- |
| مسیر سالم | نسخه ابتدا نامعلوم؛ سپس پاسخ نسخه و بعد کد callback به‌ترتیب می‌رسند | سؤال نسخه، سؤال ثبت‌شدهٔ کد، ارجاع؛ handoff و receipt جاری |
| خروجی خراب و repair | اطلاعات فعلی یکسان؛ اولین compact JSON نامعتبر است | تلاش دوم معتبر، هر دو هزینهٔ ساختگی حفظ، ادامهٔ درست route |
| دو خروجی خراب | plan قابل‌استفاده به دست نمی‌آید | سقف دو تلاش، توقف بدون proposal/release تازه، turn بعدی unvisited |
| timeout ساختگی | ارسال mock انجام شده؛ settlement نامعلوم است | حفظ uncertain، هزینهٔ کل نامعلوم، توقف route و رد allocation/factory بعدی پیش از key/index/send |

چهار سناریو در هر دو phase `development` و `evaluation`، مجموعاً **۸ تست**،
پاس‌اند. hash recipe، binding، مدل و phase واقعی reservation با receipt runner
تطبیق دارند. policy واقعی engine، handoff، بسته‌شدن همهٔ clientها و برابری
دقیق settled/reserved/uncertain با ledger موقت کنترل شده‌اند. canary مربوط
به gold/script وارد هیچ درخواست مدل نمی‌شود؛ canary پاسخ آینده هم تا turn
مجاز غایب است، شامل همهٔ retryها.

نکتهٔ دقیق timeout: ledger موقت تازه الزاماً فلگ جداگانهٔ `halted` را روشن
نمی‌کند؛ در این کنترل False می‌ماند. وجود uncertain به‌تنهایی باعث رد صریح
`LiveAccountingUnresolved` در هر دو مسیر `for_case` و `configured_factory`
می‌شود. اولین انتظار اشتباهِ تست دربارهٔ auto-halt و اصلاحش در receipt حفظ
شده‌اند؛ کد محصول برای پاس‌کردن تست تغییر نکرده است. halt اصلی پروژه و سه
hold آن عین byte باقی‌اند.

بررسی تازه شامل **۲۹۷ تست مرتبط**، review مستقل ۸ تست و Ruff برای ۳۸۹ فایل
است. شمارش‌ها هم‌پوشان‌اند. source اجرایی، تست‌های قبلی و تنظیم C4r عوض
نشده‌اند؛ بررسی گستردهٔ ۶۲۶۵ تست C4r شاهد تاریخی همان byteهای اجرایی است و
اجرای full-suite تازه ادعا نمی‌شود. parentهای محافظت‌شده صفر تلاش openِ
محافظت‌شده/شبکه ثبت کردند؛ این attestation تمام subprocessها نیست.
[رسید تست، review و تصحیح](receipts/core-selected-runner-acceptance-2026-10-16.json).

اجرای هشت کنترل از ریشهٔ پروژه، بعد از نصب dependencyهای lockشده:

```bash
agent_core_repo="$PWD"
(
  cd "$(mktemp -d)"
  "$agent_core_repo/.venv/bin/python" -m pytest \
    "$agent_core_repo/tests/test_core_delivery_runner.py" \
    -c "$agent_core_repo/pyproject.toml" -q
)
```

CWD خنثی مانع lookup ضمنی `.env` واقعی توسط Chroma می‌شود. هیچ fixture/gold
ارزیابی یا index اصلی برای این فرمان باز نمی‌شود؛ fixtureها و index موقت‌اند.

## تصحیح گزارش PR81

در review قبلی، snapshot قدیمی branch را با main جدید مقایسه کرده بودیم.
نبودن یادداشت‌های جدید main در آن snapshot را اشتباهاً حذف پیشنهادی PR دانستیم.
مقایسهٔ درست از merge-base است:

```bash
git merge-base origin/main 77ffd9c88e8489516119e6e4e7510a00850960b9
git diff --numstat origin/main...77ffd9c88e8489516119e6e4e7510a00850960b9 -- plan/plan.md
```

در main مبنا `e8b146c`، merge-base برابر `981b06d` و نتیجهٔ plan، **یک خط اضافه
و صفر حذف** است. merge سه‌طرفهٔ خود فایل plan بدون conflict، یادداشت‌های C4r،
C4q و C4j را حفظ و یادداشت native gold را اضافه می‌کند. این بررسی فقط فایل
plan است؛ کل PR merge یا gold آن فعال نشده است.

receipt تاریخی C4r عین byte حفظ می‌شود و ادعای rollback آن با این تصحیح کنار
گذاشته می‌شود. دو یافتهٔ باقی‌مانده مستقل‌اند: در فایل‌های **dev**
`fragment-rerun-9180-native-v1.json` و `tabs-blank-9259-native-v1.json`، شرط
ارجاع هنوز گزارش fix نسخهٔ 1.38 را لازم می‌داند، حتی در شاخهٔ نبودن passage
پشتیبان. این یافته‌ها در زمان C4s باز بودند؛ اکنون [E2ac](native-dev-gold-amendment.fa.md)
دو نسخهٔ افزایشی با شرط روشن، hash تازه و review دستیار جدا ثبت می‌کند. v1 و
review انسانی قبلی حفظ‌اند؛ تأیید انسانی بندهای تازه و build pin نهایی همچنان
pending است. gold برای تنظیم runtime استفاده نشده و test باز نشده است.

## مرز recovery در UI

بررسی آفلاین جدا روی SQLite موقت، برای approve/reject/edit نشان داد session
واقعاً تازه، review تازه‌ای خودکار نمی‌فرستد و اطلاعات قبلی DB را تغییر نمی‌دهد.
اگر caller همان operation اصلی را جدا نگه داشته باشد، client تازه پس از
بازسازی backend، receipt اصلی را بدون Action تکراری تأیید می‌کند.

این شاهد، بازیابی خودکار UI نیست. فهرست case و operation ارسال‌نشده فقط در
session نگه‌داری می‌شدند؛ در زمان C4s، UI راه reopen/import نداشت.
بعداً [U4a](saved-case-reopen.fa.md) بازکردن صریح پرونده باID و خواندن pending
را در sessionتازه و restartپردازش آزمود. این مسیر envelope گم‌شدهٔ review را
بازسازی نمی‌کند و outbox نمی‌سازد. شاهد قبلی C4s تاریخی و دست‌نخورده است.
