# C4y — review ارتباط، شواهد و مفیدبودن سه candidate

این بررسی، ادامهٔ [C4x](core-parameter-focus.fa.md) روی همان سه انتخاب تألیفی و
همان شواهد آشکار rehearsal است. سؤال فعلی، facts فعال USER، متن کامل منبع و
تعریف کامل پارامتر کنار هم خوانده شدند. **review از نوع AI است**؛ نمرهٔ انسانی،
انتخاب تازهٔ مدل، نتیجهٔ held-out یا تأیید انتشار پاسخ نیست.

## نتیجهٔ هر مورد

| candidate | ارتباط با سؤال فعلی | شواهد لازم در متن عرضه‌شده | محدودیت برای استفاده |
| --- | --- | --- | --- |
| B2، `icon`، نسخهٔ 1.39.0 | مستقیم؛ سؤال دربارهٔ کنار هم بودن label و icon است | عبارت «next to the button label» صریح است؛ signature هر دو را دارد. قید emoji، عدم پشتیبانی short code و قالب Material هم حفظ شده‌اند | default همین پارامتر در header و signature برابر است؛ ناسازگاری‌های سایر پارامترها، صحت همین نقل‌قول را خودکار رد نمی‌کنند. citation و دقت provenance باید روشن باشند |
| C1، `type`، نسخهٔ 1.49.0 | مستقیم؛ هدف و گزینه‌ها خواسته شده‌اند | `primary`، `secondary`، `tertiary` و توضیح هر سه در واحد کامل هستند | header می‌گوید `default=None`، اما signature و بدنه `secondary` را ذکر می‌کنند؛ default نباید بی‌هشدار قطعی معرفی شود |
| C2، `disabled`، نسخهٔ 1.49.0 | مستقیم؛ follow-up دربارهٔ disabled است، نه سؤال تاریخی type | تعریف `True` برای غیرفعال‌کردن و عبارت `False` در بدنه وجود دارد | `default=is` در header قابل مقایسهٔ امن نیست. از «temporarily» نباید زمان‌بندی، فعال‌شدن خودکار یا fix برنامه ساخته شود |

در متن کاملِ عرضه‌شده، قید ضروری دیگری برای پاسخ به **همین سؤال‌های محدود**
پیدا نشد. این مشاهده، کافی‌بودن عمومیِ پارامترها یا اعتبار همهٔ منابع را ثابت
نمی‌کند. هیچ‌یک از سؤال‌ها برای همین مقصود به توضیح اضافهٔ کاربر نیاز ندارد؛
ناسازگاری مستندات و offset را نباید با سؤال نامربوط دربارهٔ برنامه به کاربر برگرداند.

## اصلاحات انجام‌شده

یک لایهٔ inspection مستقل اضافه شد؛ candidate، payload، renderer و receiptهای
قبلی عیناً حفظ‌اند. مسیر جدید:

- آدرس HTTP(S) عرضه‌شده را در متن قابل خواندن نشان می‌دهد؛ delimiterهای Markdown
  و HTML برای citation encode می‌شوند. این کار منبع را authenticate نمی‌کند.
- defaultِ header و signature را با grammar محدودِ literal و بدون execution
  مقایسه می‌کند. `False` با `0` و `None` با رشتهٔ `"None"` یکی فرض نمی‌شوند.
  نام sentinel، مقدار مبهم و default ناقص، نامعلوم می‌مانند؛ بدنهٔ نثر تفسیر نمی‌شود.
- warning پارامتر منتخب را از warning پارامترهای دیگر جدا می‌کند؛ هیچ default
  یا متن source را اصلاح نمی‌کند.
- در هر سه مورد، اختلاف طول span عرضه‌شده و excerpt را روشن می‌کند:
  B2: ادعای۲۶۹۸ در برابر متن۲۶۹۶کاراکتری؛ C1/C2: ادعای۳۷۵۴ در برابر۳۷۵۲.
  offset نقل‌قول فقط داخل excerpt و با واحد Unicode code point معتبر است؛
  نگاشت به فایل اصلی تأیید نشده، حتی اگر طول اعلام‌شده برابر باشد.
- متن کامل پارامتر، منبع و signature را برای maintainer حفظ می‌کند. request،
  candidate و تمام متن/flagsِ review به hash متصل‌اند؛ review قدیمی، دست‌کاری‌شده
  یا با bool/float به‌جای شناسهٔ صحیح رد می‌شود.

