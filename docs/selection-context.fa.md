# C4l/E2y — context فعلی برای مرور پیشنهادی شواهد

به‌روزرسانی: ۱۶ اکتبر ۲۰۲۶. این تغییر **اختیاری و فقط advisory** است؛ factory،
مدل، retrieval، UI و tracker به آن منتقل نشده‌اند. halt و سه hold حفظ می‌شوند.

## چه مشکلی را محدود کردیم؟

در helperهای [انتخاب شاهد](evidence-selection.fa.md)، کنار گذاشتن fact منسوخ از
جدول کافی نبود: همان عبارت هنوز داخل رشتهٔ کامل history امتیاز می‌گرفت.
پیش از کد، [protocol](../experiments/core_selection_context_v1/protocol-v1.json)،
هشت fixture خنثی و digestهای ۲۴ ورودیِ حالت قبلی ثبت شدند.

در fixture تألیفی correction، موضوع از `document export` به `connection pooling`
اصلاح شده، ولی توضیح قبلی طولانی است. در baseline، منبع موضوع قبلی با امتیاز
حدود۰٫۳۵۴ بالاتر از منبع فعلی با حدود۰٫۱۲۲ می‌ایستد. با context اختیاری، منبع
فعلی اول می‌شود. **منبع قبلی همچنان می‌تواند در shortlist باشد**؛ این کنترل
ترتیب و freshness واژگانی است، نه حذف کامل شواهد قدیمی یا اثبات relevance.

## ورودی و اتصال

context خصوصی در [selection_context.py](../src/agent_app/reasoning/selection_context.py)
از سه ورودی ساخته می‌شود: `ClaimRequest` فعلی، `CaseState` کامل و
`TurnConversation` معتبر همان پرونده. caller باید دو مورد آخر را از view معتبر
همان case بخواند. `TurnConversation` فیلد `case_id` ندارد؛ تطابق محتوا و hash،
منشأ history یا هویت caller را authenticate نمی‌کند.

```python
from agent_app.reasoning.selection_context import build_evidence_query_context
from agent_app.reasoning.evidence_selection import (
    suggest_evidence_units,
    inspect_claim_selection,
)

query_context = build_evidence_query_context(request, current_case, conversation)
shortlist = suggest_evidence_units(request, query_context=query_context)
observation = inspect_claim_selection(
    request, existing_plan, query_context=query_context
)
```

این context، ساختار خصوصی برای آزمایش/inspection است؛ shared contract یا مجوز
live/action جدید نیست. ورودی‌های بالا باید همان request و state واقعی caller
باشند؛ از رشتهٔ history یا خروجی مدل fact نسازید.

- `build_reasoning_message` موجود باید دقیقاً پیام فعلی request را بازسازد؛
  همان normalization فضای ابتدا/انتها در قرارداد قبلی رعایت می‌شود.
- `build_current_query` موجود، projection حداکثر۵۰۰ کاراکتری می‌سازد. تاریخچه،
  آخرین پیام، source و متن ورودی مدل کوتاه یا بازنویسی نمی‌شوند.
- همهٔ case، conversation، projection و hash کل request در digest جدید bind
  می‌شوند؛ history نادیده‌گرفته‌شدهٔ assistant هم جزو binding کامل است.
  تغییر source، mode، revision یا هر قسمت context آن را نامعتبر می‌کند.
- recursive validation پیش از dump، nested extra و دادهٔ bypass‌شدهٔ نامعتبر
  را رد می‌کند؛ خطای خروجی فقط `grounded_context_mismatch` است. context نامعتبر
  به مسیر قدیمی fallback نمی‌کند.

سه helper `rank_evidence_units`، `suggest_evidence_units` و
`inspect_claim_selection` پارامتر اختیاری `query_context` دارند. در مسیر جدید،
واژهٔ projection فقط وقتی امتیاز می‌سازد که در متن واقعی USER یا value فعال
USER وجود داشته باشد. labelهای helper و نام fact به‌تنهایی امتیاز نمی‌سازند؛
factهای evidence/inference و متن assistant هم authority نیستند. همهٔ valueهای
فعال USER حتی اگر در projection محدود جا نشوند، در محاسبه باقی می‌مانند.

shortlist و inspection جدید `query_context_sha256` را ثبت می‌کنند. خروجی‌ها و
فیلدهای حالت بدون context یا `None` **عیناً قبلی** مانده‌اند؛ ۲۴ digest ثبت‌شده
این را کنترل می‌کنند. passage کامل، بودجهٔ۶۰۰۰ byte، scope نسخه، و
`semantic_support=null` / `human_review_required=true` ثابت‌اند. rank فقط tuple
hint می‌دهد؛ برای نگهداری نتیجه، digest context را هم کنار آن نگه دارید.

## چه چیزی هنوز حل نشده؟

negation در آخرین پیام هنوز واژهٔ نفی‌شده را match می‌کند. synonym مفید می‌تواند
امتیاز صفر بگیرد و در shortlist نیاید. جزئیات تاریخی که به fact منسوخ وصل
نیستند ممکن است در topic hint بمانند؛ مقدار فعال USER هم می‌تواند گزارش اشتباه
کاربر باشد. binding و نقل دقیق، صحت گزارش، entailment، کامل‌بودن caveat یا
مفیدبودن پاسخ را ثابت نمی‌کنند.

هشت سناریو شامل correction، A→B→A، پاسخ کوتاه نسخه، poison در assistant/evidence،
نام fact، negation، synonym و پروندهٔ مستقل‌اند. همه تألیفی و exposed dev هستند،
بدون پاسخ Issue یا gold در runtime. شانزده snapshot قبلی فقط برای default parity
خوانده می‌شوند. در [replay](../experiments/core_selection_context_v1/replay-v1.json)
هر۸۱ کنترل پاس است؛ این عدد نرخ موفقیت مدل، RAG یا test نهایی نیست. هیچ مدل
plan تازه‌ای انتخاب نکرده و usefulness انسانی همچنان نمره ندارد.

## بازتولید

```bash
uv run pytest tests/test_selection_context.py tests/test_selection_context_replay.py
uv run python -m agent_app.testing.selection_context_replay \
  --output /tmp/selection-context-fresh.json
```

مسیر output باید تازه باشد؛ runner receipt قبلی را overwrite نمی‌کند. ledger،
index واقعی، credential و gateway ساخته نمی‌شوند. تغییر از این helper خصوصی
به تنظیم محصول یا آزمایش API، تصمیم جداگانه با protocol و review لازم دارد؛
این تحویل C5، review انسانی و ارزیابی نهایی را نمی‌بندد.
