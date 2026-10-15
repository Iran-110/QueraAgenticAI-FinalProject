# R4c/C4h5 — رساندن شاهد مرتبط به core

PR50 حسن در head`1a18749` هنگام شروع این کار تغییری نکرده بود. backend هنوز
فقط top-k می‌خواند و مرتب‌سازی newest-first به‌تنهایی relevance یا نسخهٔ فعلی
را تضمین نمی‌کند. این تغییر روی branch جداست؛ branch او، snapshot، corpus،
exclusion و fixture/goldهای قبلی تغییر نکرده‌اند.

[ثبت قبل از پیاده‌سازی](../experiments/retrieval_relevance_v1/protocol-v1.json)
از queryهای واقعی اجرای C4h4 شروع شد. در replay بردارهای lexical، button۱٫۳۹
در رتبه‌های۶/۸/۲۰ و اولین chunk لازم multiselect۱٫۵۰ در رتبه۲۲ بود؛ در index
حضور داشتند ولی به مدل نمی‌رسیدند. نتیجهٔ اول بر اساس query/collection وارد
top5 می‌شد و فیلتر نسخه بعداً بعضی hitها را حذف می‌کرد.

## انتخاب کاندیدا و کنترل نسخه

تنظیم‌های opt-in زیر با قرارداد موجود کار می‌کنند:

```python
retriever = ChromaRetrieverAdapter(
    "", snapshot_id=snapshot_id, core_retriever=native,
    selection_policy="query_relevance_v1",
)
engine = SupportEngine(
    retriever, reasoner, snapshot_id=snapshot_id,
    evidence_scope="exact_user_version",
    retrieval_candidate_multiplier=5,
    evidence_utf8_budget_bytes=12000,
)
```

engine برای خروجی نهایی۵، حداکثر۲۵ کاندیدا در هر query/collection می‌خواهد؛ سقف
عمومی۵۰ است. تعداد query، دور retrieval و attempt مدل زیاد نمی‌شود. adapter
نتایج queryها و collectionها را با هم مرتب می‌کند: تطابق نام API در query با
هویت اصلی سند، شباهت واژگانی TF-IDF و reciprocal rank بومی، با tie قطعی.
ابتدا یک chunk از هر source و سپس chunkهای تکمیلی می‌آید. نسخه‌های یکسان‌متن
هویت مستقل دارند؛ مصدر سند یا نام API به‌تنهایی پشتیبانی معنایی نیست.

فقط engine و fact فعال USER دربارهٔ نسخه تصمیم می‌گیرند. متن query، مدل،
`since_version` و سند، نسخهٔ نصب کاربر را تعیین نمی‌کنند. precedence قبلی
`applicable_versions` حفظ است؛ `since_version` به نسخهٔ دقیق تبدیل نشده.
فیلتر نسخه **پیش از** cap نهایی۵ اعمال می‌شود. با نسخهٔ نامعلوم، اسناد با
نسخهٔ صریح طبق سیاست قبلی کنار می‌روند؛ سؤال نسخه همچنان لازم می‌تواند باشد.

## اندازه و تمامیت شواهد

بازپخش اول با کاندیداهای بیشتر، در۹از۱۱state زیر سقف ورودی بود؛ baseline۱۰از۱۱.
[رسید اول](../experiments/retrieval_relevance_v1/offline-candidates-before-packing-v1.json)
حفظ و [اصلاح بودجه](../experiments/retrieval_relevance_v1/whole-record-budget-amendment-v1.json)
پیش از کد این اصلاح و هر اجرای API ثبت شد. اکنون engine بعد از فیلتر نسخه،
رکورد کامل را تا سقف byte پیکربندی‌شده انتخاب می‌کند؛ رکورد بزرگ جا نشود،
رد می‌شود و رکورد بعدی امتحان می‌شود. excerpt، hash، ID، span و metadata بریده
یا بازنویسی نمی‌شوند. budget شامل JSON کامل EvidenceBundle و warning ثابت است؛
queryهای مصرف‌شده هم در آن باقی‌اند.

۱۲۰۰۰byte تخصیص این آزمایش برای bundle است؛ سقف کل prompt همان۳۲۷۶۸ و
validator gateway همچنان مرجع نهایی است. تضمین همهٔ contextهای آینده نیست.
envelope خالیِ بزرگ یا warning نامعتبر fail می‌شود. renderer همچنان تمام quote
انتخاب‌شده را کنترل می‌کند؛ این تغییر مجوز پاسخ قطعی یا اقدام tracker نیست.

