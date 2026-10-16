# اتصال core به split تازه — C4m / E2z

**C4p:** [review brief اختیاری](maintainer-review-brief.fa.md) متن proposal
تازه می‌سازد؛ نمرهٔ انسانی PR77 به آن منتقل نمی‌شود. worksheet تازه باید hash
همان proposal و renderer policy را ثبت کند. final config هنوز انتخاب نشده؛
قالب جدید default نیست و descriptor فعلی آن را bind نمی‌کند.


**آپدیت C4o/E2ab:** v2 سه dev در PR79 ثبت و دوباره با شواهد ثابت اجرا شد؛
همان سه خانواده با rubric v1 هستند، نه native gold یا caseهای تازه.
[قرارداد native review](native-evidence-review.fa.md) حضور passage را از
پشتیبانی ادعا و کفایت پاسخ جدا می‌کند. runner/scorer و routeها تغییر نکرده‌اند؛
observer اختیاری فقط مشاهدهٔ ساختاری handoff را ثبت می‌کند. native gold/routes،
worksheet C4j و freeze همچنان با محمدحسن است؛ corpus/build نهایی با حسن.

این تحویل از `main` در `9913541` شروع شد. PRهای #70 تا #76 به مخزن رسیده‌اند.
manifest، ۱۶ dev و ۱۵ test را ثبت کرده و هنوز draft است. محتوای fixture، gold
و evidenceهای test برای این کار باز یا مصرف نشده؛ فقط metadata شمارش، exclusion
و شناسهٔ Git پوشه برای کنترل عدم تغییر استفاده می‌شود. اجرای آفلاین کل split
که محمدحسن گزارش کرده، شاهد عملیاتی است؛ کیفیت مدل یا نتیجهٔ test نهایی نیست.

## سؤال‌های کاربر

فایل اختیاری جدید [`config/user-gap-support-dev-v1.json`](../config/user-gap-support-dev-v1.json)
دو تعریف قبلی را همراه `updated_form_code` و `app_state_code` دارد. این دو
سؤال فقط از درخواست‌های dev بررسی‌شده آمده‌اند؛ description و necessity علت
یا راه‌حل آیندهٔ case را به مدل نمی‌دهند. فایل تاریخی dev-three تغییر نکرده.

برای استفادهٔ بعدی، caller می‌تواند `AGENT_USER_GAP_CATALOG` را به همین فایل
اشاره دهد. این تنظیم startup مدل را مجاز نمی‌کند؛ halt و کنترل ledger قبل از
credential lookup برقرارند. نمونه و ترتیب اتصال در
[راهنمای vocabulary](user-gap-configuration.fa.md) است.

تعریف سؤال به‌تنهایی کافی نیست: نامش باید در `unknowns` فعلی caller باشد.
fact فعال USER با همان نام، سؤال را حذف می‌کند؛ fact بازنشسته یا EVIDENCE
جای تأیید کاربر را نمی‌گیرد. prose به‌تنهایی gap ثبت نمی‌کند. وجود گزینهٔ سؤال
اثبات نمی‌کند که مدل آن را انتخاب می‌کند یا سؤال در هر case لازم است.

برای test، سؤال اختصاصی یا alias از روی gold تعریف نمی‌کنیم. vocabulary عمومی
خودش «جواب آماده» نیست؛ فضای سؤال‌های مجاز سیستم است و باید پیش از test، با
dev و سناریوی خنثی تعریف و برای هر دو split ثابت شود. core فعلی سؤال آزاد
نمی‌سازد؛ از گزینه‌های ثبت‌شده انتخاب می‌کند. بنابراین «این گزینه را حذف کنیم
تا مدل خودش همان سؤال را پیدا کند» با قرارداد فعلی سازگار نیست.

مالک evaluation، بدون آشکارکردن test، قابلیت‌های vocabulary ثابت را با branchهای
ثبت‌شده تطبیق دهد. اگر سؤال معتبر پاسخ‌دهنده در fixture ثبت نشده، پوشش fixture
ناقص است؛ اگر قابلیت لازم در core وجود ندارد، محدودیت سیستم را جدا گزارش کند.
هیچ‌کدام مجوز افزودن سؤال پس از دیدن نتیجهٔ test یا تغییر بی‌صدای gold نیست.

## gold و شواهد واقعی

فعلاً گزینهٔ **الف**: برای native یک scope و نسخهٔ gold جدا، پیش از اجرای تازه
ثبت شود. runner، route validation و final preflight همگی هنوز یک gold در هر
turn دارند؛ این تحویل پشتیبانی gold چندشرطی به آن‌ها اضافه نمی‌کند.

نسخهٔ تازه باید به fixture/turn، rubric، index build، allowlist و exclusion
مشخص bind شود و مسیرهای مجاز همان شرط شواهد را ثبت کند. اجرای native با gold
ثابت قبلی، نمرهٔ معتبر native نمی‌دهد. `mode=live` هم به‌تنهایی اثبات native
بودن یا کفایت شواهد نیست. بررسی claim به bundle واقعاً مصرف‌شدهٔ همان turn،
متن passage، محدودهٔ نسخه و وضعیت فعال کاربر وابسته است.

