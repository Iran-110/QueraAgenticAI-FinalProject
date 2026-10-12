# plan و checklist تیم — Streamlit Support Assistant

به‌روزرسانی: ۲۰۲۶-۱۰-۱۳. این نسخه ادامهٔ plan محمدحسن روی `main` در commit `2ead870` است؛ [نسخهٔ قبلی](archive/plan-before-task-checklist.md) حفظ شده. مبنای regressionهای بازبینی `6131091` بود؛ انتشار tracker با `464e55e` و سپس #21 با `94b60e1` و [CI موفق](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38151154794) ثبت شده‌اند. مبنای baseline تازهٔ C2a همین `94b60e1` است. این فایل برای تقسیم کار و شرط پایان taskهاست؛ روزهای sprint قبلی را تاریخ تحویل حساب نمی‌کنیم. الزام‌ها از صورت اصلی پروژه می‌آیند، نه از ابزارها و frameworkهای پیشنهادی plan.

## وضعیت فعلی

| بخش | چیزی که داریم | چیزی که هنوز اثبات نشده |
| --- | --- | --- |
| core — ساسان | قراردادها، correction و GroundedPlan؛ C2a سرویس core و C2d اتصال HTTP به SQLite موجود با outcome اتمیک و approval دقیق؛ HTTP پایدار #30 روی main؛ UI و index محلی در [U3a/P4a، PR #32](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/32) پیاده و با تست‌های مستقل پذیرفته شده‌اند | corpus/index نهایی، اتصال مدل و کیفیت تصمیم روی caseهای ندیده؛ C5 halt |
| داده — آماده‌سازی اولیه ساسان؛ ادامه با حسن | seed اولیه در `streamlit-data-for-dev-test/`: ۲۴۰ Issue، ۱۱۷۸ comment، ۵۶ متن Markdown و ۱۱۷۲ API record؛ adapter حسن و اصلاح اتصال ساسان با #27 و #23 روی main در `ec1a1f0`؛ پذیرش mapper واقعی ۱۳۲/۱۳۲ | provenance از seed تا index، segmentation، exclusion و corpus نهایی؛ کیفیت retrieval واقعی |
| UI/API — محمدحسن | structured input و review کامل در #13/#21، case switching؛ UI پیش‌فرض memory/scripted؛ مسیر opt-in SQLite/index، auth و retry دقیق در U3a وصل شده | تنظیم نهایی index/model و auth محصول؛ recovery بعد پایان کامل session مرورگر |
| tracker/tools — محمد بهنام | SQLite #19/#20 روی main؛ state/revision/correction/authenticated review؛ اتصال C2d با ساسان outcome/snapshot/ABA و HTTP restart/retry را پاس کرده | شواهد evaluation نهایی T4 و تنظیم محصول؛ binding UI آفلاین پاس شده، action comment محلی است |
| evaluation — محمدحسن | یک dev چهار‌نوبتی، manifest پیش‌نویس، runner #15 و scenarioهای عملیاتی #18 | ۱۵ dev و ۱۵ test، rubric و split freezeشده، اجرای واقعی و داوری کیفیت؛ سناریوهای synthetic جزو ۳۰ case نیستند |

