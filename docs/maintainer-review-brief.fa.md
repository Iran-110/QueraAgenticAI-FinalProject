# متن بررسی maintainer و خوانایی Enum

**ادامهٔ C4q:** [ثبت و ساخت کنترل‌شدهٔ reasoner](core-closeout.fa.md) اکنون
policy جدید را در envelope v2 و constructor واقعی bind می‌کند. descriptor v1
و factory معمول همچنان تغییر نکرده‌اند؛ انتخاب نهایی و review کیفیت باقی است.


این تغییر پاسخ به بازخورد PR77 است: متن ارجاع عمومی بود، منابع عرضه‌شده را
نشان نمی‌داد و کد گزارش Enum با markerهای CRLF خوانا نبود. قالب جدید، اطلاعات
موجود را مرتب می‌کند؛ تشخیص Enum، فرضیهٔ تازه یا fix بی‌منبع تولید نمی‌کند.

## رفتار جدید

با انتخاب صریح `review_brief=True`، هر دو مسیر `GroundedReasoner` و
`ClaimReasoner` پیش از ساخت handoff، یک `AnalysisResult` تازه می‌سازند:

- گزارش/history عرضه‌شدهٔ کاربر، case و revision، تمام factهای فعال USER،
  بررسی‌های گزارش‌شده و unknownها در summary می‌آیند. گزارش/history ممکن است
  نسخهٔ قدیمی را در متن خود داشته باشد؛ نسخهٔ جاری فقط از fact فعال USER می‌آید.
- inventory همهٔ hitهای عرضه‌شده را با URL، revision، span، نسخه و scope نشان
  می‌دهد. «انتخاب مدل»، «نمایش اجباری به علت conflict» و «صرفاً عرضه‌شده» جدا
  هستند. هیچ‌کدام به معنی review معنایی یا پشتیبانی ادعا نیست.
- gap کاربر و منبع با description و necessity ثبت‌شدهٔ caller نمایش داده
  می‌شوند؛ conflict فعلی یا باقی‌مانده از attempt قبلی پنهان نمی‌شود.
- قدم بعدی، **پیشنهاد** بازتولید گزارش با کد عرضه‌شده و نسخهٔ گزارش‌شده است؛
  نتیجهٔ اجرا، علت خطا یا کافی‌نبودن معنایی یک سند از روی renderer حدس زده نمی‌شود.
- متن escalate کوتاه‌تر است؛ اطلاعات کامل در summary و handoff می‌مانند.
  سؤال ask عین سؤال canonical است و `retrieve_more` عین خروجی قبلی می‌ماند.
  answer تمام passageهای انتخاب‌شده را با qualification کوتاه‌تر نشان می‌دهد.

فقط CRLF واقعی در **نمایش دادهٔ USER** به LF تبدیل می‌شود. source quotationها،
کد و متن اصلی، prompt، hash و مختصات passage تغییر نمی‌کنند. CR تنها، کنترل‌های
دیگر و متن literal مثل `\\u000d` حذف نمی‌شوند؛ escape HTML/Markdown برقرار است.
کد اجرا نمی‌شود. نقل‌قول‌ها کوتاه یا به‌هم دوخته نمی‌شوند.

## اتصال و سازگاری

```python
# planner و request_factory از composition بازبینی‌شدهٔ caller می‌آیند.
reasoner = GroundedReasoner(
    planner,
    request_factory=registered_factory,
    review_brief=True,
)

# مسیر passage با همان قرارداد plan و block_mode قبلی:
reasoner = ClaimReasoner(
    planner,
    request_factory=registered_factory,
    block_mode="sections",
    review_brief=True,
)
```

توابع `render_grounded_plan` و `render_claim_plan` هم همین keyword را می‌گیرند.
این policy فقط با bool واقعی پذیرفته می‌شود. policy جدید نمایش بر flagهای
قدیمی نمایش تقدم دارد؛ policy مدل، انتخاب source، validation و سقف تلاش‌ها
تغییر نمی‌کند. حالت omitted/False تمام byteهای خروجی تاریخی را حفظ می‌کند.

**اتصال خودکار به factory، env یا runner ندارد و تنظیم نهایی freeze انتخاب
نشده است.** descriptor تاریخی v1 این گزینه را نمی‌شناسد. مسیر صریح v2 در
[تحویل C4q](core-closeout.fa.md) اکنون policy و constructor را bind می‌کند؛
برای پذیرش نهایی باید همان ثبت بازبینی‌شده انتخاب شود. برابری descriptor قدیمی
به معنی یکسان‌بودن این دو renderer نیست.

متن تازه باید با run/proposal تازهٔ مسیر معمول، handoff و review packet خودش
را بگیرد؛ هویت بستهٔ آزمایش یا pending قدیمی برای عوض‌کردن renderer دوباره
استفاده نمی‌شود. replay صرفاً مقایسه است. handoff ذخیره‌شده،
approval قبلی یا receipt تاریخی بازنویسی نمی‌شود. تست integration نشان می‌دهد
جایگزین‌کردن متن در handoff قدیمی، اعتبار آن را از بین می‌برد. ساخت متن جدید
به معنی تأیید یا اجرای tracker نیست. هیچ قرارداد مشترک یا ماژول تیم تغییر نکرد.

