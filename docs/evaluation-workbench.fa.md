# آماده‌سازی review واقعی سه dev

این ابزار کار E2 محمدحسن را جلو می‌برد: خروجی واقعی C4g، پیام همان نوبت،
و تمام منبع‌ها را برای داور کنار هم می‌گذارد. مدل، retrieval، tracker یا
API را اجرا نمی‌کند و نمرهٔ انسانی نمی‌سازد. RAG/ranking حسن و smoke دستی
UI/SQLite بهنام مسیر جدا دارند.

برای campaign تازهٔ C4h که با۴ pair از۶ متوقف شد، همان ابزار را با receipt
صریح اجرا کنید:

```bash
uv run python scripts/prepare_semantic_review.py prepare \
  --receipt experiments/core_resource_guidance_v1/model-live-receipt-v1.json \
  --output runtime/resource-review-FRESH
```

این بسته به **method فعال V2** وصل است.۲۴ نوبت ثبت‌شده،۱۶ رسیده،۱۰ پیشنهاد
تازه،۶ بدون پاسخ تازه شامل۴ stale و۸ اجرا‌نشده باقی می‌مانند.۲۲ attempt و
۲۱ send جدا هستند؛ توقف ورودی پیش از reservation، فراخوانی پرداخت‌شده نیست.
Usage اصلیِ ناقص/null حفظ می‌شود و fix اندازه‌گیری آینده آن را بازنویسی نمی‌کند.
برای C4g همان method تاریخی V1 و شمارش‌های زیر معتبرند.

از ریشهٔ repository اجرا کنید؛ مقصد باید یک پوشهٔ تازه و خصوصی باشد:

```bash
uv run python scripts/prepare_semantic_review.py prepare --output runtime/semantic-review-FRESH
```

`review-index.html` را در مرورگر باز کنید. متن Issue/مدل/منبع به‌صورت متن
escapeشده نمایش داده می‌شود؛ HTML یا script داخل منبع اجرا نمی‌شود. هر ردیف
به `context-<item_id>.json` و، برای پاسخ تازه، `pending-<item_id>.json` وصل است.
JSON کامل پیام مصرف‌شده، actual enriched request، هر attempt، نتیجهٔ native
retrieval قبل از version scope، handoff پس از scope، تمام سطح‌های خروجی،
و hash factهای فعال کاربر را حفظ می‌کند.

واحد review، **پیشنهاد تازه در همان revision** است. در receipt اصلی C4g:

| مورد | تعداد |
| --- | ---: |
| مسیر ثبت‌شده | ۱۲ |
| نوبت ثبت‌شده | ۲۴ |
| نوبت واقعاً اجراشده | ۲۳ |
| پیشنهاد تازه | ۱۷ |
| نوبت اجراشده بدون پاسخ تازه | ۶ |
| از همین ۶ مورد: مشاهدهٔ پیشنهاد قدیمی | ۲ |
| از همین ۶ مورد: بدون پیشنهاد | ۴ |
| نوبت آیندهٔ اجرا‌نشده | ۱ |

پیشنهاد revision قبلی در correction، پاسخ تازه حساب نمی‌شود. نوبت آیندهٔ
اجرانشده نیز پاسخ اشتباه مدل نیست؛ coverage ناقص است. original، edited و
released جدا نمایش داده می‌شوند. approval این آزمایش scripted بوده؛
پذیرش انسانی یا ذخیرهٔ پایدار UI از آن نتیجه نمی‌گیریم.

## داوری و امتیازدهی

از فایل pending یک کپی بسازید. `review_id` تازه و `reviewer_id` خودتان را
بگذارید؛ `reviewer_kind` را صادقانه `human` یا `assistant` ثبت کنید. پیش‌فرض
`unassigned` و `assistant` صرفاً template خالی است و scorer آن را به‌عنوان
review انجام‌شده نمی‌پذیرد. اعلام نوع داور، هویت یا انسانی‌بودن او را اثبات
نمی‌کند.

از [rubric فعلی](evaluation-rubric.md) و **شاهد واقعی همان نوبت** استفاده کنید:

- تمام سطح‌ها را بخوانید؛ فقط `user_draft` یا citation ID کافی نیست.
- تصمیم و سؤال را مستقل بسنجید؛ سؤال باید لازم، قابل پاسخ و تکرار نکردن
  اطلاعات فعال کاربر باشد. درخواست check در پاسخ یا summary هم سؤال محسوب می‌شود.
- ادعاها را در `declared_material_claim_count` بشمارید؛ برای هر مورد،
  `ReviewClaimBinding` با span دقیق خروجی و quote منبع یا hash fact فعال بدهید.
  offset بر حسب Unicode codepoint است، نه byte یا واحد UTF-16 مرورگر.
