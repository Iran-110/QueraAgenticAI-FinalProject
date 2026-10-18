# C4z — ریشهٔ defaultهای ناسازگار و خروجی مستقل اصلاح‌شده

در `streamlit.button` نسخهٔ **1.49.0**، default اعلام‌شده در signature برای
`type` برابر `"secondary"` و برای `disabled` برابر `False` است. این دو مقدار
هم با signature سند خام و هم با تعریف تابع در کد رسمی همان release تطبیق دارند.
metadata تولیدشدهٔ اسناد، برای همین پارامترها به‌ترتیب `null` و `"is"` دارد؛
آماده‌سازی قبلی، آن‌ها را بدون تطبیق با signature به header متن منتقل کرده است.

اصلاح C4z یک **خروجی مشتق‌شدهٔ آفلاین با هویت تازه** می‌سازد. متن خام، خروجی‌های
تاریخی، sourceهای داخل index و تنظیم اجرای جلسه عوض نشده‌اند. این اصلاح هنوز به
پاسخ مدل یا build فریز‌شده وصل نشده است.

## زنجیرهٔ بررسی

1. checkout تمیز اسناد رسمی روی commit `695e6ce2fb1b23afc6df66b40420ab0013ad72fd`:
   فایل `python/streamlit.json` با SHA کامل، Git blob و اندازه تطبیق داده شد؛
   API رسمی GitHub نیز همان blob و اندازه را برگرداند.
2. رکورد کامل `/1.49.0/streamlit.button` و کنترل `/1.39.0/streamlit.button`
   با JSON pointer و hash محتوای canonical جدا ثبت شدند. `null` با نبودن فیلد
   فرق دارد، اما به‌تنهایی default واقعی `None` را ثابت نمی‌کند.
3. بازسازی وفادار سیاست آماده‌سازی قدیمی از این دو رکورد، متن seed را **بایت‌به‌بایت**
   بازتولید کرد. پس ناسازگاری قبل از retrieval وجود داشته است.
4. trim مرزی همین متن seed، hash کامل excerptهای استفاده‌شده در سه candidate
   قبلی را بازتولید کرد؛ دو LF انتهایی، اختلاف طول ثبت‌شده در C4y را توضیح می‌دهند.
   از این اختلاف، خرابی index نتیجه نمی‌گیریم.
5. کد رسمی Streamlit با commit ثابت `9bde6fb465da3ae76b628a32c3258cd600949512`
   فقط با AST خوانده شد: literalهای `type` و `disabled` در خطوط ۱۰۰ و ۱۰۲ همان
   مقادیر بالا هستند. هیچ کد منبعی اجرا یا import نشد؛ نصب و رفتار runtime آزمایش نشد.

