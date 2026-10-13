# baseline مدل با شواهد ثابت — پیش‌ثبت

این مرحله رفتار مدل واقعی را از replay پیشنهادهای تألیفی V8/V9 جدا می‌کند.
همان شش وضعیت توسعه روی خانوادهٔ exposedِ Issue #12782 و duplicate قطعی #12629
با `SupportEngine` فعلی، planner مدل و renderer واقعی بررسی می‌شوند. هنوز هیچ
نتیجه، تعداد اجرای موفق، هزینهٔ تازه یا امتیاز کیفیتی برای این مرحله ثبت نشده
است. commit و protocol جدید باید قبل از اجرای ثبت‌شده کامل و push شوند.

شواهد از bundleهای ثابت و از پیش ثبت‌شده می‌آیند؛ این آزمایش کیفیت retrieval،
corpus واقعی، شش Issue مستقل یا موفقیت test نهایی را اندازه نمی‌گیرد. شاخص اصلی
مشاهدهٔ تصمیم و پشتیبانی محتوای پیشنهاد در وضعیت‌های کنترل‌شده است؛ baseline
جدید نیز به‌تنهایی افزایش کیفیت نسبت به مدل یا معماری دیگری را اثبات نمی‌کند.
ساختار تک agent حفظ می‌شود و framework تازه‌ای اضافه نمی‌شود.

## ورودی و منشأ

صورت visible، stateها و متن منابع از packetهای ثابت
[V8](../experiments/decision_quality/cases-controlled-v8.json) و
[V9](../experiments/decision_quality/cases-grounding-v9.json) گرفته می‌شوند.
شناسهٔ اجرایی case به aliasهای بی‌معنای `c4-condition-01..06` تبدیل می‌شود؛
fieldِ `condition_id` و شناسهٔ اصلی case فقط در registry و معیار reviewer
می‌مانند تا مدل از نام «stale/removed» در شناسهٔ اجرایی از قبل تصمیم را حدس
نزند. attribution خامِ `source_ref` و `turn_id` حفظ می‌شود؛ نام correction در
آن‌ها همان اصلاح صریح پیام کاربر است، نه خبر آینده. باقی state، پیام خام و منابع
حفظ می‌شوند. همراه projection catalogِ pool جاری، این یک material projection
جدید و پین‌شده است؛ byte-identical بودن ورودی runtime قدیمی V9 ادعا نمی‌شود.
نویسنده قبلاً body، workaround گزارش‌شده و commentهای همان Issue را خوانده
است؛ انتخاب مکانیزم و منابع **answer-informed** است. workaround و پاسخ همان
Issue عمداً در پیام visible و evidence نیستند. «full» یعنی شاهد رسمی مکانیزم
موجود است؛ نه اینکه کل گزارش اصلی، برنامهٔ کامل، علت یا fix مستقل را داریم.
کد کوچک کار می‌کند؛ شکست فقط دربارهٔ full app گزارش شده و callback آن غایب است.

catalogِ gapها، ضرورت سؤال، متن سؤال‌ها و گروه conflict در V9 به‌دست Codex
تألیف شده است. projection پین‌شدهٔ متناسب با **pool واقعاً جاری** آن به مدل
داده می‌شود؛ خبر تغییر آیندهٔ bundle وارد نوبت قبلی نمی‌شود. مدل از این catalog
انتخاب می‌کند؛ کشف خودکار
کمبود اطلاعات یا تناقض را نمی‌سنجیم. حتی نام‌های خاص state در سؤال callback
از همین catalog می‌آیند. conflict، یک متن false و صریحاً synthetic در کنار
release note رسمی است؛ تناقض طبیعی میان دو سند رسمی محسوب نمی‌شود.

[فایل معیار سناریو، مختص reviewer](../experiments/controlled_model_baseline/scenario-review-v1.json)
پیش از اجرا، knownها، شکاف کاربر/منبع، تصمیم اول/نهایی، سؤال و حدود ادعا را
ثبت می‌کند. **این فایل وارد مدل، prompt یا wire نمی‌شود.** driver فقط hash
byteهای آن و ترتیب conditionها را برای registration بررسی می‌کند؛ labelها،
پیشنهادهای تألیفی قبلی، نتیجه‌های پرداخت‌شده و معیار reviewer ورودی مدل نیستند.
فایل معیار در Git عمومی ثبت می‌شود؛ «مختص reviewer» یعنی از payload مدل کنار
گذاشته شده، نه اینکه فایل یا repository محرمانه است.
محتوای visible مدل همان state/message/bundle جاری، projection ثبت‌شدهٔ catalogِ V9 و
`ReasoningContext` معتبر است.

