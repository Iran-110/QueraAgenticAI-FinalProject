# اتصال runner، مدل و review — ۱۳ اکتبر

این تحویل سهم مستقل ساسان در E3/U3 و helper پیشنهادی E2 است. قراردادهای
اشتراکی، tracker و adapter حسن عوض نشده‌اند؛ تک agent مبناست. default رابط
همچنان آفلاین است. case واقعیِ ثبت‌شده هنوز یک dev و صفر test است.

## اجرای شاخهٔ درست گفتگو

```bash
uv run python -m agent_app.evaluation.runner FIXTURE.json --conditional-routes --output /tmp/offline/routes-new.json
uv run pytest tests/test_eval_conditional_routes.py
```

fixture باید `evaluation.coverage.turn_ids` و `routes` داشته باشد. هر route
دارای `from_turn`، `to_turn` (یا null برای پایان) و `guard.decision` است؛ برای
ask، `guard.question_target` به یک gap کاربر با question و necessity ثبت‌شده
در gold همان turn اشاره می‌کند. نمونهٔ کامل در
[تست شاخه‌ها](../tests/test_eval_conditional_routes.py) است. همهٔ تصمیم‌های
قابل قبول باید route داشته باشند؛ graph به جلو، بدون دور و با nodeهای قابل
دسترسی است. سقف ثبت ۶۴ node و ۲۵۶ route است؛ محدودیت هر invocation core همان
۲ attempt مدل، ۲ دور retrieval، ۲ query در هر دور و ۸ step می‌ماند.

runner فقط proposal فعلی، یا نسخهٔ واقعاً ویرایش‌شدهٔ آن، را می‌خواند. ادامهٔ
ask به سؤال دقیقِ تأییدشده و released در همان case/revision نیاز دارد. پاسخ
نسخه از قرارداد canonical موجود عبور می‌کند؛ پاسخ gapهای دیگر باید fact یا
unknown صریح همان هدف را ثبت کند. gap مستندات سؤال کاربر نمی‌شود. wording
ثبت‌نشده، حتی اگر سؤال خوبی باشد، `FixtureBranchUnavailable` و پوشش ناقص
می‌دهد؛ runner جواب ساختگی تولید نمی‌کند. مسیر terminalِ سؤال pending می‌تواند
پایان برش ثبت‌شده باشد، اما یک گفتگوی کامل یا پوشش همهٔ شاخه‌ها نیست.

receipt مسیر انتخاب‌شده، nodeهای اجراشده/اجرانشده، پایان مسیر و تعداد واقعی
مسیرهای چندنوبتی را جدا نگه می‌دارد. یک escalation زودهنگام برای حداقلِ ۱۰
گفتگوی چندنوبتی حساب نمی‌شود. حالت live همراه final-manifest این کنترل را
اجباری می‌کند؛ فرمان‌های legacy خطی تغییر نکرده‌اند. gold، future turn و
پاسخ‌های شاخه‌های دیگر به factory/model داده نمی‌شوند.

## factory مشترک RAG و GroundedPlan

`agent_app.evaluation.live:factory` اکنون index موجود را با snapshot، hash
manifest و محتوای واقعی Chroma بررسی می‌کند؛ سپس برای هر case، port تازه و
cleanup می‌سازد. catalog نسخه/gap منبع از helper production مشترک می‌آید.
vocabulary اختیاری gapهای کاربر فقط از پیکربندی caller معتبر می‌آید، فقط برای
unknown فعلی فعال می‌شود و تشخیص خودکار gap از متن آزاد نیست. default فقط
catalog عمومی نسخه و منبع دارد؛ برای baselineِ callback باید vocabulary
قبل از اجرا جدا ثبت و تزریق شود، نه از gold fixture خوانده شود.

محیط private باید صریح نصب شود؛ این factory `.env` را خودکار نمی‌خواند:

| تنظیم | معنای واقعی |
| --- | --- |
| `AGENT_EVAL_INDEX` | مسیر index موجودِ docs pilot؛ build جدید در startup نداریم |
| `AGENT_EVAL_SNAPSHOT` / `AGENT_EVAL_MANIFEST_SHA256` | pin همان build؛ hash از byteهای manifest |
| `METIS_LIVE_ENABLED=true` / `METIS_API_KEY` | فعال‌سازی و credential private؛ داخل command/receipt ننویسید |
| `AGENT_EVAL_PHASE` | development یا evaluation؛ default development |
| `AGENT_EVAL_TOP_K` | ۱ تا ۵؛ default ۱، انتخاب کیفیتِ نهایی نیست |
| `METIS_MODEL` | default gpt-4o-mini؛ pricing و serving model باید معتبر باشند |
| `METIS_INPUT_TOKEN_RESERVE` / `METIS_MAX_OUTPUT_TOKENS` / `METIS_MAX_REQUEST_USD` | default 32768 / 1024 / 0.02؛ سقف واقعی ledger مقدم است |

