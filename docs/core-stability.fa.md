# پایداری تصمیم core و برش خصمانهٔ محدود — ۱۴ اکتبر ۲۰۲۶

این مرحله ادامهٔ همان سه خانوادهٔ exposed و answer-informed است؛ صفر test
تازه و صفر اندازه‌گیری کیفیت RAG دارد. [protocol و همهٔ receiptها](../experiments/core_stability_adversarial/README.md)
قبل/بعد را جدا نگه می‌دارند. اصل خروجی‌های مدل و oracle تغییر نکرده‌اند.

## چه چیزی سنجیدیم

چهار دور paired ثبت شد؛ هر خانواده دو B/C و دو C/B، با ترتیب چرخشی خانواده‌ها.
B vocabulary بازبینی‌شده دارد؛ C فقط guidance موجودِ decision/field را اضافه
می‌کند. مدل `gpt-4o-mini`، شواهد کامل ثابت، validator، renderer با source-gap
handoff و سقف دو attempt یکسان‌اند. temperature/seed تازه اضافه نشده است.
این مقایسه تحت renderer مشترک جدید است، نه تکرار byte-identical نتیجهٔ C4d.

| مشاهده | B | C |
| --- | ---: | ---: |
| route کامل در سه دور کامل | ۳/۹ | ۷/۹ |
| route کامل با دور چهارم ناقص | ۳/۱۰ اجراشده | ۸/۱۰ اجراشده |
| first attempt معتبر | ۸ از ۱۶؛ ۷ نامعتبر، ۱ بدون خروجی قابل بررسی | ۱۶ از ۱۸؛ ۲ بدون خروجی قابل بررسی |
| همهٔ attemptها | ۹ معتبر، ۱۳ نامعتبر، ۱ بدون خروجی | ۱۷ معتبر، صفر نامعتبر، ۲ بدون خروجی |

۲۴ case-arm job برنامه‌ریزی شد؛ ۲۰ اجرا و ۴ پس از توقف اجرا نشده‌اند.
۱۰ ورودی اولیهٔ paired دقیقاً یکسان‌اند؛ follow-up/repair/refinement پس از
تصمیم‌های متفاوت الزاماً یکسان نیستند. دور چهارم کامل نشد، پس counterbalance
برنامه‌ریزی‌شده کامل اجرا نشده؛ از این نمونهٔ کوچک دقت عمومی نمی‌گیریم.

۲۵ proposal کامل با همهٔ متن user/maintainer/rationale، quote، facts، سؤال و
متن released بازبینی شدند. ۲۰ سؤال ضروری/قابل پاسخ و ۳ پاسخ محدود button
مشاهده شد. دو پاسخ Enum quote امن و handoff عمومی داشتند، ولی investigation
مشخص Enum و qualification مطابق شرط سخت‌گیرانه کامل اثبات نشد. دو اجرای
دیگر Enum `ProviderResponseInvalid` شدند؛ هر دو ۱۰۲۴ output token داشتند، اما
finish reason نگه داشته نشده و علت دقیق truncation ثابت نیست. usefulness
انسانی null است؛ review دستیار جای آن را نمی‌گیرد.

## یک اصلاح مشخص

در ۱۴ خروجی اولیه، توضیح source gap از نسخهٔ «تأییدشده» حرف می‌زد، درحالی‌که
نسخهٔ USER نامعلوم بود. catalog فعلی با evidence موجود، اول gap نسخهٔ کاربر
را ثبت می‌کند؛ کمبود مستندات همان نسخه فقط پس از معلوم‌شدن نسخه اعلام می‌شود.
evidence خالی همچنان gap منبع جدا با توضیح صادقانه دارد. این تغییر تشخیص
خودکار علت یا source gap مخصوص Enum اضافه نمی‌کند.

همان [۱۰ کنترل ثبت‌شده](../experiments/core_stability_adversarial/catalog-version-truth-protocol-v1.json)
روی archive واقعی قبل ۳ پاس/۷ شکست و روی archive candidate ۱۰ پاس داشتند.
اصل دو کنترل تاریخی اتصال محفوظ است؛ انتظار فعلیِ gap/caption به‌صورت محدود
اصلاح شد. [receipt v2](../experiments/core_stability_adversarial/catalog-version-truth-receipt-v2.json)
از observation اولیهٔ working tree جداست. اثر این fix با API تازه سنجیده نشده؛
پاس آفلاین نمرهٔ live قبلی را تغییر نمی‌دهد.

## برش خصمانه و هزینه

به دلیل توقف حسابداری، برش خصمانه فقط آفلاین اجرا شد: ۶ کنترل سالم و ۳
counterexample با planner تألیفی. انتخاب source قدیمی پس از filter و answer
با conflict اعلام‌شده رد شدند. منبع مهاجم با hash معتبر هنوز قابل quote است؛
این یک شکست semantic طبق oracle است، حتی وقتی action یا تغییر نسخه رخ نداده.
صفر action در این harness از نبود execution port می‌آید؛ مقاومت مدل یا کیفیت
RAG/bonus از آن نتیجه گرفته نمی‌شود.

۴۲ transport attempt؛ ۴۱ settled با تخمین $0.025141875، یک hold تازه
$0.0033792. کل هزینهٔ واقعی این مرحله نامعلوم است. سه scope بسته، چهارمی و
grant قدیمی طبق guard `NewUncertainty` revoke شده‌اند؛ pending صفر، hold قدیمی
$0.02 و halt محفوظ‌اند. [بستهٔ reconciliation](../experiments/core_stability_adversarial/stability-cost-reconciliation-v1.json)
شناسه/بازهٔ زمانی و مدرک provider لازم را مشخص می‌کند. ادامهٔ live با reset،
تغییر parent یا فرض صفر بودن هزینه انجام نمی‌شود.

## اتصال و کار تیم

tracker، UI، retrieval، قراردادها و final split تغییر نکرده‌اند. source gap
قبل/بعد معلوم‌شدن نسخه در UI موجود درست نمایش داده می‌شود؛ این AppTest
آفلاین است و smoke دستی بهنام را نمی‌بندد. حسن coverage/index را جلو می‌برد؛
محمدحسن review انسانی/۱۵ dev و ۱۵ test را تکمیل می‌کند؛ بهنام smoke جداگانه
را دارد. قدم core برای live، reconciliation و بعد protocol تازه است.

برای بازپخش بدون هزینه از ریشهٔ پروژه:

```bash
uv run python scripts/core_adversarial_replay.py --output runtime/adversarial-review-new.json
uv run pytest tests/test_catalog_version_truth.py tests/test_stability_probe.py tests/test_stability_review.py tests/test_core_adversarial_replay.py
```

برای بازتولید ۲۱ کنترل تاریخی C4c، بدون تغییر oracle:

```bash
uv run python scripts/user_gap_configuration_comparison.py --candidate 535e020f3be4ffce684e329bc5978ffd6d3f8bb3 --output runtime/historical-c4c-new.json
```

registration زندهٔ تاریخی C4e بعد از تغییر ledger eligible نیست و command
آن برای گرفتن اعتبار یا تکرار paid استفاده نمی‌شود.
