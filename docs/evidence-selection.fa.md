# C4k/E2x — انتخاب شاهد کامل؛ کنترل آفلاین و نشانهٔ ارتباط

به‌روزرسانی: ۱۶ اکتبر ۲۰۲۶.

انتخاب اختیاریِ section کامل، خطای ساختاریِ «عنوان بدون بدنه» را محدود می‌کند.
نشانهٔ lexical برای مرور کاندیداها هم اضافه شده؛ **هیچ‌کدام داور relevance،
entailment یا مفیدبودن پاسخ نیستند.** این تحویل API تازه یا بهبود اندازه‌گیری‌شدهٔ
مدل ندارد و مسیر production/default به آن منتقل نشده است.

## مسئله و baseline قابل بررسی

[ثبت پیش از پیاده‌سازی](../experiments/core_evidence_selection_v1/protocol-v1.json)
روی `59bd2c7` و [۱۶ baseline پیام/context/render](../experiments/core_evidence_selection_v1/default-baseline-v1.json)
پیش از تغییر ذخیره شدند. [inventory پس از مشاهدهٔ شکست‌ها](../experiments/core_evidence_selection_v1/failure-inventory-v1.json)
۱۲ مشاهده و هشت گروه regression پیشنهادی را با hash، JSON pointer و span به
رسیدهای قبلی وصل می‌کند. labelها تألیفی و exposed dev هستند؛ داوری مستقل انسانی
یا gold جدید برای test نیستند و وارد ورودی مدل یا corpus نمی‌شوند.

در C4j، مدل می‌توانست paragraph هویت Enum را همراه فقط heading الگوی module
انتخاب کند. body، import و caveat ویرایش/reload در همان source موجود بودند، اما
انتخاب نمی‌شدند. در نمونه‌ای دیگر codeِ عمداً خطادار از متن نهیِ پیش از آن جدا
انتخاب شده بود؛ خود code هنوز می‌گفت exception می‌دهد، پس آن را «fix اعلام‌شده»
توصیف نمی‌کنیم. پنج پاسخ نهایی دیگر با وجود نقل دقیق، نامرتبط یا بی‌محتوا بودند.

## تغییر اختیاری در core

`ClaimRequest` و `ClaimReasoner` در ماژول خصوصی
[claim_plan.py](../src/agent_app/reasoning/claim_plan.py) یک `block_mode` دارند:

- `paragraphs` همان پیش‌فرض قبلی است؛ context digest، messages و render هر۱۶
  baseline دقیقاً ثابت مانده‌اند.
- `sections` فقط با ساخت صریح فعال می‌شود. shallowest headingهای ATX/setext
  خارج از fence مرز واحدند؛ heading و تمام subtree تا heading هم‌سطح بعدی در
  یک unit می‌مانند. preamble جدا و متن بدون heading یک record کامل است.
  همهٔ کاراکترها، جداکننده‌ها، CRLF، code و metadata اصلی حفظ می‌شوند.
- unit خالی از body، مانند heading، separator، front matter یا fence خالی،
  در پاسخ `answer` پشتیبان مجاز نیست. code غیرخالی حتی اگر شبیه markup باشد
  body محسوب می‌شود؛ اجرا یا معنای آن تأیید نمی‌شود.
- mode و تمام spanها به context hash متصل‌اند. تغییر mode، source، revision یا
  ورودی، plan قبلی را معتبر نمی‌کند. index واحد، شناسهٔ ثابت محتوا نیست.

مثال اتصال آزمایشی با همان port و fixture موجود:

```python
from agent_app.reasoning.claim_plan import ClaimReasoner

reasoner = ClaimReasoner(
    fixture_planner,
    request_factory=reviewed_current_request_factory,
    block_mode="sections",
)
```

این مثال جایگزین factory/config عمومی یا مجوز live نیست. SYSTEM suffix جدید،
framework، agent، shared contract یا شاخهٔ تازهٔ prompt/order tuning اضافه نشد.
همان سؤال canonical، conflict، نسخهٔ فعال USER، سقف دو attempt/دو retrieval،
دو query و هشت step و guardهای input/render برقرارند. انتخاب section بزرگ
ممکن است از سقف render عبور کند؛ باید متوقف شود، نه اینکه منبع بریده شود.

### محدودیت کامل‌بودن

