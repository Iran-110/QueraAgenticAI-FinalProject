# C5 — وضعیت تطبیق live، ۱۱ اکتبر ۲۰۲۶

بررسی روی مبنای `94b60e1` و snapshot ساعت `16:18:56 UTC` انجام شد. ledger
اصلی با SQLite `mode=ro` خوانده شد؛ fingerprint DB/WAL/SHM پیش و پس یکسان
بود. کلید خوانده نشد، درخواست provider یا تغییر ledger انجام نشد.

| مورد | دادهٔ محلی موجود |
| --- | --- |
| توقف | `halt=true`؛ سقف runner برابر `4.50 USD` |
| settlement تخمینی | `0.120888405 USD` برای ۱۷۵ درخواست |
| pending / uncertainty | صفر pending؛ یک درخواست با hold برابر `0.02 USD` |
| available bound | `4.359111595 USD`؛ حسابداری محلی، نه موجودی provider یا مجوز live |
| درخواست حل‌نشده | مدل درخواستی `gpt-4.1-mini`؛ guard `ProviderModelMismatch` در ۷ اکتبر |
| serving model / usage / actual charge | نامعلوم؛ null به معنی صفر نیست |

درخواست نامعلوم در `2026-10-07T11:20:50.248Z` رزرو و در
`11:20:57.443Z` متوقف شد. [gateway](../src/agent_app/llm/metis.py) پیش از
parse usage روی guard هویت مدل متوقف می‌شود؛ receipt تاریخی نام مدل برگشتی
و provider response ID را حفظ نکرده است. افزایش hold از `0.00856064` به
`0.02 USD` در continuation قبلی، شاهد مبلغ واقعی مصرف نیست.
[قیمت‌های pinشده](../src/agent_app/llm/pricing.py) نیز صورتحساب حساب نیستند.

packet محلی `c5-local-reconciliation-2026-10-11-v1` بیرون Git، در پوشهٔ
`output/core-turn-coordinator-2026-10-11/reconciliation/` آماده است: JSON
snapshot و timeline، caller identity دقیق، مجموع مدل/phase، SHA-256 یازده
منبع و راهنمای تحویل blocker. prompt، پاسخ خام و credential صادر نشده‌اند.
SHA-256 packet:
`402972621a4e873ee60dafe0f11f40f92859e7e29e9b43669c676e20401f4300`.
وجود فایل محلی به معنی تحویل یا تأیید provider نیست.

برای رفع C5، رکورد provider همان درخواست باید به زمان و مدل درخواستی وصل
شود و serving model واقعی، usage، actual charge/rate/currency و refund را
روشن کند. سپس usage/اعتبار کل حساب با تمام هزینه‌های تیم، از جمله embedding
و evaluation، تطبیق داده شود. raw credential برای این تحویل لازم نیست.
alias حدس نمی‌زنیم و مبلغ نامعلوم را صفر حساب نمی‌کنیم.

continuation تاریخی route `gpt-4o-mini`، bound باقی‌ماندهٔ
`0.007784635 USD` دارد؛ رکورد active، مجوز عمومی یا grant تازه نیست.
با شواهد فعلی C5 باز است. halt و uncertainty حفظ شوند؛ پس از تکمیل تطبیق،
تصمیم accounting و سقف/مجوز آزمایش محدود جدا ثبت شوند. این بررسی نتیجهٔ
کیفیت مدل، RAG یا test نهایی نیست.
