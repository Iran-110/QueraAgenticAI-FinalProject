# تحویل core و مرز کارهای باقی‌مانده

مسیر اصلی تصمیم‌گیری، correction، کنترل نسخه، اعتبار شواهد و جدایی پیشنهاد از
اجرا تحویل شده است. قالب اختیاری review brief هم ثبت‌پذیر و قابل ساخت کنترل‌شده
شد. در [C4r](core-delivery-selection.fa.md)، recipe نرم‌افزاری core انتخاب و با
factory/backend واقعی تطبیق داده شد؛ renderer قبلی منتخب است. freeze مشترک
index/gold، داوری کیفیت و ارزیابی نهایی هنوز باقی‌اند. شرح C4q در ادامه، مرز
تاریخی همان تحویل را ثبت می‌کند.

## C4q: تنظیم ثبت‌شده به کدام reasoner می‌رسد؟

descriptor تاریخی v1 گزینهٔ `review_brief` را نمی‌شناخت. ما v1 یا receiptهای
قدیمی را تغییر ندادیم. ماژول جدید
[`registered_reasoner.py`](../src/agent_app/orchestration/registered_reasoner.py)
یک envelope نسخهٔ ۲ می‌سازد که v1 معتبر را همراه policy صریح
`legacy_v1` یا `review_brief_v1` ثبت می‌کند. v1 و v2 به‌صورت ضمنی به هم تبدیل
نمی‌شوند؛ hash تازهٔ یک declaration ناسازگار هم آن را معتبر نمی‌کند.

```python
from agent_app.orchestration.registered_reasoner import (
    describe_registered_grounded_configuration,
    build_registered_grounded_reasoner,
)

# expected از ثبت بازبینی‌شده؛ actual_public_arguments از تنظیم واقعی caller.
# key یا دادهٔ gold در descriptor وارد نمی‌شود.
observed = describe_registered_grounded_configuration(
    renderer_policy="review_brief_v1",
    **actual_public_arguments,
)
reasoner, construction_binding = build_registered_grounded_reasoner(
    expected,
    observed,
    planner_factory=guarded_planner_factory,
)
# caller binding را کنار receipt اجرای تازه ذخیره می‌کند و reasoner را به
# همان ports/engine بازبینی‌شده تزریق می‌کند. این مثال مجوز اجرای live نیست.
```

builder، برابری کامل دو ثبت را **پیش از فراخوانی factory** بررسی می‌کند؛ flagهای
واقعی `GroundedReasoner` و catalog سؤال از همان نسخهٔ جداشده می‌آیند. تغییر
objectهای ورودی در callback، تنظیم اعمال‌شده را عوض نمی‌کند. override جداگانه
برای renderer یا request factory ندارد. سؤال builtin نسخه و حذف سؤال دربارهٔ
fact معلوم هم همچنان با catalog واقعی انجام می‌شوند.

receipt برگشتی، SHA ثبت پذیرفته‌شده و policy را دارد و فقط ساخت همان flagها و
catalog را تأیید می‌کند. تنظیم واقعی planner/model، endpoint، code/build، policy
engine و بودجه را احراز نمی‌کند. caller باید guardهای هزینه، مالکیت و cleanup
منابع factory، تطبیق واقعی source/index و ثبت receipt را انجام دهد. برابری
declaration، احراز هویت reviewer یا مجوز پرداخت نیست. reasoner پایتونی بعداً
قابل تغییر است؛ helper نظارت دائمی runtime انجام نمی‌دهد.

این مسیر **تزریق صریح** است: factory معمول، env، UI/API و runner خودکار عوض
نشده‌اند و هنوز renderer قبلی را می‌سازند. `ClaimReasoner` هم تحت این registration
نیست؛ انتخاب pipeline و `block_mode` آن باید جدا bind شود. قالب جدید به‌عنوان
تنظیم نهایی انتخاب نشده و descriptor نهایی تیم هم توسط این تحویل freeze نمی‌شود.

