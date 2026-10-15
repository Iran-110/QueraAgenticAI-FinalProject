# C4j/E2w — مرز نقل منبع، گزارش کاربر و ادعای کاربرد

این تحویل یک مسیر **آزمایشی و صریح** برای core است. مدل به‌جای نوشتن توضیح فنی
آزاد، decision، قطعه‌های منبع جاری و factهای فعال USER را انتخاب می‌کند؛ core
همهٔ فیلدهای `AnalysisResult` را می‌سازد. این محدودیت جلوی تولید cause/fix و
نسبت‌دادن ادعای ساخته‌شده به citation را می‌گیرد؛ relevance، کامل‌بودن caveatها
و مفیدبودن انتخاب‌ها همچنان نیاز به review دارند. **مقایسهٔ آنلاین بهبود کیفیت
Enum را نشان نداد و این مسیر به تنظیم پیش‌فرض محصول تبدیل نشده است.**

## قرارداد داخلی و اتصال

`reasoning/claim_plan.py` شامل `ClaimRequest`، `ClaimPlan` و `ClaimReasoner` است.
هیچ shared contract یا port جدیدی لازم نیست. شش فیلد plan عبارت‌اند از
`context_sha256`، `decision`، `passages`، `user_facts`، `question_name` و
`retrieval_queries`. passage یک جفت index منبع/بلاک در **همین request** است؛
شناسهٔ ثابت محتوا یا شمارهٔ خط نیست. مدل متن فنی، rationale، facts_delta، check،
متن سؤال یا تأیید applicability تولید نمی‌کند. هر فیلد اضافه رد می‌شود.

بلاک‌ها تمام کاراکترها و جداکننده‌های excerpt را نگه می‌دارند و fenced code
تقسیم نمی‌شود. اتصال بلاک‌ها دقیقاً متن اصلی را بازمی‌سازد؛ متن کامل و metadata
هر منبع در ورودی حضور دارد. مرز پاراگراف یک ادعای مستقل معنایی محسوب نمی‌شود.
مدل می‌تواند caveat مهمِ بلاک دیگری را انتخاب نکند؛ hash این ضعف را حل نمی‌کند.

hash روی request کامل، وضعیت case، evidence، catalog و بلاک‌ها بسته می‌شود.
تغییر revision، correction، source یا span، پاسخ قدیمی را نامعتبر می‌کند.
fact انتخابی فقط از USER فعال است؛ مقدار خام نسخه نمایش داده می‌شود و
superseded/evidence/inference جای گزارش جاری کاربر را نمی‌گیرد. منبع قدیمی که
هنوز در pool جاری است با scope واقعی و عدم‌قطعیت نمایش داده می‌شود؛ این مسیر
تشخیص خودکار نسخه، صدق منبع یا حل خودکار تناقض اضافه نمی‌کند.

`ask` فقط سؤال canonical یک gap ثبت‌شدهٔ USER است؛ gap مستندات را نمی‌شود
به سؤال از کاربر تبدیل کرد. سؤال به‌تنهایی در draft می‌آید؛ گزارش facts، checks،
source gap و conflict در summary برای review می‌ماند. `answer` بدون passage یا
با conflict حل‌نشده پذیرفته نمی‌شود. `retrieve_more` فقط query محدود و بدون
payload نهایی دارد؛ همان سقف دو attempt، دو retrieval و terminal stop برقرار است.

برای اتصال آزمایشی، caller همان catalog و request factory بازبینی‌شده را بدهد:

```python
from agent_app.llm.claims import MetisClaimPlanner
from agent_app.reasoning.claim_plan import ClaimReasoner

# config/ledger از همان مسیر مجاز موجود؛ response_mode="analysis"،
# تمام grounded_* خاموش؛ این نمونه مجوز live یا رفع halt نیست.
with MetisClaimPlanner(config, ledger) as planner:
    reasoner = ClaimReasoner(planner, request_factory=current_request_factory)
    # reasoner از ReasonerPort موجود استفاده می‌کند.
    # برای handoff، request واقعیِ enriched را پس از analyze از
    # reasoner.last_request.grounded بگیرید، نه factory اولیه.
```

gateway همان identity، reserve/settle، provider verification، اندازه و ledger
قبلی را استفاده می‌کند. factoryهای معمول، env، API/UI، RAG و tracker آن را
خودکار انتخاب نمی‌کنند. پیشنهاد از approval و action جداست؛ هیچ اختیار اجرایی
از plan یا متن منبع به tracker منتقل نمی‌شود.

## نتیجهٔ واقعی و محدودیت‌ها

[protocol و داده‌های اصلی](../experiments/core_claim_boundary_v1/README.md)
پیش از مدل ثبت شدند: هفت خانوادهٔ exposed dev، هشت condition، شانزده snapshot
جاری، دو دور متوازن و ۶۴ invocation. دو مسیر ورودی کامل یکسان دارند ولی prompt،
schema و renderer متفاوت‌اند؛ مقایسهٔ تک‌عاملی محسوب نمی‌شود.

