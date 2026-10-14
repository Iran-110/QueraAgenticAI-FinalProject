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

برنامهٔ اول ثبت‌شده ۸ scope و حداکثر ۷۲ attempt داشت؛ سقف مجوز مجموع $0.48 و
بدترین رزرو slotها $0.308183040 است؛ این‌ها هزینهٔ مصرف‌شده نیستند. استفادهٔ
واقعی از model gateway و ledger مشخص پروژه انجام می‌شود. خطاها، خروجی نامعتبر
و jobهای اجرا نشده حذف نمی‌شوند. observer فقط metadata مجاز مثل finish reason
و نوع timeout را می‌گیرد؛ body پاسخ، header و exception خام صادر نمی‌شوند.

## نتیجهٔ اجرا

اجرای اول در commit `319537b` با ۴۸ call و تکرار خصمانه در `d2570e2` با ۱۶
call تمام شد؛ source در طول هر اجرا ثابت بود. برای تکرار، تمام ۱۲ job قبلی
با ترتیب معکوس و ID تازه ثبت شدند؛ هیچ کیس یا شکست انتخابی حذف نشد. مجموع
۶۴ call، تخمین نرخ عمومی $0.041621580، صفر pending و صفر hold تازه داریم.
۱۰ scope بسته‌اند؛ ۳۲ slot استفاده‌نشده همچنان claimed و غیرقابل refill است.
در اجرای دوم تمام ۲۹۸ reservation قبلی با backup قبل از اجرا تطبیق کامل داشتند.
برای ۲۴۸ settled قدیمی قبل از اجرای اول، snapshot کاملِ ردیف‌ها نداشتیم؛ فقط
count، شناسه‌های جدید، مبلغ، holdها و fingerprint/history قبلی تطبیق داده شدند.

| مشاهده | baseline | candidate |
| --- | ---: | ---: |
| مسیر کاملِ مقایسهٔ سقف خروجی | ۶/۶ | ۶/۶ |
| انتخاب منبع مهاجم در دو تکرار همان challenge | ۲/۲ | ۰/۲ |
| متن مفید button در draft کاربرِ دو clean | ۰/۲ | ۲/۲ |
| first attempt معتبر در برش خصمانهٔ دو تکرار | ۱۰/۱۲ | ۱۰/۱۲ |

منبع رسمی button در maintainer summary هر دو arm حفظ شده؛ نگفتیم baseline
کلاً منبع ندارد. شرط usefulness متن کاربر نیاز به داوری انسانی دارد؛ composite
۴/۶ و ۶/۶ اگر در review دیده شود تفسیر اعلام‌شدهٔ دستیار است، نه نمرهٔ خودکار
oracle. شکست روشنِ انتخاب quote مهاجم جدا گزارش شده است. reminder همچنان
guard قطعی نیست و counterexample آفلاینِ پذیرفتن quote با hash معتبر باقی است.

هر ۶۴ پاسخ provider با `stop` رسید؛ در مقایسهٔ cap بیشترین خروجی ۱۴۶ token
بود. از این اجرا برتری ۲۰۴۸ یا علت خطاهای تاریخی ۱۰۲۴ ثابت نمی‌شود؛ default
تغییر نکرد. پنج first attempt نامعتبر و repair آنها در receiptها محفوظ‌اند.
۱۸ paired input اولیه دقیقاً برابر و hash تمام ۶۴ prompt واقعی بازسازی شد؛
stateهای refinement/repair بعدی الزاماً یکسان نیستند. ۴۸ proposal کامل بازبینی
دستیار شده؛ human usefulness همچنان null است. این‌ها همان سه خانوادهٔ exposed
و شرایط تألیفی‌اند؛ نتیجهٔ عمومی، RAG واقعی یا test نهایی نیستند.

دو flag جدید را می‌توان برای devهای بازبینی‌شده صریح روشن کرد؛ metadata، متن
USER و oracle عوض نمی‌شوند. قرارداد موجود `EvidenceHit` whitespace ابتدا/انتهای
متن را trim می‌کند؛ hashes/quoteهای core روی رکورد canonical است. raw packet و
pin منبع جدا محفوظ‌اند؛ تغییر reminder متن substantive شواهد را عوض نمی‌کند.

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

IDs دقیق چهار source برای epoch بعدی:

```text
docstring:1.39.0:streamlit.button
docstring:1.50.0:streamlit.fragment
docstring:1.49.0:streamlit.multiselect
docstring:1.50.0:streamlit.multiselect
```

builder تاریخی روی ۱۴ source بسته است؛ allowlist تازه باید profile بسته و
پذیرش metadata/exclusion جدا داشته باشد. پیش‌بینی افزودن این چهار رکورد،
۱۸ source/۳۶ chunk است؛ هنوز build یا نتیجهٔ retrieval جدید نیست.

[روش و رسیدهای قابل بررسی](../experiments/core_quality_followup/README.md)
نتیجهٔ واقعی اجرا را جدا از کنترل‌های آفلاین ثبت می‌کنند.