پیش‌فرض‌ها `selection_policy="native"`، multiplier۱ و budget`None` هستند و
رفتار/trace قبلی را حفظ می‌کنند. کارخانهٔ معمول live یا UI خودکار فعال نشده؛
recipe بالا برای اتصال مستقیم و driver ثبت‌شده برای مقایسه است. forwarding
پیکربندی محصول، در صورت تأیید کیفیت، کار جداست؛ ماژول UI/tracker بازنویسی نشده.

## آزمایش

[replay روی index واقعی](../experiments/retrieval_relevance_v1/offline-candidate-replay-v1.json)
هر۱۱state مشاهده‌شده را با قالب compact مشترک و repair زیر سقف نگه داشت؛ button۱٫۳۹
و multiselect۱٫۵۰ در نوبت مناسب رسیدند. این availability است، نه کیفیت جواب.
همان۱۸source/۳۶chunk با embedding محلی lexical استفاده می‌شود؛ semantic embedding
یا corpus تازه نیست. trace اجرای تازه، read واقعی backend، رتبه و hash متن/
metadata، انتخاب adapter و request نهایی پس از scope/packing را جدا ثبت می‌کند.

مقایسهٔ API دو دور و شش pair روی همان سه dev است. compact-plan و تمام flagهای
core در هر دو arm یکسان‌اند؛ فقط بستهٔ candidate/ranking/packing تغییر می‌کند.
مقایسه با نمرهٔ تاریخی نمی‌کنیم و اثر جزءهای بسته را جدا ادعا نمی‌کنیم.
[معیار پیش از مدل](../experiments/retrieval_relevance_v1/semantic-review-preparation-v1.json)
میان متنِ مرتبطِ رسیده، منبع انتخاب‌شده، راهنمای فنیِ رسیده به کاربر، علت/fix
و usefulness انسانی فرق می‌گذارد. خروجی عمومی یا `answer` به‌تنهایی موفقیت نیست.
تمام۲۴نوبت، خطاها و unvisitedها باید بمانند. هزینه فقط از ledger موجود با
scope تازه محدود است؛ hold/halt قدیمی و سقف۴٫۵۰دلار حفظ می‌شود.

## نتیجهٔ ثبت‌شده

[رسید، داوری و محدودیت‌ها](../experiments/retrieval_relevance_v1/README.md):
دو دور روی همان سه dev، با۲۷ send و تخمین$0.026391915. مسیر کامل از۵/۶ به۶/۶
و پیشنهاد تازه از۱۰ به۱۲ رسید؛ همهٔ۲۴ نوبت، شامل یک empty و یک unvisited در
baseline، محفوظ‌اند. raw compact در baseline چهارده از پانزده و در نسخهٔ جدید
دوازده از دوازده معتبر بود. هیچ‌کدام length،
input overflow یا render overflow نداشتند.

در هر دو تکرار button، متن محدودیت icon نسخهٔ۱٫۳۹ وارد پاسخ اصلی و released
شد؛ baseline آن را نداشت. این راهنمای جزئی برای همان یک case است، نه حل warning
یا تأیید رفتار runtime. برای multiselect، شواهد۱٫۵۰ به مدل رسید ولی سؤال callback
همچنان لازم بود و راهنمای API به user draft اضافه نشد. Enum در هر دو حالت هنوز
علت/fix مستند ندارد؛ شش label پاسخ فقط background/investigation هستند. هر۱۲
سؤال ضروری بود و هر سه correction تازه، نسخهٔ فعال۱٫۳۱٫۱ را حفظ کردند.

داوری دستیار روی۲۲ پیشنهاد تازه و۱۴۸ surface انجام شد؛ usefulness انسانی null
است. باز‌محاسبهٔ جداگانه با۳۹۱۲ کنترل هزینه/native provenance، تمام۲۷ سرچ و bundle قبل/بعد از
scope/packing را بازسازی کرد. hold/halt/سقف و۴۵۲ reservation قبلی محفوظ‌اند؛
بازبین در نوشتن تست‌ها هم نقش داشت؛ این بازبینی انسانی مستقل نیست.
هر شش scope بسته و۲۱ slot باقی claimed شدند. suite کامل۴۱۵۰ و پذیرش جداگانهٔ
HTTP/SQLite۴۵۷/۴۵۷ پاس‌اند. رفتار جدید opt-in است؛ این آزمایش، RAG/test نهایی نیست.
