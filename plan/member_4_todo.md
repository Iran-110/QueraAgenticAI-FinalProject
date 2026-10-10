# محمدحسن — UI و evaluation

وضعیت، checkboxها، وابستگی‌ها و شرط پایان هر task فقط در [plan اصلی](plan.md) نگهداری می‌شوند. این فایل راهنمای نقش است؛ فهرست موازی از وضعیت‌ها نسازیم. [نسخهٔ قبلی](archive/member_4_before_task_checklist.md) حفظ شده.

- **U1:** prototype آفلاین Streamlit/FastAPI روی main موجود است؛ FakeRetriever/FakeReasoner و storage حافظه‌ای هنوز صریح‌اند.
- **U2 / U3:** اطلاعات صریح و correction را به قرارداد core وصل کند؛ کل پیشنهاد/منابع و review را نمایش دهد و اتصال واقعی را جدا تست کند.
- **E1 / P1:** حداقل ۱۵ dev و ۱۵ test در سطح خانواده انتخاب کند؛ حداقل ۱۰ سناریوی چندنوبتی، شامل حداقل ۵ در test. برای pilot یک case از dev تعریف کند.
- **E2 / E3:** fixture با ورودی شروع و ادامهٔ گفتگو، rubric و runner خودکار بسازد؛ جواب/gold وارد ورودی مدل یا index نشود.
- **E4 / E5:** baseline و تنظیم فقط روی dev، سپس freeze و test نهایی و گزارش کیفیت/شکست/هزینه.
- **E6:** bonus و ارائه پس از مسیر اصلی؛ دامنهٔ bonus با منتور هماهنگ شود.

pytest UI/API و schema/runner evaluation با محمدحسن است؛ برای قرارداد از ساسان و برای شواهد retrieval/tracker از حسن و بهنام کمک بگیرد. UI ورودی آزاد دارد و به ۳۰ case محدود نمی‌شود؛ demo دستی جای runner ارزیابی را نمی‌گیرد.

قبل از کار branch خود را از main به‌روز کند. تغییر وضعیت task همراه evidence در همان PR ثبت و لینک PR در گروه معرفی شود.
