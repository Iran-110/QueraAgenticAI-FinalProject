# C2j — validation ورودی پاسخ نسخه، پیش از dump

به‌روزرسانی: ۱۶ اکتبر ۲۰۲۶.

دو helper پاسخ نسخه در [intake.py](../src/agent_app/orchestration/intake.py)
اکنون همان `detached_contract` موجود را برای ورودی‌های خود به‌کار می‌برند.
مقدار معتبر همان خروجی قبلی را می‌دهد؛ object نامعتبرِ دست‌ساز Python پیش از
استخراج نسخه با کد ثابت `IntakeRejected("InvalidInput")` رد می‌شود.

## مشکل و اصلاح محدود

قبلاً helper ابتدا `model_dump` و سپس `model_validate` می‌کرد. فیلد اضافی که با
`model_copy` یا bypass در object قرار گرفته بود، هنگام dump حذف می‌شد؛ در نتیجه
validator دیگر آن را نمی‌دید. همین اتفاق برای metadata خصوصی یا extra در بعضی
مدل‌های nested می‌افتاد.

اصلاح فقط شش فراخوانی validation و import است:

| helper | ورودی‌هایی که پیش از dump بررسی می‌شوند |
| --- | --- |
| `prepare_version_reply` | `CaseState`، `UserTurn` و `AnalysisResult` سؤال pending |
| `prepare_approved_version_reply` | `CaseState`، `UserTurn` و `ApprovedReplyQuestion`، شامل سؤال nested |

[validator موجود](../src/agent_app/orchestration/validation.py) ابتدا ساختار کامل
Contract، فیلد اضافی و metadata خصوصی را بازگشتی بررسی می‌کند؛ cycle و عمق بیش
از حد موجود را هم رد می‌کند. سپس همان dump/revalidation قبلی را انجام می‌دهد.
خود validator، shared contractها و normalization آن‌ها تغییر نکرده‌اند.

خطاها با همان catch و `from None` به `InvalidInput` تبدیل می‌شوند؛ متن ورودی،
نام فیلد اضافی یا جزئیات Pydantic در پیام خطا بیرون نمی‌رود. بررسی case،
revision، proposal، سؤال canonical و پاسخ سه‌بخشی نسخه پس از این مرز همان است.
این helper storage یا approval را authenticate نمی‌کند؛ caller باید record
دقیق pending/approved را از tracker بخواند و original ingress را پیش از آماده‌سازی
deduplicate و همراه transition به‌صورت اتمیک ثبت کند.

## شواهد قبل و بعد

[protocol](../experiments/intake_validation_v1/protocol-v1.json) و
[۱۶ baseline معتبر](../experiments/intake_validation_v1/valid-baseline-v1.json)
در commit`ee719d3`، پیش از پیاده‌سازی ثبت شدند. هر دو helper با هشت variant
خنثی پوشش داده شدند: prefix، whitespace، releaseهای مختلف و حفظ facts/checks/
evidence و هویت turn. JSON canonical و SHA خروجی prepared turn، transition
کامل و ورودی‌ها نگهداری شده‌اند.

[مقایسهٔ ۵۵ تست یکسان](../experiments/intake_validation_v1/comparison-v1.json):

| کنترل | کد قبلی | اصلاح C2j |
| --- | --- | --- |
| ۲۷ ورودی دارای extra یا metadata نامعتبر | آماده‌سازی پذیرفته می‌شد | پیش از extraction با `InvalidInput` رد می‌شود |
| دو ReportedFact دارای extra در turn ساختاریافته | پس از پاک‌شدن extra با `StructuredTurnNotAllowed` رد می‌شد | در مرز ورودی با `InvalidInput` رد می‌شود |
| ۱۰ کنترل نوع نامعتبر، cycle و عمق اضافی | از قبل رد می‌شدند | همچنان پیش از extraction رد می‌شوند |
| ۱۶ ورودی معتبر | پاس | prepared output و transition کامل دقیقاً همان byte/hash قبلی |

پس baseline در این ۵۵ تست۲۹fail/۲۶pass و نسخهٔ جدید۵۵pass دارد. ورودی‌ها در
موفقیت و rejection تغییر نمی‌کنند. این‌ها fixtureهای تألیفی آفلاین‌اند؛ تعداد
تست، امتیاز پاسخ مدل یا تعداد Issue مستقل نیست.

[verification](../experiments/intake_validation_v1/verification-v1.json) روی source
ثابت`f780ca8`:۵۴۷۹pytest،Ruff۳۵۷فایل،سهdemo و HTTP/SQLite۴۵۷/۴۵۷، شاملrestart،
پاس‌اند. review جدا۵۵ تست جدید و۱۲ کنترل اتصال API/SQLite/history/replay را
تکرار کرد و blocker ندارد. suite اصلی شامل تست‌های قبلی canonical question،
approved reply، revision و dedup است؛ approval/retry پیاده‌سازی تازه‌ای ندارد.

## بازتولید و حدود تحویل

```bash
uv run pytest tests/test_intake_boundary_validation.py tests/test_intake.py \
  tests/test_approved_reply_intake.py
```

این تغییر در مسیر عادی همان دو helper اعمال می‌شود و flag یا framework جدید
ندارد. ورودی معتبر API/UI، استخراج نسخه و authority tracker ثابت‌اند. این
تحویل سخت‌گیری دو مرز درون Python است؛ بررسی همهٔ مرزهای داخلی، authentication،
حل recovery در session تازه، کیفیت مدل/RAG یا test نهایی را اثبات نمی‌کند.

هیچ API واقعی یا دسترسی به credential، index یا corpus جدید انجام نشد؛ همان
۱۹pin فعلی و hash ledger ثابت‌اند. halt، سهhold، سقف و همهٔ IDهای بسته حفظ‌اند.
hosted CI به علت Billing اجرا نشده و Windows/browser تازه ادعا نمی‌شود.
