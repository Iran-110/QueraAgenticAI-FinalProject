# پذیرش اتصال RAG به core — C2b / ورودی R3 و P4

این تست مستقل از آماده شدن index است. یک factory را به backend ثابت وصل
می‌کند و همان خروجی adapter را بدون اصلاح به core می‌دهد. نسخهٔ مرجع فقط
fixture است؛ پاس شدن آن به معنی آماده بودن RAG حسن، کیفیت مدل یا test نهایی نیست.

## ورودی و مرز آزمایش

[fixture v1](../experiments/retrieval_acceptance/fixture-v1.json) در commit
`db9c2c0` پیش از اجرای اول ثبت شد. پنج hit، متن و metadata دقیق منابع C3 هستند؛
hash و URL/commit اسناد و منشأ P1 در fixture ثبت شده‌اند. loader علاوه بر hash
فایل‌های منشأ، برابر بودن hitها با C3 را بررسی می‌کند. انتخاب اولیهٔ Issue
#12782 و duplicate #12629 با دیدن جواب و workaround انجام شده؛ این خانواده
**exposed dev و answer-informed** است. ادامهٔ گفتگو تألیفی است. متن مسئلهٔ
شروع به‌شکل پارافرایز به reasoner داده می‌شود؛ raw Issue و جواب‌ها، label، gold
و expected وارد backend نمی‌شوند و جواب/gold هم به مدل داده نمی‌شود. منابع
ثابت docs هستند. این انتخاب شاهد آمادگی corpus نهایی یا رعایت exclusion نهایی نیست.

قبل از اجرا، اطلاعات معلوم، کمبود اطلاعات و تصمیم‌های قابل قبول در fixture
و P1 ثبت شده‌اند. این اجرای پذیرش از reasoner اسکریپتی استفاده می‌کند؛ داوری
استقلال ادعا از منبع و ضروری بودن سؤال مدل همچنان کار rubric/E2–E4 است.

## اجرا

از ریشهٔ repository و با dependencyهای locked:

```bash
uv sync --locked --group dev
uv run python scripts/rag_acceptance.py --output /tmp/rag-acceptance-new.json
uv run pytest tests/test_retrieval_acceptance.py tests/test_rag_acceptance_cli.py
```

مسیر receipt باید جدید باشد؛ فایل قبلی overwrite نمی‌شود. SQLite هر بار موقت
و تازه است؛ tracker یا ledger اصلی دست‌کاری نمی‌شود. CLI commit، dirty flag و
fingerprint کد را همراه نتیجه ثبت می‌کند. خروجی پیش‌فرض
`reference_fixture_adapter` است. fixture رتبه‌بندی مصنوعی دارد، اما معیار پذیرش
ترتیب hit یا query و انتخاب یک hit خاص در سقف top_k را تحمیل نمی‌کند.

چهارده case و ۱۳۲ check در اجرای کامل مرجع:

- query تکی و دو query با هم‌پوشانی؛ سقف کلی top_k و حذف chunk تکراری؛
- منابع نسخهٔ معلوم و اصلاح‌شده، نتیجهٔ خالی و metadata نامعلوم؛
- حفظ کامل متن و metadata، از جمله متن ۲۰۰۰۰ کاراکتری؛
- توقف پیش از مدل برای URL نامعتبر، متن ۲۰۰۰۱ کاراکتری، خطای backend و
  snapshot ناسازگار در درخواست یا پاسخ؛ خطای داخلی backend در receipt نشت نمی‌کند؛
- چهار turn همان dev از `CoreTurnService` با SQLite واقعی: سؤال تأییدشده،
  پاسخ نسخه، correction و refinement دو query، edit/approval و withdrawal/reject؛
  approval قدیمی رد می‌شود، evidence حذف‌شده در handoff نهایی نیست و retry
  بعد از restart فقط همان اقدام را برمی‌گرداند. replay رخداد قدیمی adapter
  یا مدل تازه نمی‌سازد.

تعداد checkها اندازهٔ کیفیت نیست. mutationهای مستقل نشان می‌دهند که تست فقط
مسیر happy path را بررسی نمی‌کند: حذف metadata، منبع معتبر خارج خواندن واقعی backend، حذف query، duplicate، افزایش
سقف خروجی، snapshot غلط، نسخهٔ ساختگی، تغییر quote، clipping بی‌صدا، پنهان کردن
خطای retrieval و برگرداندن bundle قدیمی رد می‌شوند. تغییر ترتیب مجاز پاس می‌شود.

سقف دو query در هر round، تعداد ورودی‌های `RetrievalRequest.queries` است؛
تعداد خواندن‌های داخلی backend را محدود نمی‌کند. یک query ممکن است چند
collection را بخواند. `backend_query_count` در receipt تعداد فراخوانی backend
است، نه تعداد queryهای درخواست core. تکرار خواندن همان query به‌تنهایی نقص
قرارداد نیست؛ این kit کارایی، latency یا هزینهٔ retrieval واقعی را نمی‌سنجد.
این موارد باید در R4/اجرای واقعی جدا اندازه‌گیری شوند.

## همان تست روی adapter واقعی

factory قرارداد تست است، نه تغییر قرارداد production:

```python
def factory(probe):
    # Instantiate the actual adapter with its configured snapshot and an
    # injected read backend/collection. Retain its real search and hit mapper.
    # Translate only the backend seam if its native row format differs.
    return actual_adapter
```

