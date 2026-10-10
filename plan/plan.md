# plan و checklist تیم — Streamlit Support Assistant

به‌روزرسانی: ۲۰۲۶-۱۰-۱۰. این نسخه ادامهٔ plan محمدحسن روی `main` در commit `2ead870` است؛ [نسخهٔ قبلی](archive/plan-before-task-checklist.md) حفظ شده. این فایل برای تقسیم کار و شرط پایان taskهاست؛ روزهای sprint قبلی را تاریخ تحویل حساب نمی‌کنیم. الزام‌ها از صورت اصلی پروژه می‌آیند، نه از ابزارها و frameworkهای پیشنهادی plan.

## وضعیت فعلی

| بخش | چیزی که داریم | چیزی که هنوز اثبات نشده |
| --- | --- | --- |
| core — ساسان | قراردادها، correction و GroundedPlan؛ ورودی C2/P2 و خروجی کامل C3 با fixture، و مسیر gateway تا review با HTTP شبیه‌سازی‌شده | کنترل‌های واقعی UI، tracker پایدار، RAG و کیفیت تصمیم مدل روی کیس‌های ندیده |
| داده — آماده‌سازی اولیه ساسان؛ ادامه با حسن | ZIP اولیه: ۲۴۰ Issue، ۱۱۷۸ comment، ۵۶ متن Markdown و ۱۱۷۲ API record؛ GitHub snapshot ششم اکتبر | corpus تأییدشده، split نهایی، index و retrieval واقعی؛ ZIP هنوز corpus نیست |
| UI/API — محمدحسن | Streamlit/FastAPI با FakeRetriever/FakeReasoner؛ adapter جدید API، fact/correction/check و reply binding را می‌پذیرد | کنترل structured input در UI، نمایش review کامل، اتصال retriever/model واقعی |
| tracker/tools — محمد بهنام | prototype حافظه‌ای DummyTracker در UI؛ بخش هزینهٔ SQLite مربوط به gateway است | ذخیرهٔ پایدار پرونده، dedup رخداد/اقدام، approval اتمیک، ادامه پس از restart |
| evaluation — محمدحسن | تست‌های منطقی آفلاین و آزمایش‌های توسعهٔ core قابل بازپخش‌اند | ۱۵ dev و ۱۵ test مستقل، معیارهای freezeشده و نتیجهٔ سیستم نهایی |

