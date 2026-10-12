# پذیرش pilot از مسیر HTTP — C2c

به‌روزرسانی: [اتصال opt-in به SQLite در C2d](persistent-http.fa.md) اکنون همان
pilot را با protocol v2 و **۴۵۷/۴۵۷** check، از جمله restart، پاس می‌کند. این فایل
receipt و محدودیت‌های تاریخی v1 برای **API حافظه‌ای پیش‌فرض** را حفظ می‌کند.

kit آماده و اجرا شده؛ **پذیرش کامل HTTP هنوز رد است**. همان pilot چهار‌نوبتی
#12782 از `CaseRun` موجود عبور می‌کند. در process فعلی correction، approval قدیمی
و retry درست کار می‌کنند؛ با restart واقعی، API حافظه‌ای پرونده و receipt را از
دست می‌دهد. باز کردن دوبارهٔ `TestClient` فقط reconnect است.

## ورودی ثابت و مقایسه

[protocol](../experiments/http_pilot_acceptance/protocol-v1.json) در `7a8d230`
پیش از اجرای baseline ثبت شد. [fixture موجود](../data/evaluation/dev/pilot-12782.json)،
gold و شواهد تغییر نکردند؛ SHA fixture برابر
`f4b9cef54c98dd875ff0e55f41aebcde19a9b02717b7cb8c5525eba9575f2855` است.
خانوادهٔ #12782/#12629 **dev و exposed** است: پاسخ Issue هنگام طراحی خوانده شده
و follow-upها تألیفی‌اند. خود Issue، پاسخ‌ها و duplicateها نباید وارد corpus شوند.

توضیح عبارت protocol: عبارت `current turn only` در بخش `given` دقیق نیست؛
ورودی مجاز، event فعلی و history ثبت‌شده تا همان نوبت است. turnهای آینده، gold
و `expect` وارد ورودی agent نمی‌شوند. protocol ثبت‌شده بازنویسی نشده؛ حفظ مسئلهٔ
اولیه از ابتدا در requirement `short_reply_context` آمده است.

| نتیجهٔ عملیاتی | baseline `89eab33` | بعد از اصلاح `60c0712` |
| --- | --- | --- |
| checks داخل process، شامل reconnect | ۳۰۱/۳۰۲ | **۳۰۲/۳۰۲** |
| checks مربوط به restart | ۶۵/۱۰۲ | ۶۵/۱۰۲ |
| مجموع checks همین یک pilot | ۳۶۶/۴۰۴ | ۳۶۷/۴۰۴ |
| `same_process_accepted` | false | **true** |
| `restart_accepted` و `accepted` | false | false |

این تعداد، checks تکرارشدهٔ یک پرونده در checkpointهای مختلف است؛ تعداد case
مستقل یا نمرهٔ کیفیت نیست. هر پنج checkpoint در gate حفظ state شکست می‌خورند.
checks پاس restart شامل تشخیص process تازه و مشاهدهٔ refusal بدون mutation‌اند؛
به معنی موفقیت persistence نیستند.

[baseline کامل](../experiments/http_pilot_acceptance/baseline-89eab33.json)،
[نتیجهٔ کامل](../experiments/http_pilot_acceptance/results-60c0712.json) و
[مقایسهٔ hash-bound](../experiments/http_pilot_acceptance/comparison.json)
commit تمیز، hash تمام فایل‌های runtime، protocol/fixture، ورودی واقعی reasoner،
handoffها، revision، action history و شمارش portها را ثبت می‌کنند.
API در baseline دقیقاً با `main@4f576d6` برابر است؛ فقط `api.py` بین دو receipt
runtime تغییر کرد. source طی هر دو اجرا ثابت ماند.

## چه چیزی اصلاح شد

API پیش‌تر بعد از سؤال نسخه فقط `1.50.0` را به engine می‌داد؛ مسئلهٔ fragment و
multiselect گم می‌شد. اکنون همان `build_reasoning_message` موجود در core، history
ثبت‌شدهٔ سمت سرور را آماده می‌کند. اولین پیام بدون تغییر می‌رسد؛ پیام‌های میانی
و آخرین پیام دقیق حفظ می‌شوند. facts فعال همچنان از `CaseState` می‌آیند؛ نسخهٔ
قدیمی در history فقط context تاریخی است و شاهد یا مجوز اقدام نمی‌شود.

فقط خروجی approve‌شده به history اضافه می‌شود. builder تنها سؤال canonical
تأییدشده و bind‌شده به reply را وارد ورودی مدل می‌کند؛ draft، reject و سؤال
غیرمرتبط وارد reasoning نمی‌شوند. `GroundedRequest` باید همین ورودی ترکیبی را
از invocation واقعی capture کند؛ بازسازی با reply کوتاه، handoff را با
`GroundedContextMismatch` متوقف می‌کند.

اگر context از ۲۰٬۰۰۰ کاراکتر بگذرد یا ناسازگار باشد، event پذیرفته‌شده حفظ و
run پیش از ساخت port متوقف می‌شود؛ پیام truncate نمی‌شود و retry دوباره اجرا
نمی‌کند. projection پیشنهاد قبلی ممکن است برای UI با `stale=true` باقی بماند؛
handoff معتبر و pending authority آن پاک شده و approval آن 409 می‌گیرد.

