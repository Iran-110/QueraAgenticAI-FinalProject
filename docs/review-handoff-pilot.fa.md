# نتیجهٔ C3: خروجی کامل core و قرارداد review

این دور دو مشکل مشخص اتصال را حل کرد: نمایش منبعی که در run مصرف نشده بود،
و review ناقصی که case، metadata منابع و catalog تصمیم را نگه نمی‌داشت.
معماری همچنان یک agent دارد. wrapper کوچک برای ثبت ورودی همان reasoner کافی بود؛
دلیلی برای framework یا agent تولیدی دیگری پیدا نکردیم.

## baseline و تغییر قابل اندازه‌گیری

baseline کد واقعی `main@3f22ef9`، یعنی merge مربوط به PR #10 است. چهار regression
قبل از اصلاح API در `ef1f568` ثبت و اجرا شدند؛ هر چهار fail شدند. همان تست‌های
فعلی با `git archive` و `PYTHONPATH` جدا روی baseline هم بازپخش شدند؛ چهار fail،
روی API جدید چهار pass. هیچ checkout یا تغییر محلی reset نشد.

| بررسی | baseline | اکنون |
| --- | --- | --- |
| bundle آماده ولی مصرف‌نشده با همان chunk ID | منبع اصلی را در review جایگزین می‌کرد | فقط منبع ورودی نهایی reasoner نمایش داده می‌شود |
| metadata کامل منبع | source ID، commit، نسخه و score حذف می‌شد | رکورد کامل، hash محتوا و scope نسخه حفظ می‌شوند |
| case، evidence و کل analysis برای review | ورودی کامل و envelope موجود نبود | `ProposalHandoff` کامل صادر می‌شود |
| edit با متن یکسان | envelope متصل به proposal نداشت | proposal و hash بیرونی تازه؛ approval قبلی رد می‌شود |

[baseline ثبت‌شده](../experiments/review_handoff/baseline-boundary-v1.json)،
[مقایسه با تست یکسان](../experiments/review_handoff/comparison-boundary-v1.json)
و [تست‌ها](../tests/test_api_review_handoff.py) قابل بررسی‌اند.
این شمارش، بهبود قرارداد نرم‌افزار است؛ امتیاز کیفیت تصمیم مدل نیست.

## قرارداد پیاده‌شده

`ReasoningCapture` قبل از فراخوانی delegate یک کپی جدا از case، پیام، آخرین
EvidenceBundle و ReasoningContext می‌گیرد. مدل یا adapter نمی‌تواند با تغییر
آبجکت ورودی، آن سابقه را عوض کند. `build_handoff` فقط نتیجهٔ نهایی همان run و
attempt/retrieval round را می‌پذیرد؛ فراخوانی مدل یا retrieval اضافه‌ای ندارد.

`pending.review_handoff` این اطلاعات را به UI/tracker می‌دهد:

- کل CaseState آماده‌شده، قبل از ثبت pending ID، و پیام دقیق کاربر؛
- آخرین bundle واقعاً مصرف‌شده، شامل منابع uncited و warnings همان bundle؛
- کل AnalysisResult، از draft و summary تا facts_delta و checks_suggested؛
- metadata، hash و scope نسخهٔ هر منبع؛
- GroundedRequest واقعی همان invocation، با gap کاربر/منبع و conflictهای اعلام‌شده؛
- review packet همهٔ خروجی‌ها و hash بیرونی متصل به proposal ID.

مقایسهٔ scope فقط برابری metadata نسخه است؛ `1.49.0` پوشش خودکار `1.49.1` نیست.
حضور citation یا برابری نسخه به‌تنهایی پشتیبانی معنایی ادعا را ثابت نمی‌کند.

`ensure_handoff_current` کل محتوای case را با snapshot پیشنهاد مقایسه می‌کند؛
فقط pending ID مورد انتظار کنار گذاشته می‌شود. تغییر fact/check/ref با revision
یکسان هم رد می‌شود. API پیش از approve/reject/edit، projection ذخیره‌شده را با
handoff اصلی تطبیق می‌دهد. proposal خراب یا source/analysis/packet دست‌کاری‌شده
به خروجی قابل تأیید تبدیل نمی‌شود.

edit با `edit_handoff` پیشنهاد تازه و packet بازساخته‌شده می‌خواهد. شناسهٔ run
مدل اصلی حفظ می‌شود، ولی proposal ID و hash بیرونی عوض می‌شوند. اگر متن یکسان
باشد، packet ممکن است همان بماند؛ approval باید همچنان به ID تازه متصل شود.
ویرایش انسانی خودکار «grounded» فرض نمی‌شود و نیاز به review معنایی دارد.

