# ادامهٔ پرونده پس از session تازهٔ UI

پرونده و پیشنهاد در SQLite می‌ماندند، اما session تازهٔ UI فقط caseهای همان
session را فهرست می‌کرد. اکنون در sidebar، **Saved case ID** و **Open saved case**
برای backend پایدار وجود دارد. شناسهٔ پرونده را نگه دارید؛ این قابلیت همهٔ
پرونده‌های backend را فهرست نمی‌کند.

پس از pull، UI را دوباره اجرا کنید تا client جدید ساخته شود:

```bash
uv run streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

این فرمان از backend و تنظیم خصوصی قبلی استفاده می‌کند. برای نمایش آفلاین،
backend موجود `agent_app.offline_backend:application_factory` را با SQLite و
reviewer configuration محلی خودتان اجرا کنید؛ کلید یا token را داخل مستندات
یا پیام گروه نگذارید. بازکردن پرونده، halt مدل را تغییر نمی‌دهد.

## رفتار و مرزها

ورودی دستی پیش از HTTP، از نظر نوع/طول/کاراکترهای شناسه بررسی می‌شود. فقط
backend با قابلیت durable پذیرفته می‌شود. شناسهٔ ناموجود یا پاسخ خراب، case
فعال را عوض نمی‌کند. هیچ پیام یا پرونده‌ای با این کار ساخته نمی‌شود.

بازکردن موفق فقط GET است: facts، revision، history و proposal جاری از پاسخ
اعتبارسنجی‌شدهٔ backend برمی‌گردند. approval، retry یا اجرای agent خودکار نداریم.
اگر در فاصلهٔ بسته‌شدن UI، پیشنهاد ویرایش/رد/تأیید شده باشد، همان وضعیت جاری
نمایش داده می‌شود؛ cache قبلی مجوز اجرای دوباره نمی‌سازد. دکمه‌های review همان
کنترل token، revision و handoff قبلی را دارند.

در همان session، envelopeهای پیام و review نامطمئن به case خودشان تعلق دارند
و با جابه‌جایی حذف یا منتقل نمی‌شوند. اما session کاملاً تازه، draft ارسال‌نشده
یا شناسهٔ اصلی ReviewOperation گم‌شده را از مرورگر قبلی بازسازی نمی‌کند. این
قابلیت durable outbox نیست؛ وضعیت ثبت‌شدهٔ backend را دوباره می‌خواند. متن
ویرایش‌شده‌ای که قبلاً در backend ذخیره شده است، بخشی از proposal جاری است.

[تست‌های بازیابی](../tests/test_ui_case_reopen.py) از داده و DB موقت استفاده
می‌کنند؛ روش اجرا، source، شمارش و مرز restart در
[رسید](receipts/team-closeout-2026-10-17.json) ثبت شده است. ۴۱ کنترل تازه،
review مستقل ۴۱ تست و اجرای مشترک ۳۷۸ تست مرتبط پاس‌اند؛ این شمارش‌ها
هم‌پوشان‌اند. AppTest تازه با توقف و اجرای پردازش تازهٔ backend روی TCP،
proposal منتظر تأیید را برگرداند و شمار رکوردهای هر هشت جدول durable ثابت
ماند. بازبینی مستقل TCP، parent و هر دو backend را جدا guard کرد؛ این روش
جای مشاهدهٔ دستی Chrome یا اجرای تازهٔ Windows را نمی‌گیرد. این‌ها شاهد کیفیت
پاسخ مدل، retrieval نهایی یا آزمون نهایی پروژه نیستند.

```bash
uv run pytest tests/test_ui_case_reopen.py -q
```