تغییرات جدید core از طریق [PR #7](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/7) با merge commit `85b6027` به `main` رسیدند. [گزارش V8](../docs/controlled-core-v8.fa.md)، [گزارش V9](../docs/controlled-core-v9.fa.md) و [قرارداد GroundedPlan](../docs/extractive-core.md) شواهد این milestone هستند. ۱۴۱۴ تست آفلاین در milestone محلی و ۱۴۲۸ تست همراه API/UI در CI ترکیب PR با main پاس شدند؛ نتیجهٔ RAG واقعی یا test نهایی نیست. GroundedPlan اختیاری است و پیش‌فرض production تغییر نکرده.

### قدم جاری پس از پذیرش HTTP/SQLite — ۲۰۲۶-۱۰-۱۳

[PR #27](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/27) با `4162079`
به `feat/rag-module` و بعد [PR #23](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/23)
با `ec1a1f0` به main merge شدند. هر دو CI روی head تازهٔ #23 پاس شدند؛
[CI انتشار main](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38225492349)
نیز ۱۸۹۱ تست، Ruff و replayهای آفلاین را پاس کرد.
[receipt تازهٔ main](../experiments/retrieval_acceptance/results-main-ec1a1f0.json)
در checkout تمیز: ۱۴ case / ۱۳۲ check؛ ۹۵ تست مرتبط و ۴۹ check مستقل
core/SQLite دوباره پاس شدند. کد و fixture با اجرای تمیز `326480d` یکسان‌اند؛
[شواهد انتشار](../experiments/retrieval_acceptance/release-main-ec1a1f0.json)
و [حدود پذیرش](../docs/rag-adapter-acceptance.fa.md) ثبت‌اند.
انتشار R3 فقط port آفلاین را بست. پس از آن #29 روی main `cddef782` منتشر شد؛ مسیر پایدار HTTP/SQLite در #30 روی main `6e719e9` منتشر شد؛ [receipt ۴۵۷/۴۵۷](../docs/persistent-http.fa.md). اصلاح Windows بهنام در [PR #31](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/31) با `877601c` روی main است و [CI آن](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38314737701) پاس شد. اتصال UI/index محدود در [U3a/P4a](../docs/offline-ui-index-pilot.fa.md) آزمایش شده؛ [receipt روی source تمیز `c14314f`](../experiments/ui_review_acceptance/verification-c14314f.json): ۲۲۱۸ pytest، UI baseline ۲/۶ و نسخهٔ جدید ۶/۶، Chroma واقعی ۱۴ source / ۳۰ chunk، HTTP پایدار ۴۵۷/۴۵۷. این اعداد پذیرش عملیاتی‌اند؛ corpus/index نهایی و کیفیت مدل همچنان بازند.

| نفر / task | قدم بعدی | خروجی لازم برای پذیرش |
| --- | --- | --- |
| حسن — R1/R2/R4 و بخش index در P4 | از profile و builder موجود شروع کند؛ با محمدحسن exclusion خانواده‌ها را از manifest E1 بگیرد، corpus/index نهایی نسخه‌دار بسازد و retrieval را روی dev بررسی کند | PR با provenance، segmentation و coverage؛ exclusion خود case، جواب، comment و duplicateها؛ snapshot/hash و دستور build تازه؛ sourceهای لازم/مفقود و version scope روی dev، بدون tuning روی test؛ `index_data` قدیمی هنوز مسدود است |
| محمدحسن — E1/E2/U3 | خانواده‌ها و rubric را پیش ببرد؛ مسیر runnable U3a را برای تنظیم/evaluation نهایی به کار بگیرد | manifest dev/test برای حسن؛ smoke مرورگر واقعی؛ source support و سؤال ضروری با داوری مستقل؛ AppTest و payload retry در U3a پاس‌اند |
| محمد بهنام — T4، مشترک با U3 | اتصال C2d را review و تنظیم database/credential را با محمدحسن جمع کند | همان receipt restart/retry/rollback؛ وضعیت ابزار در evaluation و پیکربندی نهایی؛ tracker دوم یا reset نساختن |
| ساسان — C2f/C4/C5، مشترک با P4 | GroundedPlan در pilot پایدار آمادهٔ review؛ پذیرش snapshot نهایی حسن و ارزیابی تصمیم با معیار E2 | receiptهای آفلاین و probe محدود موجود؛ C5 هنوز halt دارد، live عمومی مجاز نیست؛ corpus نهایی و baseline کیفیت مدل جدا باقی‌اند |

اتصال محدود [PR #32](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/32) روی main با `2ce25ab` منتشر شد؛ CI لینوکس و Windows روی [head شاخه](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38316532488) و [ترکیب PR](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38316540401) سبز است. کد و checklist همین نسخه مبنای اتصال تیم است. هیچ‌کدام از تیک‌های U3a/P4a، R2/R4 یا E1–E5 را نمی‌بندد. هر نفر branch خود را با `origin/main` sync کند؛ تغییر checklist با PR و شاهد انجام کار منتقل شود.

انتخاب caseها و کار API می‌توانند هم‌زمان جلو بروند. برای E1، seed در repo
موجود است؛ منتظر ZIP یا index نمانیم. caseها، جواب‌ها و duplicateهای خانوادهٔ
ارزیابی وارد corpus مجاز نشوند؛ #12782/#12629 همچنان exposed dev هستند.

## قدم مشترک بعدی: یک case چندمرحله‌ای از dev

### درخواست تحویل قبلی — ۲۰۲۶-۱۰-۱۰

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

### قدم قبلی پس از بازبینی — ۲۰۲۶-۱۰-۱۱

اصلاحات runner/UI و نسخهٔ تازهٔ همین plan در
[PR #21](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/21) ثبت شده‌اند؛
وضعیت انتشار و CI همان PR مرجع است. اصلاح tracker در
[PR #20](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/20)
به branch بهنام merge شد (`6628758`) و سپس
[PR #19](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/19)
به main رسید (`464e55e`). [CI branch tracker](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38150131745)
و [CI بازبینی fix](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38150134843)
روی `6628758` پاس‌اند؛ [CI انتشار main](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38150252419)
هم روی `464e55e` پاس شد.

PRهای #13، #14، #15، #17 و #18 روی main هستند؛ runner هنوز کیفیت مدل را
امتیاز نمی‌دهد و API از DummyTracker استفاده می‌کند. [بازبینی اتصال](../docs/team-integration-review-2026-10-11.fa.md)
نتیجهٔ تست‌ها و اصلاحات مرزی را ثبت می‌کند. درخواست تحویل امروز، یک برش کوچک
از pilot است؛ زمان‌بندی قطعی اعضا نیست. تحویل یک branch/PR، دستور اجرا و شاهد
باشد؛ اگر وابستگی مانع است، blocker و بخش مستقل همان روز ثبت شود:

| نفر | قدم امروز | خروجی قابل بررسی | اگر وابستگی مانع بود |
| --- | --- | --- | --- |
| ساسان — C2a/C3 | [CoreTurnService و pilot مستقل](../docs/core-turn-service.fa.md) آماده‌اند؛ اتصال API را با محمدحسن و بهنام بررسی کند | receipt/replay، context چندنوبتی، full-state guard و ACK دقیق؛ ۴ turn و ۴۹ check عملیاتی | تا adapter API آماده شود، همین سرویس با SQLite و fixture اجرا شود؛ journal/CAS lifecycle هنوز بازند |
| محمد بهنام — T4/P3 با U3 | با محمدحسن مسیر API را به تنها مرجع state یعنی SQLite وصل کند | replay پیش از مدل، review_id ثابت و hash دقیق؛ restart/retry/rollback و دو پرونده مستقل | اگر مرز API/auth آماده نیست، عملیات و کدهای خطای لازم را با fixture مشترک تحویل دهد |
| محمدحسن — E1/E2/U3 | دریافت ZIP را تأیید و انتخاب خانواده‌ها را شروع کند؛ schema/rubric و branch سؤال‌ها را با core هماهنگ کند | manifest پیش‌نویس خانواده‌ها برای حسن؛ یک dev با مسیرهای معتبر؛ review جدا برای original و edited/released | اگر ZIP نرسیده، blocker تحویل را ثبت و schema/branchها را روی dev موجود جلو ببرد؛ منتظر index نماند |
| حسن — R1–R3/P4 | backend موجود PR #23 را با main sync و CI را سبز کند؛ adapter قرارداد core را روی همان backend اضافه کند | EvidenceBundle با snapshot/نسخه/span، سقف کلی top_k و dedup؛ allowlist کوچک و exclusion dev پیش از index | تا E1 نهایی، collection/embedding ساختگی و docs مجاز pilot را تست کند؛ corpus نهایی هنوز باز بماند |

بازبینی اولیهٔ [PR #23 و شرط تحویل R3](../docs/rag-handoff-review-2026-10-11.fa.md)
روی `c0d450a`: backend اولیه push شده، ولی port هنوز خروجی خام Chroma می‌دهد؛
probe آفلاین با collection ساختگی در core به `RetrievalResultInvalid` و صفر
فراخوانی مدل رسید. metadata commit/location و chunkهای بزرگ باید پیش از اتصال
اصلاح شوند؛ [CI همان head](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38157755729)
با ۳۱ finding در Ruff متوقف شد. R1/R2/R3/P4 بازند. بازبینی محدود core در
`37ce74a` ایراد تازهٔ قابل بازتولیدی پیدا نکرد؛ ۱۷۹۶ تست و pilot چهار‌نوبتی
با ۴۹ check، شاهد آمادگی آفلاین C2a هستند. این milestone کیفیت RAG/مدل نیست.

بازبینی پیشین، پیش از push اصلاحی — ۲۰۲۶-۱۰-۱۲: head #23 در `bdb7c53` بود. CI قبلی سبز شده،
ولی `adapter.py`، `retriever.py`، `data_scripts/chunking.py` و `data_scripts/data_loader.py` صفر بایت بودند؛ پس
آن CI شاهد پذیرش adapter نبود. seed کوچک و README در branch حسن موجود بودند.
در آن milestone کدها به push دوباره نیاز داشتند؛ R1/R2/R3/P4 باز بودند. [ثبت pinned head](../experiments/retrieval_acceptance/candidate-bdb7c53.json).

push تازهٔ حسن در `b571080` چهار فایل را برگرداند؛ پذیرش روی همان کد مشکل
namespace، حذف commit/span، clipping متن و snapshot را بازتولید کرد. ساسان با
اجازهٔ کاربر اصلاح محدود R3 را در branch جدا انجام داد؛ import استاندارد، حفظ
metadata/text، snapshot تنظیم‌شده و checkهای collection، filters و خطای امن اضافه
شدند. [binding و دستور واقعی](../docs/rag-core-acceptance.fa.md) اکنون mapper خود
adapter را آزمایش می‌کند؛ smoke اولیه ۱۳۲/۱۳۲ پاس است. fixture و تصمیم‌های
ثبت‌شده تغییر نکرده‌اند؛ مشاهدهٔ queryهای refinement از فرض یک read به بررسی
round فعلی اصلاح شد و mutation مستقل دارد. [receipt تمیز و مقایسهٔ pinned baseline](../docs/rag-adapter-acceptance.fa.md)
روی `326480d` ثبت شد؛ ۱۸۹۱ تست کامل و Ruff پاس‌اند. اصلاح با #27 و #23 منتشر شد؛
receipt تازهٔ main در بخش جاری بالاست. R1/R2/R4 و retrieval از index واقعی بازند.

سهم مستقل تازهٔ core، **C2b**، [kit پذیرش اتصال](../docs/rag-core-acceptance.fa.md)
است: fixture پیش از اجرا ثبت شد؛ همان factory با تست port و چهار turn
`CoreTurnService`/SQLite اجرا می‌شود. ۱۳۲/۱۳۲ check مرجع پاس؛ mutationهای
metadata، query، سقف نتیجه، snapshot، quote و evidence قدیمی رد شدند.
backend ثابت اکنون به seam کد واقعی حسن تزریق و همین protocol روی main اجرا
شده؛ نتیجهٔ fixture کیفیت RAG یا test نهایی نیست. API/persistence، index و
exclusion نهایی همچنان taskهای مستقل تیم‌اند.

healthcheck پیش از push بعدی RAG — ۲۰۲۶-۱۰-۱۲: main در `febaefa` تمیز و
با remote یکسان بود؛ [CI همان main](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38182028171)
۱۸۲۸ تست و replayهای ثبت‌شده را پاس کرد. ۱۱۸ تست مرتبط core/SQLite/acceptance
دوباره پاس شدند؛ fixture و هر ۴۷ fingerprint کد با receipt نهایی برابرند و
لینک‌های اتصال سالم‌اند. review مستقل core blocker تازه‌ای پیدا نکرد.
سقف query درخواست core با تعداد خواندن‌های داخلی backend فرق دارد؛ راهنمای
C2b این مرز را روشن می‌کند و هزینه/کارایی RAG همچنان R4 است. تغییر production
لازم نشد. قدم بعد، کد قابل اجرای R3/P4، اتصال API/SQLite با U3/T4 و freeze
caseها/exclusion با E1/R2 است؛ C5 نیز به مدرک provider وابسته است.

انتخاب caseها لازم نیست منتظر index بماند. seed اولیه همراه manifest با #23
در `streamlit-data-for-dev-test/` به main رسید؛ انتخاب E1 از همین فایل‌ها ممکن است.
این انتشار، تأیید دریافت ZIP در پی‌وی نیست. schema و [rubric پیشنهادی core](../docs/evaluation-rubric.md) هنوز
نیاز به پیاده‌سازی و freeze توسط مالک evaluation دارند؛ checkbox کیفیت باز است.

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
- [x] **P3 — tracker بهنام؛ اتصال آفلاین HTTP با ساسان.** همان پرونده و proposal با revision معتبر حفظ و approval قدیمی/قبل edit رد می‌شود؛ review دقیق پس از restart receipt/action قبلی را می‌دهد و comment محلی فقط یک بار ثبت می‌شود. [پذیرش C2d و crash/rollback](../docs/persistent-http.fa.md) شاهد است؛ این تیک pilot عملیاتی محلی است، نه اتصال frontend/index/model یا ارزیابی کیفیت.
- [ ] **P4 — حسن؛ اصلاح اتصال با ساسان:** mapper واقعی اکنون با collection ثابت از همان case عبور می‌کند؛ [receipt تمیز ۱۳۲/۱۳۲](../docs/rag-adapter-acceptance.fa.md) شامل چهار turn با SQLite است. بعد از آماده شدن corpus مجاز، همان قرارداد روی index واقعی اجرا شود؛ این قسمت هنوز باز است.

**شرط پایان pilot آفلاین:** ورودی، سؤال تأییدشده، پاسخ کاربر، correction، revisionها، evidence فعال/کنارگذاشته‌شده و proposal در trace قابل بازبینی باشند. ماژول tracker مستقل آماده است؛ تا مسیر API/UI با persistence و recovery تأیید نشده، receipt رابط فقط «pilot با fixture و storage حافظه‌ای» است.

**شرط پایان اتصال واقعی:** همان مسیر با retrieval واقعی و tracker پایدار اجرا شود؛ reject و edit، approval قدیمی، retry یک event/action و restart بررسی شوند؛ نتیجهٔ ابزار در state و تصمیم بعدی دیده شود. اجرای مدل واقعی فقط پس از حل توقف ledger و با سقف هزینهٔ ثبت‌شده مجاز است. آماده بودن pilot آفلاین به معنی رسیدن به این مرحله نیست.

## checklist هر نفر

راهنمای نقش‌ها: [حسن](member_1_todo.md)، [ساسان](member_2_todo.md)، [محمد بهنام](member_3_todo.md)، [محمدحسن](member_4_todo.md). وضعیت taskها فقط در همین checklist ثبت شود؛ فایل‌های نقش، راهنمای ارجاع به آن‌اند.

### حسن — داده و RAG

- [ ] **R1 — بازبینی seed و provenance.** seed و manifest در `streamlit-data-for-dev-test/` روی main موجودند؛ تعدادها، روش انتخاب، URL/تاریخ، commit و نسخهٔ اسناد را تا corpus/index بازبینی و ثبت کند. دامنهٔ اولیه Session State، widgets، callback/rerun است؛ همهٔ Streamlit را نمایندگی نمی‌کند. body فعلی Issue ممکن است بعداً ویرایش شده باشد.
- [ ] **R2 — کنارگذاری خانواده‌های ارزیابی، قبل از index نهایی.** فهرست dev/test از E1 را بگیرد؛ خود Issue، commentها، outcomeها، duplicateها و docs حاوی جواب مستقیم همان case را بررسی کند. خروجی: corpus allowlist، exclusion manifest و گزارش بررسی linkage/duplicate؛ candidate مرتبط به معنی duplicate قطعی نیست.
- [x] **R3 — adapter بازیابی؛ کد پایه حسن، اصلاح اتصال ساسان.** `search(RetrievalRequest)` با snapshot تنظیم‌شده، سقف کلی top_k و metadata صریح/unknown پیاده است؛ mapper واقعی همراه constructor/backend واقعی با collection ثابت، [۱۴ case و ۱۳۲ check](../docs/rag-adapter-acceptance.fa.md) را پاس کرد. پس از refinement آخرین bundle در handoff است؛ alias یا اصلاح خروجی در binding نداریم. با #27 و #23 منتشر شد و [receipt تمیز main `ec1a1f0`](../experiments/retrieval_acceptance/results-main-ec1a1f0.json) پاس است. این تیک فقط port آفلاین را می‌بندد؛ index/corpus/کیفیت RAG در R1/R2/R4/P4 بازند.
- [ ] **R4 — آزمون بازیابی روی dev.** سند کامل/ناقص، نسخهٔ نامعلوم/متفاوت، conflict و خطای retrieval را بررسی کند؛ relevance و پوشش منابع را جدا از کیفیت متن مدل ثبت کند. خروجی: تست adapter و receipt بازیابی با snapshot/config مشخص.

وابستگی: R1 و fixture مربوط به P4 اکنون مستقل قابل انجام‌اند؛ R2 و index نهایی به E1 وابسته‌اند. مدل یا embedding پولی از ledger و سقف مشترک عبور می‌کند.

### ساسان — core و قرارداد اتصال

- [x] **C1 — انتشار و اتصال نسخهٔ مشترک core.** commitهای V8/V9 و راهنمای اتصال در [PR #7](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/7) منتشر شدند؛ [CI روی commit 8cf56d8](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38033908496) پاس شد. ۱۴۱۴ تست محلی و Ruff هم پاس‌اند؛ مقایسهٔ baseline در گزارش‌های V8/V9 ثبت است. [CI ترکیب PR با main](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38033931700) هم با ۱۴۲۸ تست پاس شد؛ PR با اجازهٔ ساسان به main merge شد (`85b6027`).
- [x] **C2a — coordinator مستقل core با tracker موجود.** [CoreTurnService و دستور اجرا](../docs/core-turn-service.fa.md): original-event replay و receipt عقب‌افتاده پیش از factory متوقف؛ پیام‌های کاربر برای reply کوتاه حفظ؛ facts فعال مرجع؛ full-state freshness؛ handoff کامل و read دقیق ACK. [تست سرویس](../tests/test_core_turn_service.py)، [context](../tests/test_core_conversation.py) و [freshness](../tests/test_engine_freshness.py) با SQLite واقعی و portهای تألیفی شاهدند؛ pilot موجود چهار turn و ۴۹ check عملیاتی دارد. این تیک سهم مستقل core را می‌بندد، نه API، journal/resume، CAS lifecycle یا کیفیت مدل.
- [x] **C2b — kit پذیرش RAG/core با fixture.** [protocol و دستور اجرا](../docs/rag-core-acceptance.fa.md)، [fixture پیش‌ثبت‌شده `db9c2c0`](../experiments/retrieval_acceptance/fixture-v1.json) و [receipt مرجع](../experiments/retrieval_acceptance/results-fixture-v3.json): ۱۴ case، ۱۳۲ check؛ ۴ turn، ۵ retrieval و ۵ reasoning اسکریپتی با SQLite واقعی. [اجرای mapper واقعی R3](../docs/rag-adapter-acceptance.fa.md) نیز ۱۳۲/۱۳۲ پاس است؛ خطای فرض یک read برای هر query در observation pilot با mutation مستقل اصلاح شد. ترتیب ranking/query آزاد است؛ evidence قدیمی و نقص‌های port رد می‌شوند. هزینهٔ API صفر؛ index/corpus و کیفیت واقعی بازیابی/مدل همچنان خارج این تیک‌اند.
- [x] **C2c — پذیرش pilot آفلاین از HTTP.** #29 با review و CI به main `cddef782` رسید؛ حافظهٔ پیش‌فرض همچنان restart را رد می‌کند. مسیر opt-in SQLite در C2d همان fixture را با [receipt تمیز ۴۵۷/۴۵۷](../experiments/http_pilot_acceptance/results-sqlite-b7107c0.json) و پنج checkpoint با process تازه پاس کرد؛ correction، approval قدیمی/قبل edit، کل view/action و صفر بودن port در retry بررسی شدند. [گزارش و محدودیت‌ها](../docs/persistent-http.fa.md)؛ این تیک عملیات آفلاین HTTP/core/tracker را می‌بندد، نه اتصال UI/index/model یا کیفیت evaluation.
- [x] **C2d — اتصال مستقل HTTP به tracker موجود؛ ساسان.** با #30 روی main `6e719e9` منتشر شد: [factory و قرارداد](../docs/persistent-http.fa.md)، [protocol v2 ثبت‌شده در `6f0e8b5`](../experiments/http_pilot_acceptance/protocol-v2.json) و [مقایسهٔ backendها روی source یکسان](../experiments/http_pilot_acceptance/comparison-sqlite.json). همان CoreTurnService/SQLite، snapshot واحد، outcome واقعی و stage اتمیک؛ reviewer از credential سرور، review_id ثابت و hash دقیق؛ retry/restart بدون model/action اضافه. ۲۰۳۵ pytest، Ruff، crash واقعی بعد ingress/stage، rollback و ABA پاس؛ هزینه API صفر. payload/hash/auth و retry review در U3a وصل و آزمایش شدند؛ تنظیم محصول و evaluation کامل هنوز بازند.
- [ ] **C2 — اتصال ورودی چندنوبتی.** سهم core/API آفلاین در P2 انجام و [ثبت شد](../docs/user-intake-pilot.fa.md): reported_facts، checks_performed، context_changed، reply ثبت‌شده و original-event replay؛ تست correction/withdrawal/تغییر محیط پاس‌اند. U2 در #13 وصل شد و جداسازی فرم در #21 اصلاح شد؛ API/state/review آفلاین در C2d به قراردادهای T1–T3 وصل و P3 پذیرفته شد؛ binding UI و index محدود در U3a/P4a پاس شده‌اند؛ تنظیم index/model نهایی باقی است. [قرارداد recovery](../docs/persistent-core-handoff.md) بین commit event و stage proposal، replay بدون اجرای مدل و read پس از ACK نامعلوم را مشخص می‌کند؛ coordinator core در C2a پیاده شده؛ factory HTTP و outcome واقعی اکنون در C2d آمده؛ resume خودکار ساخته نشده است. سؤال مبهم یا ویرایش‌شده fact فرضی نمی‌سازد؛ retry همان event باید پیش از stale/reply check و ساخت adapter شناسایی شود. [بازبینی مرز اتصال](../docs/team-integration-review-2026-10-11.fa.md).
- [x] **C3 — قرارداد خروجی و review با fixture.** `ProposalHandoff` کل case، آخرین bundle واقعاً مصرف‌شده، تمام analysis و catalog واقعی GroundedPlan را نگه می‌دارد؛ gap کاربر/منبع، همهٔ منابع و scope نسخه قابل review هستند. منبع قبلی، تغییر case با revision یکسان، packet/متن دست‌کاری‌شده و approval پیش از edit رد می‌شوند. [PR #11](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/11)، [نتیجه و handoff](../docs/review-handoff-pilot.fa.md)، fixture ثبت‌شده `b085f7d`، helper `74e353b` و API `44d70a2` شاهدند. C3 فقط سهم core و مثال آفلاین را می‌بندد؛ نمایش U2 انجام شده و #21 تمام claimهای هر chunk را حفظ می‌کند. مسیر opt-in persistence/authentication/اجرای محلی در C2d پیاده است؛ اتصال UI به همان envelope باقی می‌ماند؛ review معنایی و approval جدا هستند.
- [ ] **C4 — baseline برای pilot متصل.** baseline ورودی HTTP روی `5af98e6` چهار fail و روی adapter جدید چهار pass دارد؛ [ثبت C2](../docs/user-intake-pilot.fa.md). baseline خروجی C3 روی کد واقعی `3f22ef9` با همان چهار regression بازپخش شد؛ چهار fail و روی نسخهٔ جدید چهار pass، همراه [case چهار‌نوبتی و محدودیت](../docs/review-handoff-pilot.fa.md). پس از اتصال P3/P4، مقایسهٔ تصمیم واقعی ادامه یابد؛ baseline نرم‌افزار جای کیفیت مدل/RAG/test نیست. receiptهای تاریخی حفظ شده‌اند؛ انتخاب Issue فعلی answer-informed و exposed است.
- [ ] **C5 — رفع علت halt پیش از live.** هویت مدل، usage و هزینهٔ مورد اختلاف با مدرک provider تطبیق داده شود؛ uncertainty و ledger پاک یا reset نشوند. شرط پایان: علت توقف مستند، وضعیت ledger و مجوز/سقف باقی‌مانده روشن باشند؛ فقط آن‌وقت pilot کوچک ثبت‌شده اجرا شود.

برای C2/U3 از سرویس C2a استفاده شود؛ coordinator core دیگر فقط helper تستی نیست. factory HTTP/auth و outcome پایدار C2d روی main است؛ binding frontend آفلاین U3a و index محدود P4a آماده‌اند؛ محمدحسن/بهنام تنظیم محصول و smoke مرورگر را نهایی کنند. readهای سرویس به‌تنهایی CAS lifecycle نیستند؛ C2d اکنون در transaction اولین root proposal هر revision و outcome را کنترل می‌کند و مسیر ABA قبلی را می‌بندد. resume خودکار وجود ندارد. [packet تازهٔ C5](../docs/live-reconciliation-2026-10-11.fa.md) با خواندن read-only و hash ثابت ledger ثبت شد؛ مدرک provider همچنان کم است.

وابستگی: سهم مستقل ورودی P2 و خروجی C3 با fixture انجام شده و U2 به API وصل است؛ port آفلاین R3 نیز روی main پذیرفته شد. قدم بعد retrieval از index ثابت (P4/R1/R2/R4)، وصل کردن UI به state/approval پایدار C2d و split/rubric/runner محمدحسن (E1–E3) است. تک agent مبناست؛ اضافه کردن agent/framework نیاز به شکست واقعی و مقایسهٔ مستند دارد.

[بازبینی آمادگی core](../docs/core-readiness-audit.fa.md) دو regression تازه را
روی `254e6542` با دو fail و بعد از `68dec4f` با دو pass ثبت می‌کند. مسیر gateway
موجود تا review نیز با MockTransport و ledger موقت بررسی شده؛ این شاهد اتصال
آفلاین است و C4/C5 یا کیفیت مدل را نمی‌بندد. تحویل کوچک بالا ورودی ادامهٔ
pilot مشترک است، نه درخواست بازسازی بخش‌های دیگر توسط core.

بازبینی ۱۱ اکتبر C2/C3/E3: نه regression روی `6131091` fail و پس از اصلاح
pass شدند؛ شناسه و پروندهٔ درست، accounting درخواست، حفظ review، جداسازی فرم
و نمایش همهٔ claimهای یک chunk. [شواهد و محدودیت‌ها](../docs/team-integration-review-2026-10-11.fa.md).
این baseline منطق اتصال است؛ C4 برای تصمیم مدل همچنان باز می‌ماند.
سهم تازهٔ C2 در [۱۱ تست خطای core/SQLite](../tests/test_core_tracker_failure_boundaries.py)
ثبت شد: ورودی superseded پیش از read، correction حین reasoning/قبل stage،
قطع اجرا قبل مدل و بعد مدل/قبل stage، بازیابی دقیق ACK، rollback پس از INSERT
و event/review همزمان. همراه ۱۶ تست tracker، ۲۷ تست هدفمند پاس‌اند؛ full suite
انتشار #21 روی `94b60e1` نیز ۱۷۲۱ تست و Ruff پاس داشت. helperهای recovery در این
فایل تاریخی فقط harness تست‌اند؛ نسخهٔ قابل استفادهٔ core اکنون C2a است و
مسیر opt-in coordinator/outcome واقعی API اکنون در C2d آمده؛ UI و تنظیم index/model با U3/T4 بازند.
receipt تازهٔ [runner v3](../data/evaluation/receipts/offline/core-boundary-review-2026-10-11-v3.json)
روی `37ab853`: ۱۳۶ check در ۱۱ turn، یک dev و دو scenario، صفر fail؛ همهٔ
handoffها و متن released محفوظ‌اند. ترکیب اصلاحات با SQLite در checkout
آزمایشی ۱۷۱۰ تست پاس کرد؛ API هنوز memory است و E2/C4/C5 باز می‌مانند.

### محمد بهنام — tracker و ابزارها

- [x] **T1 — ماژول مستقل SQLite: state پایدار.** CaseState، revision، history، pending proposal و نتیجهٔ اقدام‌ها ذخیره و بازیابی می‌شوند؛ دو پرونده مستقل و ادامه پس از restart تست شده‌اند. read_case در #20، state/pending/history را از یک snapshot می‌خواند. regression همزمانی و fixture موجود P1 با SQLite همراه ۱۴ تست قبلی، ۱۶ pass دارند. این تیک ماژول مستقل را می‌بندد؛ HTTP/P3 در C2d نیز پذیرفته شد، binding UI آفلاین در U3a پاس شده؛ تنظیم محصول و evaluation هنوز بازند.
- [x] **T2 — ماژول مستقل SQLite: رخداد و revision.** event ID و hash ورودی پیش از stale/reply check بررسی می‌شوند؛ replay receipt قبلی را می‌دهد و محتوای متفاوت با همان ID رد می‌شود. commit state/event و invalidation approval اتمیک‌اند و read سازگار موجود است. خواندن state پس از commit در coordinator واقعی HTTP با C2d پیاده و restart/retry آن پذیرفته شد؛ binding UI آفلاین در U3a پاس شده.
- [x] **T3 — ماژول مستقل SQLite: approval و اجرای اقدام محلی.** reviewer معتبر و همان case/revision/proposal/hash کنترل می‌شوند؛ reject اقدامی ندارد، edit پیشنهاد و approval تازه می‌خواهد، correction مجوز قبلی را باطل می‌کند. retry/restart همان review نتیجهٔ قبلی و یک action محلی می‌دهند؛ rollback و concurrent review تست شده‌اند. authentication مرز HTTP در C2d پیاده است؛ credential و envelope client/UI در U3a وصل و تست شدند؛ review معنایی مجوز اجرا نیست.
- [ ] **T4 — شواهد عملیاتی pilot و evaluation.** برای retry/restart/stale/reject/edit/خرابی ابزار receipt بدهد، نتیجهٔ ابزار در وضعیت و تصمیم بعدی مصرف شود و دستور reset واقعی tracker را مستند کند. تست pytest این بخش و log امن با خودش؛ محمدحسن این شواهد را در گزارش evaluation استفاده کند.
  - شواهد محلی Windows در ۲۰۲۶-۱۰-۱۲: ۲۷ تست tracker/failure، ۷۷ تست SQLite/API/crash، ۳۳ تست HTTP runtime و پذیرش HTTP/SQLite با ۴۵۷/۴۵۷ check (restart=true) پاس شدند. [گزارش و دستور reset توسعه](../docs/tracker-t4-operational-evidence.md)، [اصلاح harness ویندوز در PR #31](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/31). binding آفلاین UI/auth/retry در [PR #32](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/32) پیاده و تست شده؛ وضعیت انتشار همان PR مرجع است. تنظیم credential محصول، smoke مرورگر و مصرف outcome در evaluation بازند؛ T4 تیک نمی‌خورد.

شاهد T1–T3: [source ماژول](../src/agent_app/tracker/sqlite_tracker.py)، [۱۶ تست tracker](../tests/test_sqlite_tracker.py)، [pilot آفلاین](../scripts/tracker_pilot.py) و [قرارداد و دستور اجرا](../docs/sqlite-tracker.md). [PR #20](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/20) با `6628758` به branch بهنام و سپس [PR #19](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/19) با `464e55e` به main merge شدند؛ suite branch tracker با ۱۶۹۰ تست و CI انتشار main پاس‌اند. پذیرش مستقل اولیه U3/T4 را نمی‌بست؛ اکنون HTTP/P3 با C2d پذیرفته شد و binding UI/evaluation باقی است. [گزارش بازبینی](../docs/team-integration-review-2026-10-11.fa.md).

وابستگی: ماژول T1–T3 با قراردادهای فعلی موجود است؛ برای T4/UI، ورودی UserTurn، proposal دقیق، review envelope و outcome از مسیر C2d موجود است؛ binding frontend و شواهد evaluation تکمیل شوند. اقدامات فقط روی tracker محلی‌اند.

### محمدحسن — UI، caseها و evaluation

- [x] **U1 — prototype آفلاین.** Streamlit و FastAPI روی main، انتخاب scenario ساختگی و review پیشنهاد موجودند. این checkbox فقط همین prototype را پوشش می‌دهد؛ storage حافظه‌ای و فیک بودن retriever/reasoner همچنان صریح نمایش داده شوند.
- [x] **U2 — ورودی و نمایش کامل.** پیام، اطلاعات صریح/اصلاح‌شده و نتیجهٔ check به قرارداد C2 وصل شوند؛ facts فعال و superseded، unknownها و کل پیشنهاد، summary، منابع و scope نسخه به reviewer نمایش داده شوند. تغییر پرونده pending قبلی را stale کند؛ edit دوباره review/approval بخواهد. انجام‌شده در [PR #13](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/13): هر پیام event با `turn_id` پایدار و `expected_revision` می‌فرستد و retry همان payload را دوباره می‌فرستد؛ فرم fact/correction/withdraw، check، unknown و تغییر محیط؛ پاسخ کوتاه نسخه فقط به سؤال canonical تأییدشده (`awaiting_reply`) با سناریوی آفلاین `ask_version`؛ جدول facts فعال/superseded، receipt آخرین ورودی، و برای reviewer همهٔ سطوح analysis، همهٔ منابع (cited و uncited) با version scope، gapها و conflict groupها وقتی موجودند. شاهد: `tests/test_ui.py` و `tests/test_ui_client.py`. محدودیت: storage حافظه‌ای و adapterهای ساختگی؛ اتصال واقعی U3 است.
- [ ] **U3 — اتصال واقعی UI/API.** انتخاب mock از تنظیم retriever/model/tracker واقعی جدا باشد؛ error و توقف قابل فهم نمایش داده شوند. تست API و smoke test UI، case switching و approval/reject/edit با خودش؛ persistence و مجوز اجرا به tracker سپرده شود. وضعیت: انتخاب‌گر پرونده در نوار کناری اضافه شد (فهرست پرونده‌های همین session با وضعیت هر کدام، تعداد پرونده‌های منتظر review، پیام ارسال‌نشده متصل به پرونده خودش)؛ تست در `tests/test_ui.py`. ماژول T1–T3 و port آفلاین R3 روی main موجودند؛ factory پایدار HTTP/core و outcome C2d با #30 روی main است. U3a credential maintainer، review_id/hash اصلی و retry per-case را وصل کرده؛ P4a index کوچک واقعی با embedding محلی دارد. تنظیم نهایی index/model، smoke مرورگر واقعی و evaluation همچنان باقی است.
- [ ] **E1 — انتخاب و freeze caseها.** حداقل ۱۵ dev و ۱۵ test در سطح خانوادهٔ Issue؛ حداقل ۱۰ سناریوی چندنوبتی که حداقل ۵ تای آن‌ها در test باشند. manifest خانواده‌ها و شناسهٔ نسخهٔ split به حسن داده شود. کیس‌های توسعهٔ قبلاً دیده‌شده مثل 12782 و duplicate آن 12629، test مستقل نیستند؛ فهرست exposure بسته هم بازبینی شود. وضعیت: [manifest پیش‌نویس](../data/evaluation/split-manifest.json) با ۱ از ۱۵ dev و ۰ از ۱۵ test؛ خانوادهٔ #12782/#12629 و شناسه‌های رزرو exposure فقط dev. seed اولیه در `streamlit-data-for-dev-test/` با #23 روی main موجود است؛ انتخاب خانواده‌ها از همان فایل‌ها شروع شود. انتخاب اولیه منتظر R1 یا index نمی‌ماند؛ provenance و linkage با حسن پیش از freeze بررسی می‌شوند.
- [ ] **E2 — fixture و rubric پیش از اجرا.** case_id، منبع/زمان، ورودی قابل مشاهده در شروع، پاسخ‌های بعدی به‌ترتیب، factهای معلوم، gap کاربر/منبع، منابع مجاز، تصمیم‌های قابل قبول و انتظار عملیاتی ثبت شوند. جواب/label/gold برای runner/reviewer است و وارد پیام مدل یا index نمی‌شود. schema با ساسان هماهنگ شود؛ مسیر موجود `data/evaluation/` مبنا باشد. placeholder قبلی `dev_cases.json` حذف شد؛ پیش‌نویس schema در [`data/evaluation/README.md`](../data/evaluation/README.md) و نخستین fixture آن (P1) ثبت شده‌اند. هماهنگی schema با ساسان هنوز باز است.
- [ ] **E3 — runner قابل تکرار.** caseها از fixture اجرا شوند؛ turn بعدی در زمان درست آشکار شود و case/revision/proposal و config/snapshot، latency و هزینه ثبت شوند. replay منطقی بدون API و اجرای کیفیت با مدل واقعی خروجی جدا داشته باشند. schema/runner و API/UI pytest با خودش؛ برای قراردادها از ساسان کمک بگیرد. وضعیت: runner آفلاین `agent_app.evaluation.runner` آماده است: caseهای یک split را turn به turn اجرا می‌کند، case/revision/proposal، git commit، hash fixture، config/snapshot، latency، تلاش مدل، دور retrieval، step، هزینه و token را ثبت می‌کند و receipt حالت offline و live را در مسیرهای جدا نگه می‌دارد. [receipt آفلاین dev](../data/evaluation/receipts/offline/dev-2026-10-10.json). ([PR #15](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/15)) مسیر live با HTTP intercepted و BudgetLedger موقت آفلاین تست شده؛ provider و ledger اصلی استفاده نشده‌اند. #21 receipt کامل، accounting درخواست و محافظ branch نامتناسب را اضافه می‌کند؛ تکمیل E3 هنوز به adapter U3، branchهای گفتگو و validation ثبت‌شده نیاز دارد. سناریوهای عملیاتی ساختگی برای خرابی ابزار (retrieval، یک خطای مدل با retry در سقف دو تلاش، دو خطا و توقف) و جابه‌جایی میان دو پرونده در `data/evaluation/scenarios/` پیش از اجرا ثبت شدند؛ اجرای اول ۸۱ از ۸۲ پاس شد چون انتظار ثبت‌شده کد توقف را اشتباه پیش‌بینی کرده بود (engine آخرین خطای adapter یعنی `ReasoningUnavailable` را گزارش می‌کند)؛ receipt آن حفظ و نسخهٔ v2 با همان یک تغییر ثبت شد. این سناریوها جزو ۳۰ case ارزیابی نیستند.
- [ ] **E4 — baseline و تنظیم فقط روی dev.** کیفیت تصمیم/پشتیبانی ادعاها/ضرورت و پاسخ‌پذیری سؤال، retrieval، صحت عملیات و هزینه/latency جدا سنجیده شوند. تغییرات روی ورودی یکسان مقایسه و نسخهٔ code/prompt/corpus/model freeze شود. نمونهٔ قضاوت انسانی ثبت شود؛ JSON معتبر یا نظر همان مدل تنها شاهد کیفیت نیست.
- [ ] **E5 — test و گزارش نهایی.** بعد از E1–E4 و اتصال واقعی، test بدون tuning اجرا شود؛ شکست‌ها، موارد حل‌نشده و اطلاعات ناقص همراه trace گزارش شوند. شواهد RAG از حسن، tracker از بهنام و core از ساسان جمع شود؛ مالک اجرای evaluation و گزارش محمدحسن است.
- [ ] **E6 — bonus و ارائه.** فقط پس از مسیر اصلی، Adversarial Testing با دامنهٔ توافق‌شدهٔ منتور و مقایسهٔ منصفانه اجرا شود؛ اسلاید و README با رفتار و هزینهٔ واقعی هماهنگ شوند.

وابستگی: E1/E2 با fixture اکنون قابل انجام‌اند؛ U2 انجام شده و port آفلاین R3 موجود است. E1 قبل از R2، E4 قبل از E5، و ادامهٔ U3 به P4، اتصال P3/T4 و C2 وابسته است. test برای انتخاب مدل، prompt، retrieval یا architecture استفاده نشود.

یادداشت بازبینی E2/E3: [rubric پیشنهادی](../docs/evaluation-rubric.md) با `AnalysisResult` و `ProposalHandoff` سازگار است؛ evidence_links به‌تنهایی اثبات پشتیبانی تمام ادعاها نیست. تا داوری مستقل، `live` فقط نوع اجراست و quality_claim باید false بماند. gold/expected مسیر offline را با مسیرهای معتبر live یکی نکنیم؛ manifest/corpus frozen و پاسخ‌های شرطی چندنوبتی هنوز کار E1–E3 هستند. receiptهای قبلی حفظ شوند.


### برش مستقل تازه — U3a / P4a، ساسان با ماژول‌های موجود تیم

- [x] **R1a — profile قابل بازتولید seed.** [script و receipt](../experiments/corpus/seed-profile.json)، ۲۸ تست: ۱۴ فایل package، schema/grain/hash/joins؛ نسخه‌های هم‌متن مستقل، split draft و candidateهای خانواده صریح. این تیک تأیید corpus نهایی نیست.
- [x] **P4a — index کوچک docs-only و اتصال واقعی.** [allowlist ثبت‌شده](../experiments/corpus/pilot-allowlist.json)، ۱۴ source و ۳۰ chunk؛ hash/span/commit و نسخه حفظ؛ همهٔ Issue/comment/release notes/evaluation خارج. Chroma واقعی با vector lexical محلی، pin مستقل snapshot و guard محتوا/نتیجه؛ ۶۰ تست شامل mutation موقت حین query. builder قدیمی نهایی همچنان بسته است؛ R2/R4 بازند.
- [x] **U3a — UI به backend پایدار و retry review.** [راهنمای اجرا](../docs/offline-ui-index-pilot.fa.md)، ۱۰۰ تست UI/client شامل ۲۴ regression قبلی؛ operation ثابت قبل POST، همان hash و متن نمایشی معتبر، credential خصوصی session، correction/case switching و ACK نامعلوم. baseline کنترل‌شده client/API قبلی ۲/۶، نسخهٔ جدید ۶/۶؛ نمرهٔ کیفیت نیست.
- [x] **C2e — اتصال U3a/P4a به core/SQLite.** client واقعی از TCP و دو interpreter تازه، index واقعی و همان DB؛ retry فقط receipt/action اصلی. AppTest واقعی صفحه نیز سرچ docs، question/approval، reply و correction را اجرا کرده. این scope مرورگر واقعی یا recovery بعد پایان session UI نیست.
- [x] **C2f — GroundedPlan در HTTP پایدار، پذیرش محدود.** [protocol ثبت‌شده پیش از اجرا](../experiments/grounded_http_acceptance/protocol-v1.json) و [دستور اتصال/حدود](../docs/grounded-persistent-pilot.fa.md): همان fixture exposed چهارمرحله‌ای، gateway جعلی و ledger موقت؛ baseline `3c92b12` ده کنترل از دوازده و نسخهٔ جدید دوازده از دوازده. بهبودها label درست و cleanup هر run هستند؛ baseline از قبل injection را اجرا می‌کرد. اصلاح نسخه، شاهد آخرین round، approval قدیمی، restart/retry و edit/reject پاس‌اند؛ AppTest و TCP با index واقعی نیز پاس شدند. [probe واقعی ثبت‌شده](../experiments/grounded_http_acceptance/live-result-0b962de.json) فقط یک درخواست توسعه و سؤال نسخه بود، هزینهٔ تخمینی $0.000650430؛ [review جدا](../experiments/grounded_http_acceptance/live-review-0b962de.json). این کیفیت مدل/RAG یا test نهایی نیست؛ ID دقیق serving model در receipt اول نامشخص است و C5 halt/hold قبلی حفظ شده است.

مسیر تک agent است؛ پیش‌فرض pilot هنوز scripted است و `grounded_fake_gateway` اتصال gateway جعلی را فعال می‌کند. policy آفلاین محافظه‌کار است: نسخهٔ نامعلوم سؤال، نسخهٔ معلوم ارجاع؛ هزینهٔ API این launcher صفر است. probe واقعی جداگانهٔ C2f یک درخواست با هزینهٔ تخمینی $0.000650430 داشت؛ C5 halt حفظ شده. [بررسی نهایی](../experiments/grounded_http_acceptance/verification-89a0aec.json) و [smoke مرورگر](../experiments/grounded_http_acceptance/browser-receipt-89a0aec.json): ۲۲۸۳ تست پاس، correction در همان case و یک action. defect label متغیر case اصلاح شد؛ auth محصول و recovery کامل session هنوز بازند. معیار claim/source و کیفیت retrieval با داوری مستقل روی dev و سپس test سنجیده می‌شوند. [حدود دقیق و دستورها](../docs/grounded-persistent-pilot.fa.md).

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
