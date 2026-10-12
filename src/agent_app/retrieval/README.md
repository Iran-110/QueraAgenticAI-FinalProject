# اتصال RAG به core

`ChromaRetrieverAdapter` درخواست `RetrievalRequest` را می‌گیرد و
`EvidenceBundle` می‌سازد. مسیر پذیرش آفلاین، search و تبدیل hitهای همین adapter
را با collectionهای ثابت بررسی می‌کند. این مسیر index یا embedding واقعی
نمی‌سازد و کیفیت بازیابی، تصمیم مدل یا test نهایی را اندازه نمی‌گیرد.

## نصب و اجرای آفلاین

از ریشهٔ repository اجرا کنید. ChromaDB در `pyproject.toml` و `uv.lock` ثبت
شده؛ برای اجرای این نسخه نیازی به `uv add` نیست.

```bash
uv sync --locked --group dev
uv run python -m agent_app.retrieval.adapter --smoke
```

`--smoke`، client ثابت را به `StreamlitRetriever` تزریق می‌کند و mapper واقعی
adapter را اجرا می‌کند. pilot چندنوبتی هم با reasoner اسکریپتی و SQLite موقت
اجرا می‌شود. این دستور `.env` را نمی‌خواند، collection واقعی ایجاد نمی‌کند و
دانلود مدل، درخواست شبکه یا API پولی ندارد.

برای receipt قابل بازبینی از همان fixture و معیارهای پذیرش core استفاده کنید:

```bash
uv run python scripts/rag_acceptance.py \
  --factory agent_app.testing.chroma_binding:factory \
  --check-candidate src/agent_app/retrieval/adapter.py \
  --output /tmp/rag-chroma-acceptance-new.json
```

مسیر خروجی باید تازه باشد؛ receipt قبلی overwrite نمی‌شود. binding فقط rowهای
backend ثابت را به شکل native Chroma درمی‌آورد؛ خروجی `EvidenceBundle` را خود
adapter می‌سازد. ورودی و محدودیت‌های این آزمایش در
[راهنمای پذیرش](../../../docs/rag-core-acceptance.fa.md) ثبت شده‌اند.

## قرارداد اتصال

شناسهٔ snapshot باید از تنظیم backend بیاید؛ کپی کردن شناسهٔ درخواست در پاسخ
به‌تنهایی کنترل freshness نیست:

```python
adapter = ChromaRetrieverAdapter(
    base_path="streamlit-data-for-dev-test",
    snapshot_id="configured-corpus-snapshot",
    core_retriever=reviewed_retriever,
)
```

`core_retriever` برای تزریق backend بررسی‌شده است. `StreamlitRetriever` نیز
`snapshot_id` و `client` تزریقی می‌گیرد. در مسیر Chroma واقعی، collectionهای
موجود باید metadata مربوط به همان snapshot را داشته باشند؛ collection غایب،
snapshot نامعلوم یا ناسازگار باید retrieval را متوقف کند. پذیرش fixture مجوز
استفاده از corpus موجود و بررسی‌نشده نیست.

این guard metadata را دوباره می‌خواند؛ تغییر محتوا زیر همان شناسه را اثبات
نمی‌کند. snapshot نهایی باید manifest/hash و index ثابت داشته باشد. مسیر پیش‌فرض
`PersistentClient` برای index موجود است و ممکن است storage دیتابیس را باز/ایجاد
کند؛ smoke از client تزریقی استفاده می‌کند و این مسیر را اجرا نمی‌کند.

برای هر hit، متن و metadata باید بدون حدس‌زدن منتقل شوند: ID پایدار chunk و
source، URL، span، commit و نسخه‌های قابل اعمال. binding این شناسه‌ها را در
metadata native collection نگه می‌دارد؛ fallback شناسهٔ قدیمی، قرارداد legacy
مانند `doc:<native_id>` است. نتیجهٔ چند query باید dedup شود و سقف کلی `top_k`
را رعایت کند. excerpt معتبر تا ۲۰۰۰۰ کاراکتر کامل حفظ می‌شود؛ ورودی بزرگ‌تر
یا metadata نامعتبر، خطاست و نباید با clipping یا منبع ساختگی پنهان شود.

## وضعیت ingestion و corpus

داده‌های `streamlit-data-for-dev-test` هنوز seed هستند. فهرست
`development_exposure.json` فقط exposureهای شناخته‌شده را ثبت می‌کند؛ جای split
و exclusion نهایی را نمی‌گیرد. استخراج loader و chunker موجود، prototype است
و `index_data` تا تأیید corpus برای استفادهٔ نهایی بسته می‌ماند.

اجرای مستقیم `retriever.py` دستور ساخت index نیست. دستور ساخت index نهایی
باید بعد از freeze داده‌ها، همراه manifest و راه بازسازی، جدا تحویل داده شود.
ساخت collection یا embedding از تمام seed، بخشی از دستورهای آفلاین بالا نیست.

کارهای باز سمت RAG:

- **R1:** حفظ provenance از seed تا chunk؛ commit، hash، مسیر/JSON pointer و
  span قابل بررسی، به‌همراه segmentation متن‌های بلند و نسخه‌های منابع.
- **R2:** freeze خانواده‌های dev/test با مسئول evaluation، بررسی Issueها،
  commentها، duplicateها و بندهای پاسخ‌دهندهٔ docs؛ ساخت allowlist و exclusion
  manifest قبل از index نهایی. rebuild باید evidence قدیمی را کنار بگذارد.
- **R4:** سنجش relevance، هزینه و زمان روی index و retrieval واقعی؛ ledger و
  haltهای موجود پیش از هر اجرای پولی بررسی شوند.

وضعیت taskها در [plan](../../../plan/plan.md) نگه‌داری می‌شود. قبولی adapter در
این آزمایش، پذیرش قرارداد اتصال است؛ به معنی بسته‌شدن کارهای بالا نیست.
