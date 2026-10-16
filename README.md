# Streamlit Support Assistant

پروژهٔ نهایی بوت‌کمپ Agentic AI کوئرا: دستیار بررسی گزارش خطا و پیگیری پرونده، با شواهد قابل بررسی و تأیید انسانی پیش از اجرای اقدام.

**وضعیت فعلی، ۱۶ اکتبر:** core، correction، API/UI، tracker پایدار SQLite و runner متصل‌اند. PRهای #70 تا #76، تعداد ۳۱ fixture شامل ۱۶ dev و ۱۵ test ثبت کرده‌اند؛ manifest هنوز draft است. [تحویل C4m/E2z](docs/evaluation-readiness.fa.md) دو سؤال dev را به vocabulary اختیاری اضافه می‌کند و اتصال rubric تاریخی به ID و hash ثبت‌شده را کنترل می‌کند. [پذیرش R4b](experiments/evaluation_readiness_v1/native-acceptance-v1.json) روی کپی index واقعی، availability قبلی ۱/۵→۳/۵ را بازتولید کرد؛ حذف key-identity در آن اجرا از packing بایتی است، نه پرشدن capپنج. کیفیت نهایی Enum/RAG ثابت نشده؛ gold native، vocabulary/config و split نهایی، usefulness انسانی و test مستقل بازند. محتوای test در توسعه باز و برای tuning مصرف نشده است. halt و هر سه hold حفظ شده‌اند؛ C5 به مدرک provider نیاز دارد و scopeهای بسته تکرار نمی‌شوند. Actions به علت Billing اجرا نمی‌شود؛ انتشار با review و verification محلی مجازشده است. برای ادامه از [راهنمای اتصال](docs/integration.md)، [تصمیم‌های آماده‌سازی ارزیابی](docs/evaluation-readiness.fa.md) و [plan جاری](plan/plan.md) شروع کنید. گزارش‌های پایین تاریخچه و محدودیت همان زمان‌اند.

[C4h9/C4h9b: انتخاب شاهد مکمل و خوانایی Enum](docs/complementary-sources.fa.md): دو مقایسهٔ تازه، مجموع۴۸send روی همان سه dev و منابع ثابت. دستور عمومی انتخاب منابع مکمل هیچ بهبودی نداشت؛ جابه‌جایی ترتیب منابع فقط یک draft اولیهٔ منتشرنشده را با حفظ هر دو guide از۱۴۴۹۴ به۷۰۹۹کاراکتر رساند و correction دوباره طولانی شد. پوشش مشترک پاسخ‌های واقعاً منتشرشده در هر دو حالت۰/۲ بود؛ بهبود پایدار ثابت نشد. flag مکمل خاموش و توصیه‌نشده می‌ماند؛ index/exclusion/gold و قراردادها ثابت‌اند. ۴۸۹۶pytest و fixtureHTTP/SQLite۴۵۷/۴۵۷ محلی پاس؛ داوری انسانی و test نهایی بازند. نتیجهٔ منفی و تمام receiptها حفظ شده‌اند.

[C4h8: کیفیت Enum و دسترسی به شاهد](docs/enum-evidence-quality.fa.md): ۲۴ فراخوانی تازه با همان سه dev و fixture کنترل‌شده؛ با افزودن دو بخش کامل راهنمای رسمی، توضیح هویت Enum از ۰/۴ به ۳/۴ draft و الگوی کامل module از ۰/۴ به ۱/۴ رسید. در Enum فقط correctionها منتشر شدند؛ هر کدام از این دو نوع راهنما در ۱/۲ پاسخ منتشرشده دیده شد. sourceها answer-linked هستند و صرفاً در آزمایش مانده‌اند؛ index/exclusion/gold اصلی تغییر نکرده و fix محیط کاربر یا کیفیت RAG ثابت نشده است. متن هنوز طولانی است و usefulness انسانی باز است. ۴۶۱۱ تست و fixture HTTP/SQLite۴۵۷/۴۵۷ محلی پاس‌اند؛ [روش و رسیدها](experiments/core_enum_evidence_v1/README.md).

در مرحلهٔ قبلی، [C4h7: JSON و خوانایی](docs/json-readability.fa.md) تنظیم‌های اختیاری با پیش‌فرض خاموش اضافه کرد: ۲۶ فراخوانی تازه روی همان سه dev و index ثابت؛ هر دو حالت JSON روشن/خاموش ۱۲/۱۲ خروجی معتبر داشتند، پس برتری نسبی JSON mode ثابت نشد. سؤال callback در بازپخش همان plan از ۷۸۷۰ به ۱۲۲۰ کاراکتر رسید؛ مدارک reviewer کامل مانده ولی فهرست منبع جای توضیح API را نمی‌گیرد. پاسخ فنی button حفظ شد و Enum در آن اجرا هنوز generic بود؛ [رسید و محدودیت‌ها](experiments/core_json_readability_v1/README.md).