تمام boundهای قبلی باقی‌اند؛ اگر متن کامل از سقف `AnalysisResult` عبور کند،
`grounded_render_too_large` می‌گیریم. حذف شاهد، بریدن کد یا fallback بی‌صدا نداریم.
این قالب تضمین کوتاه‌بودن هر summary یا جلوگیری از تمام overflowها نیست.

## مقایسهٔ قابل بازتولید

```bash
uv run pytest tests/test_maintainer_review_brief.py -q
uv run python scripts/replay_maintainer_brief.py --output /tmp/maintainer-brief-fresh.json
```

فایل output باید تازه باشد. اسکریپت فقط archive توسعهٔ C4g با SHA ثابت را
می‌خواند؛ test، index، کلید و API وارد مقایسه نمی‌شوند. هر plan و request با
handoff اصلی همان attempt تطبیق می‌خورد. تصمیم و انتخاب مدل دوباره تولید نمی‌شود.

۱۷ پیشنهاد تازه با ۱۵۳ کنترل ساختاری بازپخش شدند. ۱۲ entry دیگر هم ثبت‌اند؛
این‌ها رکوردهای ذخیره‌شده شامل failure و stale هستند، نه ۱۲ turn مستقل.
projection مجموعاً ۲۹ entry را می‌شمارد؛ denominator تمام turnهای برنامه‌ریزی‌شده
یا اجرای کامل campaign نیست. حالت‌های unvisited و شکست‌های اصلی در archive و
registration دست‌نخورده باقی‌اند. هیچ case از گزارش کیفیت نهایی حذف نمی‌شود.

| خروجی موجود | draft قبلی | draft قالب جدید | تغییر قابل مشاهده |
| --- | ---: | ---: | --- |
| Enum، ارجاع اولیه | ۲۸۶۴ | ۳۰۶ | گزارش، inventory و قدم پیشنهادی در summary جدا شدند |
| Enum، ارجاع پس از correction | ۳۳۰۲ | ۳۰۶ | نسخهٔ جاری حفظ شد؛ markerهای CRLF مربوط به USER حذف شدند |
| Enum، answer بلند | ۱۲۲۰۱ | ۹۳۸۳ | quotationها حفظ و qualification تکراری کمتر شد |

در این replay، ۱۶ از ۱۷ summary بلندتر شدند؛ inventory همهٔ منابع و گزارش
کامل اضافه شده‌اند. پس بهبود brevity یا usefulness برای maintainer ادعا نمی‌کنیم. markerهای قابل مشاهدهٔ CR در summaryهای Enum این archive از ۴۸ به
صفر رسیدند؛ این عدد شامل همهٔ ورودی‌های ممکن نیست و normalization به sourceها
تعمیم داده نمی‌شود. اندازهٔ draft و کنترل ساختاری، نمرهٔ usefulness نیستند.

نمره‌های انسانی PR77 به متن‌های اصلی تعلق دارند و منتقل نمی‌شوند. علت/راهکار
Enum و usefulness قالب تازه هنوز review انسانی لازم دارند؛ نتیجهٔ جدید مدل،
retrieval واقعی یا held-out test ادعا نمی‌شود. halt، سه hold و سقف هزینه ثابت‌اند.

روی source `85d89ea`، ۸۴ کنترل تازهٔ root و ۲۱ کنترل مستقل پاس شدند؛ review
مستقل ۶۶۷ تست مرتبط را هم پاس کرد. بررسی گسترده، پوشش موفق ۶۰۷۳ تست انتخاب‌شده
در دو context دارد: ۶۰۶۸ در CWD خنثی و همان پنج تست مسیر نسبی از root. یک تست
خواندن held-out عمداً کنار گذاشته شد. این یک اجرای یک‌تکهٔ بی‌خطا نیست؛ log
شکست‌های CWD و تلاش اولیهٔ guard در review محفوظ‌اند. audit فایل فقط parent
را پوشش می‌دهد، نه همهٔ subprocessها. شمارش‌های متمرکز با suite جمع نمی‌شوند.
Ruff برای ۳۷۸ فایل پاس است؛ ledger و ۱۹ pin فیزیکی ثابت مانده‌اند.

ثبت پیش از replay در [protocol](receipts/maintainer-review-brief-protocol-2026-10-16.json)
حفظ شده است. رسیدها و source pinها در
[verification](receipts/maintainer-review-brief-2026-10-16.json) و
[replay](receipts/maintainer-review-brief-replay-2026-10-16.json) ثبت می‌شوند.

[review مستقل شمارش تست‌ها](receipts/maintainer-review-brief-reconciliation-2026-10-16.json)
برابری دقیق IDها و محدودیت دو context را تأیید می‌کند.
