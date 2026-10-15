# C4h6 — سؤال همراه با زمینهٔ مستند

در renderer قبلی، تصمیم `ask` فقط سؤال canonical را به کاربر نشان می‌داد؛
منابع انتخاب‌شده فقط در summary نگه‌دارنده بودند. گزینهٔ
`ask_source_background=True` در `GroundedReasoner` و `render_grounded_plan`
می‌تواند بعد از همان سؤال، نقل‌قول کامل منابع انتخاب‌شده را اضافه کند.
پیش‌فرض `False` است؛ prompt و قرارداد `GroundedPlan` تغییر نکرده‌اند.

شرط‌ها: نسخهٔ فعال با provenance کاربر معلوم باشد؛ سؤال دربارهٔ نسخه نباشد؛
تضاد فعلی یا باقی‌مانده از همین invocation نداشته باشیم؛ metadata منبع دقیقاً
همان نسخه را شامل شود. منبع تاریخی، نسخهٔ نامعلوم، متن انتخاب‌نشده یا نسخهٔ
حدس‌زده از query مجاز نیست. تمام block با qualification قبلی می‌آید؛ هیچ متن
تازهٔ فنی یا خلاصهٔ مدل ساخته نمی‌شود. اگر کل افزوده از سقف ۲۰هزار کاراکتر
draft عبور کند، همان سؤال اولیه حفظ می‌شود؛ quote بریده نمی‌شود.

تصمیم، `next_question`، `missing_info`، summary و evidence linkها عوض نمی‌شوند.
سؤال canonical نسخه همچنان دقیقاً همان متن قبلی است و narrow version intake
تغییر نکرده. پیشنهاد همچنان پیش از نمایش/اقدام به approval همان case، revision
و hash متن نیاز دارد؛ correction و retry طبق tracker فعلی‌اند.

## اتصال و مسیر شرطی

برای کارخانهٔ موجود، تنظیم trusted
`AGENT_GROUNDED_ASK_SOURCE_BACKGROUND=true` همین گزینه را فعال می‌کند؛
مقدار پیش‌فرض `false` است. این مقدار field پیام کاربر یا دستور مدل نیست.
شناسهٔ adapter غیرپیش‌فرض suffix جدا دارد تا receiptها مخلوط نشوند.
[profile retrieval متصل](candidate-live-profile.fa.md) مستقل از این گزینه است.

runner قبلاً `user_draft == question` را برای همهٔ follow-upها لازم می‌دانست.
[اصلاح ثبت‌شده پیش از کد/API](../experiments/core_ask_background_v1/route-display-amendment-v1.json)
فقط برای caller صریح `allow_source_background=True`، سؤال غیرنسخه‌ای را با
handoff فعلی معتبر و بازسازی کامل draft توسط همین renderer می‌پذیرد. prefix
سؤال یا متن دلخواه کافی نیست. یک edit انسانی با متن متفاوت هنوز coverage gap
است؛ continuation همچنان به analysis واقعاً تأییدشده و منتشرشده مقید است.
fixture، gold، سؤال ثبت‌شده و جواب بعدی تغییر نکرده‌اند.

متن تأییدشدهٔ سؤال/background در SQLite کامل می‌ماند. مطابق مرز فعلی
conversation، متن‌های قبلی دستیار وارد درخواست بعدی مدل نمی‌شوند؛ پیام‌های
USER کامل حفظ می‌شوند و evidence هر run تازه است. دو کنترل نوبت سوم با HTTP،
SQLite و gateway واقعی/transport ماک این رفتار و توقف تاریخچهٔ USER بزرگ پیش
از reservation/transport را بررسی می‌کنند. تضمین همهٔ ادامه‌های آینده نیست.

## شواهد و محدودیت‌ها

[protocol](../experiments/core_ask_background_v1/protocol-v1.json) پیش از کد/API
ثبت شد. [بازپخش planهای قبلی](../experiments/core_ask_background_v1/offline-render-replay-v1.json)
تمام ۲۴ نوبت، شامل ۲۲ پیشنهاد تازه، یک empty و یک unvisited را نگه می‌دارد.
سه draft سؤالِ نسخهٔ معلوم، با همان plan/request زمینهٔ منبع دریافت کردند؛
بقیهٔ fieldها و خطاها همان‌اند. این اثر renderer آفلاین است، نه کیفیت تازهٔ مدل.

اجرای تازهٔ پیش‌ثبت‌شده، شش job/دوازده نوبت روی همان سه dev و index ۱۸/۳۶ دارد؛
هر plan واقعی فقط یک بار از API می‌آید و هر دو renderer محلی مقایسه می‌شوند.
[معیار review](../experiments/core_ask_background_v1/semantic-review-preparation-v1.json)
سؤال ضروری، انتقال نکتهٔ مرتبط، partial guidance، تشخیص/fix و usefulness انسانی
را جدا می‌سنجد. quote طولانی به‌تنهایی جواب مفید نیست. منابع اختصاصی Enum
اضافه نشده‌اند؛ علت/fix آن از این تغییر به دست نمی‌آید. داده‌ها exposed و
answer-informed هستند؛ test نهایی و داوری انسانی همچنان جدا باقی می‌مانند.

[اجرای ثبت‌شده](../experiments/core_ask_background_v1/README.md): هر۱۲ turn
حفظ شد؛۱۱ fresh و یک stale، پنج route کامل از شش،۱۴ send با تخمین$0.012407340.
A در هر دو تکرار با همان plan از سؤال۱۰۸کاراکتری به متن۷۸۷۰کاراکتری همراه با
زمینهٔ نسخهٔ۱٫۵۰ رسید. این طول، ریسک کاربردپذیری دارد؛ usefulness انسانی null
و پیش‌فرض خاموش باقی است. یک correction از Enum هنوز JSON نامعتبر داد و
پیشنهاد قبلی stale/غیرقابل‌تأیید ماند؛ بهبود پایداری کلی از این اجرا ثابت نشد.
۴۳۲۲تست و HTTP/SQLite۴۵۷/۴۵۷ پاس؛ CI به علت Billing اجرا نشده است.
