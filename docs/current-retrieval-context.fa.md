# query بعد از correction — C2g

در receipt واقعی قبلی، query نوبت دوم دقیقاً از ۴۰۰ کاراکتر اول پیام ترکیبی
reasoning ساخته شده بود: نسخهٔ تاریخی 1.50.0 و Python بازنشستهٔ 3.12.9 در
آن بودند؛ fact جاری 1.49.0 در پایان اضافه شده بود، ولی متن correction فعلی
اصلاً جا نشده بود. این مشاهده آلودگی query را ثابت می‌کند؛ به‌تنهایی افت
ranking، relevance یا کیفیت جواب را ثابت نمی‌کند. اصل probe قبلی حفظ شده است.

## رفتار کد

API حافظه‌ای و `CoreTurnService` اکنون از همان conversation معتبر دو ورودی
می‌سازند: پیام reasoning مثل قبل، و query مستقل برای retrieval. مدل و handoff
تمام کد خام، پیام‌ها و تاریخچهٔ برچسب‌خورده را مثل قبل دریافت می‌کنند؛ ingress،
hash، revision، approval و replay عوض نشده‌اند.

`build_current_query(case, conversation)` ابتدا کل conversation و تطابق revision
را اعتبارسنجی می‌کند. factهای فعال با provenance کاربر در ابتدای query می‌آیند؛
fact منبع، مقدار superseded و evidence_ref پارامتر محیط فعلی نمی‌شوند. متن
نوبت فعلی به شکل یک projection محدودِ search اضافه می‌شود. برای اینکه پاسخ
کوتاه نسخه موضوع را گم نکند، واژه‌های موضوعی از پیام‌های قبلی کاربر هم داریم:

- tokenهای تاریخی دارای عدد، به‌صورت کامل از topic hint کنار می‌روند؛
  نسخه‌ها یا عددهای داخل کد خام و reasoning حذف نمی‌شوند.
- tokenهای مقدار user fact بازنشسته از hint کنار می‌روند؛ اگر همان مقدار
  دوباره active شده باشد، کنار نمی‌رود. این کنترل A → B → A را حفظ می‌کند.
- شناسه‌های `st.*` داخل کد قبلی برای حفظ موضوع اولویت دارند؛ کدی اجرا یا
  تفسیر نمی‌شود و این کلمات fact یا شاهد مستند نیستند.
- assistant قدیمی، source_ref و برچسب جعلی داخل متن به authority تبدیل نمی‌شوند.

query حداکثر ۵۰۰ کاراکتر است؛ factها کامل و در محدودهٔ فضای اختصاص‌یافته
pack می‌شوند، متن فعلی و hintها برای search محدودند. کلمات انتخابی summary
معنایی نیستند. کد تاریخی دارای عدد یا اطلاعات مهم خارج این projection ممکن
است در retrieval اولیه کم‌رنگ شود؛ کل آن در ورودی reasoning باقی است.
مقایسهٔ صریح قدیم/جدید در پیام **فعلی** عمداً هر دو عدد را نگه می‌دارد.
refinement مدل تغییر نکرده و تضمینی دربارهٔ نبود اصطلاح تاریخی در آن نمی‌دهیم.

ورودی optional و caller-owned `SupportEngine.run(initial_query=...)` فقط query
اول را تعیین می‌کند. فراخوانی‌های مستقیم قدیمی بدون آن رفتار legacy دارند؛
الگوریتم `build_initial_query` برای baseline دست‌نخورده مانده است. portها و
قراردادهای اشتراکی تغییر نکرده‌اند؛ adapter حسن دوباره ساخته نشده است.

## مقایسهٔ آفلاین ثبت‌شده

`experiments/retrieval_context/fixture-v1.json` ده variation از مسئلهٔ exposed
dev دارد: correction معمولی، تغییر صریح محیط، withdrawal، پاسخ کوتاه، برگشت
نسخه، مقایسه/کد فعلی، OS بازنشسته، source fact، برچسب جعلی و تاریخچهٔ بلند.
اولین متن از probe تألیفی قبلی و شناخت Issue #12782/#12629 می‌آید؛ پاسخ همان
Issue داخل evidence نیست. این‌ها ده case مستقل یا test نهایی نیستند و وارد
corpus واقعی نشوند. تصمیم‌های مجازِ pilot و شکاف کاربر/منبع قبل از مدل ثبت‌اند.

