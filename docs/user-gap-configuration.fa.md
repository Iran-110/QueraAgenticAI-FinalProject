# اتصال vocabulary سؤال به backend معمول — C4c

مسیر معمول `evaluation.live.configured_factory` قبلاً تعریف سؤال‌های caller را
نمی‌گرفت. با نسخهٔ معلوم، حتی اگر `parent_callback_code` در unknowns پرونده بود،
این سؤال به مدل عرضه نمی‌شد. در آزمایش‌های قبلی injection مستقیم Python این
قابلیت را فراهم می‌کرد؛ مشکل در اتصال تنظیمات بود، نه guard هسته.

حالا تنظیم اختیاری `AGENT_USER_GAP_CATALOG` فایل JSON بازبینی‌شدهٔ caller را
یک‌بار هنگام ساخت factory می‌خواند. runner معمول و `live_backend` از همین
factory استفاده می‌کنند. بدون این تنظیم، vocabulary اضافی خالی است و رفتار
پیش‌فرض حفظ می‌شود. این تغییر gate اجرای live را باز نمی‌کند؛ C5 همچنان باز است.

## تنظیم فایل

نمونهٔ یک تعریف خنثی؛ این فایل را به‌عنوان تنظیم محلی maintainer آماده کنید:

```json
{
  "schema_version": 1,
  "user_gaps": [
    {
      "name": "parent_callback_code",
      "kind": "user",
      "description": "The parent selector callback is not supplied.",
      "necessity": "The callback and nearby state updates can help inspect the unseen application path; documentation does not establish its cause.",
      "question": "Can you share the parent selector callback and its relevant state updates?"
    }
  ]
}
```

در تنظیمات همان process، مسیر فایل را به `AGENT_USER_GAP_CATALOG` بدهید. نام
متغیر توسط پیام، source یا مدل انتخاب نمی‌شود. فایل حداکثر ۳۲۷۶۸ byte UTF-8،
دو کلید دقیق بالا و حداکثر شش تعریف `GroundedGap` از نوع user دارد. duplicate
JSON، schema نامعتبر، فیلد اضافی، source gap، نام reserved و نام تکراری با
case متفاوت رد می‌شوند. `streamlit_version`، `exact_version_documentation` و
`unresolved_prior_source_conflict` قابل override نیستند.

بررسی budget و index پیش از این فایل انجام می‌شود؛ فایل نامعتبر نیز پیش از
credential lookup و ساخت provider client با خطای عمومی متوقف می‌شود. نام، متن
خطای parser یا محتوای فایل در diagnostic صادر نمی‌شود. تغییر فایل، factory
ساخته‌شده را عوض نمی‌کند؛ برای اعمال vocabulary جدید process را restart کنید.

## caller چه چیزی باید بفرستد؟

تعریف سؤال به‌تنهایی آن را فعال نمی‌کند. `unknowns` فعلی باید نام همان gap را
داشته باشد. در API مثلاً `unknowns: ["parent_callback_code"]`؛ در UI موجود فرم
`Report facts and corrections`، قسمت `New unknowns (one per line)` همین ورودی
را می‌فرستد. از روی prose یا source کمبود تازه استخراج نمی‌کنیم.

وقتی کاربر پاسخ را داد، آن را با همان نام در `reported_facts` ثبت کنید. fact
فعال USER سؤال را حذف می‌کند، حتی اگر نام قدیمی در unknowns باقی مانده باشد.
fact قدیمی یا EVIDENCE، تأیید اطلاعات کاربر نیست. correction و تغییر revision
همان قرارداد قبلی را دارند؛ permission اجرای action از vocabulary نمی‌آید.
سؤال canonical نسخه، source gaps و guard تعارض تغییر نکرده‌اند.

caller باید خنثی‌بودن، ضرورت و پاسخ‌پذیری سؤال را review کند. اعتبار schema
اثبات نمی‌کند که هر سؤال لازم است. نمونهٔ خراب را با نمونهٔ کاهش‌یافته‌ای که
کار می‌کند اشتباه نگیریم؛ سؤال نیز نباید از قبل callback را علت reset بداند.

## شواهد و محدودیت

[protocol و oracle قبل از اصلاح](../experiments/user_gap_configuration/README.md)
۲۱ کنترل را ثبت کردند. چهار state/message/bundle از همان خانوادهٔ exposed
#12782/#12629 و سه سؤال V9 حفظ‌اند؛ source catalog بین دو arm برابر است، ولی
catalog سؤال و hash کامل درخواست عمداً فرق دارند. این‌ها case مستقل نیستند.
gold، reviewer و label سناریو در درخواست مدل قرار نمی‌گیرند.

مقایسهٔ واقعی Git-archive کد قدیم و جدید، با همان byteهای کنترل‌ها، از **۹ pass
و ۱۲ fail به ۲۱ pass** رسید. دوازده کنترل رفع‌شده مربوط به اتصال/اعتبارسنجی
configuration و مسیر HTTP هستند؛ دوازده تصمیم مدل نیستند. چهار مقایسهٔ core
با planner تألیفی، امکان طرح سؤال callback را در سه state و حفظ سؤال نسخه را
در state نامعلوم بررسی می‌کنند؛ injection مستقیم قبلاً هم این قابلیت را داشت.

کنترل HTTP از factory واقعی، Chroma آفلاین و SQLite استفاده می‌کند؛ چهار
درخواست provider کاملاً mock‌اند. correction، رد approval قدیمی، دریافت
callback، جدایی دو case و retry review پس از ساخت مجدد backend بدون action یا
wire اضافه پاس‌اند. تست کامل **۲۸۸۱** و پذیرش HTTP/SQLite **۴۵۷/۴۵۷** پاس‌اند؛
epoch، hash و CI انتشار جدا در packet ثبت شوند.

مدل واقعی یا corpus نهایی ارزیابی نشده؛ کیفیت انتخاب مدل، cause/fix و usefulness
انسانی ثابت نشده‌اند. یک pair کوچک نیز در grant باقی‌مانده reserve کامل ندارد؛
برای این تغییر paid call، refill، reset یا unhalt انجام نمی‌شود. halt و hold
قبلی محفوظ‌اند. dev/test، exclusion نهایی و T4/U3/E5 هنوز کار خود را دارند.

از root، بدون کلید:

```bash
uv run pytest tests/test_configured_user_gap_catalog.py tests/test_user_gap_configuration_http.py
uv run python scripts/user_gap_configuration_comparison.py --output /tmp/user-gap-comparison.json
```

خروجی مقایسه باید مسیر تازه‌ای باشد. [plan](../plan/plan.md) مرجع وضعیت و تقسیم
کار است؛ برای adopted vocabulary و unknownهای واقعی هر dev case، با صاحب
UI/evaluation هماهنگ شود.
