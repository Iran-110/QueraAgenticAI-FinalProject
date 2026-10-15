# dev گسترده‌تر و کیفیت توضیح Enum — C4i/E2v

متن Enum کوتاه‌تر شد، ولی بهبود قابل اعتماد جواب اثبات نشد. مسیر موجود
`AnalysisResult + compiled_rules` را با مسیر موجود `GroundedPlan` مقایسه کردیم؛
اولی گاهی پاسخ روان اما بی‌پشتوانه ساخت. آن را به‌عنوان تنظیم بهتر پیشنهاد
نمی‌کنیم و هیچ default، factory، prompt، renderer یا قرارداد عمومی عوض نشده است.

## چه چیزی را سنجیدیم؟

سه خانوادهٔ dev قبلی و چهار خانوادهٔ مکمل #4713، #5618، #7206 و #9487 را
آماده کردیم. خانوادهٔ Enum دو شرط جدا دارد: guide کامل و همان ورودی بدون guide.
در مجموع ۷ خانواده، ۸ شرط و ۱۶ وضعیت جاری داریم؛ هر وضعیت با هر دو مسیر و
در دو تکرار متوازن اجرا شد: **۶۴ invocation، نه ۶۴ مسئلهٔ مستقل**.

قبل از مدل، اطلاعات معلوم، کمبود اطلاعات کاربر، کمبود سند و تصمیم‌های قابل قبول
در [protocol](../experiments/core_broader_dev_v1/protocol-v1.json)،
[ورودی‌ها](../data/evaluation/supplemental-core-dev-v1/input-cases-v1.json) و
[معیارها](../data/evaluation/supplemental-core-dev-v1/review-criteria-v1.json)
ثبت شدند. اصلاح‌ها با `propose_user_turn` ساخته شدند؛ هر snapshot یک اجرای مستقل
است. پیام اصلاحیِ تألیفی را پاسخ خودکار به سؤال ساخته‌شدهٔ مدل جا نزده‌ایم.

هر دو مسیر همان CaseState، پیام، bundle کاملِ فعلی و `ProposalRequirements`
متعلق به caller را گرفتند. policy، schema و نمایش آن‌ها فرق دارد؛ بنابراین این
آزمایش اثر یک prompt یا serializer منفرد را جدا نمی‌کند. هر دو حداکثر دو attempt،
دو retrieval round و هشت step داشتند. refinement همان bundle ثابت را پس داد؛
مدل در این اجرا جست‌وجوی واقعی تازه انجام نداد.

## نتیجهٔ آنلاین

| مورد | GroundedPlan | compiled AnalysisResult |
| --- | ---: | ---: |
| invocation برنامه‌ریزی‌شده و اجراشده | ۳۲ | ۳۲ |
| پیشنهاد `awaiting_approval` | ۳۲ | ۲۸ |
| بدون پیشنهاد نهایی، `ModelOutputInvalid` | ۰ | ۴ |
| درخواست واقعی به provider | ۳۸ | ۳۷ |
| تخمین هزینهٔ محلی USD | 0.031572255 | 0.043193040 |
| معیار کامل Enum با guide | ۰ از ۴ | ۰ از ۴ |
| median طول draft همان شرط | ۱۴۴۹۴ | ۷۱۸٫۵ |

کل **۷۵ send** با تخمین **$0.074765295** ثبت شد. ۶۰ پیشنهاد فقط منتظر review
ماندند؛ **هیچ approval، release، edit یا action اجرا نشد**. همهٔ failureها و
attemptهای اضافی حفظ شدند. عدد «پیشنهاد ساخته شد» نمرهٔ کیفیت نیست.

معیار Enum از قبل این بود: حداقل ۳ از ۴ پاسخِ مسیر compiled باید توضیح مستند
identity/redefinition، قدم عملی محدود، caveat مربوط به edit/reload، بیان روشن
فرضیه و محدودیت نسخه داشته باشد؛ بیشتر از کنترل و با median طول حداکثر ۳۰۰۰.
کوتاه‌شدن به این معیار نرسید. draftهای compiled طول‌های ۸۴۲، ۸۳۸، ۵۰۲ و ۵۹۹
داشتند، اما هیچ‌کدام همهٔ شرط‌ها را نداشتند.

نمونه‌های مهم برای review:

- در یک پاسخ Enum، رفتار به‌عنوان علت تأییدشده توضیح داده شد، با وجود اینکه
  guide فقط الگوی مفهومی و قدم قابل بررسی می‌دهد، نه fix اثبات‌شده برای runtime کاربر.