hash و validation اعتبار محتوا را کنترل می‌کنند؛ reviewer را authenticate
نمی‌کنند، entailment را ثابت نمی‌کنند و مجوز اقدام نمی‌دهند. API همچنان process
memory و approval آزمایشی دارد؛ هیچ ابزار tracker اجرا نشده است.

## case ثابت با GroundedPlan

fixture پیش از نخستین replay در `b085f7d` ثبت شد. چهار ورودی و انتظارهای هرکدام
در [fixture](../experiments/review_handoff/case-current-state-latest-evidence.json)
هستند. همان پنج excerpt رسمی V8 مصرف می‌شوند؛ planner و ادامهٔ گفتگو را
توسعه‌دهنده نوشته است.

| ورودی | آنچه کم داریم | مسیر ثبت‌شده |
| --- | --- | --- |
| نسخه نامعلوم | نسخه و کد callback کاربر؛ سند علت کامل bug هم نداریم | سؤال canonical نسخه، سپس approval جدا |
| جواب `1.50.0` به سؤال تأییدشده | علت کامل برنامه هنوز معلوم نیست | نقل کامل release record با محدودیت روشن؛ بدون ادعای حل bug |
| correction به `1.49.1` | سند دقیق این patch و کد callback نداریم | retrieval بیشتر؛ حذف release از bundle دوم؛ ارجاع با شواهد نهایی |
| withdrawal نسخه | نسخه دوباره unknown است | سؤال نسخه دوباره مجاز می‌شود |

مسیر اصلی چهار turn، پنج فراخوانی reasoner/retriever، دو release بعد از approval
و چهار replay همان event بدون فراخوانی اضافی دارد. تغییر catalog با متن خروجی
یکسان، hash بیرونی را تغییر می‌دهد؛ packet قدیمی به‌تنهایی برای review کافی نیست.
source تغییرکرده با chunk ID یکسان، bundle قبلی بعد از refinement، approval قدیمی
و review مربوط به متن قبل از edit رد می‌شوند.

یک control جدا، دو excerpt سازگار از نسخه‌های مختلف را فقط برای تست routing در
catalog متناقض اعلام می‌کند. answer رد می‌شود و escalation هر دو طرف را نگه
می‌دارد؛ دو attempt و یک retrieval. این تناقض واقعی اسناد یا کشف خودکار conflict
را اثبات نمی‌کند. attestation مثبت این آزمایش هم authored است؛ رأی مستقل انسان
یا سنجش خودکار صحت معنایی محسوب نمی‌شود.

در audit بعد از نخستین replay، یک ضعف scorer پیدا شد: renderer مشترک می‌توانست
کنار quote کامل، جملهٔ بی‌پشتوانه دربارهٔ علت و fix اضافه کند و v1 همچنان پاس
شود. [receipt اول](../experiments/review_handoff/results-review-handoff-v1.json)
و code آن در `2680151` حفظ شدند. سپس تمام پنج AnalysisResult با source و state
بازبینی و در [oracle ثابت](../experiments/review_handoff/expected-analysis-v1.json)
ثبت شدند (`057a4d3`)؛ runner جدید کل خروجی را مستقل از renderer با آن تطبیق
می‌دهد. این oracle بعد از اولین اجرا اضافه شده؛ inventory و تصمیم‌های قابل قبول
پیش از اجرا ثبت بودند، ولی این انتظار متنی را preregistered یا gold انسانی
نمی‌نامیم. تست mutation، حفظ quote همراه اضافه‌شدن ادعای غلط را هم رد می‌کند.
این بررسی وفاداری همین fixture است، نه داور عمومی entailment.

[receipt v2](../experiments/review_handoff/results-review-handoff-v2.json)
با SHA `f4efa6bea0e947b758001245826a5d79dbad9829d35540aaacb788e1bee8d233`
ثبت و حفظ شده است؛ فایل، fingerprint کد اجراشده، oracle و runtime را نگه می‌دارد.
پس از اصلاح normalization و خطای ساخت adapter در `68dec4f`، همان replay روی
کد تازه در [receipt v3](../experiments/review_handoff/results-review-handoff-v3.json)
با SHA `915ea1d5c82039da928a5405a1c407ec933cfe3fd54340020c50a309ea3cff79`
دوباره پاس شد. schema این receipt همچنان نسخهٔ ۲ است؛ v3 نام اجرای تازه است،
نه fixture یا oracle تازه. منابع اصلی ثبت‌شده مانده‌اند و receiptهای قبلی
overwrite نشده‌اند.

