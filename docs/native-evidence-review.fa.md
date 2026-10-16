# gold بومی و شواهد همان نوبت

پیشنهاد محمدحسن برای native gold جدا درست است. اما «source به مدل رسید»
شرط کافی برای answer نیست: passage باید ادعای همان پاسخ، محدودهٔ API، نسخهٔ
فعال کاربر و caveatهای لازم را پشتیبانی کند. بودن اسم source در index، bundle
یا citation این پشتیبانی را ثابت نمی‌کند.

## قرارداد review پیش از freeze

- هر turn، اطلاعات معلوم کاربر، gap کاربر و gap منبع را جدا ثبت کند. ask فقط
  وقتی پذیرفته شود که سؤال لازم، قابل پاسخ و تکراری نباشد؛ داشتن docs سؤال
  ضروری کاربر را حذف نمی‌کند و نبود docs هم مجوز پرسیدن اطلاعات معلوم نیست.
  اگر سؤال لازم در vocabulary ثابت عرضه نمی‌شود، محدودیت قابلیت سیستم ثبت
  شود؛ برای قبول‌شدن test سؤال یا alias تازه از روی آن نسازیم.
- پاسخ کامل یا جزئیِ مستند، ارجاع بخش حل‌نشده و retrieval بیشتر در سقف موجود
  جدا دیده شوند. نبود passage هدف، فقط کمبود همان bundle است؛ نه اثبات نبود
  راه‌حل، ممنوع‌بودن همهٔ پاسخ‌ها یا درست‌بودن هر escalation.
- passageهای لازم را با متن و revision مشخص ثبت کنیم؛ برای منابع معادل،
  alternativeهای از پیش بررسی‌شده داشته باشیم. یک source ثابت را تنها پاسخ
  ممکن حساب نکنیم. شرط مکانیکی حضور متن از داوری ارتباط، کفایت و support جداست.
- scope تازه به fixture/turn، rubric، config انتخاب‌شده، build/index/allowlist/
  exclusion و handoff/attempt واقعی bind شود. build هنوز ساخته نشده، پس pin
  نهایی ادعا نمی‌شود؛ پیش از اجرای نهایی باید همهٔ pinها تکمیل و freeze شوند.
- همهٔ routeهای لازم از قبل ثبت شوند، ولی runner فعلی فقط عضویت decision در
  gold و مسیر ثبت‌شده را بررسی می‌کند. `evidence_condition` و `required_sources`
  را داوری معنایی یا شرط خودکار route نمی‌کند؛ نتیجهٔ عملیاتی با review شرطی
  انسان جدا گزارش شود. gold و نیازهای منابع هرگز وارد prompt یا retriever نشوند.

native gold برای test نهایی روی index واقعی هم لازم است. مالک evaluation آن
را پیش از اجرا می‌نویسد و بدون retrieval روی test ثبت می‌کند؛ توسعهٔ core/RAG
محتوای آن را نمی‌بیند. corpus و vocabulary از روی سؤال یا نتیجهٔ test تنظیم
نمی‌شوند. تمام caseها، از جمله خطا/عدم پاسخ/نرسیدن شاهد، در گزارش باقی می‌مانند.
پوشش retrieval و کیفیت تصمیم مشروط به شواهد، دو denominator جدا دارند؛ نرسیدن
شاهد نباید باعث حذف case یا تبدیل خودکار آن به موفقیت مدل شود.

## PR79 چه چیزی را تحویل می‌دهد؟

v2 سه dev با rubric v1، **شواهد ثابت** دارند؛ native gold نیستند. همان سه
خانواده‌اند، نه سه case مستقل تازه. fixtureهای v1، gold و receiptهای قبلی حفظ
می‌شوند. review «۸ از ۸» تأیید کارت‌های تغییر با کمک توضیح دستیار است: ۵ correct
و ۳ unsure اولیه به ۸ correct نهایی رسیده‌اند؛ نمرهٔ کیفیت مدل یا بررسی مستقل
تمام ادعاهای خروجی نیست. محدودیتِ ادامهٔ بی‌پاسخ سؤال کد case-a هم محفوظ است.