- پس از اصلاح نسخه، `enumCoercion` پیشنهاد شد؛ مثال کاربر widget ندارد و متن
  مربوط به تبدیل مقدار برگشتی widget، پشتوانهٔ این توصیه برای Session State مستقیم نیست.
- در یک تکرار، ادعاهای نسخه‌ای دربارهٔ 1.29 و 1.31 به توضیح اضافه شدند که کاربرد
  آن‌ها برای مسئلهٔ فعلی با bundle اثبات نمی‌شود.
- بدون guide، مسیر compiled هم از متن عمومی Session State به تشخیص Enum رسید؛
  وجود citation درست به‌تنهایی این استنتاج را مستند نمی‌کند.
- در devهای مکمل، بازپرسیدن اطلاعات معلوم باعث رد بعضی خروجی‌ها شد؛ بعضی
  خروجی‌های پذیرفته‌شده نیز از سند عمومی، علت launch، restart یا faded rendering
  نتیجه گرفتند. faithful بودن نقل‌قول‌های کنترل هم به‌تنهایی به معنی انتخاب
  بهترین تصمیم یا مفیدبودن آن نیست.

بررسی همهٔ surfaceها و candidateهای parsed، شامل خروجی‌های بعداً ردشده، در
[semantic review](../experiments/core_broader_dev_v1/semantic-review-v1.json) است.
این review را assistant با اطلاع از روش و هم‌پوشانی پیاده‌سازی انجام داده؛
review انسانی مستقل نیست. متن خام نامعتبر نگهداری نشده و بازسازی نمی‌شود.
**usefulness انسانی هنوز null است.**

در این دسته‌بندی توصیفی، از ۲۸ پیشنهاد موجودِ compiled، ۱۷ مورد نقص مهم در
پشتیبانی ادعا، وفاداری به اطلاعات کاربر یا کاربرد منبع داشتند؛ ۱۰ مورد سؤال
ثبت‌شدهٔ ضروری پرسیدند و یک ارجاع محتاطانه، با وجود guide، راهنمایی موجود را
استفاده نکرد. چهار اجرای دیگر پیشنهاد نهایی ندارند. این شمارش نمرهٔ خودکار
entailment یا نمرهٔ usefulness انسانی نیست. هر ۷۵ attempt حفظ شده: ۷۲ candidate
typed/expanded و سه شکست representation بدون متن خام؛ هفت candidate parsed
نامناسبِ بعداً ردشده نیز در review آمده‌اند.

## مرز داده و exclusion

چهار خانوادهٔ مکمل از همهٔ componentهای رزروشدهٔ ۱۵ dev/۱۵ test و closure سه
dev قبلی جدا انتخاب شدند. هر شش report بررسی‌شده، حتی دو مورد انتخاب‌نشده، در
[exposure](../data/evaluation/supplemental-core-dev-v1/exposure-v1.json) ثبت‌اند.
فقط report body دیده شد؛ comment/outcome برای ساخت gold مصرف نشد. body کش‌شده
ممکن است ویرایش شده باشد و اصل اولین پیام تأیید نشده است. این packet جای split
نهایی محمدحسن را نمی‌گیرد؛ خانواده‌های بررسی‌شده دیگر test ندیده محسوب نمی‌شوند.
closure ارتباط‌ها محافظه‌کارانه است؛ review کامل یا تأیید همهٔ duplicateها ادعا
نمی‌شود. linkage بیرونی و بخش‌های پاسخ‌مرتبط release note پیش از build تازه
باید جدا بررسی شوند و در این bundleها استفاده نشده‌اند.

guide پاسخ‌مرتبطِ Enum همان fixture قبلی است و فقط در شرط دارای guide وارد شد؛
از پاسخ همان Issue برای رسیدن به این شاهد کمک گرفته شده و این محدودیت حفظ شده
است. guide، Issueها، جواب‌ها و duplicateها وارد corpus واقعی نشدند. bundleهای
مکمل از index موجود ۱۸ source/۳۶ chunk روی کپی مستقل تهیه و **قبل از مدل freeze**
شدند. این یک مقایسهٔ کنترل‌شده با شواهد ثابت است؛ نمرهٔ RAG واقعی، test نهایی
یا موفقیت end-to-end نیست.

## خطاهای آماده‌سازی هم حفظ شدند

