# C4x — پاسخ کوتاه‌تر با تعریف کامل پارامتر

برای سؤال محدود `button`، نقل کل docstring متن زیادی به کاربر می‌رساند. مسیر
آزمایشی تازه، تعریف کامل یک پارامتر را همراه گزینه‌ها و محدودیت‌های همان تعریف
به یک واحد قابل انتخاب تبدیل می‌کند. signature بدون execution بررسی می‌شود؛
source کامل، hash، span و نسخهٔ USER در request باقی می‌مانند.

| مورد آشکار dev | draft قبلی | candidate آفلاین | کاهش طول |
| --- | ---: | ---: | ---: |
| `icon` | ۹۵۵۱ | ۱۳۵۷ | ۸۵٫۸٪ |
| `type` | ۹۱۹۰ | ۱۱۹۳ | ۸۷٫۰٪ |
| `disabled` | ۴۵۵۲ | ۸۶۰ | ۸۱٫۱٪ |

این‌ها انتخاب‌های **تألیفی روی شواهد و sourceهای انتخاب‌شدهٔ قبلی** هستند؛ مدل
پاسخ تازه‌ای نداده است. همهٔ هشت attempt و هفت turn قبلی در گزارش مانده‌اند؛
شکست ارتباط multiselect و retrieval miss قبلی حل‌شده اعلام نمی‌شوند. Enum هم
با این آزمایش حل نشده است. کاهش طول، نمرهٔ usefulness یا entailment نیست.

یک کنترل توضیحیِ پس از مشاهده هم فقط source نامربوط را از plan قبلی کنار گذاشت:
متن‌های ۳۴۳۴،۴۵۵۲،۴۵۵۲ کاراکتری حاصل شدند. بنابراین تمام کاهش از حذف sourceهای
دیگر نمی‌آید؛ برای `disabled` از ابتدا فقط یک source انتخاب شده بود. qualification
دو renderer هم متفاوت است، پس اثر یک عامل بر مدل از این اعداد استنتاج نمی‌شود.

قرارداد آزمایشی، plan را به سه فیلد و integerهای همین request محدود می‌کند.
نسخهٔ نامعلوم، conflict، source یا revision قدیمی، ساختار ناقص و انتخاب نامعتبر
رد می‌شوند. review مستقل، پذیرش اشتباه `True`/`1.0` به‌جای شناسهٔ صحیح و نقص
کنترل ترتیب attemptها را پیدا کرد و regression آن‌ها اضافه شد. در نمایش تازه،
CRLF فقط به LF تبدیل می‌شود؛ متن خام و hash/span تغییر نمی‌کنند.

متن منبع هم بی‌خطا فرض نشده است: headerهای `default=None` برای type و
`default=is` برای disabled با signature/body سازگار به نظر نمی‌رسند. دادهٔ
فریز‌شده اصلاح نشد؛ ناسازگاری برای review نگه داشته شد. parser داور حقیقتِ
منبع یا کامل‌بودن caveatهای خارج از unit نیست.

کد فقط زیر `experiments/core_parameter_focus_v1/` است. `AnalysisResult`، handoff،
renderer و UI فعلی جایگزین نشده‌اند. binding مالی ۲۱ فایل، watch ۱۱۷ فایل،
ledger، halt/سهhold، منابع/exclusion و بستهٔ جلسه دست‌نخورده‌اند. corpus نباید
fixture یا پاسخ این آزمایش را بخواند.

[روش و کد](../experiments/core_parameter_focus_v1/README.md)،
[مقایسهٔ خوانا](../experiments/core_parameter_focus_v1/comparison.fa.md) و
[verification](../experiments/core_parameter_focus_v1/verification-v1.json)
برای review تیم در دسترس‌اند. قدم بعد، داوری انسانی همین candidateهای محدود و
تصمیم دربارهٔ یک اتصال نسخه‌دارِ جداست؛ پیش‌فرض محصول یا مجوز جلسه خودکار عوض
نمی‌شود. API تازه در این مرحله استفاده نشده است.
