# C4h4 — قرارداد کوتاه خروجی مدل

این بهبود از [بررسی شکست‌های اجرای قبلی](../experiments/core_compact_plan_v1/protocol-v1.json)
شروع شد: پنج JSON کامل با schema نامعتبر، یک reference ترکیبی و دو توقف
`length`. علت دو توقف طول مشخص نیست؛ کوتاه‌تر شدن خروجی را درمان قطعی آن
حساب نمی‌کنیم. معماری همان تک agent و قرارداد عمومی `GroundedPlan` است.

## رفتار کد

گزینهٔ `METIS_GROUNDED_COMPACT_PLAN=true` فقط همراه
`METIS_GROUNDED_DECISION_CONTRACTS=true` فعال می‌شود؛ پیش‌فرض خاموش است.
مدل به‌جای کپی ID و hash بلند منابع، index صحیح و صفرمبنای hitهای همین request
را انتخاب می‌کند. `context_sha256` کامل همچنان اجباری است. gateway انتخاب را
به ID و hash دقیق همان رکورد فعلی تبدیل می‌کند و سپس `GroundedPlan` معمولی
و renderer قبلی آن را کنترل می‌کنند. هیچ map سراسری یا متعلق به نوبت قبلی نداریم.

هر decision فقط fieldهای لازم خودش را دارد: `ask` نام سؤال را هم می‌خواهد؛
`retrieve_more` query می‌خواهد و field مربوط به source ندارد. همهٔ fieldها
اجباری و اضافات ممنوع‌اند. JSON با کلید تکراری، عدد غیرمتناهی، Unicode نامعتبر،
index اعشاری/boolean، تکرار source یا field بی‌ربط پذیرفته نمی‌شود. index صحیح
ولی ناشناخته و hash context نادرست، خطای terminal اتصال‌اند؛ schema نامعتبر
فقط از همان فرصت repair موجود استفاده می‌کند. توقف provider با `length`
پیش از parser رخ می‌دهد؛ متن ناقص salvage نمی‌شود و تماس سوم نداریم.

این طراحی یک tradeoff دارد: hash هر source را کد از رکورد انتخاب‌شده می‌سازد،
مدل دیگر آن را مستقلاً echo نمی‌کند. hash کامل request همچنان انتخاب را به
همان شواهد وصل می‌کند؛ این کار درستی معنایی یا اعتبار خود منبع را ثابت نمی‌کند.

پیشنهاد، تأیید، revision و اجرای tracker تغییر نکرده‌اند. flag خاموش، byteهای
prompt و خروجی gateway قبلی را حفظ می‌کند. `response_format` جدیدی به Metis
نمی‌فرستیم؛ پشتیبانی آن از Structured Outputs تأیید نشده است.

## ثبت و مقایسه

trace با flag روشن، `wire_output` جدا برای hash و شکل خروجی خام، اعتبار schema
و نتیجهٔ binding دارد؛ hash و schema خروجی canonical را به‌جای خروجی خام مدل
گزارش نمی‌کنیم. diagnostics شامل متن خام، نام field ناشناخته یا خطای کامل
validator نیستند. پاسخ terminal یا ناقص، observation ساختگی نمی‌گیرد.

[روش آزمایش](../experiments/core_compact_plan_v1/protocol-v1.json) دو دور balanced
روی همان سه dev و index واقعی۱۸source/۳۶chunk را ثبت کرده است. ranking، مدل،
سقف token و تعداد attempt ثابت‌اند؛ treatment یک بستهٔ مرکب از index منبع و
fieldهای مخصوص decision است. اثر جداگانهٔ هر جزء از این آزمایش معلوم نمی‌شود.
شرط prospective مربوط به case-a در
[آمادگی review](../experiments/core_compact_plan_v1/semantic-review-preparation-v1.json)
ثبت شده؛ اصل gold، receipt و نمرهٔ تاریخی عوض نمی‌شود. حضور سند در index کافی
نیست؛ متن پشتیبان باید واقعاً در evidence همان turn باشد.

این مقایسه ادامهٔ scope ثبت‌شدهٔ همان سه dev و rubric draft اصلی است، همراه
amendment مشخص بالا؛ ادعای اجرای rubric v1 یا E2 نهایی ندارد. PR56 هنوز rubric
را freeze نکرده است. ثبت scope تازهٔ v1 و scoring کامل با صاحب evaluation است.

دستورهای ثبت و اجرای محدود در `scripts/core_compact_model_probe.py` هستند.
اجرای عادی live هنوز با halt متوقف است؛ این driver فقط scopeهای تازه، محدود
و ازقبل ثبت‌شدهٔ همین مقایسه را مصرف می‌کند. هر دو hold قدیمی، سقف۴٫۵۰دلار و
revocationها باقی‌اند. روش بسته‌شده یا slot مصرف‌شده قابل ادامه‌دادن نیست.
نتیجهٔ واقعی، هزینه و محدودیت‌ها در پوشهٔ experiment ثبت می‌شوند؛ این داده‌ها
dev در معرض دید هستند، ارزیابی نهایی یا held-out نیستند.

## نتیجهٔ اجرا

[receipt و reviewها](../experiments/core_compact_plan_v1/README.md):۳۲send،
schema نامعتبر۳/۱۸درbaseline و۰/۱۴درcompact؛ مسیر کامل۴/۶درمقابل۵/۶، اماfresh
هر دو۱۰است. یکrefinement بیش‌ازسقف ورودی بود؛ هر دو projection همانrequest
ازسقف عبور می‌کنند. baseline یکrender overflow هم داشت؛ proposal قدیمی stale
ماند وapproval آن409گرفت. هیچ‌کدام length نداشتند؛ علت شکست طول قبلی حل‌شده
اعلام نمی‌شود. سه label پاسخ فقط background/پیشنهاد investigation بودند؛
پاسخ فنیِ درخواست‌شده درهیچarm ثابت نشد.۱۲سؤال ضروری وبدون تکرار fact معلوم
بودند؛ usefulness انسانی هنوزnull وگزینه خاموش است.

تخمین هزینهٔ این اجرا$0.034834305بود؛۱۶۷۱کنترل هزینه/provenance پاس وهر۶scope
بسته شد. تمام۲۴نوبت، ازجمله۱stale،۲empty و۱unvisited، محفوظ‌اند. snapshot ثابت
وreceiptهای اصلی برای داوری مستقل باقی‌اند.