## بررسی و تحویل

```bash
uv run pytest tests/test_registered_reasoner.py tests/test_registered_reasoner_review.py tests/test_configuration_freeze.py -q
uv run agent-app demo --scenario refine
uv run agent-app gateway-demo --scenario repair
uv run agent-app turn-demo
uv run ruff check .
uv run ruff format --check .
```

روی source `9f24376`، ۵۸۰ تست مرتبط تازه پاس شدند؛ ۴۵ کنترل root و ۱۸ کنترل
مستقل جدید هم در این شمارش هستند. review مستقل ۲۷۱ تست را پاس کرد؛ این اعداد
هم‌پوشانی دارند و با هم جمع نمی‌شوند. هر سه دمو exit صفر داشتند و Ruff برای
۳۸۱ فایل پاس شد. audit اجرای متمرکز در parent، صفر تلاش بازکردن فایل محافظت‌شده
یا اتصال شبکه ثبت کرد؛ attestation تمام subprocessها نیست.

بررسی گستردهٔ قبلی C4p مربوط به source خودش و ۶۰۷۳ تست در دو context است؛
برای C4q ادعای full-suite تازه نداریم. این تغییر فقط یک ماژول صریح و دو فایل
تست اضافه می‌کند؛ تمام sourceهای موجود و ترکیب پیش‌فرض عین byte قبلی مانده‌اند.

کنترل‌ها mismatch پیش از callback، تنظیم اعمال‌شده، mutation ورودی، حفظ v1،
سؤال canonical، fact معلوم، مسیر engine و handoff تازه و خطاهای پاک‌سازی‌شده
را بررسی می‌کنند. دموها آفلاین‌اند؛ گذشتن تست نرم‌افزار به معنی کیفیت مدل نیست.
[رسید تست و review](receipts/core-freeze-closeout-2026-10-16.json) scope و source
دقیق را ثبت می‌کند. داده‌های held-out، corpus، manifest و rubric تغییر نکردند؛
halt، سه hold و هویت‌های بستهٔ آزمایش حفظ‌اند. پیام تیمی ارسال نشده است.

## چه چیزی برای پایان پروژه مانده؟

| کار | صاحب / وابستگی | شرط پایان |
| --- | --- | --- |
| corpus و index نهایی | حسن | build قابل بازتولید، hash، exclusion و مشاهدهٔ passageهای رسیده |
| native gold، route، worksheet و freeze | محمدحسن، با هماهنگی core/RAG | ثبت قبل از اجرا، pinهای منطبق و review انسانی تنظیم منتخب |
| مرز باقی‌ماندهٔ T4 | بهنام و محمدحسن | بازیابی review تأییدنشده پس از session کاملاً تازه با رسید مشخص |
| C5 و اجرای نهایی | صاحب حساب mentor و تیم evaluation | تعیین تکلیف سه درخواست نامعلوم؛ سپس مجوز معتبر و اجرای test بدون tuning |

Enum هنوز تشخیص/fix و usefulness تأییدشدهٔ تازه ندارد. بهبود ساختار متن و
نمایش CRLF جدا ثبت شده است. در وضعیت فعلی، feature تازه‌ای برای core در اولویت
نیست؛ نتیجه‌های باقی‌مانده باید با تنظیم و دادهٔ نهایی جمع شوند.

آپدیت هم‌تیمی: [review PR80](receipts/pr80-review-2026-10-16.json) feedback
با کمک دستیار را برای ۲۲ draft تاریخی C4j ثبت می‌کند. این ثبت جای review مستقل
یا نمرهٔ claim support را نمی‌گیرد؛ worksheet اصلی و نمره‌های null آن حفظ‌اند.

[رسید اتصال PR80](receipts/pr80-integration-2026-10-16.json): ۳۲ تست مرتبط پاس؛
artifact اصلی، worksheet و receipt مدل عین byte حفظ شده‌اند.