دامنهٔ پیشنهادی ما **Session State، Widgets و callback/rerun** است؛ انتخاب نهایی دامنه و تقسیم کار با هماهنگی تیم انجام می‌شود.

بیس مشترک و چک‌های اختیاری callback از طریق PRهای قبلی روی `main` قرار دارند. در مقایسه تازه روی ۶ سناریوی ساختگی از میان ۹ جفت خروجی نهایی روش `fidelity_rules` پنج پاسخ قابل قبول داشت و روش کوتاه‌تر سه پاسخ. دقت پشتیبانی ادعاها از منبع برای هر دو روش ۶ از ۹ بود و مقایسه تکراری به سقف تعیین‌شده آزمایش رسید. روش تازه هنوز اختیاری و آزمایشی است و تنظیم پیش‌فرض تغییر نکرده. این نتیجه کیفیت روی داده واقعی یا RAG را ثابت نمی‌کند. توقف عمومی ledger و هزینه نامعلوم مدل دوم حفظ شده‌اند. جزئیات در [گزارش تازه مقایسه](docs/decision-quality-v7.md) و [راهنمای چک‌های اختیاری](docs/proposal-checks.md) است.

ادامهٔ core در ۹ اکتبر روی Issue واقعی `12782`، با شواهد ثابت و پیشنهادهای
تألیفی، دو تغییر محدود را آزمایش کرد: کنترل اختیاری نسخهٔ شواهد و اتصال پاسخ
صریح نسخه به سؤال canonical معلق. پذیرش پیشنهادهای منفی از ۶ به ۴ مورد از ۷
کاهش یافت، ولی یک مقایسهٔ تاریخی درست هم رد شد؛ چهار خطای معنایی همچنان باقی‌اند.
این نتیجه رفتار آفلاین کد است و کیفیت مدل/RAG یا test نهایی نیست. baseline روی
کد Git قبلی هم بازتولید شده است. [گزارش فارسی و راه بازبینی](docs/controlled-core-v8.fa.md)
ورودی‌ها، نتایج، محدودیت‌ها و نیاز دقیق اتصال تیم را توضیح می‌دهد.

ارتقای بعدی مسیر اختیاری `GroundedPlan` را اضافه کرد: مدل فقط تصمیم و منبع را
انتخاب می‌کند و core نقل‌قول کامل، محدودهٔ نسخه و سؤال ثبت‌شده را می‌سازد.
هر هفت قصد مفید تألیفی حفظ شد، از جمله مقایسهٔ تاریخی؛ کنترل‌های منبع/وضعیت و
بازبینی کل پیشنهاد هم اضافه شدند. تشخیص حقیقت منبع و تضادِ اعلام‌نشده همچنان
حل نشده و کیفیت انتخاب مدل زنده اندازه‌گیری نشده است. نتیجهٔ بررسی تازهٔ کاربر
نیز شواهد استنتاج‌شدهٔ قبلی را بازنشسته می‌کند. [گزارش فارسی ارتقا](docs/controlled-core-v9.fa.md)
و [قرارداد و مثال اتصال](docs/extractive-core.md) جزئیات را ثبت می‌کنند.

تحویل تازهٔ **C4a** انتخاب واقعی مدل را روی همان خانوادهٔ exposed و شواهد
ثابت ثبت کرد: baseline سه درخواست، دو سؤال callback، یک خطا و سه حالت
اجرا‌نشده داشت؛ یک follow-up جدا با همان ورودی سؤال نسخه را کامل داد.
چهار درخواست با $0.002845260 تخمینی، اصل receiptها و review کامل در
[بستهٔ C4a](experiments/controlled_model_baseline/README.md) هستند. مشکل import
مستقیم core هم رفع شد؛ ۲۷۹۷ تست و HTTP/SQLite ۴۵۷/۴۵۷ پاس‌اند. این آزمایش
کیفیت RAG یا test نهایی نیست و baseline شش‌حالته هنوز کامل نشده است.
[راهنمای تیم و agentهای کاری](docs/team-handoff-c4.fa.md) و plan مبنای ادامه‌اند.

