# Pilot آفلاین خروجی core و review — C3

این fixture ادامهٔ مسیر توسعهٔ #12782 است؛ ادامهٔ گفتگو، catalog و انتخاب‌های
`GroundedPlan` را توسعه‌دهنده نوشته است. همان پنج excerpt رسمی V8 مصرف می‌شوند؛
هیچ مدل، retrieval واقعی، index، کلید یا API پولی در این آزمایش نیست.

چهار ورودی ثابت داریم: نسخهٔ نامعلوم، جواب `1.50.0` به سؤال تأییدشده، correction
به `1.49.1` و withdrawal نسخه. در correction، پوشش دقیق `1.49.1` نداریم؛ این
کمبود منبع است و سؤال از کاربر برای پیدا کردن docs جایش را نمی‌گیرد. یک retrieval
دیگر با fixture انجام می‌شود و bundle نهایی release note قبلی را حذف می‌کند.
catalog برای هر case و bundle تازه ساخته می‌شود؛ سؤال نسخهٔ معلوم دوباره پرسیده
نمی‌شود و بعد از withdrawal برمی‌گردد.

handoff باید کل case آماده‌شده، آخرین bundle واقعی ورودی reasoner، همهٔ analysis،
catalog، hash منابع، scope نسخه و review packet را نگه دارد. review، approval و
اجرای اقدام همچنان سه مسئولیت جدا هستند. edit هم handoff و packet تازه می‌خواهد.

یک conflict control جدا، دو excerpt سازگار از نسخه‌های مختلف را **فقط در catalog
آزمایش** conflicting اعلام می‌کند تا routing و نمایش هر دو طرف بررسی شود. این
کنترل، ادعای تناقض واقعی اسناد یا توانایی کشف تناقض نیست.

انتخاب #12782 قبلاً از workaround و commentهای همان Issue اثر گرفته؛ انتخاب
`answer-informed` است. جواب/راه‌حل Issue وارد شواهد نشده و این کیس یا خانوادهٔ
#12629، final test مستقل نیست. حذف آن‌ها از index واقعی باید توسط RAG انجام شود؛
این runner آن حذف را اجرا نمی‌کند.

انتظارها و SHA fixture باید قبل از نخستین replay در Git ثبت شوند. بعد از ثبت:

```bash
uv run python experiments/review_handoff/replay.py --validate
uv run python experiments/review_handoff/replay.py
uv run python experiments/review_handoff/replay.py --output output/review-handoff/run.json
uv run pytest tests/test_review_handoff_experiment.py
```

receipt موجود overwrite نمی‌شود. baseline از کد واقعی `main@3f22ef9` در مسیر موقت
با `git archive` import می‌شود؛ fixture و هزینه ثابت‌اند. نتیجه فقط کامل بودن
قرارداد و کنترل freshness است؛ کیفیت تصمیم مدل، کیفیت RAG، حل bug Streamlit،
reviewer معتبر، transaction پایدار یا موفقیت test نهایی را اثبات نمی‌کند.

checkout باید history مربوط به `3f22ef9` را داشته باشد؛ برای CI، `fetch-depth: 0`
لازم است. shallow clone بدون این commit، baseline را اجرا نمی‌کند و موفقیت ثبت
نمی‌شود. نقل‌قول کامل، علاوه بر rerender، با excerpt ثابت و decoded quote مقایسه
می‌شود تا کوتاه‌شدن متن در خود renderer هم از آزمایش عبور نکند.

در audit بعدی، یک ضعف واقعی در scorer نسخهٔ اول پیدا شد: renderer می‌توانست در
کنار quote کامل، ادعای unsupported دربارهٔ علت و fix اضافه کند و rerender مشترک
هم همان خروجی را تأیید کند. receipt و کد v1 در `2680151` حفظ شده‌اند؛ این ضعف را
نباید با موفقیت تشخیص پشتیبانی ادعا اشتباه گرفت.

برای v2، پنج analysis کامل نسخهٔ سالم با source inspection مستقل assistant بررسی
و در `expected-analysis-v1.json`، commit `057a4d3` ثبت شدند. این oracle **بعد از
اولین replay** ساخته شده است؛ فقط inventory و تصمیم‌های قابل قبول از ابتدا در
`b085f7d` ثبت شده بودند. بررسی کامل خروجی ثابت، علاوه بر quote، اضافه‌شدن ادعای
بدون شاهد و تغییر گزارش fact را تشخیص می‌دهد. این hardening، human gold یا scorer
عمومی entailment و اندازه‌گیری کیفیت مدل نیست. receipt جدید v2، v1 را overwrite
نمی‌کند.