تغییرات جدید core از طریق [PR #7](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/7) با merge commit `85b6027` به `main` رسیدند. [گزارش V8](../docs/controlled-core-v8.fa.md)، [گزارش V9](../docs/controlled-core-v9.fa.md) و [قرارداد GroundedPlan](../docs/extractive-core.md) شواهد این milestone هستند. ۱۴۱۴ تست آفلاین در milestone محلی و ۱۴۲۸ تست همراه API/UI در CI ترکیب PR با main پاس شدند؛ نتیجهٔ RAG واقعی یا test نهایی نیست. GroundedPlan اختیاری است و پیش‌فرض production تغییر نکرده.

## قدم مشترک بعدی: یک case چندمرحله‌ای از dev

### تحویل مورد انتظار امروز — ۲۰۲۶-۱۰-۱۰

این‌ها درخواست هماهنگ‌کننده برای یک برش کوچک از pilot هستند؛ به معنی تأیید
زمان‌بندی توسط اعضا یا بسته‌شدن taskهای اصلی نیستند. اگر خروجی امروز نمی‌رسد،
همان روز blocker و قسمت قابل واگذاری اعلام شود تا تقسیم کنیم یا ساسان آن قسمت
را بردارد. تحویل هر نفر یک branch/PR و دستور اجرای نمونه یا تست مربوط است.

| نفر | خروجی قابل تحویل امروز | شاهد حداقلی |
| --- | --- | --- |
| حسن — P4/R3 | adapter `search(RetrievalRequest)` برای همین case با EvidenceBundle و metadata کامل؛ فعلاً fixture کافی است | snapshot/ID/URL/span/commit/نسخهٔ منابع؛ آخرین bundle پس از refinement |
| محمد بهنام — P3/T1–T3 | برش state/revision و pending approval برای همین case، با محل persistence مشخص | correction مجوز قبلی را باطل کند؛ retry event/action تکراری نسازد؛ هر کنترل هنوز ناقص، صریح ثبت شود |
| محمدحسن — P1/U2/E2 | ورودی fact/correction و نمایش کامل review به API وصل شود؛ همین fixture شروع pilot باشد | یک اجرای پیام/جواب سؤال/اصلاح/approve یا reject؛ برای split و caseهای ارزیابی، وضعیت واقعی و فایل manifest اولیه گزارش شود |

تکمیل index نهایی، همهٔ ۳۰ case یا evaluation نهایی، شرط این تحویل کوچک نیست.
سهم core و fixture با [PR #11](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/11)
به `main` رسید (`edea31c`) و [CI انتشار](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38045540320)
پاس شد. قبل از اتصال، تغییرات محلی را حفظ کنید، `git fetch origin` بزنید و
branch کاری خودتان را از `origin/main` به‌روز کنید. همین نسخه مبنای pilot تیم است.

fixture پایهٔ این تحویل، [case چهار‌نوبتی C3](../experiments/review_handoff/case-current-state-latest-evidence.json)
است؛ [فرمان replay و محدودیت‌ها](../experiments/review_handoff/README.md) و
[قرارداد ورودی/خروجی اتصال](../docs/integration.md#complete-proposal-handoff-c3)
کنار آن‌اند. label و oracle فقط برای بررسی‌اند؛ وارد ورودی مدل یا index نشوند.

- [x] **P1 — محمدحسن:** یک case از dev معرفی کند؛ ورودی شروع، follow-upها، اصلاح اطلاعات و تصمیم‌های قابل قبول را قبل از اجرا در fixture ثبت کند. اگر ادامهٔ گفتگو ساخته شده، آن را از گفتگوی واقعی جدا علامت بزند. case `dev-pilot-12782` (خانوادهٔ #12782/#12629، فقط dev) در [`data/evaluation/dev/pilot-12782.json`](../data/evaluation/dev/pilot-12782.json) با commit `3e0a86a` پیش از اولین اجرا ثبت شد ([PR #14](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/14))؛ follow-upها developer-authored علامت خورده‌اند و شواهد همان excerptهای رسمی C3 با SHA ثبت‌شده‌اند. runner `uv run python -m agent_app.evaluation.pilot data/evaluation/dev/pilot-12782.json` همان API رابط را آفلاین اجرا می‌کند: پیام، approve سؤال نسخه، پاسخ bind‌شدهٔ `1.50.0`، correction به `1.49.1` که proposal قبلی را stale می‌کند (approve قدیمی 409)، edit و approve نسخهٔ ویرایش‌شده، withdrawal و reject بدون ارسال، و replay همان event. [receipt](../data/evaluation/receipts/pilot-12782-v1.json): ۴۸ از ۴۸ check پاس. agent اسکریپتی است و storage حافظه‌ای؛ این receipt کیفیت تصمیم، RAG یا tracker پایدار را نشان نمی‌دهد.
- [x] **P2 — ساسان؛ مسیر آفلاین core/API:** اطلاعات صریح HTTP به UserTurn معتبر وصل شد؛ correction/withdrawal/تغییر محیط، factهای قدیمی و inference/ref را کنار می‌گذارند. reply فقط به سؤال canonical تأییدشده و همان case/revision/proposal متصل است. [fixture هفت‌نوبتی و receipt](../docs/user-intake-pilot.fa.md)، replay/old approval و baseline چهار regression قابل بررسی‌اند. این تیک adapter با storage حافظه‌ای را پوشش می‌دهد؛ UI واقعی و transaction پایدار با U2 و T2/T3 تکمیل می‌شوند. متن آزاد به‌تنهایی fact تأییدشده نیست.
- [ ] **P3 — محمد بهنام:** همان پرونده و proposal را با revision معتبر نگه دارد؛ approval قبلی بعد از تغییر پرونده قابل اجرا نباشد و اقدام جدید پس از approval فقط یک بار ثبت شود.
- [ ] **P4 — حسن:** برای همان case ابتدا EvidenceBundle ثابت بدهد؛ بعد از آماده شدن corpus مجاز، retriever واقعی را با همان قرارداد وصل کند.

**شرط پایان pilot آفلاین:** ورودی، سؤال تأییدشده، پاسخ کاربر، correction، revisionها، evidence فعال/کنارگذاشته‌شده و proposal در trace قابل بازبینی باشند. تا tracker پایدار آماده نشده، نتیجه فقط «pilot با fixture و storage آزمایشی» است.

**شرط پایان اتصال واقعی:** همان مسیر با retrieval واقعی و tracker پایدار اجرا شود؛ reject و edit، approval قدیمی، retry یک event/action و restart بررسی شوند؛ نتیجهٔ ابزار در state و تصمیم بعدی دیده شود. اجرای مدل واقعی فقط پس از حل توقف ledger و با سقف هزینهٔ ثبت‌شده مجاز است. آماده بودن pilot آفلاین به معنی رسیدن به این مرحله نیست.

## checklist هر نفر

راهنمای نقش‌ها: [حسن](member_1_todo.md)، [ساسان](member_2_todo.md)، [محمد بهنام](member_3_todo.md)، [محمدحسن](member_4_todo.md). وضعیت taskها فقط در همین checklist ثبت شود؛ فایل‌های نقش، راهنمای ارجاع به آن‌اند.

### حسن — داده و RAG

- [ ] **R1 — بازبینی seed و provenance.** ZIP `streamlit-data-for-dev-test.zip` را از ساسان بگیرد؛ تعدادها، روش انتخاب، URL/تاریخ، commit و نسخهٔ اسناد را ثبت کند. دامنهٔ اولیه Session State، widgets، callback/rerun است؛ همهٔ Streamlit را نمایندگی نمی‌کند. body فعلی Issue ممکن است بعداً ویرایش شده باشد.
- [ ] **R2 — کنارگذاری خانواده‌های ارزیابی، قبل از index نهایی.** فهرست dev/test از E1 را بگیرد؛ خود Issue، commentها، outcomeها، duplicateها و docs حاوی جواب مستقیم همان case را بررسی کند. خروجی: corpus allowlist، exclusion manifest و گزارش بررسی linkage/duplicate؛ candidate مرتبط به معنی duplicate قطعی نیست.
- [ ] **R3 — adapter بازیابی.** `search(RetrievalRequest)` یک EvidenceBundle با همان snapshot و سقف top_k برگرداند؛ chunk/source ID پایدار، URL، source_span، source_commit و applicable_versions قابل بررسی باشند. metadata نامعلوم نامعلوم بماند. بعد از refinement فقط آخرین bundle مصرف می‌شود؛ منبع قبلیِ لازم باید دوباره در آن برگردد.
- [ ] **R4 — آزمون بازیابی روی dev.** سند کامل/ناقص، نسخهٔ نامعلوم/متفاوت، conflict و خطای retrieval را بررسی کند؛ relevance و پوشش منابع را جدا از کیفیت متن مدل ثبت کند. خروجی: تست adapter و receipt بازیابی با snapshot/config مشخص.

وابستگی: R1 و fixture مربوط به P4 اکنون مستقل قابل انجام‌اند؛ R2 و index نهایی به E1 وابسته‌اند. مدل یا embedding پولی از ledger و سقف مشترک عبور می‌کند.

### ساسان — core و قرارداد اتصال

- [x] **C1 — انتشار و اتصال نسخهٔ مشترک core.** commitهای V8/V9 و راهنمای اتصال در [PR #7](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/7) منتشر شدند؛ [CI روی commit 8cf56d8](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38033908496) پاس شد. ۱۴۱۴ تست محلی و Ruff هم پاس‌اند؛ مقایسهٔ baseline در گزارش‌های V8/V9 ثبت است. [CI ترکیب PR با main](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38033931700) هم با ۱۴۲۸ تست پاس شد؛ PR با اجازهٔ ساسان به main merge شد (`85b6027`).
- [ ] **C2 — اتصال ورودی چندنوبتی.** سهم core/API آفلاین در P2 انجام و [ثبت شد](../docs/user-intake-pilot.fa.md): reported_facts، checks_performed، context_changed، reply ثبت‌شده و original-event replay؛ تست correction/withdrawal/تغییر محیط پاس‌اند. برای بستن کامل، محمدحسن کنترل‌های U2 را به همین wire وصل کند و بهنام event/question/transition را با T2/T3 پایدار و اتمیک کند. سؤال مبهم یا ویرایش‌شده fact فرضی نمی‌سازد؛ retry همان event باید پیش از stale/reply check شناسایی شود.
- [x] **C3 — قرارداد خروجی و review با fixture.** `ProposalHandoff` کل case، آخرین bundle واقعاً مصرف‌شده، تمام analysis و catalog واقعی GroundedPlan را نگه می‌دارد؛ gap کاربر/منبع، همهٔ منابع و scope نسخه قابل review هستند. منبع قبلی، تغییر case با revision یکسان، packet/متن دست‌کاری‌شده و approval پیش از edit رد می‌شوند. [PR #11](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/11)، [نتیجه و handoff](../docs/review-handoff-pilot.fa.md)، fixture ثبت‌شده `b085f7d`، helper `74e353b` و API `44d70a2` شاهدند. C3 فقط سهم core و مثال آفلاین را می‌بندد؛ نمایش UI با U2 و persistence/authentication/اجرای مجاز با T2/T3 باز می‌مانند. review معنایی و approval جدا هستند.
- [ ] **C4 — baseline برای pilot متصل.** baseline ورودی HTTP روی `5af98e6` چهار fail و روی adapter جدید چهار pass دارد؛ [ثبت C2](../docs/user-intake-pilot.fa.md). baseline خروجی C3 روی کد واقعی `3f22ef9` با همان چهار regression بازپخش شد؛ چهار fail و روی نسخهٔ جدید چهار pass، همراه [case چهار‌نوبتی و محدودیت](../docs/review-handoff-pilot.fa.md). پس از اتصال P3/P4، مقایسهٔ تصمیم واقعی ادامه یابد؛ baseline نرم‌افزار جای کیفیت مدل/RAG/test نیست. receiptهای تاریخی حفظ شده‌اند؛ انتخاب Issue فعلی answer-informed و exposed است.
- [ ] **C5 — رفع علت halt پیش از live.** هویت مدل، usage و هزینهٔ مورد اختلاف با مدرک provider تطبیق داده شود؛ uncertainty و ledger پاک یا reset نشوند. شرط پایان: علت توقف مستند، وضعیت ledger و مجوز/سقف باقی‌مانده روشن باشند؛ فقط آن‌وقت pilot کوچک ثبت‌شده اجرا شود.

وابستگی: سهم مستقل ورودی P2 و خروجی C3 با fixture انجام شده است. قدم بعد اتصال retriever حسن (P4/R3)، state/approval پایدار بهنام (P3/T1–T3) و کنترل‌های UI و split/runner محمدحسن (U2/E1–E3) است. تک agent مبناست؛ اضافه کردن agent/framework نیاز به شکست واقعی و مقایسهٔ مستند دارد.

[بازبینی آمادگی core](../docs/core-readiness-audit.fa.md) دو regression تازه را
روی `254e6542` با دو fail و بعد از `68dec4f` با دو pass ثبت می‌کند. مسیر gateway
موجود تا review نیز با MockTransport و ledger موقت بررسی شده؛ این شاهد اتصال
آفلاین است و C4/C5 یا کیفیت مدل را نمی‌بندد. تحویل امروزِ بالا ورودی ادامهٔ
pilot مشترک است، نه درخواست بازسازی بخش‌های دیگر توسط core.

### محمد بهنام — tracker و ابزارها

- [ ] **T1 — state پایدار.** CaseState، revision، history، pending proposal و نتیجهٔ اقدام‌ها ذخیره و بازیابی شوند؛ ابزار read/write/action ورودی، خروجی و خطای روشن داشته باشد. شرط پایان: دو پرونده جدا و ادامهٔ همان پرونده پس از restart تست شود.
- [ ] **T2 — رخداد و revision.** event ID ثابت و hash محتوای ورودی قبل از stale-revision check بررسی شود؛ replay همان رخداد نتیجهٔ ذخیره‌شده بدهد، محتوای متفاوت با همان ID رد شود. commit state/event و invalidation approval اتمیک و با compare-and-swap باشد؛ بعد از commit state معتبر دوباره خوانده شود.
- [ ] **T3 — approval و اجرای اقدام.** reviewer معتبر و همان case/revision/proposal ملاک باشند؛ reject هیچ اقدام نکند، edit پیشنهاد جدید و approval جدید بخواهد، correction مجوز قبلی را باطل کند. retry یا قطع ارتباط پس از اجرا نتیجهٔ قبلی را برگرداند و اقدام تکراری نسازد؛ review معنایی به‌تنهایی مجوز اجرا نیست.
- [ ] **T4 — شواهد عملیاتی pilot و evaluation.** برای retry/restart/stale/reject/edit/خرابی ابزار receipt بدهد، نتیجهٔ ابزار در وضعیت و تصمیم بعدی مصرف شود و دستور reset واقعی tracker را مستند کند. تست pytest این بخش و log امن با خودش؛ محمدحسن این شواهد را در گزارش evaluation استفاده کند.

وابستگی: T1–T3 با قراردادهای فعلی و fixture مستقل قابل انجام‌اند؛ برای اتصال، ورودی UserTurn و proposal دقیق از core/API لازم است. اقدامات فقط روی tracker محلی‌اند.

### محمدحسن — UI، caseها و evaluation

- [x] **U1 — prototype آفلاین.** Streamlit و FastAPI روی main، انتخاب scenario ساختگی و review پیشنهاد موجودند. این checkbox فقط همین prototype را پوشش می‌دهد؛ storage حافظه‌ای و فیک بودن retriever/reasoner همچنان صریح نمایش داده شوند.
- [x] **U2 — ورودی و نمایش کامل.** پیام، اطلاعات صریح/اصلاح‌شده و نتیجهٔ check به قرارداد C2 وصل شوند؛ facts فعال و superseded، unknownها و کل پیشنهاد، summary، منابع و scope نسخه به reviewer نمایش داده شوند. تغییر پرونده pending قبلی را stale کند؛ edit دوباره review/approval بخواهد. انجام‌شده در [PR #13](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/13): هر پیام event با `turn_id` پایدار و `expected_revision` می‌فرستد و retry همان payload را دوباره می‌فرستد؛ فرم fact/correction/withdraw، check، unknown و تغییر محیط؛ پاسخ کوتاه نسخه فقط به سؤال canonical تأییدشده (`awaiting_reply`) با سناریوی آفلاین `ask_version`؛ جدول facts فعال/superseded، receipt آخرین ورودی، و برای reviewer همهٔ سطوح analysis، همهٔ منابع (cited و uncited) با version scope، gapها و conflict groupها وقتی موجودند. شاهد: `tests/test_ui.py` و `tests/test_ui_client.py`. محدودیت: storage حافظه‌ای و adapterهای ساختگی؛ اتصال واقعی U3 است.
- [ ] **U3 — اتصال واقعی UI/API.** انتخاب mock از تنظیم retriever/model/tracker واقعی جدا باشد؛ error و توقف قابل فهم نمایش داده شوند. تست API و smoke test UI، case switching و approval/reject/edit با خودش؛ persistence و مجوز اجرا به tracker سپرده شود. وضعیت: انتخاب‌گر پرونده در نوار کناری اضافه شد (فهرست پرونده‌های همین session با وضعیت هر کدام، تعداد پرونده‌های منتظر review، پیام ارسال‌نشده متصل به پرونده خودش)؛ تست در `tests/test_ui.py`. بقیهٔ U3 به R3/T1–T3 وابسته است.
- [ ] **E1 — انتخاب و freeze caseها.** حداقل ۱۵ dev و ۱۵ test در سطح خانوادهٔ Issue؛ حداقل ۱۰ سناریوی چندنوبتی که حداقل ۵ تای آن‌ها در test باشند. manifest خانواده‌ها و شناسهٔ نسخهٔ split به حسن داده شود. کیس‌های توسعهٔ قبلاً دیده‌شده مثل 12782 و duplicate آن 12629، test مستقل نیستند؛ فهرست exposure بسته هم بازبینی شود. وضعیت: [manifest پیش‌نویس](../data/evaluation/split-manifest.json) با ۱ از ۱۵ dev و ۰ از ۱۵ test؛ خانوادهٔ #12782/#12629 و شناسه‌های رزرو exposure فقط dev. مانع: ZIP داده در repo نیست و انتخاب بقیه به R1 وابسته است.
- [ ] **E2 — fixture و rubric پیش از اجرا.** case_id، منبع/زمان، ورودی قابل مشاهده در شروع، پاسخ‌های بعدی به‌ترتیب، factهای معلوم، gap کاربر/منبع، منابع مجاز، تصمیم‌های قابل قبول و انتظار عملیاتی ثبت شوند. جواب/label/gold برای runner/reviewer است و وارد پیام مدل یا index نمی‌شود. schema با ساسان هماهنگ شود؛ مسیر موجود `data/evaluation/` مبنا باشد. placeholder قبلی `dev_cases.json` حذف شد؛ پیش‌نویس schema در [`data/evaluation/README.md`](../data/evaluation/README.md) و نخستین fixture آن (P1) ثبت شده‌اند. هماهنگی schema با ساسان هنوز باز است.
- [ ] **E3 — runner قابل تکرار.** caseها از fixture اجرا شوند؛ turn بعدی در زمان درست آشکار شود و case/revision/proposal و config/snapshot، latency و هزینه ثبت شوند. replay منطقی بدون API و اجرای کیفیت با مدل واقعی خروجی جدا داشته باشند. schema/runner و API/UI pytest با خودش؛ برای قراردادها از ساسان کمک بگیرد.
- [ ] **E4 — baseline و تنظیم فقط روی dev.** کیفیت تصمیم/پشتیبانی ادعاها/ضرورت و پاسخ‌پذیری سؤال، retrieval، صحت عملیات و هزینه/latency جدا سنجیده شوند. تغییرات روی ورودی یکسان مقایسه و نسخهٔ code/prompt/corpus/model freeze شود. نمونهٔ قضاوت انسانی ثبت شود؛ JSON معتبر یا نظر همان مدل تنها شاهد کیفیت نیست.
- [ ] **E5 — test و گزارش نهایی.** بعد از E1–E4 و اتصال واقعی، test بدون tuning اجرا شود؛ شکست‌ها، موارد حل‌نشده و اطلاعات ناقص همراه trace گزارش شوند. شواهد RAG از حسن، tracker از بهنام و core از ساسان جمع شود؛ مالک اجرای evaluation و گزارش محمدحسن است.
- [ ] **E6 — bonus و ارائه.** فقط پس از مسیر اصلی، Adversarial Testing با دامنهٔ توافق‌شدهٔ منتور و مقایسهٔ منصفانه اجرا شود؛ اسلاید و README با رفتار و هزینهٔ واقعی هماهنگ شوند.

وابستگی: E1/E2 و U2 با fixture اکنون قابل انجام‌اند؛ E1 قبل از R2، E4 قبل از E5، و U3 به R3/T1–T3/C2–C3 وابسته است. test برای انتخاب مدل، prompt، retrieval یا architecture استفاده نشود.

## نسبت case، corpus، UI و pytest

- **case ارزیابی:** یک مسئلهٔ انتخابی با ورودی اولیه و ادامهٔ گفتگوست. متن شروع به agent داده می‌شود، حتی وقتی آن Issue داخل corpus نیست. نگه‌داشتن جواب یا duplicate همان مسئله در index، توان بررسی مسئلهٔ تازه را اندازه نمی‌گیرد.
- **corpus RAG:** docs و Issueهای مجاز دیگر برای استدلال و شواهد مشترک‌اند؛ همهٔ Issueها حذف نمی‌شوند. اگر پس از کنارگذاری شاهد کافی نبود، پاسخ مستند محدود، سؤال ضروری، retrieval بیشتر یا ارجاع طبق rubric می‌تواند قابل قبول باشد؛ پاسخ قطعی تحمیل نمی‌کنیم.
- **UI:** ورودی آزاد مسئله دارد و به ۳۰ case محدود نمی‌شود. این ۳۰ case مجموعهٔ ارزیابی‌اند. prototype فعلی خروجی scripted scenario می‌دهد؛ رفتار مدل دربارهٔ متن جدید فقط پس از اتصال واقعی سنجیده می‌شود. انتخاب case آماده برای demo می‌تواند گزینهٔ جدا باشد.
- **fixture/runner:** caseها و gold بیرون UI نگهداری می‌شوند؛ runner همان API/adapter قراردادشده را خودکار صدا می‌زند. نمایش دستی چند case در UI جای evaluation قابل تکرار را نمی‌گیرد.
- **pytest:** تست core با ساسان، retrieval با حسن، tracker/tools با بهنام، UI/API و schema/runner evaluation با محمدحسن. تست مشترک pilot با مشارکت صاحبان اتصال و هماهنگی محمدحسن است؛ fixture/fake برای منطق مناسب است، ولی پاس شدن آن معیار کیفیت مدل/RAG نیست.

## ترتیب و شرط پایان پروژه

1. E1/E2 و بازبینی seed انجام شوند؛ adapterها و pilot ثابت می‌توانند هم‌زمان جلو بروند.
2. R2 انجام و corpus نهایی freeze شود؛ نسخهٔ split و exclusion کنار index ثبت شود.
3. pilot آفلاین و سپس اتصال واقعی با شواهد persistence/approval/retry/restart تأیید شوند.
4. baseline و بهبود روی dev مقایسه شوند؛ code، prompt، model و corpus freeze شوند.
5. test نهایی بدون tuning اجرا و گزارش کیفیت، شکست‌ها و هزینه تهیه شود؛ bonus بعد از اصل کار است.

هر checkbox زمانی بسته می‌شود که لینک commit/PR، تست، trace یا artifact شرط پایانش کنار همان task اضافه شود. تغییر owner یا قرارداد مشترک با review صاحب بخش ثبت شود. برای ساختار عمومی از [معماری](../docs/architecture.md)، [راهنمای اتصال](../docs/integration.md)، [UserTurn](../docs/user-turns.md) و [پیشرفت core](../docs/core-progress.md) استفاده کنیم؛ مستندات V8/V9 اکنون همراه core روی main هستند.

## به‌روزرسانی مشترک plan

- `main` مرجع مشترک تیم است. هرکس پیش از شروع کار، تغییرات محلی‌اش را حفظ کند، `git fetch origin` بزند و branch کاری خودش را از `origin/main` به‌روز کند. فایل plan با Git لحظه‌ای sync نمی‌شود؛ نسخهٔ تازه پس از fetch/merge دیده می‌شود.
- هر نفر taskهای خودش را در همین فایل نگه دارد؛ تغییر وضعیت یا بسته شدن checkbox همراه لینک commit/PR، تست، trace یا artifact باشد. blocker و ورودی لازم از نفر دیگر کنار همان task نوشته شود.
- تغییر کد و plan روی branch صاحب بخش ثبت و با PR به main برسد. شناسهٔ task مثل `R3` یا `U2` در توضیح PR نوشته شود؛ تغییر قرارداد مشترک با review صاحب بخش جمع شود. کار فعلی دیگران بازنویسی یا reset نشود.
- لینک PR و taskهای تغییرکرده در گروه معرفی شوند تا هماهنگ‌کننده و صاحب وابستگی باخبر شوند. برای دنبال کردن خودکار PRها، هر عضو می‌تواند اعلان‌های GitHub همان repository را فعال کند؛ صرف push شدن فایل به معنی دیده شدن آن توسط همه نیست.
- Codex/Claude هر نفر قبل از اجرا، AGENTS.md و همین plan را بخواند و از owner و شرط پایان task پیروی کند. پاس شدن mock یا pytest به‌تنهایی checkbox مربوط به اتصال واقعی یا کیفیت مدل را نمی‌بندد.

## محدودیت‌های اجرا

کل بودجهٔ تیم ۵ دلار است، شامل embedding، توسعه، evaluation و bonus. اجرای عادی live فعلاً به دلیل halt ledger متوقف است؛ ledger جدید یا reset راه ادامه نیست. کلید و raw credentials وارد log/Git/fixture نمی‌شوند. سقف هر invocation همان ۲ تلاش مدل، ۲ دور retrieval، ۲ query در هر دور و ۸ step است؛ پیشنهاد از اجرای اقدام جدا و همهٔ تغییرات عملیاتی روی tracker محلی‌اند.