## انتظار هر وضعیت پیش از مدل

| وضعیت | اطلاعات کاربر و کمبود اصلی | شاهد ثابت و تصمیم قابل قبول |
| --- | --- | --- |
| full | نسخهٔ 1.50.0 و Python 3.12.9 معلوم؛ callback، ترتیب update و مثال واقعاً failing غایب | default، fragment و release 1.50 حاضرند؛ answer محدود و مستند، سؤال لازم یا refinement؛ نتیجهٔ نهایی answer محدود، ask یا escalate |
| key evidence removed | همان اطلاعات کاربر؛ نقص سند، مجهول بودن نسخه نیست | release note در هر دو pool حذف است؛ ask/escalate نهایی، retrieval بیشتر فقط با ظرفیت؛ default/fragment علت یا مکانیزم حذف‌شده را ثابت نمی‌کنند |
| unknown version mixed | Python معلوم، نسخهٔ نصب Streamlit نامعلوم؛ callback همچنان غایب | اسناد 1.49.0/1.50.0 و snapshot بدون نسخه؛ سؤال نسخه یا gap لازمِ app، refinement با ظرفیت؛ ask/escalate نهایی، بدون حدس نسخه از منابع |
| version correction | active کاربر 1.49.1؛ مقدار 1.50.0 و شاهد قبلی superseded | poolها هنوز 1.50.0 هستند؛ سؤال app یا retrieval و answer صرفاً تاریخی/مقایسه‌ای؛ تطبیق خاموش 1.49.0 با patchِ 1.49.1 مجاز نیست |
| same-version synthetic conflict | نسخهٔ 1.50.0 معلوم؛ gapهای app پابرجا | conflict دستی هنوز unresolved است؛ ask/escalate یا retrieval اول با ظرفیت؛ answer تا وقتی conflict حاضر است مجاز نیست |
| refinement stale source | نسخهٔ 1.50.0 معلوم؛ علت app هنوز نامعلوم | با pool اول همان answer محدود/ask/escalate وضعیت full مجاز است؛ اگر pool دوم واقعاً برسد release حذف است و ask/escalate نهایی مطلوب؛ فقط pool جاری قابل citation است |

مجموعهٔ دقیق تصمیم‌ها و شرط‌ها در فایل معیار آمده است؛ JSON معتبر، label
درست و citation ID موجود به‌تنهایی پاسخ پشتیبانی‌شده نمی‌سازند. در وضعیت removed
یا **بعد از رسیدن به pool دوم** stale، یک quotation بی‌خطر ممکن است از نظر
محتوا امن باشد ولی معیار تصمیم نهایی مطلوب را پاس نکند؛ این دو را جدا گزارش
می‌کنیم. تصمیم نهایی با `allowed_final_decisions_by_retrieval_round` و round
واقعاً طی‌شده سنجیده می‌شود. پیام اولیه و pool اول stale عین full هستند و
جست‌وجو را اجباری نمی‌کنند؛ answer محدود پیش از refinement مشروع است و نباید
با علم مختص reviewer به حذف آینده جریمه شود. catalogِ نوبت اول نیز نباید حذف آینده را
اعلام کند؛ این projection جدید با pin خود ثبت می‌شود و V9 تغییر نمی‌کند.
اگر مدل در stale بلافاصله answer محدود، سؤال یا ارجاع بدهد،
مسیر refinement و guard شاهد قدیمی **اجرا نشده** است و پاس آن ادعا نمی‌شود.

سیاست این baseline برابر `evidence_scope="all"` است تا packet ثابت و امکان
comparison تاریخی حفظ شوند. binding جداگانهٔ backend live با
`exact_user_version` جزو این آزمایش نیست. نسخهٔ metadata فقط scope را تعیین
می‌کند: source نامرتبط تاریخی است، نسخهٔ کاربر نامعلوم و source بدون نسخه
unconfirmed هستند؛ metadata مساوی نیز علت، truth یا fix را اثبات نمی‌کند.

