# بازبینی PR #35 — fixture، mapper و index سه شاهد جدا هستند

PR اولیه فقط [`rag_acceptance_results.json`](../../../rag_acceptance_results.json)
را اضافه کرد. رسید اصلی بدون تغییر حفظ می‌شود: `reference_fixture_adapter`،
۱۳۲/۱۳۲، `actual_rag_accepted=false` و `git_dirty=true`. hashهای Python آن با
`56ff8ff` یکسان‌اند؛ این رسید، build یا adapter حسن را اجرا نکرده است.

دو build تازه روی source تمیز `e37a57a` همان snapshot ثبت‌شدهٔ pilot را ساختند:
۱۴ source و ۳۰ chunk، Chroma واقعی و vector lexical محلی. receipt mapper واقعی
با `chroma_binding` نیز ۱۳۲/۱۳۲ است؛ backend آن هنوز collection ثابت است و از
index تازه نمی‌خواند. replay جداگانهٔ زیر **همان indexهای ساخته‌شده** را می‌خواند،
فراخوانی مستقیم Chroma، hash بردار query، filter و metadata را کنترل می‌کند و آن‌ها را به HTTP/core/SQLite می‌برد.
[protocol و محدودیت‌ها](protocol-v1.json) تفکیک شواهد را ثبت می‌کند.

از root پروژه؛ هر مسیر destination و output باید تازه باشد. `runtime/` در Git
ignored است. روی Windows هم همین مسیرهای نسبی قابل استفاده‌اند:

```bash
uv sync --locked --group dev
uv run python scripts/build_pilot_index.py --destination runtime/rag-review-index-a --seed-root streamlit-data-for-dev-test --split-manifest data/evaluation/split-manifest.json --allowlist experiments/corpus/pilot-allowlist.json
uv run python scripts/build_pilot_index.py --destination runtime/rag-review-index-b --seed-root streamlit-data-for-dev-test --split-manifest data/evaluation/split-manifest.json --allowlist experiments/corpus/pilot-allowlist.json
uv run python scripts/rag_acceptance.py --factory agent_app.testing.chroma_binding:factory --check-candidate src/agent_app/retrieval/adapter.py --output runtime/rag-review-mapper.json
uv run python experiments/retrieval_acceptance/verify_pilot_index.py --index runtime/rag-review-index-a --rebuild-index runtime/rag-review-index-b --output runtime/rag-review-existing-index.json
uv run pytest tests/test_pilot_index_receipt.py tests/test_seed_checkout_bytes.py tests/test_offline_index.py tests/test_grounded_persistent_tcp.py tests/test_grounded_connected_ui.py
```

## metadata و exclusion

API recordها دقیقاً نسخه‌های 1.49.0، 1.50.0 و 1.64.0 را دارند. برای Markdown
نسخه حدس زده نمی‌شود. source commit، URL، pointer، hash و span خام حفظ شده‌اند؛
`EvidenceHit` فاصلهٔ ابتدا/انتهای متن را trim می‌کند. دو build manifest یکسان
دارند؛ یکسان بودن binary دیتابیس یا ranking ادعا نشده است.

این allowlist همهٔ Issueها، commentها و outcomeها را خارج می‌گذارد؛ خانوادهٔ
#12782/#12629 نیز از این مسیر وارد index نمی‌شود. split هنوز draft، یک dev و صفر
test است؛ نبودن لینک مستقیم Issue اثبات semantic duplicate review نیست. R1 نهایی،
R2 و R4 باز می‌مانند. policy مدل جعلی همان ask/escalate آفلاین است؛ receiptها
کیفیت تصمیم مدل یا retrieval نهایی را اندازه نمی‌گیرند.

## byteهای seed در checkout

یک checkout ایزوله با `core.autocrlf=true`، فایل واقعی JSONL را ۵۶ byte تغییر
داد و checksum را شکست. rule محدود `.gitattributes` اکنون فقط byteهای package
seed را ثابت نگه می‌دارد؛ تنظیم global Git و فایل‌های app تغییر نمی‌کنند.
این rule برای checkoutهای بعدی است؛ فایل محلی که قبلاً تغییر کرده خودکار repair
نمی‌شود. builder همچنان checksum خراب را رد می‌کند؛ دادهٔ محلی را بدون بررسی
و حفظ تغییرات خودتان جایگزین نکنید.

## رسیدهای این بازبینی

- [build روی e37a57a](build-review-e37a57a.json): دو invocation مستقل؛ manifest/snapshot یکسان.
- [mapper واقعی با backend ثابت](mapper-fixture-e37a57a.json): ۱۳۲/۱۳۲؛ index تازه را مصرف نمی‌کند.
- [index واقعی روی 82c39a9](actual-index-82c39a9.json): ۷۰/۷۰، ۲۸ query مستقیم Chroma شامل مسیر HTTP، چهار handoff کامل؛ به protocol ثبت‌شده bind است.
- [Git بدون byte policy](git-bytes-before.json): تغییر ۵۶ byte؛ سه regression تست اصلاح را کنترل می‌کنند.
- [verification](verification-82c39a9.json): ۲۲۹۸ pytest روی source تمیز؛ command، hash و محدودیت هر شاهد جدا ثبت‌اند.