[کد رسمی تابع](https://github.com/streamlit/streamlit/blob/9bde6fb465da3ae76b628a32c3258cd600949512/lib/streamlit/elements/widgets/button.py#L100-L102)،
[مسیر تولید metadata](https://github.com/streamlit/docs/blob/695e6ce2fb1b23afc6df66b40420ab0013ad72fd/python/generate.py#L195-L272)،
[pinها و حدود بررسی](../experiments/core_raw_defaults_v1/source-provenance-v1.json).

generator رسمی، metadata پارامتر را از `docstring_parser` و signature را از مسیر
جداگانهٔ `inspect.signature` می‌سازد. وجود ناسازگاری در فایل تولیدشده ثابت شده؛
نسخه و رفتار دقیق parser تاریخی بازاجرا نشده و علت دقیق داخلی آن را ادعا نمی‌کنیم.

## قاعدهٔ اصلاح

| وضعیت | رفتار خروجی تازه |
|---|---|
| default صریح و literal در signature | همان token منبع در header استفاده می‌شود |
| پارامتر required یا variadic بدون default | فیلد گمراه‌کنندهٔ default حذف می‌شود |
| نام sentinel یا مقدار حل‌نشده | مقدار قبلی حفظ و وضعیت حل‌نشده ثبت می‌شود |
| signature پشتیبانی‌نشده یا ورودی ناسازگار | خروجی تولید نمی‌شود |

ورودی باید با بازسازی متن قدیمی، نام/نسخه/ترتیب پارامترها و hash رکورد خام تطبیق
داشته باشد. هیچ regex جایگزینی روی متن آزاد، اجرای کد یا استنتاج از prose انجام
نمی‌شود. گزارش دوباره محاسبه و با نوع دقیق فیلدها validate می‌شود؛ تغییر provenance،
متن، مختصات، هویت یا flagهای authority رد می‌شود.

فقط قسمت default در headerها تغییر می‌کند؛ شرح پارامترها، همهٔ گزینه‌ها، زمینهٔ
ابتدا/انتهای متن و line endingها حفظ می‌شوند. نسخهٔ 1.49 علاوه بر دو هدف اصلی،
default گمراه‌کنندهٔ `label` را حذف و headerِ `width` را هم با signature هماهنگ
می‌کند. کنترل 1.39 سه header تغییر دارد. [فهرست دقیق](../experiments/core_raw_defaults_v1/comparison.fa.md).

هویت تازه به schema، نسخه، تابع، commit اسناد، hash فایل/رکورد خام و متن قبل/بعد
وابسته است. این هویت، source ID یا context قدیمی را بازنویسی نمی‌کند و مجوز
proposal، approval یا Action نیست.

## چه چیزی هنوز کامل نیست؟

- متن seed قدیمی، فیلد مفرد `example` را می‌خوانده؛ رکورد خام فیلد `examples` دارد.
  metadata تو‌در‌توی deprecation نیز در متن قدیمی نیامده است. **متن مشتق‌شده کاملِ
  سند خام نیست**؛ JSON خام کامل جدا حفظ شده تا این اطلاعات گم نشوند.
- جملهٔ قدیمی default در شرح `use_container_width` نسخهٔ 1.49 هنوز با signature
  سازگار نیست. این prose دست‌نخورده است؛ اصلاح همهٔ ناسازگاری‌های معنایی انجام نشده.
- pure normalizer، عضویت در یک فایل خام خارجی را authenticate نمی‌کند. اجرای
  source-aware جدا، فایل کامل را با SHA و رکورد را با pointer بررسی کرده است.
  اجرای portable فقط snapshot بسته را بررسی می‌کند و آن دو تأیید خارجی را `false`
  گزارش می‌دهد.
- ۸ attempt و ۷ turn قدیمی حفظ شدند. سه اتصال source تاریخی تأیید شده‌اند؛ انتخاب
  جدید مدل، usefulness انسانی، حل Enum یا کیفیت نهایی RAG/test اندازه‌گیری نشده است.

## تست، حفاظت و قدم بعد

۸۲۴ تست مرتبط شامل **۱۲۴ کنترل تازه**، Ruff/format برای ۴۴۱ فایل Python و review
مستقل پاس‌اند. ابتدا دو خطای import در اجرای مستقل رخ داد؛ bootstrap فقط در دو
فایل تست اصلاح شد و اجرای نهایی بدون `PYTHONPATH` پاس شد. این مجموعه، suite کامل
یا اجرای held-out نیست. [رسید](../experiments/core_raw_defaults_v1/verification-v1.json).

۲۱ فایل binding مالی و watch جداگانهٔ ۱۱۷ فایل اجرایی ثابت‌اند؛ healthcheck فقط
خواندنی، index فیزیکی و مسیر جلسه را تأیید کرد. ۷ نوبت جلسه مصرف نشده‌اند، halt و
سه hold قدیمی حفظ شده‌اند. هیچ فراخوانی مدل/Metis، تغییر ledger، rebuild یا خواندن
payloadهای held-out انجام نشد. خواندن منابع عمومی GitHub جدا از مصرف مدل است.

برای استفادهٔ واقعی بعدی: review انسانی کیفیت سند، استخراج کامل‌تر مثال/deprecation،
نسخهٔ تازهٔ corpus/build/profile و قرارداد تحویل لازم است؛ سپس انتخاب مدل و مسیرهای
answer/ask/escalate روی dev سنجیده می‌شوند. build، gold و scope جلسهٔ فعلی برای این
آزمایش تغییر نمی‌کنند. [فرمان بازتولید](../experiments/core_raw_defaults_v1/README.md).