فرمان زیر فقط بعد از حل C5، ثبت protocol ضروری و بازبینی سقف موجود اجرا شود:

```bash
uv run python -m agent_app.evaluation.runner DEV_FIXTURE.json --mode live --adapters agent_app.evaluation.live:factory --conditional-routes --output /tmp/live/dev-new.json
```

factory معمولی فقط `runtime/budget.sqlite3` موجود را می‌پذیرد؛ halt، pending
یا uncertain حتی با hold صفر، سقف بیش از ۵ دلار و بودجهٔ ناکافی را قبل از
key/provider رد می‌کند. continuation قبلی bypass عمومی نیست. ledger جدید،
reset یا unhalt در این تحویل نداریم. C5 همچنان باز است؛ API واقعیِ تازه در
این مرحله استفاده نشده است.

مشاهدهٔ serving ID، request/context، usage و هزینه با همان درخواست ledger
تطبیق داده می‌شود. شناسهٔ ناشناخته، payload، header، خطای خام و credential
export نمی‌شود. هزینهٔ embedding/retrieval/setup و billing واقعی provider از
این observer به دست نمی‌آید. تست اتصال factory واقعی به runner شامل پاسخ
plain/gzip، model mismatch و hold نامعلوم است؛ HTTP همهٔ این تست‌ها mock است.

## اتصال به HTTP پایدار و UI موجود

`persistent_api.create_app(case_adapters=...)` case ثبت‌شده و detached را بعد
از ingress می‌دهد. با callback قبلی `adapters` هم‌زمان فعال نمی‌شود؛ replay
همان event پیش از factory متوقف می‌شود. مدل case را از پیام/scenario انتخاب
نمی‌کند. launcher اختیاریِ همان endpointهای UI:

```bash
uv run uvicorn agent_app.live_backend:app_factory --factory --host 127.0.0.1 --port 8765
```

علاوه بر تنظیم‌های بالا، `AGENT_TRACKER_DB` باید فایل SQLite مخصوص پرونده‌ها
باشد و `AGENT_REVIEWER_TOKEN` credential private معتبر؛ ID پیش‌فرض reviewer
`local-maintainer` است. tracker نمی‌تواند به ledger، داخل index، یا alias
فایل‌های index اشاره کند. startup در halt پیش از ایجاد tracker رد می‌شود.
UI با `AGENT_API_URL=http://127.0.0.1:8765` و credential reviewer همین قرارداد
قبلی را دارد. مسیر آفلاین [U3a](offline-ui-index-pilot.fa.md) برای review در
حالت halt در دسترس است؛ این launcher باز بودن محصول live را ثابت نمی‌کند.

```bash
uv run pytest tests/test_persistent_live_factory.py tests/test_evaluation_live.py
```

تست‌ها با Chroma و SQLite واقعیِ موقت، provider اجباری mock و ledger موقت
هستند: دو case، correction، approval قدیمی 409، یک action، retry بدون SDK،
ساخت دوبارهٔ app، cleanup و رد alias. اینجا app در همان interpreter دوباره
ساخته شده؛ restart با process تازه در پذیرش HTTP/SQLite قدیمی بررسی می‌شود،
ولی restart مدل واقعی یا smoke واقعی مرورگرِ این launcher اثبات نشده است.

## امتیازدهی از review مستقل

`evaluation.semantic_review.score_review(handoff, sidecar, scope=...)` به
handoff دقیق، run/config/rubric/hash و stratum ثبت‌شده bind می‌شود. sidecar
reviewer span ادعا، quote منبع یا fact فعال و judgment را می‌دهد. helper
درستی span و reference را چک می‌کند؛ entailment یا فهرست همهٔ ادعاها را مدل
نمی‌سازد. هر ادعای unsupported بخش source support را صفر می‌کند. review
ناقص/insufficient امتیاز ندارد؛ بررسی کاملِ بدون ادعای مادی N/A است.

ضرورت سؤال، قابل پاسخ بودن، تکرار نکردن اطلاعات معلوم و usefulness صفر تا
دو judgment مستقل‌اند. `aggregate_reviews` denominatorها، strata، تعداد
case/proposal، human/assistant اعلام‌شده و model/maintainer edit را جدا نگه
می‌دارد. edit به original متفاوت با همان case/input/evidence نیاز دارد؛
اصلاح انسانی نمرهٔ مدل اصلی را بالا نمی‌برد. rubricهای متفاوت گروه‌های جدا
دارند و تکرار در همان rubric رد می‌شود. declaration انسان احراز هویت نیست؛
خروجی helper مجوز action نمی‌دهد و `quality_claim=false` می‌ماند.

```bash
uv run pytest tests/test_evaluation_semantic_review.py
```

محمدحسن باید schema/rubric را review و adopt کند و annotation مستقل انسانی
را برای baseline آماده کند. این helper E2 را نمی‌بندد؛ ۳۰ case، split/exposure
review، corpus نهایی، baseline dev و test بدون tuning همچنان لازم‌اند.
