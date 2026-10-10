# بازبینی آمادگی core برای اتصال تیم

این بازبینی بعد از C3 انجام شد؛ نسخهٔ قبلی را «بی‌نقص» فرض نکردیم.
دو ایراد اتصال پیدا و اصلاح شدند، و مسیر gateway موجود تا review کامل را
با HTTP شبیه‌سازی‌شده وصل کردیم. معماری همان یک agent است.

## دو اصلاح با baseline یکسان

| ورودی | قبل از `68dec4f` | بعد از اصلاح |
| --- | --- | --- |
| پیام معتبر با فاصلهٔ ابتدا/انتها | engine پیشنهاد می‌داد ولی handoff رد می‌شد | متن اصلی حفظ می‌شود؛ مقایسهٔ GroundedRequest با normalization قبلی سازگار است |
| خطای ساخت adapter پس از ثبت رخداد | HTTP500 و بدون توضیح عملیاتی | خطای امن `AdapterSetupUnavailable`، بدون پیشنهاد یا اجرای دوبارهٔ event |

دو تست قبل از اصلاح در `d14cfc4` ثبت شدند. همان bytes تست روی کد واقعی
`254e6542` دو fail و روی کد اصلاح‌شده دو pass دارند؛
[baseline](../experiments/review_handoff/baseline-adapter-boundary-v1.json) و
[مقایسه](../experiments/review_handoff/comparison-adapter-boundary-v1.json) حفظ شده‌اند.
تست تکمیلی نشان می‌دهد اگر setup بعد از correction شکست بخورد، approval قبلی
همچنان رد می‌شود. review مستقل هم خطای constructor را با صفر فراخوانی
retrieval/model بررسی کرد. جزئیات exception به کاربر صادر نمی‌شوند.

## gateway واقعی کد، پاسخ شبیه‌سازی‌شده

[protocol](../experiments/gateway_handoff/protocol-gateway-handoff-v1.json)
در `d9c8e82` پیش از اجرای این pilot ثبت شد. runner همان چهار turn و oracle
ثابت C3 را مصرف می‌کند؛ oracle C3 بعد از نخستین اجرای C3 اضافه شده بود و gold
انسانی یا انتظار متنی پیش از نخستین اجرا نیست.

در این مسیر، `MetisGroundedPlanner` و `MetisReasoner` واقعی کد، JSON درخواست
را به `httpx.MockTransport` می‌فرستند. پاسخ authored از همان payload خوانده‌شده
ساخته می‌شود و از parsing، GroundedReasoner، core و HTTP review عبور می‌کند.
label و oracle در پیام provider قرار نمی‌گیرند. credential یک ثابت عمومی
ساختگی است و ledger فقط داخل directory موقت ساخته می‌شود.

- چهار turn اصلی و control مربوط به conflict در مجموع هفت send شبیه‌سازی‌شده
  دارند؛ چهار replay رخداد، send اضافه نمی‌سازند.
- reservation پیش از رسیدن transport دیده می‌شود؛ request IDها از context
  واقعی caller ساخته و settlement با usage ساختگی ثبت می‌شود.
- controlهای جدا، repair پس از JSON خراب، توقف روی model mismatch و timeout
  بدون retry را بررسی می‌کنند. هزینهٔ نامطمئن در ledger موقت حفظ می‌شود.
- clientها بسته می‌شوند؛ تغییر کد حین اجرا، Python `-O` و overwrite receipt
  موفق مجاز نیستند.

settlement ساختگی مسیر اصلی `USD 0.000490875` است؛ **خرج واقعی صفر است**.
این رقم صورت‌حساب provider یا هزینهٔ مدل واقعی نیست. halt و ledger واقعی
باز نشده‌اند و تغییری نکرده‌اند. اولین اجرای harness به‌خاطر پاس دادن string
به config عددی شکست خورد؛ runner با Decimal صریح اصلاح شد و protocol تغییر نکرد.

[receipt کامل](../experiments/gateway_handoff/results-gateway-handoff-v1.json)
با `receipt_sha256` برابر
`3942a016e1fc01eee8a943a68d298abec2926259adf94d7f27808612da520629`
ثبت شد؛ payloadهای JSON، contextها، reservationها و fingerprint کد/runtime
قابل بررسی‌اند. تست mutation، تغییر پیام روی wire را رد می‌کند؛ تست جدا نیز
اجرای pilot را با HTTPTransport و خواندن config از environment ممنوع، پاس می‌کند.

بررسی نهایی: **۱۶۳۴ تست آفلاین پاس**، ۱۰۵ تست بیشتر از `main@3f22ef9`؛
۱۳ تست این بازبینی تازه‌اند. dependency lock، Ruff lint/format و هر ۱۹ فرمان
validation/replay/demo در CI پاس‌اند. review مستقل اصلاحات و runner، ایراد
قابل اقدام پیدا نکرد. یک warning موجود Starlette/httpx باقی است.

```bash
uv run python experiments/gateway_handoff/replay.py --validate
uv run python experiments/gateway_handoff/replay.py
uv run pytest tests/test_core_adapter_boundaries.py tests/test_gateway_handoff_pilot.py
```

## تا کجا آماده‌ایم

قرارداد core، ورودی fact/correction، سؤال متصل به approval، آخرین evidence و
review کامل با fixture قابل اتصال‌اند. این آزمایش‌ها کیفیت مدل/RAG، اصلاح واقعی
برنامهٔ کاربر، UI متصل یا persistence و مجوز اجرای tracker را اثبات نمی‌کنند.
gapها و conflictهای catalog فعلاً caller-owned و دستی‌اند؛ discovery خودکار
آن‌ها ادعا نشده است. case #12782/duplicate #12629 دیده‌شده و answer-informed
است؛ وارد test مستقل یا corpus مجاز همان ارزیابی نمی‌شود.

قدم مفید بعدی، گرفتن خروجی adapter حسن، state/approval بهنام و ورودی/review
محمدحسن برای همین pilot است. [تحویل امروز و checklist](../plan/plan.md)
برش کوچک قابل تحویل هر نفر را مشخص می‌کند؛ index و evaluation نهایی هنوز بازند.
ساسان پس از دریافت adapterها اتصال و baseline مشترک را ادامه می‌دهد. پیش از
آزمایش live، C5 به مدرک هویت مدل/usage/billing provider نیاز دارد؛ uncertainty
با حدس، alias تازه یا reset برطرف نمی‌شود.

## انتشار روی main

[PR #11](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/11)
پس از review نهایی با commit `edea31c6b511520ffcb78b6b5c6fc565b2266265`
به main merge شد؛ [CI خود main](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38045540320)
هم پاس است. تاریخچهٔ ثبت fixture و receiptها حفظ شد. دو توضیح قدیمی دربارهٔ
خطای setup و approval محلی UI اصلاح شدند؛ ایراد قابل اقدام دیگری در بازبینی
کد، آزمایش‌ها و handoff تیم پیدا نشد. مبنای شروع اعضا، `origin/main` است؛
کارهای باز و شرط پایانشان در plan باقی مانده‌اند.