بررسی نهایی محلی: **۱۶۲۱ تست آفلاین پاس**، یعنی ۹۲ تست اضافه نسبت به main؛
Ruff lint/format، dependency lock و هر ۱۸ فرمان validation/replay/demo در CI هم
پاس‌اند. بعد از اصلاح scorer، کل suite و replay نهایی دوباره اجرا شدند.
یک warning موجود Starlette/httpx باقی است.

در بازبینی بعدی دو regression دیگر قبل از اصلاح در `d14cfc4` ثبت شدند:
پیام معتبر با فاصلهٔ ابتدا/انتها به‌خاطر normalization متفاوت به handoff نمی‌رسید؛
خطای ساخت adapter بعد از commit رخداد، HTTP500 بدون log عملیاتی می‌داد.
[baseline](../experiments/review_handoff/baseline-adapter-boundary-v1.json) و
[مقایسه با همان تست‌های اولیه](../experiments/review_handoff/comparison-adapter-boundary-v1.json)
روی کد واقعی `254e6542` دو fail و روی `68dec4f` دو pass دارند.
handoff حالا متن اصلی را دقیق نگه می‌دارد و برای GroundedRequest فقط فاصلهٔ بیرونی
را طبق قرارداد قبلی کنار می‌گذارد. خطای setup با کد امن ثبت می‌شود؛ replay
دوباره adapter را نمی‌سازد و correction اجازهٔ تأیید پیشنهاد قدیمی را نمی‌دهد.
تست سومِ stale approval بعد از ثبت baseline اضافه شد؛ جزء دو تست اولیه نیست.
این‌ها بهبود نرم‌افزار اتصال‌اند، نه امتیاز تصمیم مدل.

انتخاب Issue #12782 از workaround و commentهای همان Issue اثر گرفته و
`answer-informed` است. پاسخ/راه‌حل همان Issue داخل evidence نیست؛ منابع رسمی
ثابت‌اند. این case، duplicate #12629 و خانوادهٔ exposed، final test مستقل نیستند.
حذف خانواده‌ها از corpus واقعی با حسن و manifest E1 است؛ این runner index ندارد
و حذف واقعی را انجام نمی‌دهد. receiptهای تاریخی C2/V8/V9 حفظ شده‌اند.

## بازپخش و سهم باقی‌ماندهٔ تیم

```bash
uv run python experiments/review_handoff/replay.py --validate
uv run python experiments/review_handoff/replay.py
uv run pytest tests/test_review_handoff.py tests/test_api_review_handoff.py tests/test_api_review_handoff_guards.py tests/test_review_handoff_experiment.py
```

baseline به commit تاریخی دسترسی می‌خواهد؛ در clone کم‌عمق ابتدا history را از
Git بگیرید. CI برای این replay با `fetch-depth: 0` checkout می‌کند. receipt جدید
با `--output` ساخته می‌شود و فایل موجود overwrite نمی‌شود. Python `-O` و تغییر
code هنگام اجرا نمی‌توانند receipt موفق صادر کنند.

| نفر | ورودی آماده از core | خروجی لازم برای مرحلهٔ بعد |
| --- | --- | --- |
| حسن، R2/R3/P4 | RetrievalRequest، fixed source pool و قرارداد metadata | EvidenceBundle از snapshot مجاز؛ منابع مورد نیاز فقط در آخرین bundle؛ exclusion manifest واقعی |
| بهنام، T1–T3/P3 | UserTurn/transition، ApprovedReplyQuestion و ProposalHandoff | state و event پایدار، CAS و invalidation اتمیک، reviewer معتبر و action idempotency/restart |
| محمدحسن، U2/E1–E3 | wire مربوط به facts/correction، `pending.analysis` و `pending.review_handoff` | کنترل‌های ورودی/اصلاح، نمایش همهٔ خروجی‌ها و منابع، split خانواده‌ها و runner ارزیابی |
| ساسان، C4/C5 | fixture، baseline و guardهای اتصال | وصل کردن adapterهای آماده، مقایسهٔ dev واقعی و حل اختلاف provider/ledger پیش از live |

هزینهٔ این دور صفر است؛ کلید خوانده نشده و ledger تغییر نکرده است. live همچنان
به تطبیق هویت مدل/usage/billing و حفظ uncertainty وابسته است. اتصال واقعی،
کیفیت مدل/RAG و test نهایی هنوز سنجیده نشده‌اند.