pilot جدید **C2/P2**، اطلاعات صریح کاربر و correction را از HTTP به core وصل
می‌کند؛ پاسخ کوتاه نسخه به سؤال تأییدشده متصل و retry همان event بدون run تازه
شناخته می‌شود. case هفت‌نوبتی با fixture و storage حافظه‌ای قابل بازپخش است.
کنترل‌های UI متصل‌اند و ماژول SQLite با read سازگار روی main است؛ مسیر opt-in
HTTP و outcome پایدار در [C2d](docs/persistent-http.fa.md) با #30 منتشر شد.
client/UI در [U3a](docs/offline-ui-index-pilot.fa.md) به approval پایدار وصل است؛
دستور opt-in و محدودیت کنسول محلی در همان راهنما آمده.
[نتیجه و ورودی/خروجی لازم برای هر نفر](docs/user-intake-pilot.fa.md) را ببینید.

خروجی **C3** حالا کل case، آخرین evidence مصرف‌شده، analysis و catalog تصمیم
را برای review نگه می‌دارد. مسیر gateway تا همین review با HTTP شبیه‌سازی‌شده
و ledger موقت هم قابل بازپخش است؛ اجرا و هزینهٔ واقعی مدل ندارد.
[نتیجهٔ C3](docs/review-handoff-pilot.fa.md) و
[بازبینی آمادگی اتصال](docs/core-readiness-audit.fa.md) محدودیت‌ها و شواهد را ثبت می‌کنند.

سهم مستقل **C2a**، [CoreTurnService](docs/core-turn-service.fa.md) است: اتصال
receipt/state به core، حفظ مسئله و پیام‌های کاربر در reply کوتاه، توقف روی
تغییر state و بازیابی دقیق ACK پیشنهاد. pilot چهار‌نوبتی با SQLite واقعی و
portهای آفلاین قابل اجراست. C2d همین سرویس را به HTTP/SQLite و outcome اتمیک
وصل کرده و gate staging را اضافه کرده؛ demo پیش‌فرض حافظه‌ای است و UI با config
جدید به SQLite و index محلی وصل می‌شود.
[وضعیت C5](docs/live-reconciliation-2026-10-11.fa.md)
ابهام مدل/usage/billing لازم برای ادامهٔ live را ثبت می‌کند؛ توقف برقرار است.

## شروع سریع

