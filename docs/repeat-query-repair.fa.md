# C4h2 — اصلاح محدود query تکراری

در receipt اصلی C4h سه plan معتبر `retrieve_more`، query همان نوبت را تکرار
کردند. engine جلوی retrieval تکراری را گرفت، اما آن نوبت پیشنهاد تازه نداشت.
هر سه فقط gap از نوع SOURCE داشتند؛ سؤال تازه از کاربر راه‌حل این کمبود نبود.

گزینهٔ `SupportEngine(..., repair_repeated_queries=True)`، بعد از کنترل‌های
terminal منبع و اطلاعات کاربر، plan تکراری را با feedback محدود
`invalid_field / retrieval_queries` رد می‌کند. در صورت باقی‌بودن allowance،
همان تلاش دوم مدل با همان evidence انجام می‌شود. مدل می‌تواند پاسخ محدود و
مستند، سؤال USER ضروریِ ثبت‌شده یا ارجاع بدهد؛ پیشنهاد خودش approval نیست.

مرجع history، queryهای `RetrievalRequest` خود engine در همین invocation است.
`EvidenceBundle.queries_used` برای این اختیار قابل اعتماد نیست. history به
case یا revision تازه منتقل نمی‌شود. queryها بازنویسی، حذف یا ترکیب نمی‌شوند؛
tuple شامل query تکراری و تازه یک‌جا رد می‌شود. guard قبلی retrieval هم پابرجاست.

گزینه strict boolean و پیش‌فرض خاموش است. API/UI و factory معمول آن را روشن
نمی‌کنند؛ ابتدا فقط engine و driver آزمایش متعلق به core از آن استفاده می‌کنند.
حد دو model attempt و دو retrieval round، کنترل stale revision، conflict و
terminal provider/budget stop تغییر نمی‌کند. تلاش دوم ظرفیت retrieval سپس
مدل سوم ندارد. route کامل‌تر با ارجاع بیشتر، به‌تنهایی کیفیت بهتر نیست.

## آزمایش آفلاین با planهای ثبت‌شده

```bash
uv run python scripts/replay_repeat_query_repair.py --output runtime/repeat-replay-new.json
```

[protocol](../experiments/core_repeat_repair_v1/protocol-v1.json) قبل از
implementation ثبت شد. سه plan اصلی بدون تغییر و با اتصال به query واقعی
caller بازپخش می‌شوند؛ fallback ارجاع، تألیفی و اسکریپتی است. ۴۲/۴۲ کنترل
نشان می‌دهد repair بدون retrieval اضافی و بدون اختراع سؤال USER ممکن است.
این بازپخش کیفیت مدل را اندازه نمی‌گیرد و receipt یا نمرهٔ live قبلی را تغییر
نمی‌دهد. منابع همان context کامل‌اند؛ index، ledger یا کلید استفاده نمی‌شود.

## مقایسهٔ واقعی جدا

روش تازه دو دور OFF/ON روی همان سه خانوادهٔ dev و index ثابت۱۸/۳۶ دارد؛
ranking حسن در آن ثابت می‌ماند. resource guidance خاموش است. پیش از کلید،
method، source/input/index، ledger و مجوزهای finite تازه بررسی می‌شوند.
holdها، halt عمومی، سقف$4.50 و تمام revocationهای قبلی حفظ می‌شوند.

کل مقایسه حداکثر۴۸ slot تازه دارد، با سقف$0.06 برای هر pair. وضعیت نامعلوم
یا تغییر source/input/index/accounting کل campaign را متوقف می‌کند. تمام
failureها و نوبت‌های اجرا‌نشده در گزارش می‌مانند؛ identities مصرف‌شده و
campaign قبلی از سر گرفته نمی‌شوند. نتیجهٔ واقعی و بررسی semantic در
[بستهٔ آزمایش](../experiments/core_repeat_repair_v1/README.md) ثبت می‌شود.
میزان usefulness انسانی و test نهایی هنوز از این سه dev قابل نتیجه‌گیری نیست.
