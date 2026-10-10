# Pilot آفلاین اتصال اطلاعات کاربر — C2 / P2

[`case-widget-version-correction.json`](case-widget-version-correction.json) یک fixture توسعه برای اتصال HTTP ورودی کاربر به core است. این pack از خانوادهٔ **Issue #12782** استفاده می‌کند که قبلاً در V8 دیده شده؛ یک test نهایی مستقل نیست. ادامهٔ گفت‌وگو، خروجی reasoner و انتظارهای ارزیابی را توسعه‌دهنده نوشته است.

| Turn | اطلاعات ورودی | خروجی ثابت برای آزمایش اتصال |
| --- | --- | --- |
| `intake-1` | گزارش اولیه، Python و سایر اطلاعات؛ نسخهٔ Streamlit عمداً حذف شده | سؤال canonical نسخه، با approval قبل از نمایش |
| `intake-2` | پاسخ تنها `1.50.0`، متصل به ID سؤال تأییدشده | پاسخ محدود شامل نقل کامل release note؛ بدون ادعای علت یا fix |
| `intake-3` | correction ساخت‌یافته به `1.49.1` | سؤال callback؛ کنارگذاری نسخه/استنتاج قبلی و رد approval قدیمی |
| `intake-4` | withdrawal نسخه با `value: null` | نسخه دوباره unknown؛ سؤال نسخه قابل پاسخ دادن |
| `intake-5` | محیط جدید؛ فقط Streamlit `1.50.0` و Python `3.13` تأیید شده‌اند | سایر اطلاعات محیط قبلی superseded؛ پاسخ محدود مستند |
| `intake-6` | یک نتیجهٔ check جدید، بدون تغییر نسخه | استنتاج و reference قبلی کنار می‌روند؛ سؤال کدِ لازم |
| `intake-7` | تکرار همان check با تفاوت حروف/فاصله | check دوباره ثبت نمی‌شود؛ event جدید revision را بالا می‌برد؛ پیشنهاد ارجاع با approval یک‌باره |

برای **هر turn قبل از reasoner**، `inventory` اطلاعات معلوم، کمبود قابل روشن‌شدن توسط کاربر، کمبود مستندات، تصمیم‌های قابل قبول و قواعد بررسی ادعا/سؤال را مشخص می‌کند. خروجی scripted فقط یکی از تصمیم‌های قابل قبول است؛ تطابق آن با انتظار، امتیاز کیفیت مدل محسوب نمی‌شود.

## اتصال fixture

- `user_turn` نمونهٔ کامل قرارداد core است؛ `wire_request_template` بدنهٔ HTTP است. `case_id` و `source_ref` را سرور می‌سازد. `turn_id` و `expected_revision` هویت event و revision ورودی را مشخص می‌کنند.
- تنها در turn دوم، `$approved_proposal_id` را یک‌بار با ID دقیق سؤال canonical تأییدشده جایگزین کنید. retry باید همان request حل‌شده و immutable را بفرستد. یک proposal تأییدنشده یا سؤال ویرایش‌شده اجازهٔ تبدیل متن به version را نمی‌دهد.
- `port_fixture` برای جایگزینی `api._script` در تست آفلاین است. از `FakeRetriever` و `FakeReasoner` فعلی استفاده کنید و `api.SNAPSHOT_ID` را در fixture با snapshot واقعی bundle هماهنگ کنید. scenario جدید، index، مدل یا framework لازم نیست.
- فقط bundle و analysis به portها می‌روند؛ `inventory`، انتظارها و seedهای کنترل‌شده به reasoner یا retriever داده نمی‌شوند.
- `controlled_transition_checkpoints` بعد از turn دوم و قبل از turnهای ششم/هفتم یک fact با provenance از evidence و reference آن را **فقط برای آزمون state** seed می‌کند. این precondition جای ذخیره‌سازی خروجی مدل را نمی‌گیرد؛ API قرار نیست `facts_delta` مدل را خودکار ذخیره کند.
- turnهای دوم تا ششم proposalهای جایگزین‌پذیر می‌سازند. تصحیح یا پیام جدید باید proposal و approval قبلی را بی‌اعتبار کند. replay یک event نباید revision، log یا تعداد فراخوانی reasoner را دوباره تغییر دهد؛ محتوای متفاوت با ID تکراری conflict است.

## منشأ شواهد و حد گزارش

پنج hit رسمی، کپی دقیق سناریوی `controlled-v8-unknown-version-mixed` هستند. fixture اصلی در commit `8814fbba5666040500ae9bb2bfe214f4297af404` ثبت شده؛ SHA آن و docs commit `695e6ce2fb1b23afc6df66b40420ab0013ad72fd` داخل JSON آمده‌اند. هیچ منبع تازه‌ای از وب جمع نشده و هیچ snippet اجرا نمی‌شود.

انتخاب سناریو از بررسی متن اولیه، workaround و commentهای همان Issue اثر گرفته؛ workaround و جواب Issue داخل ورودی نمایان یا شواهد نیستند. این انتخاب **answer-informed** است. کل خانوادهٔ #12782/#12629 و reservationهای قبلی باید از RAG واقعی و final test کنار بمانند؛ fixture این حذف را در index اجرا نمی‌کند.

quote پاسخ فقط توضیح release event نسخهٔ 1.50.0 است. برای نسخهٔ اصلاح‌شدهٔ 1.49.1، pool پوشش دقیق ندارد؛ متن 1.49.0 یا 1.50.0 پوشش patch آن را اثبات نمی‌کند. کمبود کد callback را کاربر می‌تواند روشن کند؛ کمبود coverage مستندات مسئولیت retrieval است.

این مسیر کاملاً آفلاین است: هزینهٔ API صفر، retrieval ثابت، reasoner authored و tracker فقط در حافظه. پاس شدنش کیفیت RAG/مدل، کارکرد fix، دوام approval پس از restart یا موفقیت test نهایی را ثابت نمی‌کند. انتظارها و شواهد این فایل باید قبل از نخستین replay ثبت شوند؛ نتایج بعداً جدا گزارش می‌شوند.