نیازمندی‌ها: Git، Python 3.13 و [uv](https://docs.astral.sh/uv/). دستورها را از ریشهٔ همین ریپو اجرا کنید:

```bash
uv sync --locked --group dev
uv run agent-app demo --scenario ask
uv run agent-app demo --scenario answer
uv run agent-app demo --scenario refine
uv run agent-app gateway-demo --scenario repair
uv run agent-app turn-demo
uv run python -m agent_app.reasoning.controlled_experiments
uv run python -m agent_app.reasoning.grounding_experiments
uv run python experiments/user_intake/replay.py
uv run python experiments/review_handoff/replay.py
uv run python experiments/gateway_handoff/replay.py
```

سناریوهای دیگر: `escalate` برای ارجاع و `error` برای خرابی بازیابی. خروجی JSON شامل نتیجه و ردگیری اجراست. سناریوی `error` عمداً با کد خروج ۱ تمام می‌شود. برای این دمو کلید API لازم نیست.

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

برای اجرای رابط کاربری و اتصال آن به بک‌اند، باید هر دو را در ترمینال‌های جداگانه اجرا کنید:

ترمینال اول (بک‌اند FastAPI):
```bash
uv run uvicorn agent_app.api:app --host 127.0.0.1 --port 8000
```

ترمینال دوم (فرانت‌اند Streamlit):
```bash
uv run streamlit run app.py --server.address 127.0.0.1
```

دستور آخر رابط اولیهٔ پروژه را باز می‌کند و به سرور FastAPI که در ترمینال اول اجرا کرده‌اید متصل می‌شود. اگر بک‌اند روی آدرس دیگری است، متغیر `AGENT_API_URL` را تنظیم کنید. سناریوی ساختگی هر پیام از نوار کناری انتخاب می‌شود و هر پیش‌نویس تا تأیید نگه‌دارنده به کاربر نشان داده نمی‌شود. وضعیت پرونده‌ها فعلاً فقط در حافظهٔ همین فرایند است؛ با راه‌اندازی دوبارهٔ بک‌اند (از جمله `--reload`) پاک می‌شود. برای پروندهٔ تازه دکمهٔ «New case» را بزنید.

[backend SQLite برای HTTP](docs/persistent-http.fa.md) با #30 روی main منتشر شد؛
pilot آفلاین و restart/retry آن ۴۵۷/۴۵۷ check پاس دارد. client اکنون health را
بررسی و review_id، hash دقیق، credential خصوصی و payload ثابت retry را می‌فرستد.
دستور بالا همچنان demo حافظه‌ای است؛ برای SQLite و Chroma محلی از
[دستور اجرای pilot پایدار UI/index](docs/offline-ui-index-pilot.fa.md) استفاده کنید.
این pilot ۱۴ source مجاز و ۳۰ chunk دارد؛ embedding محلی lexical و reasoning
پیش‌فرض scripted است. برای اتصال همان GroundedPlan/gateway با provider جعلی،
از [دستور C2f](docs/grounded-persistent-pilot.fa.md) و `AGENT_PILOT_REASONING=grounded_fake_gateway`
استفاده کنید؛ UI mode واقعی backend را نشان می‌دهد. launcher آفلاین هزینهٔ API
ندارد. corpus/split نهایی و کیفیت مدل/RAG هنوز باقی‌اند.

پایپلاین GitHub Actions برای تست و بررسی سبک کد بدون مصرف API تنظیم شده، اما فعلاً به علت Billing شروع نمی‌شود. تا رفع آن، review و تست‌های محلی روی source ثبت‌شده مبنای انتشارند؛ نتیجهٔ محلی را CI سبز گزارش نکنید. پیش از ادامه کار، branch خودتان را از `origin/main` به‌روز کنید.

## تقسیم کار چهار نفره

| بخش | مسئولیت | مسیر |
| --- | --- | --- |
| هستهٔ ایجنت | قراردادها، تصمیم پاسخ/پرسش/ارجاع، جست‌وجوی تکمیلی محدود و هزینهٔ مدل | `src/agent_app/contracts.py`، `orchestration/`، `reasoning/` و `llm/` |
| داده و RAG | دریافت و پاک‌سازی داده، chunking، بازیابی و ارجاع | پیشنهاد: `data/`، `scripts/`، `src/agent_app/ingestion/` و `retrieval/` |
| رهگیر و ابزارها | ذخیرهٔ پایدار، تأیید/ویرایش/رد و اجرای بدون تکرار | پیشنهاد: `src/agent_app/tracker/` و `tools/` |
| UI و ارزیابی | اتصال رابط، پرونده‌های dev/test و گزارش نتایج | `app.py`؛ پیشنهاد: `src/agent_app/evaluation/` |

مسیرهای پیشنهادی پیش از شروع هر بخش هماهنگ می‌شوند. هر بخش روی branch خودش جلو می‌رود؛ فایل‌های مشترک و تغییر قراردادها با review صاحب بخش جمع می‌شوند. روش کار در [راهنمای توسعه](docs/development.md) آمده است.

## مرز نسخهٔ فعلی

- قراردادهای معتبرشده و جریان تصمیم‌گیری محدود، با mock قابل اجرا هستند.
- سقف هر اجرا: ۲ تلاش مدل، ۲ دور بازیابی، ۲ کوئری در هر دور و ۸ مرحله؛ تلاش ناموفق هم از همین سقف مصرف می‌شود.
- کلاینت متیس و ledger هزینه با SQLite ساخته شده‌اند؛ رابط فعلی approve/reject/edit محلی دارد. [tracker SQLite](docs/sqlite-tracker.md) با approval اتمیک روی main است؛ factory پایدار HTTP در C2d نیز restart/retry را پاس کرده. demo پیش‌فرض حافظه‌ای است؛ UI opt-in و index واقعی کوچک در U3a/P4a وصل‌اند. corpus/model و ارزیابی کیفیت نهایی بازند.
- خروجی نامعتبر با کد و نام فیلد مشخص گزارش می‌شود و یک تلاش باقی‌مانده با بازخورد محدود می‌تواند آن را اصلاح کند؛ اعتبارسنجی شاهد و مجوزها پابرجاست.
- اطلاعات صریح و اصلاح‌شدهٔ کاربر به یک وضعیت پیشنهادی تبدیل می‌شوند؛ تاریخچه حفظ و شواهد قدیمی بی‌اعتبار می‌شوند. ذخیره و اعمال این وضعیت با رهگیر است.
- هسته فقط پیشنهاد می‌سازد؛ اجرای اقدام با tracker است. مسیر HTTP/SQLite در C2d action/review محلی را پس از restart بدون ثبت تکراری نگه می‌دارد؛ UI در U3a با همان envelope/hash و retry وصل است. [قرارداد recovery و retry](docs/persistent-core-handoff.md) و receiptها مرز نتیجه را مشخص می‌کنند.
- پاسخ بدون citation رد می‌شود؛ citation معتبر، پشتیبانی معنایی ادعا یا جلوگیری کلی از حدس‌زدن محیط/حل مسئله را تضمین نمی‌کند. بازبینی کل پیشنهاد همچنان لازم است.

## بودجه و ارزیابی

سقف **۵ دلار برای کل تیم و کل پروژه** است؛ embedding، توسعه، ارزیابی و امتیازی هم از همین بودجه‌اند. کلاینت پیش از ارسال، مبلغی را در ledger مشترک رزرو می‌کند و هزینهٔ نامعلوم را پس نمی‌دهد. هزینهٔ محاسبه‌شده از مصرف توکن و قیمت عمومی باید با صورتحساب متیس تطبیق داده شود. اجرای زنده پیش‌فرض خاموش است؛ تست‌های منطقی با mock اجرا می‌شوند. جزئیات و محدودیت‌ها در [راهنمای مدل و بودجه](docs/model-gateway.md) آمده‌اند.

پیش از ساخت index، ۱۵ پروندهٔ dev و ۱۵ پروندهٔ test را در سطح پرونده و خانوادهٔ گزارش‌ها جدا می‌کنیم. خود پرونده‌ها و پاسخ‌های بعدی‌شان نباید وارد منابع بازیابی شوند. حداقل ۱۰ سناریو چندنوبتی لازم است، که ۵ موردشان در test باشند.

مسیر امتیازی پیشنهادی پس از تکمیل اصل پروژه **Adversarial Testing** است؛ دامنه و سهم امتیاز با منتور هماهنگ می‌شود.

## مستندات

- [معماری و مرز اتصال بخش‌ها](docs/architecture.md)
- [مثال اجرایی برای اتصال ماژول خودتان](docs/integration.md)
- [توسعه، branch و commit](docs/development.md)
- [کلاینت متیس و دفتر مشترک هزینه](docs/model-gateway.md)
- [اطلاعات کاربر و اصلاح وضعیت در چند نوبت](docs/user-turns.md)
- [pilot اتصال HTTP، correction و سؤال تأییدشده؛ نتیجه و handoff](docs/user-intake-pilot.fa.md)
- [خروجی کامل core، آخرین evidence و review؛ نتیجه و قرارداد C3](docs/review-handoff-pilot.fa.md)
- [بازبینی آمادگی core و اتصال gateway تا review با HTTP شبیه‌سازی‌شده](docs/core-readiness-audit.fa.md)
- [پیشرفت واقعی هسته و کارهای بعدی](docs/core-progress.md)
- [مقایسه روش‌های تصمیم‌گیری و محدودیت نتایج](docs/decision-quality.md)
- [مقایسه منابع و اطلاعات کاربر با نتایج بازبینی](docs/decision-quality-v3.md)
- [نتیجه چک‌های callback و سؤال‌های مجاز](docs/decision-quality-v4.md)
- [مقایسه قالب محدودتر و کیفیت معنایی پاسخ‌ها](docs/decision-quality-v5.md)
- [بررسی آفلاین کل پاسخ و مرز چک‌های کد](docs/decision-quality-v6.md)
- [مقایسه تازه دقت گزارش و پشتیبانی ادعاها از منبع](docs/decision-quality-v7.md)
- [آزمایش کنترل‌شدهٔ Issue واقعی، ورودی نسخه و مرز شواهد](docs/controlled-core-v8.fa.md)
- [ارتقای پاسخ مستند و بازبینی کل پیشنهاد با مقایسهٔ کنترل‌شده](docs/controlled-core-v9.fa.md)
- [قرارداد اختیاری پاسخ مستند و مثال اجرایی اتصال](docs/extractive-core.md)
- [چک‌های اختیاری callback و سؤال‌های مجاز](docs/proposal-checks.md)
- [راهنمای مشترک ایجنت‌های کدنویسی](AGENTS.md) و [ورودی Claude Code](CLAUDE.md)
- [plan و checklist کار تیم](plan/plan.md) و [نسخهٔ داخل ریپو از صورت‌مسئله](QBC13_AgenticAI_FinalProject.md)

پلن و صورت‌مسئلهٔ داخل ریپو با پیشنهادهای فنی تکمیل شده‌اند. الزام نهایی را از [سند اصلی پروژه](https://docs.google.com/document/d/1N13vE1IoqTDlEFndNOULGgXYIU2SER6pVkwEG8iPLYM/edit) می‌گیریم؛ این branch انتخاب‌های فنی کل تیم را نهایی نمی‌کند.