`probe.snapshot_id` شناسهٔ پیکربندی و `probe.backend.search(query, top_k=...,
filters=...)` backend ثابت هستند؛ هر بار dictهای مستقل EvidenceHit را می‌دهند.
factory به gold، پاسخ بعدی کاربر یا تصمیم مورد انتظار دسترسی ندارد. بعد از
refinement، harness فقط دادهٔ backend را عوض می‌کند تا evidence قدیمی قابل
تشخیص باشد. adapter همچنان باید request واقعی core را مصرف کند.

binding باید روی constructor/collection seam **کد واقعی adapter** تزریق شود.
ساختن EvidenceBundle بیرون adapter یا برگرداندن `FixtureRetriever`، پذیرش کد
حسن نیست. اگر ساختار backend او Chroma است، فقط rowهای fixture به شکل native
collection برگردانده می‌شوند؛ mapper تولید باید خودش metadata و Bundle را بسازد.
پس از review کد، binding آفلاین ثبت و اجرا می‌شود:

```bash
uv run python scripts/rag_acceptance.py \
  --factory reviewed_binding:factory \
  --check-candidate src/agent_app/retrieval/adapter.py \
  --output /tmp/rag-candidate-new.json
```

`reviewed_binding` placeholder است؛ هنوز binding واقعی ثبت نشده. قبل از import،
constructor و importهای آن بررسی شوند تا client واقعی، embedding، دانلود مدل
یا index اجرا نشود. CLI sandbox شبکه نیست؛ فقط binding بررسی‌شده و آفلاین
مجاز است. این آزمایش نیازی به `.env` یا API ندارد و هزینهٔ API آن صفر است.
ادعای هزینه برای factory دلخواه و بررسی‌نشده معتبر نیست.

`--check-candidate` فقط AST فایل را می‌خواند: فایل خالی، syntax نامعتبر یا نبودن
`ChromaRetrieverAdapter.search` رد می‌شود. این check هیچ import/indexی نمی‌کند
و به‌تنهایی شاهد پذیرش adapter نیست؛ receipt آن را از اجرای factory جدا می‌کند.
CI، fixture را اجرا می‌کند و در صورت حضور entrypoint، همین preflight را هم
می‌گیرد؛ نتیجهٔ CI پیش‌فرض فقط پذیرش fixture و سلامت entrypoint است.

## نتیجه و محدودیت

[اجرای اول مرجع](../experiments/retrieval_acceptance/results-fixture-first-v1.json)
۱۱۰/۱۱۰ check و ده case پاس شد؛ receipt آن حفظ است. در review
خود تست، کنترل metadata کامل boundary و factory بدون source قابل inspect
بهتر شد؛ سپس سه probe نسخه/URL و یک تزریق snapshot پاسخ از protocol ثبت‌شده
فعال شدند. نتیجهٔ کامل ۱۳۲/۱۳۲ است. این افزایش، تکمیل پوشش تست است؛ بهبود
اندازه‌گیری‌شدهٔ کیفیت RAG/core تصمیم‌گیر ادعا نمی‌شود.
کد اجرای اول هنوز commit نشده بود؛ hash فایل factory در receipt ثبت است.
receipt نهایی به commit و fingerprint کل کد bind می‌شود.

[receipt نهایی](../experiments/retrieval_acceptance/results-fixture-v3.json) و
[وضعیت pinned PR #23](../experiments/retrieval_acceptance/candidate-bdb7c53.json)
مبنای handoff هستند. در head `bdb7c5369319b9b0a47f330cf89193eab6398072`
چهار فایل Python RAG صفر بایت‌اند؛ CI سبز آن head کد adapter را آزمایش نمی‌کند.
R3/P4 هنوز بازند. بعد از push کد، همان factory/protocol روی adapter واقعی اجرا
می‌شود، بدون تغییر معیارها برای پاس شدن آن.

[preflight همان blob](../experiments/retrieval_acceptance/results-preflight-bdb7c53.json)
پیش از ساخت adapter با `CandidateEmpty` متوقف شد. اجرای کامل پیش از کنترل membership روی
checkout تمیز `6f8ba04` بود؛ [receipt آن](../experiments/retrieval_acceptance/results-fixture-v1.json)
حفظ است. review بعدی منبع معتبر خارج پاسخ query را هم رد کرد؛
[receipt v2](../experiments/retrieval_acceptance/results-fixture-v2.json) هم حفظ است.
نسخهٔ v3 این کنترل را به خواندن واقعی backend، از جمله سقف یک hit، متصل می‌کند.
receipt v3 نتیجهٔ نهایی همان protocol است؛ sourceها حین اجرا تغییر نکردند. regression قدیمی
`core_tracker_pilot.py` هم دوباره ۴۹/۴۹ check پاس کرد؛ locked sync، ۱۸۲۸ تست
و Ruff پاس‌اند. هیچ ledger، index، embedding یا API واقعی در این کار استفاده نشد.

این kit filterهای غیرخالی، HTTP/UI، CAS/journal lifecycle، index واقعی، embedding، segmentation
در ingestion، corpus/exclusion نهایی یا کیفیت مدل را نمی‌سنجد. برای ورودی
۲۰۰۰۱ کاراکتری fail-closed انتظار داریم؛ اگر ingestion آن را به chunkهای معتبر
تقسیم کند، به آزمایش جدا نیاز دارد. C2/U3/T4 و R1/R2/R4/E1–E5 باز می‌مانند.