## ظرفیت اجرا و توقف

هر condition از engine واقعی با سقف دو attempt مدل، دو round retrieval، دو
query در هر round و هشت step استفاده می‌کند. تصمیم اول واقعاً از مدل می‌آید؛
refinement اجباری نیست. در صورت انتخاب آن، bundle دوم ثبت‌شده استفاده می‌شود؛
برای pool تکراری، retrieval اطلاعات تازه ایجاد نمی‌کند. repair خروجی malformed
همان attempt دوم را مصرف می‌کند و اجازهٔ attempt سوم، پول اضافی یا fallback
به source قدیمی نمی‌دهد. `retrieve_more` فقط با `can_refine` و ظرفیت واقعی
مجاز است؛ budget ممکن است ادامهٔ یک run را متوقف کند.

ابتدا plumbing هر شش condition با gateway mock و بدون key/ledger تولیدی بررسی
خواهد شد. این شش replay، شش پاسخ واقعی مدل نیستند؛ `real_provider_requests=0`
و `paid_api_cost_usd=0` دارند. sendها و هزینه‌های ledger mock فقط bookkeeping
مصنوعی‌اند و خرج واقعی API محسوب نمی‌شوند. batch پرداخت‌شده حداکثر شش
send دارد و فقط prefix مرتبِ واجد شرایط را با ledger اصلی و grant موجود اجرا
می‌کند. آخرین remaining ثبت‌شده همان grant برابر $0.00491479 بود؛ preflight
جدید و protocol پین‌شده eligibility دقیق و reservation هر request را تعیین
می‌کنند. تکمیل هر شش وضعیت تضمین نشده است؛ تعداد registered، visited، complete،
incomplete و unvisited باید جدا ثبت شوند.

halt عمومی C5، hold نامعلوم قدیمی $0.02 و سقف موجود حفظ می‌شوند؛ reset، unhalt،
grant تازه یا ledger موازی مجاز نیست. وضعیت terminal/uncertain تازه، ادامهٔ
batch را متوقف می‌کند. نتیجهٔ ناقص حفظ می‌شود و مجوز rerun یا retune نیست.
هزینهٔ تازه از request ID واقعی، usage، serving model و settlement ثبت خواهد
شد؛ مبلغ واقعی حساب تا شاهد خارجی نامعلوم است. ordinary live startup همچنان
به C5 وابسته است. stage، approval و اجرای tracker در این آزمایش انجام نمی‌شود.

## داوری و مرز نتیجه

پس از اجرا، کل `user_draft`، summary، rationale، claimهای لینک، quotationها،
scope و handoff با hash دقیق بررسی می‌شوند. ادعای material بدون پشتیبانی، علت
یا fix برنامهٔ غایب، نسخهٔ قدیمی به‌عنوان نسخهٔ فعلی، source حذف‌شده، سؤال دربارهٔ
اطلاعات معلوم یا درخواست یافتن docs از کاربر، شکست محتوا/سؤال است. سؤال باید
دربارهٔ اطلاعات غایبِ قابل ارائه توسط کاربر باشد؛ کمبود سند به retrieval یا
بررسی maintainer تعلق دارد. تکرار مثال کارکرده، reproduction شکست را ثابت نمی‌کند.

ایمنی محتوا، admissibility تصمیم، مسیر طی‌شده و توقف عملیاتی جدا ثبت می‌شوند.
اجرای انجام‌نشده یا متوقف‌شده با expected answer پر نمی‌شود. معیارها پس از
مشاهدهٔ خروجی تغییر نمی‌کنند. بازبینی assistant جای داوری مستقل انسانی نیست؛
امتیاز usefulness و rubric انسانی فعلاً `null` است و original/edit بعدی باید
داوری جدا با hash خودشان داشته باشند.

این فایل و caseها، outputها، جواب‌ها، comment/outcomeها و duplicateهای خانوادهٔ
ارزیابی وارد corpus واقعی RAG نشوند. corpus/exclusion و منابع مرتبط حسن، case
و rubric مستقل محمدحسن، شواهد tracker بهنام و حل حسابداری C5 همچنان وابستگی‌های
تیم‌اند. نتیجه، هزینه، review و CI فقط پس از اجرای ثبت‌شده به این سند افزوده
خواهند شد.