| مسیر | برنامه‌ریزی | بازدیدشده | پیشنهاد pending | error | بازدیدنشده |
| --- | ---: | ---: | ---: | ---: | ---: |
| compiled موجود | ۳۲ | ۱۸ | ۱۵ | ۳ | ۱۴ |
| passage plan جدید | ۳۲ | ۱۹ | ۷ | ۱۲ | ۱۳ |

تنها پاسخ جدید Enum-guide یک پاراگراف identity و **عنوان** module را انتخاب
کرد؛ بدنهٔ الگو و caveat ویرایش/reload نیامد. دو پاسخ compiled نیز cause/fix را
بیش از شواهد قطعی کردند. معیار ازپیش‌ثبت‌شدهٔ مشترک identity، module، caveat
و کاربرد مشروط پاس نشد؛ دو snapshot برنامه‌ریزی‌شدهٔ هر مسیر اصلاً اجرا نشدند.
در Enum-withheld دو plan جدید به منبع خارج از catalog اشاره کردند و guard هر
دو را رد کرد؛ پاسخ مفید نهایی نداریم. دو اجرای دیگر هر مسیر بازدیدنشده‌اند.
رد انتخاب نامعتبر یک کنترل software است، نه موفقیت کیفیت روی چهار خروجی.

در کل، compiled شش سؤال لازم و نه پیشنهاد دارای ادعای مهم بی‌پشتوانه داشت.
هفت پیشنهاد جدید شامل یک سؤال لازم، یک Enum ناقص و پنج نقل وفادار ولی نامرتبط
یا heading-only بود. انتخاب عین متن از اختراع ادعا جلوگیری می‌کند، اما این
اعداد برتری پاسخ‌گویی را نشان نمی‌دهند. raw متنِ ردشده نگهداری نشده و خطای
`invalid_grounded_plan` در اجرای اصلی syntax/shape/branch را تفکیک نمی‌کند؛
علت دقیق خطاهای قالب را از روی این رسید بازسازی نمی‌کنیم.

پس از اجرای مدل، شرط‌های وابسته به decision و feedback امن parser جداگانه
آفلاین دقیق‌تر شدند. این کدِ بعدی در cohort آنلاین بالا اجرا نشده است؛ آزمون
آفلاین repair، جای مقایسهٔ API تازه را نمی‌گیرد. جزئیات source و آزمون‌ها در
[verification](../experiments/core_claim_boundary_v1/verification-v1.json) ثبت‌اند.

## هزینه، توقف و مرز داده

۵۲ درخواست ارسال شد: ۵۱ settled با تخمین محلی تازهٔ `$0.051594510` و یک
`connect_timeout` با هزینهٔ نامعلوم و hold تازهٔ `$0.0067584`. جمع settled
محلی `$0.599798760` و سه hold جمعاً `$0.0301376` است؛ این‌ها صورتحساب سرویس
یا مصرف سایر لپ‌تاپ‌های تیم نیستند. HTTP response/model/usage برای درخواست
آخر مشاهده نشد؛ صفر بودن هزینه یا نرسیدن آن به سرویس ثابت نشده است.

guard تمام کمپین را متوقف کرد؛ ۲۷ invocation اجرا نشد و نتیجهٔ ناقص حفظ شد.
۸۰ slot تخصیص‌یافته شامل ۵۲ مصرف و ۲۸ unused دائماً claimed است. ۴۸ slot
برنامه‌ریزی‌شده اصلاً در SQLite تخصیص نیافت؛ روش بسته اجازهٔ استفادهٔ مجدد از
آن شناسه‌ها را هم نمی‌دهد. halt، holdهای قدیمی و سقف `$4.50` حفظ‌اند؛ این تحویل
reconciliation یا مجوز ادامهٔ live نیست. هیچ approval، release یا action نداشتیم.

تمام ۶۶۶ reservation قبلی و ۱۴ جدول حفظ شدند؛ audit V2 دارای ۲۳۵۵ کنترل پاس
است. اشتباه فرمول auditor در V1 همراه گزارش شکست حفظ شده؛ فقط audit اصلاح شد،
نه ledger یا receipt. epoch جاری ۱۹ فایل ثابت است. drift تاریخی دو فایل native
در مطالعهٔ قبلی همچنان ثبت است؛ بازگردانی hashهای تاریخی ادعا نمی‌شود.

corpus/index/exclusion، case/gold/manifests و کار اعضا تغییر نکردند. همان راهنمای
answer-linked فقط در fixture کنترل‌شده است و وارد RAG واقعی نشده. refinement
همان pool ثابت را برمی‌گرداند؛ سرچ واقعی نیست. snapshotهای correction مستقل‌اند،
نه پاسخ واقعی به سؤال مدل. امتیاز انسانی usefulness خالی است و review دستیار
با پیاده‌سازی و طراحی oracle هم‌پوشانی دارد؛ final test و کیفیت RAG سنجیده نشده‌اند.