- `claim_inventory_complete` فقط پس از بررسی همهٔ ادعاها و سطح‌ها true شود.
  صفر ادعا همراه inventory ناقص، `unassessed` است؛ قبولی محسوب نمی‌شود.
- usefulness، نمرهٔ مستقل ۰ تا ۲ با دلیل است؛ خالی‌ماندن آن جای نمرهٔ انسانی را نمی‌گیرد.

نمونهٔ شکل claim را در
[تست‌های موجود semantic review](../tests/test_evaluation_semantic_review.py)
ببینید. این ابزار همان `SemanticReview` و `score_review` موجود را مصرف می‌کند؛
schema تازه‌ای برای معنای «supported» یا قرارداد core نمی‌سازد.

پس از تکمیل کپی‌ها، امتیازها را در فایل تازه ثبت کنید:

```bash
uv run python scripts/prepare_semantic_review.py score \
  --workbench runtime/semantic-review-FRESH/workbench.json \
  --reviews runtime/semantic-review-FRESH/reviewed-ONE.json \
  --output runtime/semantic-review-FRESH/scores-ONE.json
```

فایل‌های اصلی receipt، fixture، scenario، protocol، method و rubric با hash
bind شده‌اند. اگر هرکدام عوض شود یا handoff/sidecar به نوبت یا arm دیگری
اشاره کند، score رد می‌شود. فایل‌های موجود بازنویسی نمی‌شوند. review تکراری
یک داور حتی با ID تازه دوباره شمرده نمی‌شود؛ چند داور در panelهای جدا
می‌مانند. این نسخه پیشنهاد **مدل اصلی** را score می‌کند؛ edit فقط به‌صورت
جدا ثبت و نمایش داده می‌شود و به نمرهٔ مدل اضافه نمی‌شود.

## محدودیت برداشت نتیجه

هر سه case exposed، answer-informed و dev هستند؛ held-out test نیستند.
rubric هنوز draft تیم است. stratum و decision condition ثابتِ fixture برای
شواهد کنترل‌شده حفظ شده‌اند؛ **با شواهد native برابر نیستند**. برای مثال
`dev-case-b/version` در fixture قابل پاسخ است چون button 1.39 در bundle ثابت
حضور دارد؛ وقتی همان منبع در top5 واقعی نمی‌آید، صرف برچسب fixture دلیل
رد escalation نیست. معیار native از `protocol-v1.json` ثبت‌شدهٔ C4g جدا
نمایش داده می‌شود. برچسب‌ها را بعد از دیدن تصمیم مدل عوض نمی‌کنیم.

گزارش scorer تعداد نوبت‌ها، no-fresh، stale، unvisited و reviewهای ناقص را
نگه می‌دارد؛ فقط پاسخ‌های سالم را به مخرج تبدیل نمی‌کند. armهای ۱۴ و ۱۸
source، stratumهای مرجع، داورهای انسانی/assistant و اصل مدل جدا گزارش
می‌شوند. `quality_claim=false` و `authorizes_action=false` همیشه برقرارند.
داور هنوز باید entailment، applicability و usefulness را بررسی کند؛ hash
یا پاس‌شدن pytest کیفیت مدل و RAG نهایی را اثبات نمی‌کند.

اینجا فقط artifactهای همین dev خوانده می‌شوند. هیچ body/answer مربوط به
candidateهای test باز نشده، split نهایی freeze نشده و E1/E2/E4/E5 از ساختن
این workbench بسته نمی‌شوند. در حالت عادی halt هزینه و هر دو hold قبلی
بدون تغییر باقی می‌مانند.

## ادامهٔ C4h2 و C4h3

هر دو receipt جدید هم پشتیبانی می‌شوند. معیار native از protocol اولیهٔ C4g
خوانده و با hash همان method بررسی می‌شود؛ معیار fixture یا داوری پس از دیدن
جواب جای آن نمی‌نشیند. روش C4h2 همهٔ۲۴ نوبت شامل۱۶fresh،۱stale،۵empty و۲unvisited
را نگه می‌دارد. C4h3 شامل۱۶fresh،صفرstale،۴empty و۴unvisited است.

```bash
uv run python scripts/prepare_semantic_review.py prepare   --receipt experiments/core_source_capacity_v1/model-live-receipt-v1.json   --output runtime/capacity-review-FRESH
```

برای C4h2 مسیر receipt را به `experiments/core_repeat_repair_v1/model-live-receipt-v1.json`
تغییر دهید و مقصد تازه بدهید. در هر دو حالت usefulness و claim inventory خالی‌اند؛
این کار E2 را برای محمدحسن آماده می‌کند و جای داوری انسانی را نمی‌گیرد.
