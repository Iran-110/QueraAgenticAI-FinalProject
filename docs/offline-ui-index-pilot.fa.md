# pilot محلی UI، core، SQLite و Chroma — U3a / P4a

این مسیر قابل اجراست: صفحهٔ Streamlit از client واقعی به backend پایدار وصل
می‌شود؛ retrieval از Chroma واقعی می‌آید و اقدام فقط در transaction tracker
موجود ثبت می‌شود. reasoning پیش‌فرض scripted است: نسخهٔ نامعلوم سؤال canonical
می‌گیرد؛ نسخهٔ معلوم برای بررسی مستندات ارجاع می‌گیرد. این policy عامدانه
تشخیص یا پاسخ نهایی تولید نمی‌کند و معیار کیفیت agent/RAG نیست.

کد و plan این milestone در [PR #32](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/32)
ثبت‌اند؛ وضعیت انتشار و CI همان PR مرجع است.

اتصال افزودهٔ [C2f](grounded-persistent-pilot.fa.md) همان backend را با
`AGENT_PILOT_REASONING=grounded_fake_gateway` از مسیر GroundedPlan/gateway جعلی
اجرا می‌کند. [smoke مرورگر](../experiments/grounded_http_acceptance/browser-receipt-89a0aec.json)
اولین approval، جواب نسخه و correction همان case را تأیید کرده است؛ product
auth و recovery کامل session همچنان جدا باقی‌اند. probe واقعی C2f جدا از این
launcher صفرهزینه ثبت شده و halt عمومی را برنمی‌دارد.

## اجرای قابل بازتولید

از root پروژه، با dependencyهای lockشده:

```bash
uv sync --locked --group dev
uv run python data_scripts/seed_profile.py
uv run python scripts/build_pilot_index.py --destination data/indexes/docs-pilot-v1
```

builder شبکه را مسدود می‌کند و مسیر موجود را overwrite نمی‌کند. اگر build
قبلی شکست خورد، علت را بررسی و مقصد تازه انتخاب کنید. stdout فقط اطلاعات
عمومی index را می‌دهد. `snapshot_id` همان build را در config وارد کنید؛ backend
بدون pin مستقل snapshot باز نمی‌شود. این pin با تغییر split/seed/config عوض می‌شود.

در ترمینال backend (نمونهٔ `read` برای zsh؛ token خصوصی ۳۲ تا ۵۱۲ کاراکتر
ASCII مجاز، بدون فاصله، از تنظیم مورد اعتماد maintainer بیاید):

```bash
read -rs "AGENT_REVIEWER_TOKEN?Private reviewer token: "
export AGENT_REVIEWER_TOKEN
export AGENT_TRACKER_DB="$PWD/runtime/pilot.sqlite3"
export AGENT_PILOT_INDEX="$PWD/data/indexes/docs-pilot-v1"
export AGENT_PILOT_SNAPSHOT="docs-pilot-87bdaf9a3dadcefff48a6775ef616f3d3dd5bf1c8cb23a9521b0e11ccaae160c"
uv run uvicorn agent_app.offline_backend:application_factory --factory --host 127.0.0.1 --port 8000
```

در ترمینال UI، همان token را بدون چاپ دوباره وارد کنید:

```bash
read -rs "AGENT_REVIEWER_TOKEN?Private reviewer token: "
export AGENT_REVIEWER_TOKEN
export AGENT_API_URL="http://127.0.0.1:8000"
uv run streamlit run app.py --server.address 127.0.0.1
```

برای pilot صرفاً scripted، هر دو متغیر `AGENT_PILOT_INDEX` و
`AGENT_PILOT_SNAPSHOT` را unset کنید؛ SQLite و قرارداد review همان است.
هیچ‌کدام از این factoryها `.env` یا کلید مدل را نمی‌خوانند. token در payload،
session_state، receipt یا log نمی‌رود. این UI یک **کنسول خصوصی maintainer محلی**
است؛ credential سمت سرور، احراز هویت کاربران مرورگر یا سرویس چندکاربره نیست.

## چه چیزی از داده وارد index می‌شود؟

[allowlist ثبت‌شده](../experiments/corpus/pilot-allowlist.json) فقط پنج صفحهٔ
Session State/widget و نه API record در نسخه‌های 1.49.0، 1.50.0 و 1.64.0 دارد:
**۱۴ source، ۳۰ chunk**. همهٔ Issueها، commentها، release notes و داده‌های
evaluation/fixture کنار گذاشته می‌شوند؛ این سیاست کوچک، جای exclusion نهایی
خانواده‌های dev/test را نمی‌گیرد. حتی release notes حاوی لینک به caseهای exposed
اجازهٔ ورود ندارند. split همچنان `draft_not_frozen` با یک dev و صفر test است.

هر chunk متن خام، hash، commit، مسیر/JSON pointer و span با واحد Unicode
codepoint دارد؛ اتصال همهٔ spanها متن seed را کامل بازسازی می‌کند. recordهای
API هم‌متن در نسخه‌های مختلف هویت مستقل دارند. Markdown نسخهٔ قطعی ادعا
نمی‌کند. متن خام index lossless است؛ قرارداد موجود `EvidenceHit.excerpt`
فاصله‌های ابتدا/انتهای span را trim می‌کند (۱۴ از ۳۰ chunk)، بدون clipping
متن داخلی. hash/span متن خام با excerpt نرمال‌شده اشتباه گرفته نشود.

[profile داده](../experiments/corpus/seed-profile.json) ۱۴ فایل package، hashها،
grain، joinها و metadata را بررسی می‌کند؛ صحت معنایی استخراج یا متن اصل
GitHub را از روی hash محلی اثبات نمی‌کند. ۳۴ ارتباط candidate، duplicate قطعی
نیستند. متادیتای updated_at هم اثبات ویرایش body نیست. مجوز docs همراه
[LICENSE منبع](../experiments/corpus/LICENSE.streamlit-docs) حفظ شده؛ این مجوز
به Issue/commentها تعمیم داده نشده است.

embedding در این pilot، `lexical_hash_v1` محلی با ۲۵۶ بُعد است؛ semantic model
یا کیفیت embedding ادعا نمی‌کنیم. در Chroma صریحاً `embedding_function=None`
و vectorهای محلی استفاده می‌شوند؛ query نیز `query_embeddings` می‌فرستد.
[قرارداد رسمی Chroma](https://docs.trychroma.com/docs/embeddings/embedding-functions)
این مسیر را پشتیبانی می‌کند؛ حذف config embedding ممکن است default model را
فعال کند، پس constructor معمولی و ingestion قدیمی جای این builder نیستند.

verified client قبل و بعد از read، membership، متن، metadata، vector و config
را کنترل می‌کند؛ خودِ rowهای نتیجه هم باید عضو manifest و دقیقاً برابر باشند.
تغییر محتوا زیر همان snapshot یا تغییر موقت هنگام query و بازگرداندن آن،
پذیرفته نمی‌شود. این facade برای Chroma transaction بین processها نمی‌سازد؛
index pilot را در مسیر جدا و بدون writer هم‌زمان نگه دارید.

## review و recovery

UI ابتدا handoff را با validator موجود اعتبارسنجی می‌کند؛ draft، sourceها،
version scope و دیگر فیلدهای نمایشی باید با همان handoff برابر باشند. سپس
operation تغییرناپذیر با case، revision، proposal، hash، decision و review_id
ساخته و **قبل از POST** ذخیره می‌شود. Bearer از client خصوصی session می‌آید.
backend ناشناخته یا تغییر protocol به demo، مجوز fallback بدون auth نیست.

timeout، 503 حتی با JSON، پاسخ 200 خراب یا ACK گمشده، همان operation را نگه
می‌دارند. correction یا رفتن به case دیگر ID/body آن را عوض نمی‌کند؛ retry
receipt اصلی و state فعلی را می‌گیرد. در فاصلهٔ ACK نامعلوم، review تازه بسته
است، ولی کاربر می‌تواند update بفرستد. edit proposal تازه و approval جدا دارد.
outcome ثبت‌نشده می‌تواند اجرای در جریان یا interrupted باشد؛ retry مدل را
خودکار resume نمی‌کند.

operationهای ارسال‌نشده فقط در session UI هستند؛ بسته‌شدن کامل session مرورگر
آن‌ها را پایدار نمی‌کند. DB تاریخچهٔ review موفق را نگه می‌دارد؛ برای سناریوی
cross-browser recovery به flow محصول جدا نیاز داریم. کنسول maintainer فعلی
عمداً browser authentication یا outbox پایدار دوم نمی‌سازد.

## شواهد عملیاتی و محدودیت‌ها

[protocol UI](../experiments/ui_review_acceptance/protocol-v1.json) پیش از اجرا
ثبت شد. client/API قبلی از `6e719e9` بارگذاری می‌شوند؛ روی همان ورودی و fault،
baseline **۲/۶** و نسخهٔ اصلاح‌شده **۶/۶** است. baseline ورودی و correction را
ثبت می‌کرد، اما envelope approval پایدار را نداشت؛ این نسبت نمرهٔ کیفیت نیست.

[receipt baseline](../experiments/ui_review_acceptance/results-baseline-c14314f.json)،
[receipt نسخهٔ جدید](../experiments/ui_review_acceptance/results-current-c14314f.json)،
[receipt index واقعی](../experiments/corpus/local-index-c14314f.json) و
[تأیید اجرا روی checkout تمیز `c14314f`](../experiments/ui_review_acceptance/verification-c14314f.json)
همراه hash کد، fixture و protocol ثبت‌اند. ۲۲۱۸ pytest، Ruff و سه demo پاس‌اند؛
کنترل‌های HTTP/SQLite، core/tracker و adapter ثابت به‌ترتیب ۴۵۷، ۴۹ و ۱۳۲ هستند.

```bash
uv run python scripts/ui_review_acceptance.py --baseline --output /tmp/ui-baseline-new.json
uv run python scripts/ui_review_acceptance.py --output /tmp/ui-current-new.json
uv run pytest tests/test_ui_persistent.py tests/test_indexed_backend.py tests/test_persistent_tcp.py
```

runner UI از ASGI و backend recreation در همان interpreter استفاده می‌کند؛
تست مستقل TCP دو interpreter تازه، index واقعی و همان DB را به client واقعی
وصل می‌کند. AppTest اجرای واقعی صفحه، case switching و lost ACK را بررسی
می‌کند؛ screenshot یا claim مرورگر واقعی نیست. protocol HTTP v2 مستقل هنوز
restart پنج‌مرحله‌ای را کنترل می‌کند. case #12782/#12629 exposed و answer-informed
بوده؛ follow-upها authored هستند و هیچ‌کدام held-out test نیستند.

باقی‌ماندهٔ تیم: E1/E2 split و rubric؛ R2 corpus/exclusion نهایی؛ R4 relevance و
پوشش dev؛ C4 کیفیت تصمیم مدل و E4/E5 ارزیابی واقعی. C5 همچنان halted است؛ هیچ
ledger، reservation، کلید `.env` یا provider را برای دور زدن توقف دست نزده‌ایم.
هزینهٔ API این مسیر صفر است. تک agent و همان tracker باقی مانده‌اند.
