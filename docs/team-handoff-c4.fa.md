# تحویل C4 به تیم و agentهای کاری

این کار سهم مستقل ساسان است: اجرای انتخاب واقعی مدل روی شش variation موجود
V8/V9 با شواهد ثابت و core فعلی. این بسته تا قبل از تحویل جدید فقط با proposalهای
تألیفی اجرا شده بود؛ fixtureها و protocolهای تاریخی بدون تغییر می‌مانند.
منشأ همهٔ variationها خانوادهٔ exposed #12782/#12629 است؛ انتخاب مکانیزم از
شناخت Issue/comment/workaround تأثیر گرفته، ولی جواب و workaround داخل شاهد
و ورودی قابل مشاهده نیست. این خانواده و case/answer/outcome/duplicateها وارد
corpus واقعی یا test مستقل نشوند.

وضعیت جاری در [PR #39](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/39):
baseline واقعی سه send داشت؛ دو سؤال callback با منابع جاری، یک خطای provider
و سه condition اجرا‌نشده. [رسید و review جدا](../experiments/controlled_model_baseline/README.md)
حفظ‌اند. [follow-up یک‌درخواستی](controlled-output-cap-followup.fa.md) با همان
prompt برای نسخهٔ نامشخص روی `07d759f` پس از CI اجرا شد: سؤال نسخهٔ لازم،
کاربرد منابع تأییدنشده و خروجی کامل. جمع دو اجرای جدا چهار send با هزینهٔ
تخمینی $0.002845260؛ این تکمیل یک درخواست است، نه کیفیت RAG یا موفقیت test.
مشکل import مستقیم core در process تازه هم با همان API عمومی اصلاح شده؛
این تغییر ربطی به علت خطای provider ندارد. نتیجهٔ مدل را با تعداد pytest یا
mock موفق یکی نگیریم؛ C4 مستقل و کارهای evaluation/corpus هنوز بازند.

## فایل‌هایی که تغییر کرده‌اند

- `testing/controlled_decision_inputs.py`: projection فقط state/message/bundle/
  catalog از fixture ثابت؛ reviewer/gold و proposalهای تألیفی وارد مدل نمی‌شوند.
- `testing/controlled_model_baseline.py` و wrapper: dry/preflight، core/gateway
  واقعی با منابع fixture، ledger و ثبت خروجی/هزینه؛ tracker/action صفر است.
- `experiments/controlled_model_baseline/`: protocol تازه، inventory reviewer،
  receipt و review جدا و پروتکل محدود follow-up. فایل‌های قدیمی بازنویسی نمی‌شوند.
- `orchestration/__init__.py`: public exportها lazy هستند؛ `GroundedReasoner`
  را می‌شود اول import کرد. اسم، قرارداد و هویت کلاس‌ها حفظ شده‌اند.
- plan و مستندات core: task مالک‌ها، محدوده و معنی نتایج تازه.

این تحویل shared contract یا port را عوض نمی‌کند و adapter جدید RAG/tracker/UI
نمی‌سازد. catalog سؤال‌ها و conflictهای این آزمایش دستی‌اند؛ تشخیص عمومی نقص
اطلاعات یا تناقض از متن اندازه‌گیری نمی‌شود. fixed retriever سرچ index واقعی
انجام نمی‌دهد؛ query/roundها فقط رفتار core روی bundleهای ثبت‌شده‌اند.

## گرفتن نسخه و جلوگیری از تداخل

بعد از merge شدن PR مربوط، در checkout تمیز `git fetch origin` و branch خود را
با `origin/main` sync کنید؛ تغییرات local را حفظ کنید. main جدید و PR/CI مرجع
در plan مشخص است. agent هر نفر ابتدا `AGENTS.md`، بخش جاری plan و این فایل را
بخواند. `data/evaluation/`، corpus/index و tracker صاحب خود را دارند؛ فایل‌های
این baseline و oracle آن را هم‌زمان بازنویسی نکنید. برای تغییر رفتار مدل یا
قواعد rubric، protocol تازه با disclosure جدا لازم است؛ نتیجهٔ قدیمی را پاک نکنید.

## کار بعد هر نفر

- حسن: source coverage و version-aware ranking/filter/backfill را روی dev
  مستقل بررسی کند؛ منبع 1.64 برای کاربر1.49 در C2g مشاهده شده. این packet
  fixture جای R4 یا corpus نهایی نیست. exclusion خانواده‌ها با محمدحسن ببندد.
- محمدحسن: سه dev case و rubric مستقل را ادامه دهد. reviewer inventory این
  packet نمونهٔ تفکیک gap کاربر/منبع است؛ gold/سؤال آینده را وارد ورودی مدل
  نکند. قضاوت usefulness انسانی و review original/edit مستقل هنوز لازم است.
- بهنام: smoke دو-case UI/API/SQLite از نسخهٔ جدید main را ادامه دهد؛ retry،
  correction، approval قدیمی و صفر بودن action تکراری. قرارداد tracker ثابت است.
- ساسان: protocol، baseline مدل، بررسی کل پاسخ/quote/scope/question، هزینه و
  محدودیت‌ها را ثبت کند؛ فقط اگر baseline مسئلهٔ مشخصی نشان داد بهبود بعدی را
  روی همان ورودی‌ها مقایسه کند. framework/agent تازه فعلاً مبنا نیست.

## معنی گزارش

mock فقط plumbing است. اجرای واقعی انتخاب مدل در همین دامنهٔ controlled و
با catalog دستی گزارش می‌شود؛ از روی JSON معتبر یا source hash، کیفیت معنایی
یا صحت منبع نتیجه نمی‌گیریم. تعداد درخواست، condition، خانوادهٔ Issue، decision
admissibility، quote binding، review انسانی و هزینه denominator جدا دارند.
اجرای ناقص/بودجه‌نخورده با skip/error ثبت می‌شود و امتیاز موفقیت ندارد.
ledger اصلی، عدم‌قطعیت $0.02 و halt قبلی حفظ‌اند؛ API عمومی همچنان C5 را لازم دارد.
