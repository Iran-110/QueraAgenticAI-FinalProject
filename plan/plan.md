# plan و checklist تیم — Streamlit Support Assistant

به‌روزرسانی: ۲۰۲۶-۱۰-۱۵. این نسخه ادامهٔ plan محمدحسن روی `main` در commit `2ead870` است؛ [نسخهٔ قبلی](archive/plan-before-task-checklist.md) حفظ شده. مبنای regressionهای بازبینی `6131091` بود؛ انتشار tracker با `464e55e` و سپس #21 با `94b60e1` و [CI موفق](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38151154794) ثبت شده‌اند. مبنای baseline تازهٔ C2a همین `94b60e1` است. این فایل برای تقسیم کار و شرط پایان taskهاست؛ روزهای sprint قبلی را تاریخ تحویل حساب نمی‌کنیم. الزام‌ها از صورت اصلی پروژه می‌آیند، نه از ابزارها و frameworkهای پیشنهادی plan.

## وضعیت فعلی

- [x] **انتشار محلی PR54/57/58؛ ساسان.** هر سه به‌ترتیب به main رسیدند؛
  source نهایی `3cbbdd3` همان tree تحویل PR58 است. اجرای کامل ثابت روی همین
  main:۴۱۵۰ تست پاس؛ [رسید انتشار](../experiments/local_release_2026_10_15/verification-v1.json).
  Actions همچنان به علت Billing اجرا نشده؛ اجرای تازهٔ Windows ادعا نمی‌شود.
- [x] **C4h6 — سؤال همراه با زمینهٔ مستند موجود؛ ساسان، تحویل محدود و opt-in.**
  [ثبت پیش از کد/API](../experiments/core_ask_background_v1/protocol-v1.json).
  فقط منابع انتخاب‌شده با نسخهٔ دقیق USER، بدون conflict، بعد از سؤال غیرنسخه‌ای؛
  متن کامل و qualified، با حفظ سؤال و fallback به سؤال در صورت عبور از سقف.
  [نتیجه و محدودیت‌ها](../experiments/core_ask_background_v1/README.md): شش job
  و هر۱۲ turn حفظ‌اند؛۱۱ fresh و یک stale، پنج route کامل از شش. A در هر دو
  تکرار کنار سؤال callback، متن مستند۱٫۵۰ را واقعاً released کرد؛ همان plan
  در OFF فقط۱۰۸ کاراکتر سؤال و در ON متن۷۸۷۰ کاراکتری دارد. اثر نمایش است،
  usefulness انسانی ثابت نشده و طول متن نیاز به review دارد. B همان راهنمای
  جزئی icon۱٫۳۹ را حفظ کرد؛ یک text_input بی‌ربط در summary اولیه هم دیده شد.
  Enum هنوز fix ندارد؛ یک correction پس از retrieve_more خروجی JSON نامعتبر
  داشت، پیشنهاد قبلی stale و approval آن۴۰۹ بود. schema خام۱۳/۱۴؛ این اجرا
  نسبت به R4c با۶/۶ route، بهبود پایداری کلی را نشان نداد. هزینه۱۴ send برابر
  تخمین$0.012407340؛۳۳۲۳ کنترل native/هزینه پاس،۴۷۹ reservation قبلی و۱۴ جدول
  حفظ؛ شش scope بسته و۱۰ slot مصرف‌نشده claimed. این‌ها همان سه dev دیده‌شده‌اند؛ test نهایی نیست.
