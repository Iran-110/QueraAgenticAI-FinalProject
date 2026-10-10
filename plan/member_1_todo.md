# حسن — داده و RAG

وضعیت، checkboxها، وابستگی‌ها و شرط پایان هر task فقط در [plan اصلی](plan.md) نگهداری می‌شوند. این فایل راهنمای نقش است؛ فهرست موازی از وضعیت‌ها نسازیم. [نسخهٔ قبلی](archive/member_1_before_task_checklist.md) حفظ شده.

- **R1:** بازبینی seed موجود، provenance و نسخهٔ منابع؛ جمع‌آوری اولیه انجام شده و آماده‌سازی corpus با حسن ادامه پیدا می‌کند.
- **R2:** دریافت خانواده‌های dev/test از محمدحسن و ثبت corpus allowlist و exclusion قبل از index نهایی.
- **R3:** adapter بازیابی مطابق RetrievalRequest/EvidenceBundle، با metadata و آخرین bundle معتبر.
- **R4:** تست adapter و ارزیابی retrieval روی dev؛ pytest این بخش با حسن است.
- **P4:** برای pilot مشترک اول EvidenceBundle ثابت، بعد retrieval واقعی ارائه کند.

R1 و fixture مستقل قابل انجام‌اند؛ index نهایی به E1 وابسته است. خانواده‌های dev/test، پاسخ‌ها و duplicateها از index جدا می‌مانند.

قبل از کار branch خود را از main به‌روز کند. تغییر وضعیت task همراه evidence در همان PR ثبت و لینک PR در گروه معرفی شود.