observer قدیمی `experiments/user_intake/replay.py` انتظار latest-only داشت؛ اکنون
اصل مسئله، پیام آخر و history را مستقل بررسی می‌کند. fixture/gold تاریخی دست
نخورده‌اند؛ receiptهای قدیمی حفظ شدند. mutation با حذف history باید replay را
رد کند.

## سناریوها و تصمیم قابل قبول، پیش از اجرای مدل

مدل واقعی اجرا نشده؛ تصمیم‌های script همان fixture ثبت‌شده‌اند.

| مرحله | اطلاعات موجود و کمبود | رفتار قابل قبول |
| --- | --- | --- |
| مسئلهٔ اولیه | reset در fragment؛ نسخهٔ Streamlit نامعلوم | سؤال canonical نسخه، فقط پس از approve نمایش داده شود |
| reply نسخه | reply bind‌شدهٔ `1.50.0` و docs ثابت؛ callback کامل نداریم | پاسخ script با منابع ثبت‌شده؛ متن مسئله در reasoning حفظ شود؛ pending تا review |
| correction | `1.49.1` گزارش می‌شود؛ شاهد دقیق آن نسخه نداریم | 1.50 superseded؛ checks/evidence قدیمی پاک؛ ارجاع script، edit با proposal تازه؛ approval قدیمی 409 |
| withdrawal | نسخه پس گرفته می‌شود و unknown است | سؤال script؛ reject هیچ متنی آزاد نکند |
| retry همان event | identity، payload، revision و reply binding اصلی | receipt کامل اصلی با `replayed=true`؛ state فعلی بدون تغییر؛ صفر factory/retrieval/reasoning |
| restart | process تازه با همان مسیر storage؛ globals قبلی حذف | تمام state و history حفظ؛ review/retry بی‌اجرای اضافه. API حافظه‌ای این شرط را نمی‌گذراند |
| قطع setup | ingress ثبت، adapter construction متوقف | بدون proposal تازه؛ retry همان event، داخل process و بعد restart، کار را خودکار از سر نگیرد |

restart در پنج نقطه اجرا می‌شود: سؤال approve‌شده، پاسخ pending، edit و approve،
withdrawal و reject، و قطع setup بعد از ingress. child با interpreter تازه، PID
متفاوت و همان storage path شروع می‌شود؛ state از والد کپی نمی‌شود.
برای هر refusal **کل view** ثابت است؛ log/revision به‌تنهایی کافی نیست.
GET، review موفق/ناموفق و event replay نیز نباید port تازه اجرا کنند.
retry باید کل intake اصلی را حفظ کند؛ صرف `replayed=true` کافی نیست.

## اجرا و اتصال بعدی

از root پروژه، بدون `.env`، model، embedding، index و production ledger:

```bash
uv sync --locked --group dev
uv run python scripts/http_pilot_acceptance.py --output /tmp/http-pilot-new.json
uv run pytest tests/test_http_pilot_acceptance.py tests/test_http_pilot_runtime.py tests/test_api_conversation.py
```

خروجی موجود overwrite نمی‌شود. دستور اول روی API حافظه‌ای exit 1 می‌دهد و
`accepted=false` ثبت می‌کند؛ این شکست persistence مورد انتظار و قابل بررسی است.
CI با `--expect-memory-gap` **فقط** اگر checks داخل process کامل پاس و persistence
رد شده باشد exit 0 می‌دهد؛ receipt همچنان `accepted=false` است. flag خطای startup،
خرابی context یا تغییر source را پنهان نمی‌کند.

بعد از اتصال واقعی API به tracker موجود، binding بازبینی‌شده باید context manager
با ورودی `Path state_dir` باشد، storage همان مسیر را باز کند و `HTTPRuntime` برای
**خود `agent_app.api.app` و seam واقعی `api._adapters`** برگرداند. این kit app دلخواه
را قبول نمی‌کند. wiring باید review شود؛ برچسب backend به‌تنهایی مدرک SQLite یا
at-most-once نیست. اجرای binding جدید با `--factory module:factory` و خروجی تازه
انجام شود؛ `--expect-memory-gap` برای candidate مجاز نیست.

مسیر HTTP باید از `CoreTurnService` و tracker موجود استفاده کند؛ storage تازه‌ای
برای پاس کردن تست نسازیم. U3/T4 همچنان شامل احراز maintainer، `review_id` ثابت،
digest دقیق handoff، transaction/CAS lifecycle و journal/outcome قطع‌شده‌اند.
whole-view/action history در این kit جای inspection واقعی actionهای SQLite،
review احراز‌شده یا اجرای ابزار بیرونی را نمی‌گیرد.

## اعتبار نتیجه

تمام اجرا آفلاین با ASGI `TestClient` و portهای اسکریپتی بود؛ TCP server یا browser
UI آزمایش نشده. اتصال‌های socket و DNS قبل از factory بسته‌اند؛ این guard sandbox
امنیتی برای کد ناشناس نیست. فقط factory بررسی‌شده را اجرا کنید.
هزینهٔ API **صفر** است و C5 halt/ledger دست نخورده‌اند. این نتیجه کیفیت RAG واقعی،
پشتیبانی معنایی ادعاها توسط منبع، کیفیت تصمیم مدل یا موفقیت test نهایی را نشان
نمی‌دهد. معیارهای evaluation و review انسانی همچنان لازم‌اند.
