# بازبینی live پس از ارائه، L1 تا L4

تاریخ: ۲۲ اکتبر ۲۰۲۶. مالک: Member 4. راهنمای کار:
[تحویل live پس از ارائه](post-presentation-live-handoff.fa.md). وضعیت checkboxها
در [plan](../plan/plan.md) است.

در این کار هیچ درخواست مدل فرستاده نشد. هزینهٔ واقعی صفر است. ledger تیم،
halt، سه hold، scopeها، watch، protocol و receiptهای تاریخی تغییر نکرده‌اند.
فایل‌های held-out test، native test gold و payload فریز exposure باز نشدند.

## L1 — baseline ثبت‌شده

| مورد | مشاهده |
| --- | --- |
| شروع کار | `origin/main` در `46bf062`؛ branch کاری `fix/l1-live-startup-diagnostics` |
| مدل | `gpt-4o-mini` از gateway متیس، `grounded_plan`؛ مدل واقعی serving فقط از receipt اجرای واقعی مشخص می‌شود |
| core profile | `grounded_candidate_prefilter_v2`، recipe `ae7b2d04202324bda360b478dd2dd6dff79a3482395fc5dd1e0deade1d9491c4` |
| index | `runtime/demo-final-corpus-v3`؛ snapshot `docs-pilot-20ab0d69…f8277b6`؛ sha256 manifest محلی `933682e5…d1908dc` با رسید v3 برابر است |
| startup معمولی | `uv run uvicorn agent_app.live_backend:app_factory --factory --host 127.0.0.1 --port 8765` |

### blockerها

**B1، پیام خطای startup (در L2 اصلاح شد).** وقتی startup معمولی live رد می‌شد،
اپراتور فقط `LiveBackendConfigurationInvalid` می‌دید و دلیلش معلوم نبود.
وقتی ledger تیم وجود نداشت، خود factory هم به‌جای کد مشخص، کد کلی
`LiveEvaluationConfigurationInvalid` برمی‌گرداند.

- بازتولید: روی این دستگاه `runtime/budget.sqlite3` وجود ندارد. با `.env` محلی و
  pinهای بالا، دستور startup را اجرا کنید.
- قبل: traceback فقط `ValueError: LiveBackendConfigurationInvalid` را نشان می‌داد.
- بعد: یک خط log با `Live backend startup refused: LiveLedgerUnavailable`
  نشان داده می‌شود و خطای عمومی بدون تغییر باقی می‌ماند. فایل ledger ساخته
  نمی‌شود. در log فقط کدهای ثابت فهرست مجاز نوشته می‌شود؛ مسیر، متن خام و
  secret هرگز در آن نمی‌آیند.

**B2، مجوز اجرای پولی (مشکل کد نیست؛ باز است).** live معمولی به‌خاطر halt
ledger تیم، سه hold و C5 متوقف است. روی این laptop هم ledger تیم اصلاً وجود
ندارد. اجرای پولی به مجوز صریح و جداگانه نیاز دارد. این guard را دور نزدیم.

**B3، مسیر ارائه.** `presentation_scoped_v1` به protocol، ledger و watch خارج
از Git نیاز دارد که روی این دستگاه نیستند. بنابراین وضعیت read-only امروز آن
از اینجا قابل بررسی نیست. ظرفیت گزارش‌شده در ۱۸ اکتبر هم مجوز تازه حساب نمی‌شود.

### بررسی PR #93 (`feat/user-live-backend`، head `11f39d6`)

1. **حساب هزینه:** ledger جدای ۱ دلاری، halt تیم و کنترل کل ۵ دلار را دور
   می‌زند. ledger روی هر laptop مستقل است و reservationها برچسب `development`
   دارند. این PR مجوز هزینه یا reconciliation نیست و تصمیمش با ساسان است.
2. **برچسب UI:** health همچنان `development_live_sqlite` را نشان می‌دهد و UI
   متن «bounded live development probe» را؛ کاربر عادی برچسب توسعه می‌بیند.
3. **همگام‌سازی:** branch از main عقب است و یک خط plan آن با main تداخل دارد.
4. **بخش قابل استفاده:** تزریق `adapters_factory` به `configured_app`، بدون
   تغییر core درست است و تست‌های mock آن مفیدند.

پیشنهاد: PR93 تا تصمیم مالی باز بماند و merge نشود. در این تحویل از آن
استفاده یا merge نشد و backend موازی هم ساخته نشد.

## L2 — اصلاح

- `src/agent_app/live_backend.py`: کد مجاز factory را log می‌کند. پیام عمومی
  خطا بدون تغییر است.
- `src/agent_app/evaluation/live.py`: اگر ledger تیم موجود نباشد، کد
  `LiveLedgerUnavailable` برگردانده می‌شود.

تغییر `evaluation/live.py` روی یکی از ۲۱ فایل binding مالی ارائه اثر می‌گذارد.
هر تغییری زیر `src/agent_app` هم watch ۱۱۷ فایلی را تغییر می‌دهد. پس scope قدیمی
ارائه نباید با این کد اجرا شود. watch، protocol و hash را برای عبور از drift
دوباره نساختیم.

## L3 — پذیرش آفلاین

- تست‌های تازه با provider ماک و ledger موقت:
  - `test_missing_designated_ledger_reports_unavailable_without_creating_it`
  - `test_backend_startup_reason_shows_only_allowlisted_codes`، با دو حالت
  - بررسی log در `test_halted_live_configuration_stops_before_creating_tracker_or_allocating_ports`
- مجموعهٔ هدفمند live: ۶ فایل تست، ۱۵۱ تست، همه پاس.
- مجموعهٔ کامل توسعه: ۷۱۵۳ تست پاس. پنج مصرف‌کنندهٔ محافظت‌شده طبق AGENTS.md
  deselect شدند؛ این اجرای held-out نیست.
- `ruff check`، `ruff format --check` و سه demo آفلاین پاس شدند.
- startup واقعی قبل و بعد از اصلاح، روی index v3 مقایسه شد؛ رد شدن پیش از
  کلید و provider اتفاق افتاد.
- smoke مرورگر اجرا نشد، چون مسیر UI/API تغییری نکرده و startup پیش از ساخت
  tracker رد می‌شود. correction، approval قدیمی، retry و restart با تست‌های
  موجود همان فایل‌ها پاس شدند.

## L4 — تحویل

- بازگشت: revert همین commit کافی است. داده، tracker و ledger تغییری نکرده‌اند.
- model call واقعی: صفر. هزینه: صفر.
- باقی‌مانده: B2 (مجوز مالی و C5)، B3 (بررسی read-only مسیر ارائه روی دستگاه
  دارای protocol) و تصمیم دربارهٔ PR93.
