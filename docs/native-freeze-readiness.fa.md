# آمادگی pin و freeze نهایی — E2ad

**آخرین وضعیت، C4u:** loader اکنون protocol بستهٔ۱۲۲۸منبعیِ docs/API/release-note را می‌پذیرد و build محلی pre-freeze با pinهای حسن منطبق شد. [پذیرش اتصال](final-build-core-acceptance.fa.md) و [رسید](receipts/final-build-core-acceptance-2026-10-17.json). دو بندdev درPR87 تأیید انسانی شدند؛ PR88 فقطcustody و PR89 ثبت freeze منابع/exclusion۹۵ است. exposure payload باز نشده. rebuild۹۵ با خروجی تازه، native gold/pin و versioned core v2/config freeze و C5 هنوز لازم‌اند؛ یادداشت‌های E2ad بعدی تاریخی‌اند.

**به‌روزرسانی ۱۷ اکتبر:** PR83 ثبت native test را اضافه کرده است؛ بررسی core
فقط metadata/custody است و ادعای انسانی یا payloadها را تأیید نمی‌کند.
[مرز exposure و اصلاح plan](pr83-custody.fa.md) باید پیش از freeze با مالک
evaluation تعیین تکلیف شود. تأیید دو بند dev، pinهای نهایی و build سازگار
همچنان بازند. جدول زیر دربارهٔ این gateهاست؛ نیاز به ساخت native test اکنون
به بررسی ثبت موجود و نسخهٔ pinned تازه تبدیل شده است.

بررسی remote در مبنای `7fbef14`، PR باز یا push تازه‌ای پس از PR81 نشان نداد.
آخرین تحویل حسن، R4b/PR72، و آخرین تحویل محمدحسن، native dev/PR81، روی main
هستند. این بررسی دربارهٔ Git است؛ از کار منتشرنشدهٔ اعضا خبری نداریم.

## اصلاح مستقل gate نهایی

یک بستهٔ کاملاً ساختگیِ `frozen_final_v1` از gate قبلی عبور می‌کرد، در حالی که
fixture آن `native_index` و `pending_final_build` با pinهای null داشت.
[preflight موجود](../src/agent_app/evaluation/preflight.py) اکنون این حالت را
پیش از ساخت adapter مدل رد می‌کند. مسیر عادی dev و fixtureهای قبلیِ فاقد
native marker تغییر نمی‌کنند؛ ابزار freeze یا loader موازی اضافه نشده است.

| کنترل برای fixture صریحاً native در بستهٔ نهایی | خطای ثابت |
| --- | --- |
| برچسب همهٔ turnها و `native_scope` برابر `native_index` باشد | `NativeEvidenceConditionRejected` |
| build و snapshot شناسهٔ محدود باشند؛ build موقت و pin خالی/خراب پذیرفته نیست | `NativeIndexPinsRequired` |
| SHA ثبت‌شدهٔ corpus با فایل واقعی corpus ارزیابی برابر باشد | `NativeCorpusHashMismatch` |
| پنج pin همهٔ fixtureهای native بسته یکسان باشند | `NativeIndexBindingMismatch` |

`build` حداکثر ۱۲۸ و `index_snapshot` حداکثر ۱۶۰ کاراکتر ASCII شناسه دارند؛
سه SHA باید ۶۴ رقم lowercase hex باشند. `pending_final_build` با هر ترکیب
حروف رد می‌شود. note یا فیلد اضافی، اختیار binding نمی‌سازد و صادر نمی‌شود.
رسید فقط count و hash ثبتِ پنج pin را همراه
`physical_index_verified=false` و `semantic_support_assessed=false` می‌دهد.

**معنی hashها:** `native_scope.corpus_manifest_sha256`، hash خام فایل corpus
ارزیابی است که به `--final-corpus-manifest` داده می‌شود. hash فایل فیزیکی
`pilot-manifest.json`/index manifest، pin جداگانهٔ loader است؛ این دو یکی نیستند.
allowlist و exclusion در این gate فقط SHA اعلام‌شده‌اند؛ فایل آن‌ها یا storage
فیزیکی از روی برابری declaration تأیید نمی‌شود. بررسی passage، کاربرد نسخه،
support، قضاوت انسانی و مجوز هزینه نیز کار این gate نیستند.

