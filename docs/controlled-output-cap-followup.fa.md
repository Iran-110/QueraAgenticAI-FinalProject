# پیش‌ثبت follow-up محدود C4a

baseline اصلی روی commit `8b16f2c` سه درخواست واقعی داشت: دو proposal سؤال
callback و یک `ProviderResponseInvalid` برای نسخهٔ نامشخص. سه condition بعدی
به‌دلیل خطای terminal اجرا نشدند. خروجی درخواست سوم ۳۸۴ token، برابر سقف
ثبت‌شده بود؛ `finish_reason` در رسید اول ثبت نشده و علت truncation قطعی نیست.
اصل protocol و receipt اول تغییر نمی‌کنند.

این follow-up یک آزمایش تازهٔ تخصیص سقف خروجی است، نه retry خودکار baseline
و نه اصلاح prompt محصول. فقط همان condition نسخهٔ نامشخص با همان state،
پیام، پنج source، catalog دستی و همان reviewer اجرا می‌شود. SHA پیام اولیه
`706520610e1eea395765bcf306d36f1558d130304309b91856c9a549eea4117c`
باید با درخواست واقعی قبلی برابر بماند. مدل همان `gpt-4o-mini` است.

سقف خروجی از ۳۸۴ به ۵۱۲ و reserve محافظه‌کار ورودی از ۱۶۳۸۴ به ۱۵۳۶۰
تغییر می‌کند؛ تمام مسیرهای ثبت‌شدهٔ prompt با همان متن در این reserve جا
می‌شوند. هزینهٔ رزرو با قیمت ثبت‌شدهٔ Metis برابر `$0.002872320` است و از
باقی‌ماندهٔ grant قبلی، `$0.002909545`، کمتر است. این آزمایش فقط **یک send**
دارد؛ انتخاب repair یا retrieval بیشتر مجوز send دوم نیست و نتیجهٔ ناقص
همان‌طور گزارش می‌شود. سقف منطقی core همچنان ۲ attempt و ۲ retrieval round است.

پروتکل تازه source، fixture، reviewer، prompt و ledger را روی commit تمیز و
push‌شده pin می‌کند؛ قبل از کلیدخوانی و هر attempt/send دوباره بررسی می‌شوند.
همان ledger اصلی، halt و uncertainty قبلی `$0.02` حفظ می‌شوند. هیچ grant
تازه، refill، reset یا unhalt انجام نمی‌شود. پایان provider فقط به‌صورت مقدار
allowlist ثبت می‌شود؛ payload خام یا validation error حاوی ورودی صادر نمی‌شود.

اگر این بار خروجی کامل برسد، فقط تکمیل عملیاتی یک ورودی را با اجرای قبلی
مقایسه می‌کنیم. یک نمونه و تغییر resource، بهبود کیفیت تصمیم یا اثبات علت
خطای قبلی نیست. اگر باز شکست بخورد، receipt شکست هم منتشر می‌شود و اجرای
دیگری از این پروتکل انجام نمی‌دهیم. انتخاب‌های واقعی، بررسی کل پاسخ و
پشتیبانی منبع جدا ثبت می‌شوند؛ usefulness انسانی و امتیاز test همچنان نداریم.

دستورهای ریشهٔ پروژه:

```bash
# mock: بدون کلید و بدون ledger اصلی
uv run python scripts/controlled_model_baseline.py --output-cap-followup --mock
# preflight خواندنی؛ پس از مصرف fingerprint دیگر واجد شرایط نیست
uv run python scripts/controlled_model_baseline.py --output-cap-followup
```

اجرای live فقط روی source preregistered و ledger واجد شرایط، با `.env` محلی
و output directory تازه انجام می‌شود. این خانواده exposed است؛ تمام caseها،
reviewer، پاسخ‌ها و receiptهای آن از corpus واقعی و test مستقل خارج می‌مانند.