section کامل، **subtree ساختاری** کامل است. caveat یک بخش هم‌سطح یا منبع دیگر
ممکن است همچنان جا بماند. حتی source کامل ممکن است نامرتبط، شامل متن مهاجم یا
دارای scope متفاوت باشد. وجود `enumCoercion` در بخش widget، fix ذخیرهٔ مستقیم
Enum در Session State را ثابت نمی‌کند. هیچ علت، نسخهٔ نصب‌شده یا حل runtime
با این تغییر اثبات نشده است.

## نشانهٔ ارتباط، جدا از داوری

[evidence_selection.py](../src/agent_app/reasoning/evidence_selection.py) سه helper
خالص و اختیاری دارد:

- `rank_evidence_units`: cosine overlap با IDF محلی بین متن unit و پیام عرضه‌شده
  همراه مقدار factهای USER فعال. source/case ID، URL، score metadata، oracle و
  factهای superseded/evidence/inference در جدول facts امتیاز نمی‌سازند.
- `suggest_evidence_units`: پیش‌فرض حداکثر دو unit دارای body و overlap مثبت در
  بودجهٔ ۶۰۰۰ byte متن خام؛ رکورد بزرگ کامل کنار گذاشته می‌شود و truncate نمی‌شود.
  دو chunk مکمل از یک source هم مجازند. منابع دارای scope صریحِ نسخهٔ دیگر از
  این shortlist مربوط به محیط فعلی کنار می‌روند، اما evidence اصلی حذف نمی‌شود.
- `inspect_claim_selection`: فقط مشاهدهٔ ساختاری/lexical از plan فعلی؛ hash و
  عضویت source/fact را کنترل می‌کند. decision را تغییر نمی‌دهد و داور کامل
  question/conflict/semantics یا مجوز review/action نیست.

این helperها وارد مدل، ranking متعلق به RAG، factory، API/UI یا tracker عادی
نشده‌اند. shortlist یک پیشنهاد برای inspection است، نه پاسخ agent یا source gap.
بودجهٔ متن خام، سقف prompt/token/render را تضمین نمی‌کند.

اعداد نسخه از lexical matching اختیار scope نمی‌گیرند. از طرف دیگر پیام
عرضه‌شده ممکن است reasoning history داشته باشد؛ حذف factهای superseded از
جدول، واژه‌های تاریخی داخل آن رشته را خودکار حذف نمی‌کند. این محدودیت تست شده
و پنهان نشده است. overlap مثبت می‌تواند misleading باشد و synonym مفید می‌تواند
overlap صفر بگیرد. در همهٔ حالت‌ها `semantic_support=null` و review انسانی لازم است.

در ادامهٔ C4l، [context اختیاری فعلی](selection-context.fa.md) با CaseState و
TurnConversation کامل به request متصل می‌شود و برای همین helperها projection
فعلی می‌سازد. حالت بدون context دقیقاً رفتار بالا را حفظ می‌کند. این extension
واژه‌های fact منسوخ را در hint محدود می‌کند؛ حذف کامل موضوع قدیمی یا semantics
را تضمین نمی‌کند و وارد مدل یا retrieval پیش‌فرض نشده است.

## نتیجهٔ بازپخش؛ انتخاب مدل تازه نیست

[replay V2](../experiments/core_evidence_selection_v1/replay-v2.json) با
[runner آفلاین](../src/agent_app/testing/evidence_selection_replay.py) ساخته شد.
تمام ۱۰ plan نگهداری‌شدهٔ claim بررسی شدند؛ سه binding نامعتبر ابتدا رد می‌شوند
و به projection موفق تبدیل نمی‌شوند. هفت خروجی معتبر به unitهای جدید **به‌صورت
تألیفی و پس از مشاهدهٔ شکست** projection شده‌اند. ۲۱ خروجی خام ناموجود claim
بازسازی نشدند:۲۰ representation ردشده و یک failure سرویس بدون خروجی؛ این عدد
۲۱ خطای اثبات‌شدهٔ JSON نیست. ۲۷ invocation بازدیدنشدهٔ مطالعهٔ قبلی همچنان
بازدیدنشده‌اند.

| کنترل مشاهده‌شده | انتخاب اصلیِ نگهداری‌شده | projection تألیفیِ section |
| --- | --- | --- |
| body الگوی module در Enum، span `[98,544)` | غایب | کامل حاضر |
| caveat ویرایش/reload همان record، span `[1896,2143)` | غایب | کامل حاضر |
| متن نهیِ پیش از مثال خطادار در پروندهٔ restart | غایب | کامل حاضر |
| draft سؤال canonicalِ معتبر | ۹۳ کاراکتر | همان ۹۳ کاراکتر |
| median طول draft در همان هفت خروجی | ۱۴۵۹ | ۵۰۷۳ |

