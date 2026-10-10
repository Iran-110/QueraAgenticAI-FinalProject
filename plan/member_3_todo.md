# محمد بهنام — tracker و ابزارها

وضعیت، checkboxها، وابستگی‌ها و شرط پایان هر task فقط در [plan اصلی](plan.md) نگهداری می‌شوند. این فایل راهنمای نقش است؛ فهرست موازی از وضعیت‌ها نسازیم. [نسخهٔ قبلی](archive/member_3_before_task_checklist.md) حفظ شده.

- **T1:** CaseState، revision، history، pending proposal و نتیجهٔ ابزار را پایدار نگه دارد؛ restart و جداسازی دو پرونده.
- **T2:** dedup رخداد، hash ورودی، compare-and-swap و invalidation approval را اتمیک پیاده کند.
- **T3:** reviewer و همان case/revision/proposal را کنترل کند؛ reject، edit، approval قدیمی و retry امن.
- **T4:** pytest tracker/tools، trace عملیاتی و reset واقعی را آماده کند؛ شواهد را برای evaluation به محمدحسن بدهد.
- **P3:** پروندهٔ pilot را پس از approval فقط یک بار ثبت کند؛ state ذخیره‌شده و ادامه پس از restart قابل بررسی باشد.

انتخاب caseهای dev/test، اجرای evaluation و گزارش نهایی با محمدحسن است. prototype حافظه‌ای UI جای tracker پایدار را نمی‌گیرد.

قبل از کار branch خود را از main به‌روز کند. تغییر وضعیت task همراه evidence در همان PR ثبت و لینک PR در گروه معرفی شود.
