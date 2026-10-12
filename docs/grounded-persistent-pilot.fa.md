# اتصال GroundedPlan به HTTP، UI و SQLite — C2f

این برش از قراردادهای موجود و همان tracker استفاده می‌کند. factory برای هر
run یک `GroundedReasoner` و gateway تازه می‌سازد؛ request واقعی آخرین invocation
به handoff منتقل می‌شود. فقط tracker پس از approval دقیق اقدام محلی ثبت می‌کند.
قراردادهای مشترک و adapter حسن تغییر نکرده‌اند.

## اجرای آفلاین برای اتصال تیم

backend قبلی همچنان پیش‌فرض `scripted` است. روی همان تنظیمات مستند
[pilot محلی](offline-ui-index-pilot.fa.md)، این گزینه را اضافه کنید:

```bash
export AGENT_PILOT_REASONING=grounded_fake_gateway
uv run uvicorn agent_app.offline_backend:application_factory --factory --host 127.0.0.1 --port 8000
```

`AGENT_TRACKER_DB` و credential خصوصی reviewer همچنان لازم‌اند. برای Chroma
موجود، `AGENT_PILOT_INDEX` و `AGENT_PILOT_SNAPSHOT` باید با خروجی builder یکسان
باشند. UI همان backend را می‌خواند؛ برای این حالت، selector سناریوی scripted
نمایش داده نمی‌شود و caption صریحاً mocked provider و هزینهٔ API صفر را می‌گوید.

این policy فقط نسخهٔ نامشخص را سؤال می‌کند و با نسخهٔ مشخص ارجاع می‌دهد؛ در
ارجاع حداکثر یک excerpt کامل را انتخاب می‌کند تا متن ساخته‌شده از سقف قرارداد
نگذرد. این انتخاب retrieval relevance یا تصمیم خوب مدل را اثبات نمی‌کند.
برای هر run، metadata، quote و scope همچنان در proposal قابل review هستند.
catalog این launcher فقط از factهای فعال و bundle فعلی ساخته می‌شود؛ gold،
fixture چندمرحله‌ای و پاسخ Issue وارد آن نمی‌شوند.

gateway از `httpx.MockTransport` استفاده می‌کند؛ `.env` یا provider واقعی را
نمی‌خواند. ledger شبیه‌سازی در پوشهٔ موقت جداست، با shutdown حذف می‌شود و از
ledger واقعی تیم مستقل است. client هر run بعد از ساخت handoff و قبل از stage
بسته می‌شود؛ این ترتیب در شکست، replay و interruption نیز کنترل شده است.
شکست cleanup، `AdapterCleanupFailed` را ثبت می‌کند و proposal تازه نمی‌سازد.
launcher payloadهای کامل اجراهای پایان‌یافته را در حافظه جمع نمی‌کند.

## شاهد قابل بازتولید

[protocol آفلاین](../experiments/grounded_http_acceptance/protocol-v1.json) پیش
از اجرا ثبت شد. baseline فایل‌های اصلی HTTP و coordinator از `3c92b12` را با
Git archive وارد می‌کند؛ بقیهٔ dependencyها با hash ثبت می‌شوند. همان چهار
turn، پنج invocation اصلی و شش invocation کنترل با provider جعلی اجرا می‌شوند.

```bash
uv run python scripts/grounded_http_acceptance.py --baseline --output /tmp/grounded-baseline-new.json
uv run python scripts/grounded_http_acceptance.py --output /tmp/grounded-current-new.json
uv run pytest tests/test_grounded_connected_ui.py tests/test_grounded_persistent_tcp.py
```

مقایسه برای label و cleanup است؛ baseline از قبل با injection قادر به اجرای
GroundedPlan بود. oracle کامل متن، quote، آخرین bundle، اصلاح/withdrawal نسخه،
conflict اعلام‌شده، repair، timeout و model mismatch بررسی می‌شوند. oracle از
اجرای اولیهٔ C3 بعدتر ثبت شده و gold انسانی مستقل نیست. خانوادهٔ #12782/#12629
exposed و انتخاب fixture، answer-informed بوده؛ پاسخ همان Issue شاهد نیست.
این‌ها evaluation نهایی یا کیفیت RAG واقعی نیستند.

AppTest صفحهٔ واقعی و Chroma واقعی را با gateway جعلی اجرا می‌کند. تست TCP از
دو interpreter تازه و همان SQLite/index استفاده می‌کند. retry همان approval
موفق بعد از correction، receipt اصلی را برمی‌گرداند؛ approval قدیمی با ID تازه
رد می‌شود. آزمون کامل مرورگر و recovery پس از پایان session جداست.

## API واقعی؛ فقط probe ثبت‌شده

launcher عمومی این صفحه live را قبول نمی‌کند. probe جداگانه با
[protocol محدود](../experiments/grounded_http_acceptance/live-protocol-v1.json)
و `scripts/grounded_live_probe.py` ثبت شده است: فقط اولین turn توسعه، حداکثر
دو send شامل repair، مجوز immutable موجود `gpt-4o-mini` و سقف رزرو مجموع
$0.006420480. اجرای پیش‌فرض فقط eligibility را read-only بررسی می‌کند.

این probe halt عمومی یا hold قبلی را رفع نمی‌کند، approval خودکار ندارد و
تکرارش بدون registration تازه ممکن نیست. هزینهٔ ledger از قیمت ثبت‌شده تخمین
زده می‌شود؛ برداشت واقعی حساب provider نامشخص می‌ماند. بعد از هر send، حتی
شکست HTTP، receipt هزینه و وضعیت ledger حفظ می‌شود. بررسی تصمیم و تمام ادعاهای
proposal جدا از پذیرش عملیاتی گزارش می‌شود. C5، C4 و ارزیابی نهایی بازند.

حسن همان `EvidenceBundle` با snapshot/version/span لازم را می‌دهد؛ محمدحسن
همان handoff کامل و manifest/rubric مستقل را مصرف می‌کند؛ بهنام همان review
دقیق را در tracker نگه می‌دارد. برای اتصال نهایی به framework یا tracker جدید
نیازی پیدا نکردیم.
