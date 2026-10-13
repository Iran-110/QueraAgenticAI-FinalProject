# حفظ تناقضِ حل‌نشده در core — C4b

وقتی caller در یک run تناقض منابع را اعلام کرده، حذف یک طرف در retrieval بعدی
به معنای رفع آن نیست. قبلاً با خالی‌شدن `conflict_groups`، core پاسخ را قبول
می‌کرد و summary می‌گفت تناقضی اعلام نشده است. همین اتفاق با تغییر متن زیر
همان `chunk_id` یا warningِ «تناقض حل شد» هم قابل بازتولید بود.

حالا `GroundedReasoner` وضعیت حل‌نشده را برای همان `run_id`، `case_id` و
`case_revision` نگه می‌دارد. اگر pool بعدی گروه تناقض را نداشت، source gapِ
`unresolved_prior_source_conflict` به **درخواست واقعی planner** اضافه می‌شود و
hash دوباره ساخته می‌شود. `answer` با `grounded_conflict_unresolved` رد می‌شود؛
سؤال لازم یا ارجاع همچنان ممکن است. وضعیت در maintainer summary و rationale
می‌آید؛ متن سؤال همان سؤال canonical می‌ماند. فقط excerptهای pool فعلی قابل
نمایش‌اند؛ متن، hash و citationِ شاهد قبلی از cache برنمی‌گردد.

## مقایسهٔ ثبت‌شده

[پروتکل](../experiments/conflict_continuity/protocol-v1.json) و ۱۴ کنترل قبل از
اصلاح، در `c9f15b8` ثبت شدند؛ اصلاح production در `de5d106` و مقایسهٔ کد در
`8cc41bff45a3d95e8ca9f12ef13c573ba9036f86` انجام شد. همان فایل تست، با همان
hash، روی source آرشیوشدهٔ Git و source جدید اجرا شد:

| مشاهده | قبلی `03225e2` | جدید `8cc41bf` |
| --- | --- | --- |
| ۱۴ کنترل ثابت | ۷ pass و ۷ fail | ۱۴ pass |
| سه پاسخ پس از حذف/تغییر شاهد یا warning | `awaiting_approval` | error، بدون proposal |
| چهار سؤال/ارجاع پس از تغییر pool | مجاز، ولی تناقض فراموش می‌شد | مجاز، با بیان تناقض حل‌نشده |

[receipt مقایسه](../experiments/conflict_continuity/comparison-v1.json)،
[review](../experiments/conflict_continuity/review-v1.json) و
[verification](../experiments/conflict_continuity/verification-v1.json) خروجی،
hash ورودی و source هر دو اجرا را جدا نگه می‌دارند. ۲۵ تست مرزی و پنج تست
HTTP/SQLite با `MockTransport` هم اضافه شده‌اند؛ مجموع کنترل‌های تازه ۴۴ است.
تست کامل محلی با همان byteهای runtime/testِ `8cc41bf`، **۲۸۴۱ pytest در
۱۱۰٫۱۰ ثانیه**، Ruff برای ۲۰۳ فایل و سه demo آفلاین پاس‌اند. هنگام تست کامل
stage/commit انجام می‌شد؛ تطبیق مربوط به byteهاست. receipt مقایسه و پذیرش
HTTP/SQLite با process تازه روی commit تمیز `8cc41bf` ثبت شدند؛ پذیرش
**۴۵۷/۴۵۷**، شامل restart، پاس است. CI انتشار نهایی جدا ثبت می‌شود.

planner این آزمایش scripted است و retrieval با fixture انجام می‌شود؛ درخواست
مدل واقعی، سرچ index واقعی و خرج API در این مرحله صفر است. این کنترل‌ها از
همان خانوادهٔ exposed و answer-informedِ V9، Issueهای #12782/#12629، می‌آیند.
تناقض synthetic و دستی است؛ case مستقل یا داوری کیفیت مدل اضافه نمی‌کنند.
case، پاسخ، reviewer، receipt و duplicateهای این خانواده وارد corpus واقعی
RAG یا test مستقل نشوند. [بستهٔ کامل و حدود نتیجه](../experiments/conflict_continuity/README.md).

## اتصال و مرزها

- وضعیت cache فقط یک flag و کلید scope است؛ حداکثر ۳۲ run ناتمام، بدون حذف
  وضعیت قبلی برای جا دادن run جدید. اگر slot تازهٔ تناقض لازم باشد و cache پر
  باشد، اجرا قبل از planner متوقف می‌شود. اگر افزودن marker لازم باشد و catalog
  هشت gap داشته باشد، همان‌جا متوقف می‌شود؛ سؤال کاربر برای جا دادن marker حذف نمی‌شود.
- خطای قابل repair، همان allowance قبلی را مصرف می‌کند و تناقض را حفظ می‌کند.
  توقف terminal و پایان invocation، حتی در خطای retrieval، stale state یا
  کمبود step، flag همان scope را آزاد می‌کنند. cleanup ورودی نهایی handoff را
  پاک نمی‌کند؛ خطایش با `ReasoningUnavailable` و بدون پیشنهاد قابل تأیید ثبت می‌شود.
- adapter باید `GroundedRequest` واقعاً رسیده به `plan()` را برای
  `grounded_request_supplier` نگه دارد. درخواست اولیهٔ factory ممکن است marker
  و hash نهایی را نداشته باشد؛ از آن برای گزارش ورودی مصرف‌شده استفاده نکنید.
  `GroundedHttpBinding` و factory موجودِ live این ورودی واقعی را capture می‌کنند.
- wrapperِ یک reasonerِ قابل استفادهٔ مجدد باید cleanup خصوصی
  `_release_core_scope` را forward کند؛ `ReasoningCapture` این کار را می‌کند.
  adapterهای معمول برای هر run نمونهٔ تازه می‌سازند. امضای portها، قراردادهای
  مشترک، revision و approval tracker تغییر نکرده‌اند؛ core همچنان فقط پیشنهاد می‌دهد.

تشخیص خودکار تناقض و قرارداد رفع آن ساخته نشده‌اند. catalog پیش‌فرض هم گروه
تناقض تولید نمی‌کند؛ این guard از **تناقضی که قبلاً اعلام شده** محافظت می‌کند.
تغییر run، case یا revision، وضعیت invocation قبلی را منتقل نمی‌کند؛ caller
باید اطلاعات مربوط به وضعیت جدید را جدا فراهم کند. E1/E2/R4/E4/E5/C5 و C4
روی dev مستقل بازند. برآورد بخش الزامی همان حدود ۷۵٪ است؛ تعداد تست‌ها را
درصد تکمیل یا کیفیت مدل حساب نمی‌کنیم.

از ریشهٔ repository، بدون کلید:

```bash
uv run pytest tests/test_conflict_continuity.py tests/test_conflict_continuity_boundaries.py tests/test_conflict_continuity_http.py
uv run python scripts/conflict_continuity_comparison.py --output /tmp/conflict-continuity-comparison.json > /tmp/conflict-continuity-console.json
```