در Enum متن draft از۱۴۵۹ به۵۹۶۲ کاراکتر می‌رسد؛ این قیمتِ coverage ساختاری
است، نه اثبات خوانایی یا usefulness بهتر. shortlist lexical مستقل، در هر دو
snapshot دارای guide، دو بخش مکمل همان source را با۴۷۷۴ byte متن خام پیشنهاد
می‌کند. assertionهای span فقط پس از selection برای review خوانده می‌شوند؛
هیچ شرط Enum/source-ID یا gold در runtime نیست.

نقل نامرتبط در projection خودبه‌خود مرتبط نشده و همهٔ هفت decision ثابت‌اند.
مدل هیچ plan جدیدی انتخاب نکرد؛ نمی‌گوییم کیفیت یا نرخ موفقیت مدل افزایش یافته.
guide answer-linked همچنان فقط fixture کنترل‌شده و بیرون corpus واقعی است.

### حد ورودی و amendment

شمارش اولیهٔ ابزار replay فقط content را جمع می‌زد؛ این کار overhead و escaping
JSON را کم می‌شمرد. [مشاهدهٔ اول](../experiments/core_evidence_selection_v1/first-replay-v1.json)
و [amendment](../experiments/core_evidence_selection_v1/preflight-amendment-v1.json)
حفظ شده‌اند. V2 دقیقاً فرمول gateway، یعنی اندازهٔ UTF8ِ `json.dumps(messages,
ensure_ascii=False)` به‌اضافهٔ۱۰۲۴ را استفاده می‌کند؛ سقف۳۲۷۶۸ تغییر نکرد.

همهٔ۱۶ ورودی کامل بازسازی شدند. ۳۲ run تألیفی با engine واقعی، شامل۶۴ context
normal/repair/refinement و۱۶ feedback چهارتایی، داخل حدود موجود ماندند؛ بیشینهٔ
ورودی۲۷۳۶۶ byte است. نتیجهٔ escalation آن‌ها scripted است و کیفیت تصمیم مدل نیست.
کنترل quote-heavy نشان می‌دهد content-count ظاهراً زیر سقف می‌تواند با framing
واقعی بالاتر باشد؛ gateway پیش از reserve و transport آن را رد می‌کند.

## هزینه و اتصال تیم

[بررسی فقط‌خواندنی سه uncertain](../experiments/core_evidence_selection_v1/c5-readonly-report.fa.md)
با۳۶ کنترل، همان۷۱۸ reservation و۱۴ جدول و SHA ledger را حفظ کرد؛ settled محلی
`$0.599798760`، سه hold جمعاً`$0.030137600`، halt و سقف`$4.50` ثابت‌اند. HTTP200
مورد اول، duration مورد دوم یا connect_timeout مورد سوم مدرک هزینهٔ صفر نیست.
مبلغ/model/usage قطعی به رکورد provider نیاز دارد؛ C5 حل نشده است.

در این task هیچ API جدید، client واقعی Chroma یا تغییر corpus/index/exclusion،
case/gold/split، فایل‌های UI/tracker/RAG یا قراردادهای مشترک انجام نشد. متدهای
settle/release/unhalt فراخوانی نشدند؛ scopeها و شناسه‌های بسته همچنان بسته‌اند.

## بازتولید و قدم بعد

از root، یک مسیر خروجی **جدید** بدهید؛ receipt قبلی overwrite نمی‌شود:

```bash
uv run pytest tests/test_claim_sections.py tests/test_evidence_selection.py \
  tests/test_evidence_selection_replay.py
uv run python -m agent_app.testing.evidence_selection_replay \
  --output /tmp/evidence-selection-new.json
```

برای C5، script همراه به artifactهای خصوصی همان لپ‌تاپ نیاز دارد؛ portable بودن
ledger یا دستیابی به provider را فرض نکنید. اجرای دوبارهٔ read-only هم C5 را نمی‌بندد.

پیش از انتخاب تنظیم نهایی، review انسانیِ ارتباط و کامل‌بودن راهنمای کاربردی
روی خروجی‌های موجود لازم است. سپس با مدرک provider، تطبیق هزینه و protocol
تازه می‌توان دربارهٔ آزمایش بعدی تصمیم گرفت. این task به‌تنهایی E1/E4/E5،
T4 یا کیفیت RAG/final test را نمی‌بندد.