اجازهٔ tip در decision conditionِ case-b، شرط support rubric را تغییر نمی‌دهد.
گفتنِ «در منابع پیدا نکردم» ادعای محصول/API/نسخه را مستند نمی‌کند؛ اگر ادعای
مهمی بی‌پشتوانه باشد، support gate همچنان صفر است، حتی اگر decision یا usefulness
جدا قابل قبول باشد. پیشنهاد آزمایش با نتیجهٔ نامعلوم باید از ادعای قابلیت یا
fix جدا داوری شود؛ هیچ فرضیه‌ای خودکار به پشتیبانی‌شده تبدیل نمی‌شود.
gold و نمره‌های انسانی PR79 برای این توضیح بازنویسی نشده‌اند.

شناسه‌های `required_sources` در v2، labelهای bundle ثابت‌اند؛ آن‌ها را با
source یا chunk بومی index یکسان نگیریم. native registration باید provenance
و passage واقعی خودش را داشته باشد و بعد از build نهایی pin شود.

## corpus فعلی را با corpus نهایی اشتباه نگیریم

manifest pinned بیلد توسعهٔ `coverage-18`، ۱۸ source و ۳۶ chunk دارد: ۵ Markdown و
۱۳ docstring، بدون release note. نسخه‌های docstring آن ۱٫۳۹٫۰، ۱٫۴۹٫۰، ۱٫۵۰٫۰ و
۱٫۶۴٫۰ هستند؛ ۱٫۲۲ در این inventory نیست. این شمارش از metadata ثبت‌شده است،
نه retrieval تازه یا فهرست تمام دادهٔ seed. پس نگرانی محمدحسن دربارهٔ نبودن
بعضی شواهد در این بیلد بجاست؛ این index را پوشش کامل ۱۶ dev حساب نمی‌کنیم.

انتخاب corpus نهایی با حسن است: سیاست عمومی docs/release notes/API نسخه‌دار،
raw hash/revision، build قابل بازتولید و exclusion نهایی را ثبت کند؛ اضافه‌کردن
هر سند فقط به‌خاطر جواب یک test مجاز نیست. وجود passage در corpus و رسیدن آن
به request، دو مشاهدهٔ مستقل باقی می‌مانند. این task corpus یا ranking را
تغییر نداده است.

## ابزار کمکی مستقل سمت core

[`evidence_observation.py`](../src/agent_app/evaluation/evidence_observation.py)
یک observer آفلاین و بدون hook در runner است. requirementها از گروه‌های AND و
alternativeهای OR ساخته می‌شوند. هر alternative، `source_id`، `source_commit`
صریح، `source_url` و `passage` دقیق دارد؛ `None` برای revision مقدار دقیق است،
نه wildcard. score/rank و chunk ID شرط جست‌وجو نیستند؛ hash کامل hit بعد از
مشاهده ثبت می‌شود تا تغییر score هویت passage را خراب نکند.

`passage_requirements_sha256` کل declaration مرتب را bind می‌کند؛
`observe_required_passages` آن hash و `expected_handoff_sha256` مستقل را کنترل
می‌کند، handoff را با validator موجود می‌سنجد و فقط bundle همان handoff را
جست‌وجو می‌کند. متن باید کامل داخل یک hit باشد؛ متن چند chunk به هم دوخته
نمی‌شود. برای هر hit منطبق، اولین span دقیق Unicode، hash، version scope و
عضویت chunk در citation جدا ثبت می‌شوند؛ citation داوری support نیست.