برای runner فعلی، فایل gold جانبی خودکار خوانده نمی‌شود. artifact تازه باید
نسخهٔ fixture مشخصی با `fixture_id` تازه، `turns[].gold` و
`evaluation.coverage.routes` سازگار باشد؛ در profile نهایی، pinهای final packet
هم باید همان scope را ثبت کنند. gold جانبی فقط می‌تواند مبنای review دستیِ
جدا باشد؛ checkهای runner با gold ثابت قبلی را معتبر نمی‌کند.
ورودی اجرای آن scope فقط همان نسخه را انتخاب کند. نسخه‌های ثابت و native را
با case_id تکراری در یک invocation جمع نکنیم. دادهٔ قابل‌مشاهدهٔ کاربر و خانوادهٔ
case حفظ شوند؛ ثبت scope تازه اجازهٔ بازنویسی receiptهای قدیمی نیست.

در case-a، گزارهٔ محدود «`st.multiselect` در 1.50.0، در صورت داشتن key، هویتش
را از key می‌گیرد» با عبارت کلی «همهٔ widgetها در 1.50 عوض شدند» یکسان نیست.
طبق [review قبلی](pr55-evidence-review.fa.md)، passage پشتیبان باید به مدل
رسیده باشد؛ بودن سند در allowlist یا index کافی نیست. سند عادی معتبر در corpus
می‌ماند، ولی سند answer-linkedِ excluded صرفاً fixture می‌ماند. gold و نتیجهٔ
تاریخی شواهد ثابت بازنویسی نمی‌شوند؛ علت کامل خطای app یا fix از این گزاره
به‌تنهایی نتیجه نمی‌شود.

## rubric تاریخی و جدید

dev-three و receiptهای قبلی همان `e2-core-review-draft-v1` می‌مانند؛ caseهای
جدید همان `e2-rubric-v1` هستند. برای review/اجرای تازه با v1، scope تازه ثبت
شود؛ ID قدیمی را به متن یا قضاوت جدید وصل نکنیم و نتیجه‌ها را در یک denominator
جمع نزنیم. لازم نیست برای تغییر نام rubric، fixture تاریخی را ویرایش کنیم.

برای اجرای نهایی یکدست با v1، از همان سه dev نسخهٔ v2 جدا با `fixture_id`
تازه ثبت شود و gold/routeهای آن با rubric جدید review شوند؛ صرف تغییر نام
کافی نیست. manifest اجرای تازه فقط نسخهٔ انتخاب‌شده را pin کند. v2 سه case
مستقل تازه نیست و تعداد خانواده‌ها را افزایش نمی‌دهد؛ v1 و receiptهای تاریخی
بدون تغییر باقی می‌مانند.

مرز ساخت workbenchهای تاریخی حالا ID و SHA دقیق rubric ثبت‌شده را با scenario
و gold همهٔ turnها تطبیق می‌دهد. متن v1 زیر ID قدیمی، متن دست‌کاری‌شده با نام
قبلی و اختلاف ID قبل از نوشتن خروجی رد می‌شوند. این کنترل custody است؛ نمرهٔ
انسانی یا تأیید پشتیبانی معنایی را تولید نمی‌کند.

## تصویر و screenshot

این تحویل text-only می‌ماند. قرارداد پیام، UI/API و درخواست مدل، ورودی تصویر
یا OCR ندارند. اشارهٔ کاربر به screenshot به معنی دسترسی agent به محتوای آن
نیست. در صورت نیاز، کد یا متن خطا را بخواهیم و ادعا نکنیم تصویر خوانده شده.
سؤال `app_state_code` همین مسیر درخواست متن را برای dev فراهم می‌کند؛ هیچ
تشخیص خودکار تصویر یا fallback بینایی اضافه نشده است.

## ادامهٔ کار بدون تداخل

- **حسن:** relevance و packing شاهد key-identity را روی dev بررسی کند؛ تعداد
  کاندیدا، نسخه، ترتیب و بودجهٔ بایتی را جدا ثبت کند. تغییر corpus/build یا
  default فقط با مقایسهٔ ثبت‌شده؛ exclusion نهایی همراه build hash باشد.
- **محمدحسن:** gold native و routeهای همان scope را ثبت کند؛ coverage سؤال‌های
  vocabulary ثابت، نسخهٔ v2 سه dev برای rubric جدید و review usefulness را جمع
  کند؛ سپس manifest را freeze
  کند. محتوای test تا اجرای نهایی محفوظ بماند.
- **ساسان:** صحت مرز rubric، availability سؤال‌های dev، بازپخش retrieval امن
  و اتصال آفلاین را تحویل می‌دهد. C5 و سه درخواست نامعلوم هنوز بازند؛ هیچ API،
  scope تازهٔ پرداختی یا استفادهٔ مجدد از IDهای بسته در این تحویل وجود ندارد.

روش و نتایج دقیق در [packet](../experiments/evaluation_readiness_v1/README.md)
ثبت می‌شوند. هیچ‌یک از این کنترل‌های نرم‌افزاری، کیفیت نهایی جواب Enum، RAG یا
held-out test را ثابت نمی‌کنند.