سه variant با **همان** CaseState و conversation مقایسه می‌شوند: تابع query
اصلی از Git `109f59e`، فقط آخرین پیام، و current state + topic. انتظارها
کنترل لفظی و حفظ موضوع‌اند؛ passing آن‌ها داوری semantic کیفیت نیست.

```bash
uv run python scripts/retrieval_context_comparison.py --validate-only
uv run python scripts/retrieval_context_comparison.py --output /tmp/query-context-new.json
uv run python scripts/retrieval_context_comparison.py --index /PATH/TO/REGISTERED/INDEX --output /tmp/query-context-index-new.json
uv run pytest tests/test_current_retrieval_context.py tests/test_retrieval_context_comparison.py
```

script قبل/بین/بعد اجرای variantها byteهای protocol، fixture، script و کد را
چک می‌کند؛ output موجود را بازنویسی نمی‌کند. حالت index، محتوای موجود و pin
snapshot/manifest را می‌خواند و query فیزیکی، IDs، scope، distance و hash متن
را جدا ثبت می‌کند. index ساخته یا embedding پولی مصرف نمی‌شود. این pilot
۱۴ source/۳۰ chunk دارد، API multiselect/fragment و release note ندارد و متن
بعضی APIها بین دو نسخه یکسان است؛ تغییر رتبه مساوی به معنی کیفیت بیشتر نیست.

## مقایسهٔ آنلاین ضروری و محدود

protocol تازهٔ `live-protocol-v1.json` و `case-v1.json` دو arm با **همان** state
و پیام کامل مدل دارند؛ فقط query اول و شواهد واقعاً برگشتی فرق دارند. سناریو
صریحاً `context_changed=True` دارد، یعنی محیط دیگر؛ Python قبلی unknown است.
correction معمولی با Python حفظ‌شده کنترل آفلاین جداست. oracle قبلی اشتباه
Python را تکرار نکرده‌ایم و protocol/receipt قبلی را عوض نکرده‌ایم.

پیش از key، هر دو retrieval/prompt روی همان index بررسی می‌شوند؛ source باید
clean، committed و pushشده باشد. همان ledger اصلی و grant توسعهٔ موجود استفاده
می‌شوند. سقف تازه: input reserve 16384، output 384، هر request $0.002956800 و
کل دو send حداکثر $0.005913600. حد قبلی با output 768 از remaining grant بیشتر
بود. هر arm یک attempt و یک دور retrieval دارد؛ repair، refinement یا retry
پولی خودکار نداریم. grant جدید، ledger دوم، reset یا unhalt ساخته نمی‌شود.

```bash
# eligibility/dry prompts only; no credential or provider send
uv run python scripts/retrieval_context_live_probe.py
# execute once, only from the clean pushed preregistration and ignored private .env
uv run python scripts/retrieval_context_live_probe.py --live --env-file .env --output-dir /PRIVATE/NEW/OUTPUT
```

request IDها، serving model معتبر، usage، هزینهٔ settled و hold نامعلوم جدا
ثبت می‌شوند؛ هزینهٔ کل نامعلوم null است. guard grant، ceiling، halt و incident
قدیمی را حفظ می‌کند؛ عدم قطعیت تازه اجرای باقی‌مانده را متوقف می‌کند. تغییر
fingerprint پس از مصرف مجوز این protocol را غیرقابل تکرار می‌کند. نتیجهٔ ناقص
ثبت می‌شود و مجوز اجرای دوباره نیست. پیشنهادها stage یا approve نمی‌شوند و
action صفر است. ordinary live factory همچنان در C5 halt مسدود است.

نتیجه و review هر دو arm پس از اجرا جدا ثبت شوند؛ این probe exposed dev است،
نه held-out، billing provider یا proof کیفیت نهایی RAG/model. حذف آلودگی
query، تغییر منابع و کیفیت سؤال/ادعا سه موضوع جدا برای گزارش‌اند.
