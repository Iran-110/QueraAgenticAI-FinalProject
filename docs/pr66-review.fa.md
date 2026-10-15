# T4a — پذیرش رسیدهای بهنام در PR #66

به‌روزرسانی: ۱۶ اکتبر ۲۰۲۶.

[PR #66](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/66) با head
`0d21450322a10bee9ca95c49000f378141fec913` review و به main با
`c69b0b435eb275f412ea835c43cbcf31fd2c725c` merge شد. فقط دو JSON اضافه می‌کند؛
کد، قرارداد، تست، index و ledger عوض نشده‌اند. رسیدهای اصلی بدون اصلاح حفظ‌اند:

- [قطع پاسخ موفق و Retry از UI](receipts/approval-ack-drop-ui-retry-sanitized.json).
- [خلاصهٔ آزمایش دو پرونده روی f8b3106](receipts/two-case-smoke-2026-10-14-sanitized.json).
- [رسید review و تست محلی](receipts/pr66-final-review-2026-10-16.json).

## چه چیزی پذیرفته شد؟

بهنام گزارش کرده proxy محلی، پاسخ موفق Approval را **پس از commit در backend**
قطع کرده و از خود Streamlit گزینهٔ `Retry review` را زده است. شمار Actionها
پیش از Approval صفر، پس از commit یک، بعد از Retry یک و بعد از بازشدن دوبارهٔ
Chrome یک مانده است. revision در سناریوی fault برابر۱ و status نهایی
`answer_sent` است. دوپرونده‌ای، سناریوی جدا با revision۲ و وضعیت `awaiting_user`
دارد؛ وضعیت متفاوت این دو رسید تناقض نیست.

این‌ها **مشاهدهٔ دستی گزارش‌شدهٔ هم‌تیمی** در backend آفلاین و synthetic‌اند.
JSON معتبر و پاک‌سازی‌شده است و دادهٔ احراز هویت/کلید ندارد؛ screenshot، DB یا
token خصوصی برای پذیرش این خلاصه لازم نیست. رسید fault، commit دقیق اجرای
آزمایش، تاریخ run و proxy ذخیره‌شده ندارد؛ آن را اجرای مستقل بازتولیدشده روی
main فعلی یا اثبات پوشش همهٔ failureها حساب نمی‌کنیم.

## بازکردن مرورگر چه چیزی را ثابت نمی‌کند؟

خود رسید می‌گوید پس از بازشدن Chrome، **session و case تازه** ساخته شده است؛
فقط اطلاعات پروندهٔ اصلی در SQLite باقی مانده‌اند. این نتیجه به معنی restore
خودکار همان case، بازیابی `unsent_reviews` یا retry درخواست تأییدنشده در session
کاملاً تازه نیست. آن مورد همچنان کار مشترک UI/product و tracker است.

رفتار فعلی هم همین مرز را دارد: `app_pages/assistant.py` لیست پرونده‌ها و
`unsent_reviews` را در `st.session_state` نگه می‌دارد. SQLite با همان `review_id`
و payload دقیق، receipt قبلی را پس از restart برمی‌گرداند؛ ساخت یک Approval
تازه جای بازیابی operation قبلی نیست. این تحویل چنین مسیری اضافه نمی‌کند.

## تست محلی چه بود؟

روی main مبنا`d8a3cd3`، **۱۷۶ تست موجود** در شش فایل زیر پاس شد:

```bash
uv run pytest tests/test_sqlite_tracker.py tests/test_sqlite_runtime.py \
  tests/test_persistent_api.py tests/test_persistent_http_crash.py \
  tests/test_ui_persistent.py tests/test_ui_client.py
```

پوشش شامل تراکنش/revision، restart و crash، رد approval قدیمی، عدم تکرار Action،
رد reuse هویت با payload متفاوت، و retry از AppTest با timeout/503/پاسخ نامعتبر
است. AppTest و backend آزمایشی جای اجرای دستی Chrome با proxy را نمی‌گیرند؛
root آزمایش تازهٔ Chrome انجام نداده است.

درخت merge پیش از انتشار محاسبه و بعد از merge دقیقاً تطبیق داده شد؛ نسبت به
main مبنا فقط همان دو JSON اضافه شده‌اند. کد و تست‌ها با source`50a3f8d` که
قبلاً۵۴۲۴ تست پاس کرده بود یکسان‌اند؛ آن suite در این review دوباره اجرا نشد.
hosted job لینوکس به علت Billing شروع نشده؛ CI سبز یا Windows تازه ادعا نمی‌شود.
همان hash ledger و۱۹pin فعلی ثابت‌اند؛ API صفر، halt و سهhold محفوظ‌اند.

## چه چیزی باز می‌ماند؟

T4 کامل تیک نمی‌خورد: pin اجرای fault، failure/outcome و مصرف نتیجهٔ ابزار در
تصمیم بعد، handoff ارزیابی و recovery در session تازه هنوز شاهد جدا می‌خواهند.
این تحویل کیفیت مدل، RAG یا test نهایی را نمی‌سنجد.

قدم مستقل بعدی core، task **C2j** در plan است: دو helper پاسخ نسخه در
`orchestration/intake.py`، object دست‌ساز Python دارای field اضافی nested را
با dump پاک و قبول می‌کنند. probe خنثی آفلاین در همان main نشان داد helperهای
pending و approved هر دو این مورد را می‌پذیرند، ولی `detached_contract` موجود
همان ورودی را رد می‌کند. این **گپ validation درون Python** است، نه اثبات exploit
از HTTP، نقص approval یا خطای مدل. رفع آن هنوز در این تحویل انجام نشده؛ مسیر
محدود بعدی استفاده از validator موجود، regression و حفظ خروجی معتبر است.
این وضعیت مربوط به تحویل T4a است؛ [تحویل بعدی C2j](intake-validation.fa.md)
اصلاح و شواهد جداگانهٔ آن را ثبت می‌کند و receipt تاریخی T4a تغییر نکرده است.
