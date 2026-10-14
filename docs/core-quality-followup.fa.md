# بهبود محدود core بعد از C4e

تمدید دو روزه و مجوز تازهٔ ساسان برای آزمایش paid، مبنای این مرحله است.
نتیجهٔ قبلی ۷/۹ تغییر نمی‌کند. ورودی‌های همان سه خانواده exposed و answer-informed،
جواب‌های authored و oracle قبلی ثابت‌اند؛ صفر case تازهٔ held-out داریم.

دو مقایسه قبل از مدل ثبت شده‌اند: سقف خروجی ۱۰۲۴ در برابر ۲۰۴۸، و reminder
عمومیِ انتخاب منبع روی شش وضعیت سالم/خصمانه. در مقایسهٔ reminder، هر دو arm
سقف ۲۰۴۸ دارند. hash درست یا نسخهٔ همسان هنوز تضمین صحت محتوا نیست؛ reminder
guard قطعیِ quote یا تشخیص خودکار conflict نیست. همهٔ سطح‌های پاسخ باید بررسی شوند.

اصلاح renderer جداست: وقتی caller کمبود منبع را اعلام کرده، حالت اختیاری
`source_gap_investigation=True` گزارش و code فعلی USER را به‌عنوان موضوع بررسی
می‌آورد؛ علت/fix را از quote عمومی نتیجه نمی‌گیرد و بررسی را اقدام انجام‌شده
نمی‌خواند. ۱۷ کنترل یکسان روی archive اصلی، قبل ۴ پاس/۱۳ شکست و بعد ۱۷ پاس
داشتند. replay دو پاسخ قدیمی Enum جدا ثبت است؛ نتیجهٔ live قدیمی نمرهٔ تازه نمی‌گیرد.
پاسخ‌ها بلندند و usefulness انسانی هنوز بررسی نشده است.

## هزینه و توقف

دو درخواست نامعلوم با hold مجموع $0.0233792 باقی‌اند. سقف ledger همان $4.50
و halt عمومی فعال است؛ grant و scopeهای قبلی احیا نمی‌شوند. API تازهٔ
`authorize_quarantine_scope` فقط برای مجوز تازهٔ انسانی و یک protocol محدود است:
تمام رکوردهای نامعلوم، audit trail و history قبلی، source و ورودی‌ها و request
IDهای تازه دقیقاً bind می‌شوند. بسته‌شدن scope دائمی است. خطای نامعلوم تازه،
overrun یا تغییر این مبنا کل آزمایش را متوقف می‌کند؛ pending/hold خودکار آزاد نمی‌شود.
این مسیر C5 را نمی‌بندد و برای startup معمول برنامه اجازهٔ live نمی‌دهد.

برنامهٔ ثبت‌شده ۸ scope و حداکثر ۷۲ attempt دارد؛ سقف مجوز مجموع $0.48 و
بدترین رزرو slotها $0.308183040 است؛ این‌ها هزینهٔ مصرف‌شده نیستند. استفادهٔ
واقعی از model gateway و ledger مشخص پروژه انجام می‌شود. خطاها، خروجی نامعتبر
و jobهای اجرا نشده حذف نمی‌شوند. observer فقط metadata مجاز مثل finish reason
و نوع timeout را می‌گیرد؛ body پاسخ، header و exception خام صادر نمی‌شوند.

## اتصال تیم

قراردادهای مشترک، tracker، UI و corpus عوض نشده‌اند. factory موجود دو flag
اختیاری می‌پذیرد: `METIS_GROUNDED_SOURCE_GAP_INVESTIGATION=true` با handoff فعال،
و `METIS_GROUNDED_SOURCE_SELECTION_REMINDER=true` در حالت GroundedPlan.
هر دو پیش‌فرض false دارند و مجوز هزینه یا اجرا نیستند. خروجی پیشنهاد همچنان
به approval همان case/revision/proposal نیاز دارد.

index واقعی فعلی ۱۴ source/۳۰ chunk دارد. چهار source لازم برای coverage
این devها هنوز در آن نیستند: button 1.39، fragment 1.50 و multiselect 1.49/1.50.
رکوردها در seed موجود و pin شده‌اند؛ کار حسن یک epoch تازه با allowlist و
exclusion/metadata/receipt مشخص است. builder تاریخی pilot و manifest اصلی
برای بازتولید محفوظ‌اند. محمدحسن همچنان review انسانی و split کامل را دارد؛
smoke دستی بهنام با آزمایش‌های خودکار جایگزین نمی‌شود.

[روش و رسیدهای قابل بررسی](../experiments/core_quality_followup/README.md)
نتیجهٔ واقعی اجرا را جدا از کنترل‌های آفلاین ثبت می‌کنند.