۲۷۹ تست مرتبط شامل ۷۰ regression تازه پاس شدند؛ reviewهای مستقل و Ruff/format
۳۹۲ فایل هم پاس‌اند. شمارش‌های مستقل هم‌پوشان‌اند و full-suite تازه ادعا
نمی‌شود. همهٔ بسته‌های اجرای final در این بررسی ساختگی‌اند؛ هیچ fixture مربوط
به test واقعی باز نشده است. guard parent تلاش محافظت‌شده/شبکه ثبت نکرد؛
این attestation تمام subprocessها نیست.

## چه چیزی واقعاً برای freeze کم است؟

| بخش | وضعیت و تحویل لازم |
| --- | --- |
| حسن؛ corpus/build | سیاست corpus، allowlist، provenance، segmentation و exclusion نهایی؛ سپس build نسخه‌دار و رسید فیزیکی قابل بازتولید |
| اتصال build به core | loader فعلی فقط پروفایل‌های بستهٔ ۱۴/۱۸ منبعی را می‌پذیرد؛ بیلد گسترده‌ترِ شامل release note به protocol/loader سازگار و review مشترک نیاز دارد. hash تازه به‌تنهایی آن را قابل اجرا نمی‌کند |
| محمدحسن؛ gold/review | تأیید انسانی دو بند E2ac، بررسی eligibility پس از exposure محدود، نسخهٔ pinned تازهٔ native gold توسط خودش، review معنایی تنظیم منتخب و freeze rubric/exposure/family/coverage |
| packet نهایی | fixtureهای native فعلی همگی pending هستند؛ برای pin نهایی نسخه‌های تازه بسازیم. `case.family_id` و coverage witness موردنیاز قرارداد final در ۱۶ dev فعلی هنوز ثبت نشده‌اند |
| اجرای واقعی | پس از pin و تطبیق فیزیکی index، C5 و سه درخواست نامعلوم باید با مدرک provider تعیین تکلیف شوند؛ halt فعلی مجوز اجرای تازه نمی‌دهد |

exclusion فعلی، ۹۰ Issue دارد؛ hash کل manifest نسبت به رسید قدیمی عوض شده،
اما خود exclusion تغییر نکرده است. guide آزمایشی answer-linked مربوط به Enum
همچنان خارج corpus واقعی می‌ماند. packing/relevance شاهد key-identity نیز
با حسن باز است؛ بیلد تازه خودکار این مشکل رسیدن منبع به مدل را حل نمی‌کند.

audit مستقل فقط از کپی manifest مجاز ۱۸ source/۳۶ chunk استفاده کرد؛ Chroma
خوانده نشد. از ۱۶ بلوک `answer_required` در dev، ۹ بلوک همهٔ requirementهای
ثبت‌شده را در chunkهای همین inventory دارند. این عدد **رتبهٔ retrieval، رسیدن
شاهد به مدل، کفایت نسخه یا کیفیت پاسخ نیست**. هفت turn فاقد answer-required
ثبت‌شده در این denominator نیستند و به‌عنوان موفقیت شمرده نشده‌اند.

## ترتیب بدون چرخه برای pinها

1. rubric، provenance و خانواده‌ها/exclusion مستقل بازبینی و ثبت شوند؛ محتوای
   test فقط دست صاحب evaluation بماند.
2. build سازگار، allowlist، exclusion و receipt فیزیکی index آماده شود؛ شناسهٔ
   snapshot و hash فیزیکی از همان build بیایند.
3. corpus JSON ارزیابی با declarationهای بازبینی‌شده ثبت و hash خامش محاسبه شود.
4. نسخه‌های تازهٔ fixture/registration، همین pinها و review معتبر را ثبت کنند؛
   byteهای pending v1/v2 یا receiptهای تاریخی درجا پر/بازنویسی نشوند.
5. packet نهایی تازه، hash fixtureها و corpus را pin کند؛ مالک evaluation کل
   بسته را بعد از freeze بررسی کند. سپس تطبیق adapter واقعی و مجوز هزینه لازم است.

این مرحله نه freeze را خودکار می‌کند و نه برای انسان witness می‌سازد.
[رسید source، بررسی dev و تست‌ها](receipts/native-freeze-readiness-2026-10-16.json).

بازتولید فقط با دادهٔ ساختگیِ نرم‌افزار، از root پروژه:

```bash
uv run pytest tests/test_native_final_pins.py tests/test_evaluation_preflight.py tests/test_eval_runner_final_preflight.py -q
uv run ruff check .
uv run ruff format --check .
```

اجرای این فرمان‌ها نمرهٔ test نهایی پروژه نیست. halt، ledger و سه hold، تمام
۲۲ artifact JSON ثبت‌شدهٔ native، corpus و vocabulary محفوظ‌اند؛ API و پیام تیمی صفر.