registration اولیه به‌اشتباه input=49152 اعلام کرده بود؛ config موجود آن را
قبل از API رد کرد. [amendment پیش از هزینه](../experiments/core_broader_dev_v1/bound-amendment-v1.json)
حد موجود ۳۲۷۶۸ و output=2048 را نگه داشت. همهٔ ۶۴ payload normal/repair زیر همین
حد جا شدند؛ بیشینهٔ برآورد ۳۱۷۶۴ بود. شاهدی بریده نشد و guard بالا نرفت.

یک بار Chroma هنگام خواندن index اصلی دو فایل ذخیره‌سازی را بازنویسی کرد.
[خطا](../experiments/core_broader_dev_v1/preparation-first-failure-v1.json)
حذف نشد و ادعای بازیابی byteهای تاریخی نداریم: ۱۷ از ۱۹ hash اصلی همچنان برابرند
و دو اختلاف ثبت شده‌اند. [بررسی مستقل](../experiments/core_broader_dev_v1/index-recovery-review-v1.json)
با ۱۸۲ کنترل، کل ۱۸ source، ۳۶ chunk، metadata، vector و exclusion را با manifest
قبلی برابر یافت. سپس یک [epoch آماده‌سازی جدید](../experiments/core_broader_dev_v1/preparation-amendment-v1.json)
پیش از method/API با ۱۹ hash جاری ثبت شد. تمام خواندن‌های بعدی این مطالعه از کپی بودند؛
هر ۱۹ hash همین epoch در طول مطالعه ثابت ماندند. برابری منطقی، جای ادعای برابری
byteهای تاریخی را نمی‌گیرد. clientهای production پروژه در این کار به copy-only
تبدیل نشده‌اند؛ آن اتصال‌ها و تنظیم‌های runtime عوض نشده‌اند.

## هزینه، تست و بازبینی

[cost review](../experiments/core_broader_dev_v1/cost-review-v1.json) با ۳۰۲۷ کنترل
read-only، حفظ همهٔ ۵۹۱ reservation قبلی و ۱۴ جدول را بررسی کرد. ۱۶ scope بسته
شدند؛ ۷۵ slot مصرف و ۵۳ slot استفاده‌نشده برای همیشه claimed ماندند. pending و
uncertainty تازه صفر است؛ دو hold قدیمی $0.0233792، halt عمومی و سقف $4.50 حفظ
شدند. تخمین settled محلی در پایان $0.548204250 است؛ invoice یا جمع هزینهٔ همهٔ
لپ‌تاپ‌ها تأیید نشده و C5 حل‌شده نیست. هر ۷۵ wire واقعی بدون `response_format`
بودند؛ این را موفقیت JSON mode گزارش نمی‌کنیم.

۴۹۸۱ pytest، Ruff روی ۳۳۷ فایل، سه demo و ۴۵۷/۴۵۷ پذیرش آفلاین HTTP/SQLite پاس‌اند؛
[verification](../experiments/core_broader_dev_v1/verification-v1.json) commitها و
hashها را ثبت می‌کند. تست‌های registry اکنون به فایل‌های ignored ماشین وابسته
نیستند: byteهای مصنوعیِ صریحاً نامعتبر برای Chroma در root موقت ثبت می‌شوند و
mutation همچنان guard را می‌شکند. این تست واحد، اثبات native RAG نیست؛ بررسی
native روی کپی و receipt آماده‌سازی جداست. Billing همچنان مانع اجرای hosted CI
است؛ CI سبز ادعا نمی‌شود.

## قدم بعدی

این دور دلیل مشخصی برای تغییر معماری چند-agent یا اضافه‌کردن framework نداد.
مسئلهٔ واقعی مرز **ادعا، متن منبع، کاربرد برای وضعیت کاربر و فرضیه** است؛ یک
schema معتبر آن را حل نمی‌کند. قبل از هر default تازه، باید همین counterexampleها
در یک طراحی عمومیِ کنترل ادعا پوشش داده شوند و دوباره روی dev بررسی شوند؛ تغییر
دیگر در ترتیب منبع یا prompt برای گرفتن نمره از همین Enum پیشنهاد نمی‌شود.

محمدحسن می‌تواند [worksheet انسانی](../experiments/core_broader_dev_v1/human-review-v1.json)
را پر کند و پذیرش خانواده‌های مکمل را با split نهایی تطبیق دهد. حسن همچنان مالک
relevance، source coverage و build/exclusion بعد از freeze نهایی است. تسک‌های T4
بهنام جابه‌جا نشده‌اند. E1، E2، E4، E5 و C5 با این مطالعه بسته نمی‌شوند.