- [x] **R4d/C2i — profile قابل اتصال retrieval؛ ساسان.**
  [راهنمای اتصال](../docs/candidate-live-profile.fa.md): profile اختیاری
  `candidate_relevance_v1` به engine هر دو مسیر API حافظه‌ای/runner و HTTP/SQLite
  می‌رسد؛ native پیش‌فرض ثابت است. wrapper runner نیز metadata را حفظ می‌کند.
  read واقعی۲۵ کاندیدا، نسخهٔ فعال پیش از cap، budget کامل۱۲۰۰۰، correction،
  approval متن دقیق و restart/retry با همان tracker تست شده‌اند. اجرای API تازه
  از named profile حافظه‌ای/runner بوده؛ provider ماک در پذیرش SQLite، live SQLite
  یا مرورگر تازه حساب نمی‌شود. [verification](../experiments/core_ask_background_v1/verification-v1.json):
  ۴۳۲۲pytest،Ruff۳۰۵فایل،سهdemo وHTTP/SQLite۴۵۷/۴۵۷ پاس؛CI اجرا نشده است.
  دو کنترل نوبت سوم، حفظ background در SQLite و عدم مصرف آن به‌عنوان متن قبلی
  دستیار در مدل، حفظ USERhistory و توقف بزرگ‌بودن پیش از هزینه را بررسی کردند.
  contracts/ports و فایل‌های UI/tracker تیم تغییر نکرده‌اند؛ E1/E2/T4/R4 نهایی بازند.
  انتشار هر دو task در [PR #59](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/59)
  مستقیماً با پایهٔ main است؛ review کد/گزارش و gate محلی طبق مجوز فعلی ثبت‌اند.

- [ ] **C4h7 — reliability خروجی مدل؛ ساسان، کار بعدی.** یک JSON نامعتبر پس
  از refinement باقی است؛ raw متن provider نگه‌داری نشده و تشخیص دقیق syntax
  از hash ممکن نیست. قبل از افزودن JSON mode باید سازگاری Metis با canary مستقل
  محدود بررسی شود؛ OpenAI-compatible بودن اثبات پشتیبانی همهٔ پارامترها نیست.
  به‌صورت کور پارامتر اضافه یا validator/retry شل نشود. تنظیم نهایی پس از
  review usefulness و dev بیشتر freeze شود؛ test برای tuning استفاده نشود.

کارهای مستقل اعضا برای نسخهٔ نهایی (پیش از شروع branch خود را از main به‌روز کنید):

| نفر | تحویل بعدی | شرط پایان |
| --- | --- | --- |
| حسن | review profile جدید و پوشش/رتبه‌بندی منابع؛ provenance و exclusion بعد از split نهایی | source دقیقِ رسیده به مدل، برچسب relevance/Recall@k و build pinned؛ عضویت در index به‌تنهایی کافی نیست |
| محمدحسن | usefulness انسانی خروجی‌های فعلی، به‌خصوص سؤال۱۰۸کاراکتری درمقابل متن۷۸۷۰کاراکتری؛۱۲dev و۱۵test باقی، freeze rubric/gold وابسته به evidence condition | test برای tuning دیده نشود؛ حداقل ۱۰ گفتگوی چندنوبتی شامل ۵ test؛ سپس baseline و test نهایی |
| بهنام | بخش‌های باز T4: receipt پاک‌سازی‌شده و pin، lost-ACK از خود UI و failure/outcome | revision/approval/retry مستقل دو پرونده و شاهد مصرف outcome در تصمیم بعد؛ token/DB خصوصی منتشر نشود |
| ساسان | C4h6 و R4d/C2i تحویل شد؛ C4h7 و config پیشنهادی پس از review انسانی و dev بیشتر | قراردادها و defaultها ثابت، source/cost/خطاها کامل؛ این تحویل پایان evaluation نیست |

**قاعدهٔ انتشار فعلی — ۱۵ اکتبر، با دستور صریح ساسان:** منتظر رفع Billing
نمی‌مانیم. برای انتشار، review و تست محلی روی source ثبت‌شده، پذیرش اتصال و
محدودیت‌های پلتفرم را ضمیمه می‌کنیم؛ Actions همچنان blocked است و CI سبز ادعا
نمی‌کنیم. این قاعده جای شرط انتظار CI در یادداشت‌های قبلی را می‌گیرد؛ workflowها،
ledger، holdها، halt و receiptهای تاریخی تغییر نمی‌کنند. branch هر نفر پیش از
کار از `origin/main` به‌روز شود؛ کارهای E1/E2، R4، T4 و ارائه همچنان شاهد جدا می‌خواهند.

- [x] **R4c/C4h5 — رساندن منابع مرتبط و مقایسهٔ محدود؛ ساسان، کمک مستقل به RAG.**
  [protocol](../experiments/retrieval_relevance_v1/protocol-v1.json) و
  [رفتار و اتصال](../docs/retrieval-relevance.fa.md): PR50 حسن درhead`1a18749`
  تغییری نکرده؛ کار روی branch جدا، بدون تغییر branch/index/corpus اوست.
  برای خروجی نهایی۵، تا۲۵ کاندیدا می‌گیریم؛ ranking عمومی API/واژه‌ها و
  فیلتر نسخهٔ فعال USER پیش از cap نهایی اعمال می‌شوند. همهٔ گزینه‌ها opt-in اند.
  [بودجهٔ رکورد کامل](../experiments/retrieval_relevance_v1/whole-record-budget-amendment-v1.json)
  پس از مشاهدهٔ overflow آفلاین و پیش از API ثبت شد؛ متن منبع بریده نمی‌شود.
  replay روی index واقعی در۱۱ state، با packing هر۱۱ را زیر سقف نگه داشت.
  [مقایسهٔ تازه](../experiments/retrieval_relevance_v1/README.md) با flagهای core
  مشترک: route کامل۵/۶ در baseline و۶/۶ در نسخهٔ جدید؛ fresh از۱۰ به۱۲ رسید.
  هر۲۴ نوبت، شامل۲۲ fresh، یک empty و یک unvisited محفوظ‌اند. schema خام معتبر
  ۱۴/۱۵ در baseline و۱۲/۱۲ در نسخهٔ جدید؛ هیچ length/input/render overflow نبود.
  راهنمای مستند button۱٫۳۹ در هر دو تکرار به کاربر رسید، در baseline صفر از دو؛
  پاسخ جزئی برای همان یک case است. multiselect به مدل رسید ولی سؤال callback
  همچنان لازم بود؛ Enum هنوز علت/fix اثبات‌شده ندارد. usefulness انسانی null است.
  ۲۷ send با تخمین$0.026391915؛۳۹۱۲ کنترل هزینه/provenance پاس، همهٔ۴۵۲ reservation
  قبلی و۱۴ جدول، hold/halt/سقف محفوظ‌اند. شش scope بسته و۲۱ slot باقی claimed شدند.
  بودجهٔ bundle حداکثر۱۱۷۵۱/۱۲۰۰۰ byte بود. این تیک تحویل آزمایش است؛ RAG/eval
  نهایی بسته نشده‌اند و پیش‌فرض‌ها خاموش‌اند.
  انتشار در [PR #58](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/58)،
  پس از ادغام PR54/57، روی main `3cbbdd3` رسید؛
  [verification محلی](../experiments/local_release_2026_10_15/verification-v1.json)
  و blocked بودن CI ثبت‌اند. PR50 و branch حسن دست‌نخورده‌اند؛ این کار به merge آن وابسته نیست.

- [x] **C4h2 — repair query تکراری و مقایسهٔ محدود؛ ساسان.**
  [ثبت قبل از تغییر](../experiments/core_repeat_repair_v1/protocol-v1.json) و
  [قرارداد رفتار](../docs/repeat-query-repair.fa.md): گزینه پیش‌فرض خاموش است؛
  همان دو attempt، بدون retrieval/مدل اضافی یا اعتماد به `queries_used`.
  بازپخش سه plan واقعی قبلی با fallback تألیفی۴۲/۴۲ پاس است؛ کیفیت مدل نیست.
  [مقایسهٔ واقعی](../experiments/core_repeat_repair_v1/README.md)،۲ دور و۶ pair
  با ranking/index ثابت۱۸/۳۶: مسیر کامل۲/۶ درOFF و۴/۶ درON؛ پیشنهاد تازه۷ و۹.
  دو query تکراری به ارجاع موجه تبدیل شدند؛ صفر پاسخ فنی درهر دو حالت و
  ۱۲ سؤال ضروری.۳ repair واقعی،۲ موفق و۱length/provider-invalid؛ یکoverflow
  مستقل با۴source باقی است. تمام۲۴ نوبت شامل۱۶fresh/۱stale/۵empty/۲unvisited
  ثبت‌اند؛ usefulness انسانیnull وپیش‌فرض خاموش است.۲۸send، تخمین$0.032936640،
  صفرhold تازه؛۱۲۲۰ کنترل هزینه/پرووننس، تمام۳۶۴reservation قبلی و۱۴جدول محفوظ.
  scopeها بسته و۲۰slot مصرف‌نشدهclaimed؛ halt/C5 همچنانباز. تحویل تست/اصلاح
  محدود است؛ C4h کلی،R4 وevaluation نهایی بسته نشده‌اند.
  انتشار در [PR #51](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/51)
  با review مستقل و چهار CI موفق روی head`d1be786`؛ merge رویmain`17426b1`.
  [verification](../experiments/core_repeat_repair_v1/verification-v1.json):
  ۳۷۴۰pytest، Ruff و سه demo پاس؛ پذیرش آفلاین HTTP/SQLite با۴۵۷/۴۵۷
  شاملrestart/retry. آزمایش مدل این تحویل از TestClient/DummyTracker استفاده
  کرد؛ شاهد تازهٔ مرورگر/SQLite یا بهبود پاسخ فنی محسوب نمی‌شود.

- [x] **C4h3 — ظرفیت source و مقایسهٔ محدود؛ ساسان، بدون بهبود live اثبات‌شده.**
  [روش و receiptها](../experiments/core_source_capacity_v1/README.md) و
  [رفتار واقعی](../docs/source-capacity.fa.md): گزینهٔ پیش‌فرض خاموش؛ فقط کاهش
  maxItems موجود، بدون متن اضافی، بریدن quote یا تماس سوم. روی شکست قبلی،
  سقف امن۳ به دست آمد؛ در۱۵۸context تاریخی رشد ورودی صفر بود.
  live تازه روی همان index۱۸/۳۶: OFF وON هر دو۴/۶ route و۸fresh،۵ سؤال و۳ ارجاع؛
  صفر پاسخ فنی. فقط۲call یک correction واقعاً سقف متفاوت داشت؛ overflow در
  هیچ arm رخ نداد، پس کاهش failure یا افزایش کیفیت از این اجرا ثابت نشد.
  همهٔ۲۴نوبت شامل۱۶fresh،۴empty و۴unvisited محفوظ؛ دوlength، schema وsource-mismatch
  باقی‌اند.۲۸send، تخمین$0.032721150، صفرhold تازه؛۱۲۲۵کنترل هزینه/provenance،
  حفظ۳۹۲reservation قبلی و۱۴جدول؛۶scope بسته و۲۰slot مصرف‌نشدهclaimed.
  halt/C5 وtest نهایی بازند. این تیک تحویل آزمایش است، نه آمادگی نهایی core.

- [x] **E2r — بستهٔ داوری C4h2/C4h3؛ ساسان، کمک محدود به محمدحسن.**
  [workbench](../docs/evaluation-workbench.fa.md) اکنون هر دو receipt را می‌پذیرد؛
  criterion اصلی native با hash به method وصل است و با gold ثابت fixture
  جایگزین نمی‌شود. شکست‌ها وunvisitedها هم نمایش داده می‌شوند؛ sidecarها برای
  داوری انسانی خالی‌اند. schema ارزیابی/UI/tracker ومالکیت محمدحسن عوض نشده‌اند.

- [x] **C4h4 — قرارداد خروجی کوتاه و مقایسهٔ ثبت‌شده؛ ساسان.**
  [protocol قبل از تغییر](../experiments/core_compact_plan_v1/protocol-v1.json)،
  [رفتار واقعی](../docs/compact-plan-wire.fa.md) و
  [شرط review پیش از مدل](../experiments/core_compact_plan_v1/semantic-review-preparation-v1.json):
  index منبع و fieldهای لازم هر decision، با flag پیش‌فرض خاموش؛ قرارداد عمومی،
  hash کامل request، renderer، approval و سقف دو attempt محفوظ‌اند.۱۶۱تست هدفمند
  پاس؛ [مقایسهٔ دو دور](../experiments/core_compact_plan_v1/README.md)
  روی همان سه dev/index۱۸/۳۶ وranking ثابت انجام شد: schema نامعتبر۳/۱۸ درbaseline،
  صفر/۱۴ درcompact؛ binding هر۱۴انتخاب درست. مسیر کامل۴/۶به۵/۶، ولیfresh هر دو۱۰.
  ۱۲سؤال،۵ارجاع و۳label پاسخ، بدون پاسخ فنیِ مسئله؛ usefulness انسانیnull.
  همه۲۴نوبت، شامل۲۰fresh/۱stale/۲empty/۱unvisited محفوظ‌اند. یکrefinement سقف ورودی
  را رد کرد؛ projection هر دو قالب روی همانrequest بیش‌ازسقف است. length درهیچarm
  رخ نداد، پس کاهش length ثابت نشده.۳۲send، تخمین$0.034834305؛۱۶۷۱کنترل هزینه،
  حفظ۴۲۰reservation قبلی و۱۴جدول، صفرhold تازه؛۶scope بسته و۱۶slotباقیclaimed.
  پیش‌فرض خاموش؛ این تیک تحویل آزمایش است، نه کیفیت نهایی core/RAG.
  wire خام و expansion جدا ثبت می‌شوند؛ schema/route با پشتیبانی ادعا و usefulness
  یکی نیست. خروجی ناقص salvage نمی‌شود. regression کامل۴۰۰۶pytest،Ruff،سهdemo
  وپذیرشHTTP/SQLite۴۵۷/۴۵۷ پاس‌اند؛CI به‌علت سهمیهٔActions هنوز اجرا نمی‌شود.
  انتشار در [PR #57](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/57)،
  پس از merge54 به main retarget و همان‌جا merge شد؛ انتشار فعلی با استثنای
  محلیِ ثبت‌شده در بالای plan و رسید main `3cbbdd3` انجام شده است.

- [ ] **R4b — review اصلاح ranking حسن؛ مالک اصلاح حسن.**
  [PR #50](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/50)
  در head`1a18749` آمادهٔmerge نیست؛ [شواهد review](../experiments/rag_pr50_review/README.md):
  newest-first شاهد نسخهٔ فعلی را کنار می‌زند، over-fetch ذکرشده پیاده نیست،
  معنای `since_version` با exact applicability یکسان فرض شده و format محلی هنوز fail است.
  lint رفع شده؛ GitHub به علت Billing اصلاً jobها را شروع نکرده است.
  بازپخش۲۴query روی index واقعی۱۸/۳۶، همان membership قبلی را داد؛ over-fetch
  هنوز وجود ندارد.۹۶/۹۶ صرفاًquery-control بدون خواندن index است.
 ۹۱ تست موجود پاس ولی regression را پوشش نمی‌دهند. Hassan branch تغییر نکرد؛
  native receipt، کنترل نسخهٔunknown/قدیمی/correction وrelevance لازم است.
  کار core مستقل از این اصلاح ادامه دارد. محمدحسن review سه dev را درPR55 و
  rubric پیش‌نویس را درPR56 رویmain رسانده؛ usefulness۱۷خروجی و۱۲dev/۱۵test
  باقی با اوست. کمک ساسان محدود به اتصال وreviewpack است.

- [ ] **T4 — دریافت و review گزارش تازهٔ بهنام؛ انتشار receipt و بخش‌های باقی‌مانده با بهنام.**
  [گزارش روی commit ثابت`8420a3b`](https://github.com/Iran-110/QueraAgenticAI-FinalProject/blob/8420a3beed37e6bc79504487cd44724a40a30d79/docs/two-case-ui-sqlite-smoke-2026-10-14.md)
  اکنون در [PR #52](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/52)
  بازبینی شد؛ branch او تغییر نکرد. اجرای دستی
  Windows، آفلاین/scripted و رویsource`f8b3106` بوده، نهmain`17426b1`.
  correction، سؤال پس از correction، stale409، Edit/Reject، جداسازی دو case،
  restart backend و یکaction پس از replay تأییدشده را گزارش می‌کند.
  این‌ها فعلاً گزارش اپراتورند؛ JSON و screenshot در این PR ضمیمه نیستند.
  retry ازAPI بوده؛ در این گزارش شاهدی برای recovery مرورگر/session و
  lost-ACK از خودUI ثبت نشده. receipt پاک‌سازی‌شده با pin لازم است؛ token/DB منتشر نشود.
  tool failure، مصرف outcome در تصمیم بعد و handoff ارزیابی همچنان بازند؛
  T4 تیک نمی‌خورد و این گزارش، کیفیت مدل/RAG را نشان نمی‌دهد.

تحویل C4h1/E2p/E2q در [PR #49](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/49)
با head`344b260`، review مستقل وچهار CI موفق، رویmain با`f78c6e9` منتشر شد.
نتیجهٔ منفی آزمایش وhold/haltها حفظ‌اند؛ از آن بهبود کیفیت ادعا نمی‌شود.

- [x] **E2p — ابزار review خروجی واقعی؛ ساسان، کمک موقت به محمدحسن.**
  [راهنما](../docs/evaluation-workbench.fa.md): صفحهٔ محلی با پیام مصرف‌شده،
  تمام output surfaceها، factهای فعال، sourceهای واقعی و template خالی برای
  داوری. C4g همهٔ۲۴ نوبت را نگه می‌دارد:۲۳ رسیده،۱۷ پیشنهاد تازه،۶ بدون پاسخ
  تازه شامل۲ stale و۱ نوبت اجرا‌نشده. C4h متوقف‌شده هم۲۴ نوبت را نگه می‌دارد:
  ۱۶ رسیده،۱۰ پیشنهاد تازه،۶ بدون پاسخ تازه شامل۴ stale و۸ اجرا‌نشده.
  scope/hash و duplicate review کنترل می‌شوند؛ fixed oracle با native evidence
  یکی نیست. usefulness انسانی خالی است؛ E1/E2 نهایی یا۳۰ case بسته نشده‌اند.

- [x] **C4h1 — آزمایش راهنمای محدودیت query و اندازهٔ source؛ ساسان، نتیجهٔ منفی.**
  [ثبت قبل از تغییر و اصل نتایج](../experiments/core_resource_guidance_v1/README.md):
  همان۱۸ source/۳۶ chunk در هر دو arm، بدون تغییر ranking حسن؛۲۱ send با
  تخمین$0.024946020،۴ pair از۶ ثبت‌شده. هر arm فقط۱ مسیر کامل از۴ مسیر
  واقعاً اجراشده داشت؛۴ job آینده اجرا نشدند. راهنمای اختیاری برتری ثابت نکرد
  و پیش‌فرض خاموش است. یک refinement جدید با راهنما۳۳۰۷۵ و بدون آن۳۲۰۶۵
  byte همراه margin بود؛ guard۳۲۷۶۸ جلوی send را گرفت. اصل Usage آن attempt
  unrecorded/null ماند و campaign طبق شرط حسابداری متوقف شد؛ resume نداریم.
  چهار scope بسته،۱۱ slot مصرف‌نشده permanently claimed،۱۶ slot آینده تخصیص
  نیافته؛ تمام۳۴۳ reservation قبلی و schema/۱۴ جدول،دو hold و halt حفظ‌اند.
  [review حسابداری V2](../experiments/core_resource_guidance_v1/cost-review-v2.json)
  ۸۸۲/۸۸۲ است؛ V1 با یک انتظار اشتباه دربارهٔ method-v1/v2 محفوظ است.

- [x] **E2q — تشخیص attempt متوقف‌شده پیش از reservation؛ ساسان، آفلاین.**
  [اصلاح محدود پس از مشاهده](../experiments/core_resource_guidance_v1/pre-dispatch-accounting-amendment-v1.json):
  فقط typed ContextLimitExceeded از gateway واقعی با نبود reservation و هر
  transport marker پیش/پس، برای اجراهای آینده skipped_before_reservation با
  هزینه صفر ثبت می‌شود. حالت مبهم یا hold واقعی صفر نمی‌شود.۲۸ کنترل جدید
  و۸۸ regression پاس؛ receipt/campaign قبلی تغییر نکرد و هیچ API تازه برای
  این fix مصرف نشد. صفر send در کنترل HTTP، صفر route کامل بود؛ کیفیت نیست.

[بررسی انتشار این تحویل](../experiments/core_resource_guidance_v1/verification-v1.json):
۳۶۴۹pytest،Ruff روی۲۶۸ فایل،سه demo وپذیرشHTTP/SQLite۴۵۷/۴۵۷ باrestart/retry
پاس‌اند؛ CI همان head وreview نهایی شرط انتشار است. E1/E2/R4/T4/E4/E5/C5
با این تحویل بسته نشده‌اند و کار اعضا ادامه دارد.

- [x] **C4g / R4a — build نسخه‌دار و آزمایش سه dev با index واقعی؛ ساسان، کمک به RAG حسن.**
  انتشار و review در [PR #48](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/48)؛
  [protocol قبل از اجرا](../experiments/dev_rag_coverage_v1/protocol-v1.json) و
  [رسید/محدودیت‌ها](../experiments/dev_rag_coverage_v1/README.md): profile بسته۱۸/۳۶،
  چهار source رسمی و۴۶ reservation؛ پذیرش۸۹/۸۹، دو build مستقل یکسان و حفظ تمام
  chunkها/snapshotهای قدیمی۱۴/۳۰. این تیک تحویل محدود است، R4/کیفیت نهایی نیست.
  دو دور balanced با source ثابتa6c7f8c؛۲۹ call، تخمین$0.032363430، صفر hold تازه،
  شش scope بسته و۱۹ slot مصرف‌نشدهclaimed. ۶۲۹ کنترل حسابداری، همهٔ۳۱۴ ردیف
  reservation قبلی و ردیف‌های۱۴ جدول/schema محفوظ؛ C5/halt/دو hold قبلی بازند.
  route قدیم۴/۶ و جدید۲/۶؛ بهبود کیفیت از افزایش corpus ثابت نشد. fragment1.50
  رسید ولی button1.39/multiselect اضافه‌شده در bundle مدل نیامد؛ پنج RepeatedQuery
  و یک Enum overflow در دو attempt حفظ‌اند.۱۷ proposal تازه/دو مشاهدهٔ stale جدا،
 ۳۲ hit نسخهٔ ناسازگار/نامعلوم حذف، سه plan نامعتبر و repairها حفظ؛ usefulness
  انسانیnull.۳۵۱۵pytest و HTTP/SQLite۴۵۷/۴۵۷ و demos/Ruff پاس؛ CI head شرط انتشار.
  head1c01442 دو Linux و یک Windows پاس؛ Windows دیگر در سقف۲۰ دقیقه نزدیک
  انتهای suite cancel شد. هیچ assertion fail یا gate حذف نشد؛ بودجهٔ job۳۰ دقیقه شد.

- [ ] **C4h — رفع بن‌بست query و انتخاب source در حد خروجی؛ ساسان.**
  آزمایش C4h1 فقط prompt guidance بود و مسئله را حل نکرد. C4h2 بالای همین
  فایل،history خودcaller وfallback را باگزینهٔخاموش پیش‌فرض ودو attempt
  تحویل داده؛ دو ارجاع تازهٔ واقعی داشت، ولی پاسخ فنی اضافه نشد. قدم بعد
  C4h3،کفایت واندازهٔ انتخاب source است؛ guard engine وquote کامل محفوظ‌اند.
  repair درattempt دوم ظرفیت retrieval سپس model سوم نمی‌دهد؛ route کامل‌تر
  باescalation بیشتر، به‌تنهایی بهبود کیفیت نیست. baseline/شکست‌های قبلی محفوظ‌اند.
  کار حسن در R4: ranking/backfill نسخه و relevance این queryهای واقعی؛ source-ID
  یا gold filter برای بالا بردن نتیجه ممنوع. محمدحسن human review/split و بهنام
  smoke دستی UI/SQLite را ادامه دهند؛ این کارها با C4g بسته نشدند.

- [x] **C4f — مقایسهٔ محدود مدل و بهبود انتخاب منبع؛ ساسان.**
  انتشار و review در [PR #47](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/47)؛
  ۳۳۴۶ pytest، Ruff و HTTP/SQLite ۴۵۷/۴۵۷ با restart/retry پاس.
  [روش ثبت‌شده](../experiments/core_quality_followup/README.md): همان سه dev و
  oracle قبلی؛ دو دور paired سقف ۱۰۲۴/۲۰۴۸، و مقایسهٔ reminder روی شش وضعیت
  سالم/خصمانه. source-gap investigation جدا روی ۱۷ کنترل archived از ۴ پاس
  به ۱۷ پاس رسیده؛ پاسخ‌های قدیمی و نمرهٔ ۷/۹ بازنویسی نمی‌شوند.
  [راهنمای اتصال و هزینه](../docs/core-quality-followup.fa.md): مجوز تازهٔ ساسان
  برای finite quarantine-set، با هر دو hold و تمام revocationهای قبلی، halt
  عمومی و سقف $4.50 محفوظ. این reconciliation نیست؛ خطای نامعلوم تازه کل
  آزمایش را می‌بندد. دو epoch واقعی، ۶۴ call با تخمین $0.041621580 و بدون
  hold تازه؛ تمام sourceها هنگام اجرا ثابت. مقایسهٔ cap هر دو ۶/۶ بود، برتری
  ۲۰۴۸ اثبات نشد. در دو تکرار همان challenge، baseline دو بار quote مهاجم
  را انتخاب کرد و reminder صفر بار؛ در clean، متن مفید button در draft کاربر
  صفر از دو در برابر دو از دو، با حفظ source برای maintainer در هر دو arm.
  usefulness انسانی null و نمرهٔ composite تفسیر دستیار است. تمام ۴۸ proposal
  و ۶۴ prompt بررسی شده؛ پنج first attempt نامعتبر/repair محفوظ‌اند. ۱۰ scope
  بسته و ۳۲ slot استفاده‌نشده claimed باقی‌اند. C5، RAG واقعی و test نهایی
  هنوز بازند؛ defaultها ثابت‌اند. CI همان head و review شرط انتشار است.
  یک Windows با همین تغییرات پاس و دیگری در سقف ۱۰ دقیقه cancel شد؛ تمام
  checkها حفظ و سقف job بیست دقیقه شد تا head نهایی کامل بررسی شود.

- [x] **C4e — اندازه‌گیری محدود پایداری و برش خصمانهٔ آفلاین؛ ساسان.**
  انتشار و review در [PR #46](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/46)؛
  ۳۲۰۴ تست، HTTP/SQLite ۴۵۷/۴۵۷ و restart/retry پاس؛ CI همان head شرط merge است.
  [protocol](../experiments/core_stability_adversarial/stability-protocol-v1.json)
  قبل از مدل ثبت شد؛ سه دور کامل، دور چهارم پس از ۲ job از ۶ با خطای provider
  متوقف شد. [اصل receipt و review](../experiments/core_stability_adversarial/README.md):
  در سه دور کامل B سه route از ۹ و C هفت از ۹؛ با دور چهارم ناقص B سه از ۱۰
  و C هشت از ۱۰. ۱۰ paired input اولیه یکسان‌اند؛ ترتیب متوازنِ چهار دور
  کامل اجرا نشد. ۴۲ transport attempt، ۴۱ settled با تخمین $0.025141875 و
  یک hold تازه $0.0033792؛ ۴ job اجرا نشده‌اند، نه موفق. دو پاسخ Enum با
  `ProviderResponseInvalid` و خروجی ۱۰۲۴ token شکست محسوب شدند؛ علت دقیق
  truncation ثابت نشده. ۲۵ proposal، ۲۰ سؤال ضروری، ۳ پاسخ محدود button؛
  کفایت سخت‌گیرانهٔ ۲ پاسخ Enum کامل اثبات نشد و usefulness انسانی null است.
  ۱۴ qualification اولیه نسخهٔ نامعلوم را تأییدشده خواندند؛ [fix مستقل catalog](../experiments/core_stability_adversarial/catalog-version-truth-receipt-v2.json)
  همان ۱۰ کنترل archived را از ۳ پاس/۷ شکست به ۱۰ پاس رساند؛ نتیجهٔ live
  بازنویسی یا دوباره نمره‌گذاری نشده و fix با API تازه آزمایش نشده است.
  برش خصمانه پس از توقف فقط آفلاین است: ۶ کنترل سالم و ۳ counterexample؛
  انتخاب شاهد قدیمی و answer با conflict رد شدند، quote منبع مهاجم با hash
  معتبر پذیرفته شد و شکست semantic ثبت شد. این‌ها کیفیت RAG/test یا بستن
  bonus نیستند. tracker/UI/RAG/قراردادهای مشترک تغییر نکرده‌اند؛ دو انتظار
  تست اتصال برای catalog جدید اصلاح و اصل کنترل‌های تاریخی حفظ شده‌اند.

- [ ] **C5b — تطبیق درخواست نامعلوم تازهٔ C4e؛ ساسان.**
  [بستهٔ reconciliation](../experiments/core_stability_adversarial/stability-cost-reconciliation-v1.json)
  شناسهٔ محلی و بازهٔ UTC را دارد. HTTP status، model و usage دریافت نشده‌اند؛
  بدون رسید provider، صفر بودن هزینه فرض نمی‌شود. سه scope بسته و چهارمی
  با `NewUncertainty` revoke شد؛ grant قدیمی نیز طبق guard موجود revoke است،
  hold قبلی $0.02 و hold تازه باقی‌اند، pending صفر و halt پابرجاست.
  پروتکل live قبلی بسته می‌ماند؛ ledger reset یا parent تازه برای دورزدن این
  وضعیت ساخته نمی‌شود. C4f با مجوز تازهٔ انسانی و scope مستقلِ محدود، هر دو
  hold را حفظ می‌کند؛ reconciliation و halt عمومی همچنان بازند. smoke بهنام مستقل است.

- [x] **C4d — آزمایش محدود سه dev و اصلاح تصمیم‌های GroundedPlan؛ ساسان.**
  انتشار در [PR #45](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/45)؛
  ۳۱۳۹ تست محلی و HTTP/SQLite ۴۵۷/۴۵۷ پاس، CI همان head شرط merge است.
  [ورودی/known/unknown و oracle قبل از مدل](../data/evaluation/dev-three-v1/scenario-review-v1.json)
  و [receiptها و مقایسه](../experiments/dev_three_baseline/README.md) ثبت‌اند.
  A catalog معمول: ۲ خروجی معتبر از ۸، صفر مسیر کامل از سه؛ B vocabulary:
  ۳ از ۷ و یک مسیر؛ C guidance اختیاری decision/فیلد: ۸ از ۸ و سه مسیر.
  پنج state مشترکِ اولین attempt، request hash یکسان دارند؛ repair و refinement
  بعدی یکسان نیستند. Enum پاسخ مستند داشت ولی handoff صریحِ source gap کم بود؛
  نتیجهٔ اصلی حفظ است و replay اصلاح اختیاری renderer جدا گزارش می‌شود؛ پیش‌فرض تاریخی ثابت است.
  ۴۱ کنترل mode از ۲۰ پاس/۲۱ شکست به ۴۱ پاس، و ۱۷ کنترل config/HTTP از
  ۵ پاس/۱۲ شکست به ۱۷ پاس رسیدند؛ شکست اولیهٔ suite حفظ شده. این اعداد
  کیفیت عمومی، حل Issue یا test نهایی نیستند. ۲۳ send، تخمین $0.013688565؛
  سه scope بسته، cap/hold/halt و grant قبلی حفظ، C5 باز. index واقعی با مدل
  mock، ۷۳/۷۳ و دو build همسان/۴۰ query؛ همین ۱۴ docs/۳۰ chunk و vectors محلی،
  بدون پوشش تازهٔ نسخه‌های fixture. [راهنما](../docs/dev-three-baseline.fa.md).

- [ ] **E1a — سه dev پذیرفتهٔ انسانی؛ split نهایی با محمدحسن.**
  خانواده‌های #12782/#12629، #9770 و #8129/#2379/#8180 exposed و answer-informed؛
  صفر test تازه. chronology/duplicate خارجی و review usefulness هنوز باز.
  [manifest فعال این آزمایش](../data/evaluation/dev-three-v1/split-manifest.json)
  جداست؛ manifest تاریخی pilot برای بازتولید تغییر نکرده. routeها را می‌توان
  در runner موجود مصرف کرد؛ جواب نسخه فقط پس از همان سؤال released وارد شود.
  این کمک جای باقی ۱۵ dev/۱۵ test یا E1–E5 را نمی‌گیرد.
  [review انسانی caseها](../data/evaluation/dev-three-v1/case-review-v1.json)
  (پیش‌نویس دستیار، تأیید/اصلاح محمدحسن ۱۵ اکتبر، ساخته‌شده با
  `scripts/prepare_case_review.py`): هر سه برای dev پذیرفته؛ خانواده‌ها کامل‌تر شدند:
  #12629/#12782/#13022، #9770 به‌همراه #7300/#8734/#14297، و #8129/#2379/#8180
  به‌همراه #4909/#6985/#7419. مسیر جدید سند custom-classes باید به exclusion اضافه شود.
  release note۱٫۵۰ تغییر مشخص multiselect را می‌گوید؛ widget-behavior فقط rollout
  تدریجی۱٫۵۰تا۱٫۵۵ را می‌گوید. متن دقیق باید به مدل برسد؛ عضویت درallowlist کافی
  نیست. [review و شرط prospective ساسان](../docs/pr55-evidence-review.fa.md)
  برای اجرای تازه ثبت شد؛ gold/receipt تاریخی دست‌نخورده‌اند.
  usefulness خروجی مدل هنوز باز است.

کار جاری حسن: از build بستهٔ۱۸/۳۶ تحویل C4g جلو برود و relevance،ranking نسخه
و backfill را با queryهای واقعاً ثبت‌شده قبل/بعد بسنجد؛ چهار source اضافه شده‌اند
ولی membership به معنی رسیدن source به مدل نیست. برای همین سه dev منتظر
manifest تازه نماند؛ final split و exclusion انسانی جداست. PR #43 در آخرین
HEAD بررسی‌شدهٔ `3f9e7b1` بدون diff بود. محمدحسن review سه dev وdraft rubric را
منتشر کرده؛ ساسان ابزار review و اندازه‌گیری را جلو برده، ولی usefulness انسانی،
ثبت exclusion تکمیلی و باقی۱۲ dev/۱۵ test همچنان بازند. بهنام smoke دستی دو-case روی
main تازه را با Edit/Reject،correction،approval قدیمی وrestart/retry ادامه دهد؛
هر blocker UI/API را ثبت کند تا ساسان بردارد. تغییر ranking/tracker در این
تحویل انجام نشده و source/oracle/corpus قدیمی ثابت‌اند.

- [x] **C4c — vocabulary سؤال‌های caller در factory معمول؛ ساسان، محدود آفلاین.**
  انتشار و CI نهایی در [PR #44](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/44) است.
  [ثبت قبل از اصلاح](../experiments/user_gap_configuration/protocol-v1.json):
  ۲۱ کنترل، چهار state از همان خانوادهٔ exposed و سه سؤال بازبینی‌شده.
  مسیر معمول فقط gap نسخه را داشت؛ تنظیم اختیاری `AGENT_USER_GAP_CATALOG`
  باید vocabulary موجود را به factory برساند، فقط برای unknown صریح و بدون
  تکرار fact فعال USER. source catalog، قراردادها و فایل‌های اعضا ثابت‌اند.
  [مقایسهٔ واقعی Git و review](../experiments/user_gap_configuration/README.md):
  همان ۲۱ کنترل از ۹ pass/۱۲ fail به ۲۱ pass رسیدند؛ دوازده مورد مربوط به
  configuration و اتصال HTTP هستند، نه دوازده تصمیم مدل. تست کامل ۲۸۸۱، Ruff
  روی ۲۱۰ فایل، سه demo و پذیرش HTTP/SQLite ۴۵۷/۴۵۷ همراه restart پاس‌اند.
  [راهنمای اتصال](../docs/user-gap-configuration.fa.md): unknownها باید صریح در
  UI/API ثبت شوند؛ vocabulary خودکار کمبود را کشف نمی‌کند. factory بدون تنظیم
  اضافی همان رفتار قبلی را دارد. source catalog و قراردادها تغییر نکرده‌اند.
  ledger/halt/grant قبلی محفوظ‌اند؛ pair مدل با remaining grant کامل تأمین
  نمی‌شود، پس برای این اصلاح اجرای paid انجام نمی‌دهیم.

قدم اتصال محمدحسن: برای dev caseها نام gapهای لازم را در unknowns و جواب‌ها را
با همان نام در reported_facts ثبت کند؛ vocabulary سؤال‌ها را قبل از اجرای
مدل review و در config خصوصی freeze کند. فرم UI موجود این ورودی را دارد؛
نسخهٔ معلوم یا callback دریافت‌شده دوباره پرسیده نشود. این کار جای E1/E2 یا
rubric و داوری usefulness نیست. task بهنام برای smoke دستی C2h همچنان پابرجاست.

- [x] **C2h — سؤال‌های mock مطابق facts فعلی؛ ساسان، تحویل محدود آفلاین.**
  انتشار و CI نهایی در [PR #42](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/42) است.
  [ثبت، نتیجه و review](../experiments/offline_corrections/README.md): همان ۱۹
  کنترل V2 روی source قدیم پنج pass/چهارده fail و روی `090c1e5` نوزده pass
  دارند. V1 و شکست assertion ظاهری UI حفظ‌اند؛ V2 فقط «Approve فعال نباشد» را
  به‌جای الزام وجود دکمهٔ disabled ثبت می‌کند. فقط backend بدون index و scripted
  در `ask/ask_version` اصلاح شد: نسخهٔ نامعلوم سؤال canonical؛ نسخهٔ معلوم
  سؤال widget؛ اطلاعات کافی با شاهد synthetic ناکافی، ارجاع. guard core پابرجاست.
  AppTest، پاسخ کوتاه پس از approval، correction، 409 برای approval قدیمی،
  replay و retry در سه process تازه پاس‌اند؛ تست کامل ۲۸۶۰ و HTTP/SQLite
  ۴۵۷/۴۵۷ پاس است. [راهنمای ادامه](../docs/offline-scripted-corrections.fa.md):
  replay رخداد ناموفق قبلی همان نتیجه را نگه می‌دارد؛ ادامه با turn تازه.
  هزینه صفر؛ کیفیت مدل/RAG یا بستن T4/U3/E5 از این نتیجه گرفته نمی‌شود.

قدم کوچک بعدی بهنام: main تازه را بگیرد و smoke دو-case خودش را از UI با پیام
جدید تکرار کند؛ correction و سؤال بعدی، Edit/Reject جدا، approval قدیمی و
restart/retry با envelope دقیق ثبت شوند. هر review موفق یک action مورد انتظار
دارد؛ retry همان review نباید action اضافه کند. گزارش اصلی #40 تغییر نکند؛
نتیجهٔ تازه با PR، command و receipt جدا بیاید. محمدحسن اگر در UI blocker دید
به او کمک کند؛ مسئولیت dev/test/rubric و corpus نهایی اعضا پابرجاست.

### تحویل‌های قبلی و موارد اتصال باز

تحویل مستقل تازهٔ ساسان **C4b — حفظ تعارض اعلام‌شده در refinement/repair** در
[PR #41](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/41) است.
[مقایسهٔ اصل کد قدیم و جدید](../experiments/conflict_continuity/README.md) با
۱۴ کنترل ثبت‌شده پیش از fix: روی `03225e2` هفت pass/هفت fail و روی source تمیز
`8cc41bf` چهارده pass/صفر fail. سه answer نامجاز دیگر به approval نمی‌رسند؛
چهار ask/escalate مجاز، status حل‌نشده را برای maintainer حفظ می‌کنند و quoteها
فقط از bundle جاری‌اند. حذف منبع یا هشدار «حل شد» رفع تعارض نیست. marker فقط
gap منبع است؛ اطلاعاتی که کاربر می‌تواند روشن کند سؤال جدا دارد.

[راهنمای اتصال C4b](../docs/conflict-continuity.fa.md): status فقط در همان
run/case/revision نگه داشته می‌شود؛ هیچ quote قدیمی cache نمی‌شود. handoff باید
request واقعی planner پس از افزودن marker را capture کند. قراردادهای مشترک و
ماژول‌های اعضا عوض نشده‌اند؛ catalog پیش‌فرض هنوز تعارض را خودکار تشخیص نمی‌دهد.
تست کامل ۲۸۴۱ pass، ۴۴ regression تازه، Ruff و سه demo پاس؛ پذیرش جداگانهٔ
HTTP/SQLite ۴۵۷/۴۵۷ و restart پاس است. [receipt و review مستقل assistant](../experiments/conflict_continuity/README.md)
ثبت‌اند؛ CI نسخهٔ انتشار در PR مرجع بررسی شود. این کنترل تألیفی/آفلاین یک
خانوادهٔ exposed است، هزینهٔ API صفر، case مستقل اضافه نمی‌کند و کیفیت مدل/RAG
را ثابت نمی‌کند. E1/E2/R4/E4/E5/C5 و برآورد حدود ۷۵٪ تغییری نکرده‌اند.

[گزارش دو-case بهنام، PR #40](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/40)
پس از review و CI Linux/Windows با `78901d7` روی main است؛
[گزارش مشاهدهٔ دستی](../docs/two-case-ui-sqlite-smoke-2026-10-13.md) correction،
رد approval قدیمی، یک approval و replay بعد از restart backend را ثبت می‌کند.
این رسید خودکار/کیفیت مدل نیست؛ browser session باز ماند و Edit/Reject جدا
اجرا نشده‌اند. run scripted پس از correction با `KnownFactMarkedMissing` متوقف
شد، پس تصمیم follow-up موفق یا بستن T4/U3/E5 را از آن نتیجه نمی‌گیریم.

تحویل قبلی ساسان **C4a — انتخاب واقعی مدل روی شواهد ثابت** در
[PR #39](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/39) است؛
از main `80f9913` شروع شد. [بستهٔ شواهد و محدودیت‌ها](../experiments/controlled_model_baseline/README.md)
اصل preregistration، receipt و review جدا دارد. baseline روی `8b16f2c` پس از
CI لینوکس/ویندوز اجرا شد: ۳ send واقعی، ۲ سؤال callback قابل بررسی، یک
`ProviderResponseInvalid` و ۳ condition اجرا‌نشده از ۶ مورد. هزینهٔ تخمینی
$0.002005245 و hold تازه صفر؛ هزینهٔ حساب واقعی unknown است.

[follow-up تازهٔ سقف خروجی](../docs/controlled-output-cap-followup.fa.md) فقط
همان نسخهٔ نامشخص را با همان ورودی/prompt/model و یک send مجاز ثبت می‌کند؛
خروجی ۳۸۴ به ۵۱۲، reserve ورودی ۱۵۳۶۰ و رزرو $0.002872320 در باقی‌ماندهٔ
grant قبلی $0.002909545 جا شد. روی `07d759f` پس از
[CI Linux/Windows](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38445395851)
یک send، یک سؤال ضروری نسخه، `finish_reason=stop` و ۳۸۵ token خروجی داشت؛
کاربرد هر پنج source تأییدنشده ماند. مقایسهٔ همان ورودی فقط تکمیل عملیاتی
۰ به ۱ است؛ علت خطای قبلی و افزایش کیفیت ثابت نشده. baseline اصلی همچنان
۲ proposal از ۶ condition و سه کنترل آخر در live اجرا نشده‌اند.
جمع دو epoch چهار send با $0.002845260 تخمینی، hold تازه صفر؛ grant قدیمی
$0.00206953 باقی دارد و رزرو کامل اجرای دیگر در آن جا نمی‌شود. halt/hold
قبلی حفظ‌اند؛ baseline و reviewer تغییر نکرده‌اند و retry خودکار نداریم.

این‌ها variationهای exposed یک خانواده‌اند، نه شش Issue مستقل، RAG واقعی
یا test نهایی؛ catalog و conflictها دستی‌اند. مشکل import مستقیم core در
process تازه جدا اصلاح شد و API عمومی حفظ است؛ این علت خطای provider نبود.
تست کامل محلی ۲۷۹۷ مورد، Ruff و سه demo پاس‌اند. CI و انتشار نهایی در PR
مرجع ثبت شوند؛ branchها پس از merge با `origin/main` sync شوند.

[راهنمای C4 به تیم و agentهای کاری](../docs/team-handoff-c4.fa.md) محدودهٔ
فایل‌ها و adopt کردن را مشخص می‌کند. قراردادهای مشترک و ماژول‌های اعضا تغییر
نکرده‌اند. وظایف سه dev case/corpus/smoke تیم پابرجاست؛ E1/E2/R4/E4/E5/C5 بازند.

انتشار #37 روی main `109f59e` و [CI Linux/Windows](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38406080389)
پاس شد. تحویل مستقل ساسان **C2g** در [PR #38](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/38)،
[query بعد از correction](../docs/current-retrieval-context.fa.md)،
است: reasoning/history حفظ می‌شود و context اولیهٔ retrieval از factهای فعلی،
پیام اخیر و hint موضوعی جدا می‌آید. [نتیجه و اصل receiptها](../experiments/retrieval_context/README.md):
روی ده variation تألیفی، کنترل لفظی ۷۲/۹۶ به ۹۶/۹۶ و همهٔ کنترل‌های هر سناریو
۲/۱۰ به ۱۰/۱۰ رسید؛ این کیفیت مدل نیست. index واقعی ۶۰ collection read داشت.
دو send آنلاین با $0.001115400 تخمینی همان سؤال ضروری callback را انتخاب کردند؛
منبع arm جدید نسخهٔ 1.64.0 برای کاربر 1.49.0 بود. کیفیت RAG/تصمیم بهتر اثبات نشد.
سیاست موجود `exact_user_version` به backend توصیهٔ نسخهٔ فعلی، **پس از probe و
با تست آفلاین** وصل شد؛ comparison با `all` محفوظ است. این فیلتر ranking/backfill
و coverage حسن در R4 را نمی‌بندد؛ وظایف سه dev case و corpus تیم همان‌اند.

تحویل محلی C2g: ۲۷۱۴ pytest، Ruff و HTTP/SQLite با process تازه ۴۵۷/۴۵۷ پاس؛
۲۱ تست مستقل scope روی هر دو seam اتصال اجرا شد. source receipt آنلاین همان
`0b3f1cc` است و binding بعدی آفلاین در `a06925f`؛ CI انتشار نهایی در PR مرجع
است. [verification و اصل receiptها](../experiments/retrieval_context/README.md)
بهبود query را از کیفیت مدل و source جدا نگه می‌دارند.

نسخهٔ قبلی با [PR #36](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/36)
روی main `a087770` است؛ [CI انتشار Linux/Windows](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38387712898)
پاس شد. [تحویل تازهٔ مستقل](../docs/evaluation-live-routes.fa.md): runner فقط
مسیر ثبت‌شدهٔ متناسب با سؤال واقعی را اجرا می‌کند؛ factory مشترک Chroma/model،
case binding پایدار و helper امتیازهای review اضافه شده‌اند. این‌ها پذیرش
عملیاتی با mock هستند؛ rubric/fixture نهایی، کیفیت و C5 هنوز بازند.

بررسی نهایی محلی این تحویل: ۲۶۱۶ pytest، Ruff و سه demo پاس؛ AppTest صفحهٔ
واقعی با همین factory و provider mock و HTTP/SQLite تازه ۴۵۷/۴۵۷ پاس‌اند.
[مقایسهٔ ثبت‌شدهٔ runner](../experiments/evaluation_routes/README.md) روی همان
fixture و portهای mock: تکمیل مسیر قبلی ۰/۳ و مسیر شاخه‌ای ۳/۳؛ baseline
هیچ check مکانیکیِ fail نداشت، اما ادامهٔ درست گفتگو را کامل نمی‌کرد.
این بهبود عملیاتی است؛ کیفیت مدل/RAG یا سه case مستقل نیست. CI و publication
نسخهٔ نهایی در PR ثبت شوند؛ [verification محلی](../experiments/evaluation_routes/verification-v3.json)
و اصلاحات audit نسخه‌های V1/V2/V3 حفظ‌اند؛ اصل receiptها بازنویسی نشوند.

هدف امشب درخواست ساسان است، نه تأیید زمان اعضا. اول یک برش dev قابل بررسی
بسازیم، سپس تمام الزام‌ها را ببندیم؛ سه case جای ۳۰ case را نمی‌گیرد.
هر تحویل PR، دستور اجرا و receipt داشته باشد؛ اگر امروز نمی‌رسد، blocker و
قسمت قابل تقسیم همان روز اعلام شود. فردا ارائه/bonus پس از روشن شدن وضع
بخش الزامی بررسی شود. branchها از `origin/main` sync شوند؛ تغییر plan با PR
منتقل می‌شود و از لپ‌تاپ دیگر فوری دیده نمی‌شود.

| مالک / محدودهٔ فایل | کار مشخص این برش | شرط پذیرش و ادامه |
| --- | --- | --- |
| ساسان — core، `evaluation/runner.py`، `routes.py`، `live.py`، `semantic_review.py`، `live_backend.py` | اتصال مسیرها، receipt معتبر، case/revision/retry و helper review؛ review/انتشار این تحویل؛ بعد baseline واقعی dev | تست‌های آفلاین و CI؛ baseline با config ثابت و protocol قبلی؛ خرج فقط ضروری/ثبت‌شده با همان ledger و علت C5 محفوظ. هم‌زمان این فایل‌ها توسط اعضا ویرایش نشوند |
| محمدحسن — `data/evaluation/dev/`، `test/`، manifest، rubric و UI | [packet سه dev آماده](../data/evaluation/dev-three-v1/split-manifest.json) را review/adopt کند؛ chronology، خانواده‌ها/exposure، oracle و rubric را با حسن ببندد | fixtureها قبل از run ثبت شده‌اند؛ ادامهٔ تألیفی و exposure صریح است. review مستقل original و edit جدا، usefulness انسانی؛ سپس تکمیل ۱۵ dev/۱۵ test و حداقل ۱۰ multi-turn، پنج test. E1/E2 هنوز بازند |
| حسن — retrieval، corpus و exclusion | برای همان سه dev case، شاهد مرتبط و نسخه‌دار یا unknown صریح معرفی کند؛ linkage/exclusion خانواده‌ها را با محمدحسن ببندد؛ top hit نسخهٔ 1.64 برای کاربر 1.49 را با ranking/filter/backfill و coverage منابع dev بررسی کند | URL/revision/hash/span/نسخه و coverage لازم/مفقود؛ خود case/comment/outcome/duplicate و جواب مستقیم از index خارج؛ build نهایی نسخه‌دار و receipt retrieval روی dev. فیلتر core منبع جایگزین نمی‌آورد؛ docs pilot فعلی برای ادعای کیفیت کافی نیست |
| بهنام — tracker/tools و شاهد T4 | یک receipt دو-case از UI موجود تا API/SQLite: approve/edit/reject، correction، approval قدیمی، restart/retry و جابه‌جایی case | action تکراری صفر و revision درست؛ PR با command/receipt روی main تازه. tracker موجود را استفاده کند؛ startup مدل عمومی در C5 halt مسدود است، smoke آفلاین مستقل انجام شود |

پس از این برش، ساسان baseline/model comparison ثبت‌شده را اجرا می‌کند؛
خانواده‌های test فقط پس از freeze و بدون tuning اجرا شوند. هیچ case، نمرهٔ
انسانی، corpus نهایی یا حل halt از طرف افراد تأییدشده فرض نمی‌شود.

بازبینی بخش الزامی پس از #37، بدون bonus: **حدود ۷۵٪، برآورد مهندسی و نه نمرهٔ کیفیت**.
برآورد قبلی ۷۰٪ بود؛ آماده‌شدن routeها/factory/helper موجب این تغییر است،
نه افزایش تعداد pytest یا اثبات کیفیت مدل. dev مستقل همچنان ۱ و test صفر است.
[مسیر کوتاه تکمیل و حدود شواهد](../docs/delivery-readiness-2026-10-13.fa.md):
اولویت با caseهای مستقل، corpus/exclusion نهایی، baseline واقعی dev و test
بدون tuning است. infra آماده‌تر است؛ تست‌های آفلاین این کارها را نمی‌بندند.

گام مستقل تازه: cleanup runner اصلاح شده؛ [۱۵/۱۵ candidate metadata](../data/evaluation/candidates/reservations-v1.json)
و gate مکانیکی `frozen_final_v1` آمادهٔ بازبینی‌اند. candidateها هنوز case نهایی
نیستند، partial exclusion هنوز به corpus نهایی اعمال نشده و E1–E5 بازند.
runner در حالت final کل bundle و evidenceهایش را قبل از live factory بررسی
می‌کند؛ branchهای adaptive در تحویل تازه پیاده‌اند و semantic helper judgment
caller را ثبت می‌کند؛ scoring مستقل و freeze هنوز باقی‌اند. [protocol اتصال واقعی دو turn](../experiments/grounded_http_acceptance/connected-live-protocol-v1.json)
با index موجود، correction و ledger اصلی ثبت می‌شود؛ اجرا و نتیجه جدا گزارش
می‌شوند. مجوز API جدید کاربر شامل آزمایش ضروری است؛ سقف تیم و halt/hold قبلی
حفظ می‌شوند. هیچ پیام تیمی از این مرحله ارسال نشده است.

اجرای واقعی همین مرحله روی `fbac1b4` انجام شد؛ [receipt و review](../experiments/grounded_http_acceptance/connected-live-README.md):
۲ send، $0.001104015 تخمینی؛ correction، proposal تازه، retry و ساخت دوبارهٔ
API پایدار پاس‌اند. در هر دو turn مدل سؤال callback لازم را انتخاب کرد؛ fix یا
حل Issue ادعا نشد. source نسخهٔ نامعلوم و relevance محدود داشت؛ R4 و C4 بازند.
ناسازگاری انتظار Python با `context_changed=true` در review ثبت شده و اصل
protocol حفظ شده است. ۱۵/۱۵ metadata همچنان candidate است؛ dev واقعی ۱ و test
واقعی ۰. خرج بیشتر پس از case/rubric و یک مقایسهٔ dev ثبت‌شده انجام شود.

بررسی محلی پس از receipt: ۲۴۲۴ pytest، mapper ۱۳۲/۱۳۲، core/SQLite ۴۹/۴۹،
HTTP/SQLite با interpreter تازه ۴۵۷/۴۵۷ و replay روی دو index موجود ۷۰/۷۰.
این‌ها عملیاتی‌اند. گسترش تست‌های Windows، خواندن seed با encoding پیش‌فرض
در یک تست تازه را آشکار کرد؛ UTF-8 صریح اصلاح شده و پذیرش CI نسخهٔ نهایی
پیش از merge لازم است. جزئیات در verification همان packet ثبت می‌شوند.

| بخش | چیزی که داریم | چیزی که هنوز اثبات نشده |
| --- | --- | --- |
| core — ساسان | قراردادها، correction و GroundedPlan؛ C2a سرویس core و C2d اتصال HTTP به SQLite موجود با outcome اتمیک و approval دقیق؛ HTTP پایدار #30 روی main؛ UI و index محلی در [U3a/P4a، PR #32](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/32) پیاده و با تست‌های مستقل پذیرفته شده‌اند | corpus/index نهایی، اتصال مدل و کیفیت تصمیم روی caseهای ندیده؛ C5 halt |
| داده — آماده‌سازی اولیه ساسان؛ ادامه با حسن | seed اولیه در `streamlit-data-for-dev-test/`: ۲۴۰ Issue، ۱۱۷۸ comment، ۵۶ متن Markdown و ۱۱۷۲ API record؛ adapter حسن و اصلاح اتصال ساسان با #27 و #23 روی main در `ec1a1f0`؛ mapper واقعی ۱۳۲/۱۳۲؛ [بازبینی #35](../experiments/retrieval_acceptance/pr35/README.md) رسید reference را از mapper و index واقعی جدا می‌کند؛ build pilot ۱۴ docs/۳۰ chunk | provenance تمام corpus، segmentation و exclusion نهایی؛ کیفیت retrieval واقعی و split مستقل |
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
| ساسان — C2f/C4/C5، مشترک با P4 | اتصال GroundedPlan در [C2f/PR #34](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/34)؛ پذیرش snapshot نهایی حسن و ارزیابی تصمیم با معیار E2 | receiptهای آفلاین و probe محدود موجود؛ C5 هنوز halt دارد، live عمومی مجاز نیست؛ corpus نهایی و baseline کیفیت مدل جدا باقی‌اند |

[PR #35](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/35) رسید اصلی حسن را بدون تغییر حفظ می‌کند؛ آن رسید `reference_fixture_adapter` است، نه index. [build و replay جدا روی index موجود](../experiments/retrieval_acceptance/pr35/README.md) با همان adapter/core/tracker انجام می‌شود. دو build تازه manifest/snapshot یکسان دارند؛ [verification](../experiments/retrieval_acceptance/pr35/verification-82c39a9.json): mapper واقعی با backend ثابت ۱۳۲/۱۳۲، replay روی همان index موجود ۷۰/۷۰ با ۲۸ query Native و suite تمیز ۲۲۹۸ تست. rule محدود Git، byteهای seed را با `autocrlf=true/false` حفظ می‌کند. این شواهد P4a محدود را تقویت می‌کند؛ R1 نهایی، R2، R4 و E1/E2 همچنان بازند. وضعیت انتشار و CI همان PR مرجع است.

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
- [ ] **R4 — آزمون بازیابی روی dev.** سند کامل/ناقص، نسخهٔ نامعلوم/متفاوت، conflict و خطای retrieval را بررسی کند؛ relevance و پوشش منابع را جدا از کیفیت متن مدل ثبت کند. [مشاهدهٔ واقعی C2g](../experiments/retrieval_context/README.md): query تمیز هم `text_input` نسخهٔ 1.64.0 برای مسئلهٔ multiselect کاربر 1.49.0 آورد؛ gate core ranking/backfill ندارد. خروجی: تست adapter و receipt بازیابی با snapshot/config مشخص، منابع مرتبط multiselect/fragment و رفتار پس از رد نسخهٔ نامرتبط.

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
- [x] **C4a — harness و prefix محدود انتخاب واقعی مدل؛ ساسان.** [بستهٔ نتیجه و review](../experiments/controlled_model_baseline/README.md) runtime/reviewer جدا، ID خنثی و catalog مربوط به bundle فعلی دارد. شش variation یک خانوادهٔ exposed، mock شش‌مسیره و baseline واقعی prefix ثبت شد: ۳ send، ۲ proposal، یک خطا و سه terminal skip؛ follow-up جدا با همان prompt فقط یک سؤال نسخهٔ کامل داد. کل چهار send $0.002845260 تخمینی؛ منابع/کل پاسخ/سؤال، هزینه و محدودیت‌ها review شده‌اند، نمرهٔ انسانی null است. این تیک تحویل محدود را می‌بندد؛ baseline شش‌حالته کامل نشده و C4 مستقل/RAG/test نهایی بازند؛ correction/conflict/stale در live این packet اجرا نشدند.
- [x] **C4b — تداوم تعارض اعلام‌شده پس از refinement؛ ساسان، تحویل محدود آفلاین.** [protocol، مقایسه، receipt و review](../experiments/conflict_continuity/README.md): همان ۱۴ کنترل روی اصل `03225e2` هفت pass/هفت fail و روی `8cc41bf` چهارده pass. سه answer خطرناک مسدود، چهار ask/escalate مجاز با status حل‌نشده و فقط quote جاری؛ ۲۵ کنترل lifecycle/boundary و پنج تست HTTP با provider mock نیز پاس‌اند. repair مجاز status را حفظ و stop نهایی scope را آزاد می‌کند؛ run/case/revision بعدی تازه است. approval/retry/restart امن و request واقعی handoff بررسی شده‌اند. این تیک فقط این رفتار software را می‌بندد؛ تشخیص خودکار تناقض، مدل/RAG واقعی، C4 مستقل و test نهایی بازند؛ هزینه صفر و fixtureهای تاریخی بدون تغییر.
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
  - گزارش دستی تازه روی branch`test/mohammadbehnam-latest-two-case-smoke`، commit`8420a3b`، در وضعیت فعلی بالای این فایل ثبت شد: اجرای تاریخی روی`f8b3106` با API retry؛ انتشار receipt، browser/session recovery، lost-ACK از UI و باقی شواهد T4 هنوز بازند. از این گزارش تکرار تمام smokeها لازم فرض نمی‌شود؛ ابتدا receipt همان اجرای ثبت‌شده منتشر و فقط شکاف‌های باقی‌مانده تکمیل شوند.

شاهد T1–T3: [source ماژول](../src/agent_app/tracker/sqlite_tracker.py)، [۱۶ تست tracker](../tests/test_sqlite_tracker.py)، [pilot آفلاین](../scripts/tracker_pilot.py) و [قرارداد و دستور اجرا](../docs/sqlite-tracker.md). [PR #20](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/20) با `6628758` به branch بهنام و سپس [PR #19](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/19) با `464e55e` به main merge شدند؛ suite branch tracker با ۱۶۹۰ تست و CI انتشار main پاس‌اند. پذیرش مستقل اولیه U3/T4 را نمی‌بست؛ اکنون HTTP/P3 با C2d پذیرفته شد و binding UI/evaluation باقی است. [گزارش بازبینی](../docs/team-integration-review-2026-10-11.fa.md).

وابستگی: ماژول T1–T3 با قراردادهای فعلی موجود است؛ برای T4/UI، ورودی UserTurn، proposal دقیق، review envelope و outcome از مسیر C2d موجود است؛ binding frontend و شواهد evaluation تکمیل شوند. اقدامات فقط روی tracker محلی‌اند.

### محمدحسن — UI، caseها و evaluation

- [x] **U1 — prototype آفلاین.** Streamlit و FastAPI روی main، انتخاب scenario ساختگی و review پیشنهاد موجودند. این checkbox فقط همین prototype را پوشش می‌دهد؛ storage حافظه‌ای و فیک بودن retriever/reasoner همچنان صریح نمایش داده شوند.
- [x] **U2 — ورودی و نمایش کامل.** پیام، اطلاعات صریح/اصلاح‌شده و نتیجهٔ check به قرارداد C2 وصل شوند؛ facts فعال و superseded، unknownها و کل پیشنهاد، summary، منابع و scope نسخه به reviewer نمایش داده شوند. تغییر پرونده pending قبلی را stale کند؛ edit دوباره review/approval بخواهد. انجام‌شده در [PR #13](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/13): هر پیام event با `turn_id` پایدار و `expected_revision` می‌فرستد و retry همان payload را دوباره می‌فرستد؛ فرم fact/correction/withdraw، check، unknown و تغییر محیط؛ پاسخ کوتاه نسخه فقط به سؤال canonical تأییدشده (`awaiting_reply`) با سناریوی آفلاین `ask_version`؛ جدول facts فعال/superseded، receipt آخرین ورودی، و برای reviewer همهٔ سطوح analysis، همهٔ منابع (cited و uncited) با version scope، gapها و conflict groupها وقتی موجودند. شاهد: `tests/test_ui.py` و `tests/test_ui_client.py`. محدودیت: storage حافظه‌ای و adapterهای ساختگی؛ اتصال واقعی U3 است.
- [ ] **U3 — اتصال واقعی UI/API.** انتخاب mock از تنظیم retriever/model/tracker واقعی جدا باشد؛ error و توقف قابل فهم نمایش داده شوند. تست API و smoke test UI، case switching و approval/reject/edit با خودش؛ persistence و مجوز اجرا به tracker سپرده شود. وضعیت: انتخاب‌گر پرونده در نوار کناری اضافه شد (فهرست پرونده‌های همین session با وضعیت هر کدام، تعداد پرونده‌های منتظر review، پیام ارسال‌نشده متصل به پرونده خودش)؛ تست در `tests/test_ui.py`. ماژول T1–T3 و port آفلاین R3 روی main موجودند؛ factory پایدار HTTP/core و outcome C2d با #30 روی main است. U3a credential maintainer، review_id/hash اصلی و retry per-case را وصل کرده؛ P4a index کوچک واقعی با embedding محلی دارد. تنظیم نهایی index/model، smoke مرورگر واقعی و evaluation همچنان باقی است.
- [ ] **E1 — انتخاب و freeze caseها.** حداقل ۱۵ dev و ۱۵ test در سطح خانوادهٔ Issue؛ حداقل ۱۰ سناریوی چندنوبتی که حداقل ۵ تای آن‌ها در test باشند. manifest خانواده‌ها و شناسهٔ نسخهٔ split به حسن داده شود. کیس‌های توسعهٔ قبلاً دیده‌شده مثل 12782 و duplicate آن 12629، test مستقل نیستند؛ فهرست exposure بسته هم بازبینی شود. وضعیت جاری: [packet سه dev](../data/evaluation/dev-three-v1/split-manifest.json)، سه خانوادهٔ exposed و صفر test، هنوز draft و بدون freeze نهایی؛ [راهنمای review و chronology](../docs/dev-three-baseline.fa.md). [manifest تاریخی pilot](../data/evaluation/split-manifest.json) با یک dev و صفر test برای حفظ receiptهای قدیمی تغییر نکرده؛ پروندهٔ #12782 در این دو packet یک case است و دوبار شمرده نمی‌شود. seed اولیه در `streamlit-data-for-dev-test/` با #23 روی main موجود است؛ باقی خانواده‌ها از همان داده‌ها انتخاب شوند. انتخاب اولیه منتظر R1 یا index نمی‌ماند؛ provenance و linkage با حسن پیش از freeze بررسی می‌شوند.
- [ ] **E2 — fixture و rubric پیش از اجرا.** case_id، منبع/زمان، ورودی قابل مشاهده در شروع، پاسخ‌های بعدی به‌ترتیب، factهای معلوم، gap کاربر/منبع، منابع مجاز، تصمیم‌های قابل قبول و انتظار عملیاتی ثبت شوند. جواب/label/gold برای runner/reviewer است و وارد پیام مدل یا index نمی‌شود. schema با ساسان هماهنگ شود؛ مسیر موجود `data/evaluation/` مبنا باشد. placeholder قبلی `dev_cases.json` حذف شد؛ پیش‌نویس schema در [`data/evaluation/README.md`](../data/evaluation/README.md) و نخستین fixture آن (P1) ثبت شده‌اند. هماهنگی schema با ساسان هنوز باز است. [rubric v1](../docs/evaluation-rubric-v1.md) (`e2-rubric-v1`، ۱۵ اکتبر) پیش‌نویس ساسان را مبنا می‌گیرد و خواسته‌های او را اضافه می‌کند: بررسی همهٔ ادعاهای مهم با متن و نسخهٔ منبع حتی بیرون citation، نمرهٔ جدای پیشنهاد مدل و متن edited/released، gap کاربر/منبع با ادامهٔ مورد انتظار برای هر نوع سؤال، و gold جدا برای شواهد ثابت و index واقعی. هنوز freeze نشده؛ پشتیبانی runner از gold چندشرطی پیاده نشده است.
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
- [x] **C2f — GroundedPlan در HTTP پایدار، پذیرش محدود.** کد و شواهد در [PR #34](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/34)؛ وضعیت انتشار و CI همان PR مرجع است. [protocol ثبت‌شده پیش از اجرا](../experiments/grounded_http_acceptance/protocol-v1.json) و [دستور اتصال/حدود](../docs/grounded-persistent-pilot.fa.md): همان fixture exposed چهارمرحله‌ای، gateway جعلی و ledger موقت؛ baseline `3c92b12` ده کنترل از دوازده و نسخهٔ جدید دوازده از دوازده. بهبودها label درست و cleanup هر run هستند؛ baseline از قبل injection را اجرا می‌کرد. اصلاح نسخه، شاهد آخرین round، approval قدیمی، restart/retry و edit/reject پاس‌اند؛ AppTest و TCP با index واقعی نیز پاس شدند. [probe واقعی ثبت‌شده](../experiments/grounded_http_acceptance/live-result-0b962de.json) فقط یک درخواست توسعه و سؤال نسخه بود، هزینهٔ تخمینی $0.000650430؛ [review جدا](../experiments/grounded_http_acceptance/live-review-0b962de.json). این کیفیت مدل/RAG یا test نهایی نیست؛ ID دقیق serving model در receipt اول نامشخص است و C5 halt/hold قبلی حفظ شده است.
- [x] **C2g — context فعلی retrieval و binding کنترل نسخه.** [protocol، receipt و حدود](../experiments/retrieval_context/README.md): تاریخچهٔ reasoning خام حفظ، query اولیه از facts فعال/پیام اخیر/topic جدا؛ ده variation تألیفی با همان baseline، همهٔ کنترل‌های query ۲/۱۰ به ۱۰/۱۰. دو send آنلاین همان سؤال callback را انتخاب کردند و منبع نامرتبط نسخهٔ 1.64 برای کاربر1.49 را آشکار کردند؛ افزایش کیفیت تصمیم/RAG ادعا نمی‌شود. forwarding سیاست موجود `exact_user_version` به HTTP و انتخاب آن در backend توصیهٔ نسخهٔ فعلی، پس از probe با ۲۱ تست آفلاین پذیرفته شد؛ default `all` برای comparison باقی است. فیلتر ranking/backfill نیست و corpus/داوری/test نهایی را نمی‌بندد.

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

### وضعیت انتشار C4h3/E2r

[بررسی محلی](../experiments/core_source_capacity_v1/verification-v1.json):۳۸۲۷pytest،
Ruff،سهdemo وHTTP/SQLite۴۵۷/۴۵۷ پاس. تغییرات در [PR #54](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/54)
رویbranch`feat/core-source-capacity` منتشر شدند. شرط انتظار CI با دستور صریح
۱۵ اکتبر ساسان جای خود را به review و verification محلی داد؛ این به معنی CI
موفق یا رفع Billing نیست. درhead`6a4bd26`، هر دوjob قبل از شروع با خطای Billing
متوقف شدند؛ اصل verification و receiptها حفظ می‌شوند.
