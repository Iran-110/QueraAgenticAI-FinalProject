# اتصال آفلاین gateway به core و review handoff

این replay مسیر واقعی `HTTP API`، `GroundedReasoner`، `MetisGroundedPlanner`،
`MetisReasoner`، رزرو/settlement هزینه و `ProposalHandoff` را کنار هم بررسی می‌کند.
ارسال HTTP حتماً با `httpx.MockTransport` قطع می‌شود؛ پاسخ provider را fixture
می‌سازد. کلید، یک رشتهٔ عمومی و ساختگی است. هر ledger داخل `TemporaryDirectory`
ساخته و بعد پاک می‌شود. `.env` و ledger واقعی پروژه خوانده نمی‌شوند.

## شرایط ثبت‌شده و شواهد

شرایط قبل از اولین replay در `protocol-gateway-handoff-v1.json`، commit
`d9c8e82` با SHA-256
`440ce8b91ec33f15f360be9aebae5cf0cc2bc919e7a2d4f637f9d3c372315d98` ثبت شده‌اند.
چهار نوبت گفتگو و پنج منبع رسمی، دقیقاً همان
[fixture آزمایش C3](../review_handoff/case-current-state-latest-evidence.json) هستند:
نسخهٔ نامشخص، جواب `1.50.0`، correction به `1.49.1` و پس‌گرفتن نسخه.
در correction، retrieval دوم واقعاً bundle متفاوت می‌دهد و منبع release قبلی
از ورودی نهایی کنار می‌رود. کنترل conflict جدا و مصنوعی است؛ تناقض کشف‌شده در docs نیست.

این داده‌ها به Issueهای `#12782/#12629` مربوط‌اند و انتخاب شواهد، answer-informed
و exposed development است؛ جواب همان Issue به‌عنوان منبع وارد نشده است.
اینجا index واقعی ساخته نمی‌شود و quarantine واقعی RAG هم ارزیابی نمی‌شود.

متن کامل پنج خروجی با `expected-analysis-v1.json` مقایسه می‌شود. این oracle در
آزمایش اصلی C3 **بعد از اولین replay** و با بررسی منابع توسط assistant اضافه شده؛
human gold یا scorer عمومی کیفیت پاسخ نیست. استفادهٔ مجدد از آن در این آزمایش،
این سابقه را تغییر نمی‌دهد. expected labelها و oracle به پیام provider وارد نمی‌شوند؛
فقط case، evidence، catalog، source reference، schema، ظرفیت و feedback ارسال می‌شوند.

اولین اجرای harness در ساخت adapter متوقف شد: مقدار JSON سقف هزینه `str` بود
و `MetisConfig`، `Decimal` صریح می‌خواهد. runner آن تبدیل نوع را اصلاح کرد؛ protocol
تغییر نکرد، هیچ ارسال provider انجام نشد و receipt موفقی برای آن اجرا ساخته نشد.

## چیزی که بررسی می‌شود

- چهار نوبت HTTP، پنج بار reasoning دارند؛ کنترل conflict هم دو تلاش جدا دارد.
  مجموع این مسیر هفت ارسال mock و هفت reservation/settlement است.
- چهار replay یک event، هیچ ارسال gateway اضافه نمی‌سازند. request IDها با
  `request_id_for` واقعی و context همان تلاش تطبیق داده می‌شوند.
- payload واقعاً ارسال‌شده از case فعلی، catalog فعلی و آخرین bundle ساخته شده؛
  hashهای منابع، version scope و تحلیل کامل به review handoff می‌رسند.
- JSON خرابِ plan یک repair دارد؛ feedback `invalid_grounded_plan` در تلاش دوم
  ارسال می‌شود و هر دو completion با usage ساختگی settlement دارند.
- model mismatch و timeout هر کدام بعد از یک ارسال متوقف می‌شوند، proposal ندارند
  و reservation نامطمئن حفظ می‌شود. فقط mismatch این ledger موقت را halt می‌کند.
- header و Authorization ذخیره نمی‌شوند؛ همهٔ clientها بسته می‌شوند. تغییر فایل
  حین اجرا، `python -O` و تلاش برای overwrite یک receipt، موفقیت را رد می‌کنند.

کل ارسال‌های intercept شده ۱۱ است: ۷ مسیر اصلی، ۲ repair و ۲ خطای terminal.
**درخواست پولی واقعی و هزینهٔ واقعی هر دو صفرند.** usage ثابت `125/75` فقط ساختگی
است؛ توکن واقعی prompt اندازه‌گیری نشده. settlement شبیه‌سازی‌شدهٔ مسیر اصلی
`0.000490875 USD` و repair `0.000140250 USD` است. هر خطای terminal، رزرو
`0.006082560 USD` نامطمئن نگه می‌دارد. این حسابداری، reconciliation حساب تیم نیست.

## اجرا

از ریشهٔ repository:

```bash
uv run python experiments/gateway_handoff/replay.py --validate
uv run pytest -q tests/test_gateway_handoff_pilot.py
uv run python experiments/gateway_handoff/replay.py --output /tmp/gateway-handoff-new.json
```

checkout باید تاریخچهٔ Git را داشته باشد؛ runner از C3 و baseline ثبت‌شدهٔ
`3f22ef9` استفاده می‌کند. `--output` فقط فایل جدید می‌سازد. receipt شامل protocol
hash، fingerprint کد اجراشده، payloadهای واقعی transport ساختگی، وضعیت ledgerهای
موقت، handoffها و محدودیت‌هاست. fingerprint کد، زمان اجرای همان receipt را نشان می‌دهد؛
receipt تاریخی را با تغییر کد بازنویسی نمی‌کنیم.

این نتیجه، اتصال و رفتار نرم‌افزار را نشان می‌دهد. هنوز انتخاب مدل واقعی، سازگاری
provider واقعی، کیفیت RAG، auth و persistence tracker یا test نهایی ارزیابی نشده‌اند.
معماری و port جدیدی اضافه نشده؛ adapterهای موجود روی یک مسیر مشترک آزمایش شده‌اند.
