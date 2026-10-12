# پذیرش آفلاین adapter واقعی — R3 / C2b

در ۲۰۲۶-۱۰-۱۲ چهار فایل حسن در head `b571080` #23 برگشتند. پذیرش ثابت روی آن
کد هنوز رد شد. با اجازهٔ ساسان، اصلاح اتصال روی branch جدا
`fix/rag-core-acceptance` انجام شد؛ branch اصلی حسن و receiptهای قبلی حفظ شدند.
core/contract مشترک و ساختار تک agent تغییر نکردند.

## رفتار اصلاح‌شده

- import فقط از `agent_app` است؛ خروجی همان کلاس‌های قرارداد core را دارد.
- canonical chunk/source ID، URL، commit، span، source_type، نسخه و scoreهای
  صریح منتقل می‌شوند؛ unknown نامعلوم می‌ماند. fallback ID قدیمی مثل
  `doc:<native_id>` همچنان پایدار است. source URL یا span از عنوان ساخته نمی‌شود.
- excerpt معتبر ۲۰۰۰۰ کاراکتری کامل می‌ماند؛ ۲۰۰۰۱ یا metadata نامعتبر، خطاست.
  duplicate یکسان حذف می‌شود؛ محتوای متناقض زیر یک chunk ID خطاست.
- snapshot تنظیم‌شده با درخواست مقایسه می‌شود. هر دو collection موجود، در
  constructor، پیش از read و پس از read، metadata snapshot سازگار لازم دارند.
- filter صریح به collectionها می‌رسد؛ top_k سقف کلی خروجی است. خطای backend
  به تشخیص ثابت تبدیل می‌شود و جزئیات خصوصی آن بیرون نمی‌رود.

mapper canonical ID را از metadata می‌گیرد و آن را با storage ID یکی فرض
نمی‌کند. prefix قدیمی حسن ذاتاً نقص نبود؛ اما fixture ثابت canonical ID جدا دارد.
این تفاوت اکنون در backend seam روشن است، بدون تغییر IDهای fixture یا اصلاح
Bundle بیرون adapter.

## مقایسهٔ قابل بازتولید

اجرای تمیز source commit `326480d305cf8a837087bfc23a3e100a049a27a2` ثبت شده است.
fixture همان SHA
`de36c80081af1f6ec9e1e420523a1df51ddbc72a6fc59550a409e734c554f470` را دارد؛
پنج excerpt و اطلاعات/تصمیم‌های از قبل ثبت‌شدهٔ سناریوها تغییر نکردند.

| کد و حالت | caseهای پاس | checkهای پاس / اجراشده | نتیجه |
|---|---:|---:|---|
| [b571080 با import اصلی](../experiments/retrieval_acceptance/baseline-b571080-current-kit.json) | ۴/۱۴ | ۱۰/۲۸ | اتصال رد؛ توقف زودهنگام namespace |
| [b571080 با alias فقط برای تشخیص](../experiments/retrieval_acceptance/diagnostic-b571080-current-kit.json) | ۴/۱۴ | ۷۴/۸۵ | provenance، boundary و snapshot نیز رد شدند |
| [adapter اصلاح‌شده، بدون alias](../experiments/retrieval_acceptance/results-fixed-326480d.json) | ۱۴/۱۴ | ۱۳۲/۱۳۲ | پذیرش قرارداد با backend ثابت |

مخرج کوچک baseline ناشی از توقف زودهنگام است؛ درصدها نمرهٔ کیفیت نیستند.
بعضی stopهای baseline به‌علت namespace پاس می‌شوند و کنترل درست snapshot یا
oversize را اثبات نمی‌کنند. alias تشخیصی، نقص import را می‌پوشاند؛ آن اجرا
شاهد پذیرش نیست. شکست pilot قدیمی به‌تنهایی نشان‌دهندهٔ ایراد correction نیست.

همان kit برای baseline و نسخهٔ اصلاح‌شده استفاده شد. یک خطای observation آن
اصلاح شد: `calls[-2:]` دو query را با دو read فیزیکی یکی می‌گرفت. اکنون queryهای
round جاری سنجیده می‌شوند؛ سقف منطقی query/round/attempt دست‌نخورده است. mutation
مستقل چند read را می‌پذیرد و حذف query، echo جعلی یا read در round قبلی را رد
می‌کند. شرح کامل این اصلاح در [راهنمای پذیرش](rag-core-acceptance.fa.md) ثبت است.

اجرای جدید، هر دو constructor و search/mapper واقعی را با native collection
ثابت اجرا می‌کند. چهارنوبت از `CoreTurnService` و SQLite واقعی می‌گذرد:
سؤال نسخه، پاسخ کاربر، correction و refinement، edit/approval و withdrawal/reject؛
evidence قدیمی از آخرین handoff حذف شده و retry پس از restart اقدام تکراری ندارد.
reasoner اسکریپتی است؛ ۵ retrieval و ۵ reasoning call ثبت شده‌اند.

۱۸۹۱ تست کامل، ۹۵ تست مرتبط، locked sync، Ruff و سه demo الزامی پاس شدند.
regression مستقل `core_tracker_pilot.py` نیز ۴۹/۴۹ check پاس کرد.
CI اکنون factory واقعی RAG و smoke را جدا از fixture مرجع اجرا می‌کند.

## اجرا

از ریشهٔ repository، با output تازه:

```bash
uv sync --locked --group dev
uv run python -m agent_app.retrieval.adapter --smoke
uv run python scripts/rag_acceptance.py \
  --factory agent_app.testing.chroma_binding:factory \
  --check-candidate src/agent_app/retrieval/adapter.py \
  --output /tmp/rag-fixed-new.json
uv run python experiments/retrieval_acceptance/replay_b571080.py \
  --output /tmp/rag-baseline-new.json
```

baseline از Git blobهای pinned استفاده می‌کند؛ کل repo reset نمی‌شود. دستور
baseline وقتی رد شدن قدیمی را بازتولید کند exit صفر دارد؛ receipt صریحاً
`accepted=false` است. گزینهٔ `--namespace-diagnostic` فقط اجرای تشخیصی جداست.

## حدود نتیجه و قدم باقی‌مانده

این خانوادهٔ #12782/#12629 از ابتدا exposed dev و answer-informed بود؛ ادامهٔ
گفتگو تألیفی است. نتیجه کیفیت RAG واقعی، مدل، حل Issue یا موفقیت test نهایی نیست.
آزمایش index/embedding/مدل دانلود نکرد، `.env` یا ledger اصلی را نخواند و هزینهٔ
API صفر بود. SQLite آزمایش موقت است؛ API/UI همچنان اتصال مستقل لازم دارند.

snapshot metadata، محتوا را immutable نمی‌کند؛ تغییر محتوا با همان ID هنوز به
manifest/hash و مدیریت index ثابت وابسته است. client پیش‌فرض ممکن است storage
را باز/ایجاد کند، ولی collection یا index خودکار ساخته نمی‌شود و smoke این
مسیر را اجرا نمی‌کند. `index_data` prototype تا builder با corpus مجاز خطا می‌دهد.
چانک‌سازی واقعی، provenance از seed، exclusion خانواده‌ها/جواب‌ها، index و
relevance/latency همچنان R1/R2/R4 و قسمت واقعی P4 هستند. قبل از live نیز C5 باز است.