خروجی، حضور/عدم مشاهدهٔ requirementها را می‌دهد؛ support، کفایت پاسخ و تصمیم
همچنان `unassessed` هستند. مشاهدهٔ همهٔ متن‌ها نمرهٔ کیفیت نمی‌سازد. handoff
ناموجود یا خراب رد می‌شود و به «همهٔ منابع غایب‌اند» تبدیل نمی‌شود. caller باید
این مشاهده را به attempt واقعاً ثبت‌شدهٔ همان turn وصل کند؛ helper ارسال به
provider، منشأ واقعی source، preregistration انسانی یا build فیزیکی را احراز
نمی‌کند. نتیجه‌های post-hoc باید صریحاً post-hoc بمانند.

```python
from agent_app.evaluation.evidence_observation import observe_required_passages

# requirements پیش از run بررسی/ثبت شده؛ expected hash از رکورد attempt
# همان turn می‌آید، نه از model یا خود معیارِ مورد داوری.
observation = observe_required_passages(
    captured_handoff,
    requirements,
    expected_handoff_sha256=captured_handoff_sha256,
    requirements_sha256=registered_requirements_sha256,
)
```

سقف ۲۰ requirement، ۱۰ alternative در هر گروه و ۱۰۰ alternative در کل است؛ ورودی
خالی/خراب، hash نامطابق و declaration تکراری با `EvidenceObservationRejected`
رد می‌شوند. این helper کتابخانه‌ای است؛ CLI، UI و runner خودکار ندارد.

این ابزار gold را انتخاب نمی‌کند، decision را عوض نمی‌کند و اجازهٔ اجرا یا
پرداخت نمی‌دهد. ranking/corpus، UI/tracker، renderer و حدود تلاش‌ها تغییر
نمی‌کنند. `halt` و سه hold هزینه حفظ‌اند.

## شواهد این تحویل

[review PR79](receipts/pr79-review-2026-10-16.json)،
[verification](receipts/native-evidence-review-2026-10-16.json) و
[probe آرشیوی](receipts/native-evidence-archive-probe-2026-10-16.json).
۵۲ تست observer و ۶ کنترل scorer موجود اضافه شده؛ ۱۰۷ تست متمرکز root و ۱۵۶ تست
متمرکز review مستقل پاس‌اند و با suite جمع نمی‌شوند. ۱۲ probe جدا هم hidden
state را با diagnostic ثابت رد می‌کنند. همهٔ ۵۹۶۸ تست انتخاب‌شده پوشش موفق
دارند: ۵۹۶۳ در CWD خنثی و پنج تست مسیر نسبی/CLI از ریشهٔ مخزن. یک تست خواندن تمام
held-outها عمداً کنار گذاشته شد؛ این **یک اجرای یک‌تکهٔ کاملاً سبز نیست**.

اجرای اولیه با guard اضافی فایل واقعی `.env`، setupهای Chroma را متوقف کرد؛
کتابخانه dotenv مربوط به CWD را به‌صورت ضمنی می‌خواند. اجرای خنثی کلید دستگاه را از
آن dependency جدا کرد؛ پنج شکست باقیمانده فقط مسیرهای نسبی بودند و همان پنج
ID از CWD درست پاس شدند. هیچ کد یا تستی بین اجراها برای عبور از خطا عوض نشد؛
guardها برقرار و log/receipt همهٔ تلاش‌ها محفوظ‌اند. دو اجرای نهایی در parent
تلاش بازکردن test یا فایل اصلی `.env` نداشتند؛ این audit شامل فایل‌های تمام
subprocessها نیست. runtime/config پیش‌فرض تغییر نکرده‌اند.

probe آرشیوی دو passage تألیفی از یک سند را بررسی می‌کند؛ فقط یکی در handoff
بود. این دو، معیارِ پاسخ مسئلهٔ icon نیستند؛ صرفاً کنترل ابزار روی دادهٔ exposed
و post-hoc هستند. نمره یا قضاوت انسانی/مدل تازه ساخته نشده است. بیلد اصلی،
۱۹ pin، ledger، exclusion و metadata مربوط به test محفوظ‌اند؛ C5 read-only با ۳۶/۳۶ به معنی
تطبیق provider نیست. API صفر است؛ CI موفق و freeze/test نهایی ادعا نشده‌اند.