این inspection، `AnalysisResult` یا پیشنهاد قابل approval نیست؛ relevance،
caveatهای خارج واحد و usefulness در قرارداد خودکار همچنان نمره ندارند.
یادداشت‌های معنایی AI در sidecar جدا هستند و وارد payload انتخاب مدل یا corpus نمی‌شوند.

اختلاف طول به‌تنهایی خطای index نیست. قرارداد فعلی `EvidenceHit` فاصله‌های ابتدا
و انتهای متن را حذف می‌کند و metadataِ span را نگه می‌دارد. افزودن دو LF به این
سه excerpt، هم طول اعلام‌شده و هم prefix شانزده‌رقمیِ hash در chunk ID را بازسازی
می‌کند؛ این مشاهده با trim در مرز قرارداد سازگار است. raw document یا hash کامل
آن را در این بررسی authenticate نکردیم، پس mapping اصلی همچنان نامعلوم است.
[مشاهده و محدودیت فرضیه](../experiments/core_parameter_review_v1/boundary-normalization-observation-v1.json)
و سه regression مستقل، تفاوت «normalization» با «خرابی منبع» را ثبت می‌کنند.

## شواهد و حد نتیجه

۷۰۰ تست مرتبط پاس شدند؛ ۱۰۰ کنترل تازه داخل همین شمارش‌اند، نه افزون بر آن.
Ruff/format۴۳۶فایل پاس است. دو assertion متنی پس از کوتاه‌کردن warningها شکست
خوردند؛ عبارت‌های صریح عدم اصلاح default و عدم تأیید mapping حفظ و regression
کامل دوباره پاس شد. لاگ شکست و خروجی‌های میانی پاک نشده‌اند. review مستقل،
hash هر سه candidate/request/source و هشت عبارت پشتیبان را تطبیق داد.

طول inspection کمی بیشتر از candidate کوتاه C4x است، چون اکنون citation و
مسئلهٔ مشخص منبع را نشان می‌دهد؛ کاهش طول هدف پذیرش این مرحله نیست. تمام هشت
attempt و هفت turn قبلی حفظ‌اند؛ multiselect در A3، retrieval miss در B1 و
کیفیت Enum با این کار حل نشده‌اند.

کد فقط در `experiments/core_parameter_review_v1/` است. watch۱۱۷فایل، binding
مالی۲۱فایل، مسیر جلسه، index/exclusion/gold، halt و سه hold تغییر نکرده‌اند.
هیچ فراخوانی provider یا ledger write تازه نداریم؛ healthcheck بدون provider
همچنان جلسه را با ۷نوبت و ۱۴slot مصرف‌نشده آماده نشان داد.

## پیش از استفادهٔ واقعی چه می‌ماند؟

1. داوری انسانیِ relevance، caveatهای لازم و usefulness؛ AI review جای آن را نمی‌گیرد.
2. بررسی استخراجِ default و نگاشت span با مرجع خام، در کار مستقل داده/RAG.
   build و receipt فریز‌شدهٔ جلسه بازنویسی نمی‌شوند؛ اصلاح بعدی نسخهٔ تازه می‌خواهد.
3. آزمایش انتخاب واقعی مدل روی dev گسترده‌تر، شامل انتخاب نامرتبط و قید ضروری
   بیرون پارامتر. payload کنونی فقط `answer` دارد؛ برای مسئلهٔ نامناسب، تصمیمِ
   غیرپاسخ و تشخیص gap هم باید در قرارداد جدا طراحی و آزموده شود.
4. قرارداد تحویل، handoff/approval و تنظیم نسخه‌دارِ جدا پیش از هر اتصال عملیاتی.
   این مرحله مجوز یا scope جدید ایجاد نمی‌کند و مسیر جلسه را عوض نمی‌کند.

[متن سه inspection و مقایسه](../experiments/core_parameter_review_v1/comparison.fa.md)،
[AI review و عبارات پشتیبان](../experiments/core_parameter_review_v1/ai-review-v1.json)،
[روش بازتولید](../experiments/core_parameter_review_v1/README.md) و
[verification جاری](../experiments/core_parameter_review_v1/verification-v2.json).
