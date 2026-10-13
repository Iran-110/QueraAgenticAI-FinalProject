# ادامهٔ سؤال و correction در UI آفلاین — C2h

در گزارش دستی [PR #40](two-case-ui-sqlite-smoke-2026-10-13.md)، بعد از تأیید
نسخهٔ کاربر، script دوباره نسخه را جزو اطلاعات مفقود اعلام می‌کرد. guard هسته
با `KnownFactMarkedMissing` جلوی این پیشنهاد را می‌گرفت. guard درست عمل می‌کرد؛
سؤال ثابت mock با facts جدید هماهنگ نبود.

اصلاح فقط در `offline_backend.configured_app`، برای حالت **بدون index** و
reasoning برابر `scripted` انجام شده است. سؤال بعدی اکنون از facts جاری
پرونده انتخاب می‌شود:

| وضعیت کاربر در سناریوی `ask` | پیشنهاد بعدی |
| --- | --- |
| نسخهٔ فعال و صریح کاربر نداریم | سؤال canonical نسخه؛ فقط `streamlit_version` مفقود است |
| نسخه معلوم است، تعریف widget را نداریم | `Can you share the widget's key and code?`؛ فقط `widget_definition` مفقود است |
| هر دو fact معلوم‌اند | ارجاع برای بررسی مستندات؛ شاهد synthetic پاسخ مستند را اثبات نمی‌کند |

در `ask_version` فقط نسخه مطرح است؛ پس از روشن شدن آن، script ارجاع می‌دهد و
سؤال widget اضافه نمی‌کند. fact باید `active` و دارای provenance نوع `user`
باشد. نسخه در evidence، fact بازنشسته یا متن آزاد پیام، تأیید نسخهٔ نصب‌شده
کاربر محسوب نمی‌شود. این دو gap از قبل برای همین سناریوی ساختگی تعریف شده‌اند؛
تشخیص خودکار همهٔ اطلاعات لازم برای هر Issue نیستند.

## امتحان از صفحهٔ واقعی

config خصوصی SQLite و reviewer را طبق [راهنمای backend/UI](offline-ui-index-pilot.fa.md)
آماده کنید. در ترمینال backend، برای انتخاب همین مسیر:

```bash
unset AGENT_PILOT_INDEX AGENT_PILOT_SNAPSHOT
export AGENT_PILOT_REASONING="scripted"
uv run uvicorn agent_app.offline_backend:application_factory --factory --host 127.0.0.1 --port 8000
```

در ترمینال UI، با همان تنظیم خصوصی reviewer و `AGENT_API_URL`:

```bash
uv run streamlit run app.py --server.address 127.0.0.1
```

سناریوی `Ask a follow-up question` را انتخاب کنید و مسئله را بفرستید. سؤال
نسخه تا approval به کاربر ارسال نمی‌شود. بعد از تأیید **همان سؤال canonical**،
فرم `Streamlit version` پاسخ کوتاه مثل `1.50.0` را به سؤال و revision ثبت‌شده
وصل می‌کند؛ این اتصال پس از restart backend هم از SQLite بازیابی می‌شود.

تعریف widget و correction را از فرم `Report facts and corrections` وارد کنید:
برای تعریف widget، نام fact برابر `widget_definition` و مقدار شامل key و
code باشد؛ برای اصلاح نسخه، از `streamlit_version` و مقدار جدید استفاده کنید.
سؤال widget فرم استخراج خودکار ندارد. پس از تأیید این facts، کمبود مستندات
با تکرار سؤال نسخه/widget جبران نمی‌شود و script ارجاع می‌دهد.

correction، revision و proposal تازه می‌سازد؛ approval قدیمیِ اجرا‌نشده رد
می‌شود. اگر approval قبلاً ثبت شده ولی ACK گم شده باشد، `Retry review` همان
operation را تأیید می‌کند و action دوم نمی‌سازد، حتی بعد از restart. تا روشن
شدن receipt، approval تازه در UI قابل اجرا نیست؛ دکمه می‌تواند حذف یا
غیرفعال باشد. retry یک event قدیمیِ ناموفق نیز نتیجهٔ ثبت‌شدهٔ همان event را
حفظ می‌کند. برای ادامه بعد از ارتقا، پیام تازه با turn ID تازه بفرستید؛
گزارش تاریخی #40 و outcome قبلی بازنویسی نمی‌شوند.

## شواهد و قدم بعد

[بستهٔ مقایسه](../experiments/offline_corrections/README.md) protocol اولیه،
baseline، candidate و amendment را جدا حفظ می‌کند. کنترل‌ها پیش از اصلاح
ثبت شدند. V1 روی کد قبلی ۵ pass و ۱۴ fail داشت؛ candidate اولیه ۱۸ pass و یک
شکست assertion UI داشت: تست وجود دکمهٔ غیرفعال را لازم می‌دانست، در حالی که
approval موفق pending را پاک می‌کند و دکمه نمایش داده نمی‌شود. V2 فقط این
assertion را به «هیچ approval قابل اجرا نباشد» تغییر داد؛ payload، revision،
receipt و شمار actionها ثابت ماندند. همان ۱۹ کنترل V2 روی Git-archive کد قدیم
`a6ec28d`، با source برابر `ab6ed04`، **۵ pass/۱۴ fail** و روی source جدید
`090c1e5` **۱۹ pass/صفر fail** دارند.

AppTest واقعی، سه process تازهٔ TCP، correction، canonical reply و retry
پایدار پوشش داده شده‌اند. سه نمونهٔ HTTP جدا برای نسخهٔ معلوم، correction و
هر دو fact معلوم، قبلاً همگی `KnownFactMarkedMissing` داشتند؛ حالا به‌ترتیب
سؤال widget، سؤال widget و ارجاع دارند. revisionها ۱/۲/۳ و actionهای این سه
نمونه صفرند. ابزار مقایسه نیز origin importها را با snapshot کنترل می‌کند؛
اولین guard بیش‌ازحد سخت namespace معتبر RAG را رد کرد و پیش از اجرای
مقایسه اصلاح شد. این توقف ابزار مقایسه، خطای محصول نبود.

مجموع suite محلی **۲۸۶۰ تست** در 111.83s، Ruff روی ۲۰۷ فایل، سه demo با lock
و پذیرش جداگانهٔ HTTP/SQLite **۴۵۷/۴۵۷** همراه restart پاس‌اند. runtime/test
bytes این بررسی‌ها با `090c1e5` یکسان‌اند؛ وجود harness ثبت‌نشده یا ویرایش‌شده هنگام اجرا
به معنی receipt یک Git کاملاً clean نیست. CI انتشار جدا بررسی می‌شود.
این نوبت مدل، index یا ledger واقعی را اجرا نکرده و هزینهٔ API صفر بوده است.
legacy API، scriptهای صریح دیگر، guard هسته، مسیر indexed/GroundedPlan/live و
قراردادهای مشترک تغییر نکرده‌اند.

برای تحویل تیم، بهنام و محمدحسن هنوز باید دو case را از UI دستی تکرار و
`Edit`/`Reject` را با SQLite بررسی کنند؛ receipt جدید را کنار گزارش #40
ثبت کنند. T4، U3 و E5 با این تست‌های خودکار بسته نمی‌شوند. کیفیت مدل/RAG و
ارزیابی نهایی هم جدا باقی‌اند؛ [plan و checklist](../plan/plan.md) مبنای تقسیم
کار است.
