**تکمیل پس از PR91:** rebuild نهاییِ exclusion۹۵ نیز مستقلاً روی همین سیستم ساخته شد؛ هر پنج pin، counts و exclusion با receipt v3 حسن برابرند. ۱۲۲۸منبع/۱۸۲۷chunk، deterministic rebuild، snapshotهای تاریخی و دو سرچ خنثی adapter پاس‌اند. [رسید پذیرش v3](receipts/final-build-v3-core-acceptance-2026-10-17.json). متن قالبی «پیش از freeze» در limitation خروجی builder قدیمی مانده؛ ورودی واقعی این اجرا frozen95 است و byteهای رسید اصلی تغییر نکرده‌اند. مطالب C4u پایین شاهد تاریخیِ build90 و پذیرش core با provider mock هستند؛ پذیرش تازه v3 کیفیت مدل یا اجرای packet نهایی نیست. اکنون native gold و packet/config نسخه‌دار با محمدحسن است؛ feature مستقل ضروری تازه‌ای سمت core باقی نمانده.

# پذیرش build گسترده و اتصال profile نسخه‌دار — C4u

build حسن در PR85 و prefilter در PR86 قبل از این مرحله روی main بودند.
در این مرحله، آن‌ها مستقل review شدند؛ build روی همین دستگاه بازتولید شد و
اتصال opt-in فیلتر نسخه به factory، API/service و runner موجود انجام شد.
[رسید](receipts/final-build-core-acceptance-2026-10-17.json) source و مرز هر شاهد
را ثبت می‌کند. مدل، prompt، vocabulary، renderer و حدود بودجه عوض نشده‌اند.

## ۱. چه چیزی واقعاً بازتولید شد؟

پروتکل بستهٔ `docs-api-release-final-v1` روی مقصد تازه و آفلاین ساخته شد:

| نوع منبع | source | chunk |
| --- | ---: | ---: |
| docs محصول | ۴۷ | ۷۴ |
| release note | ۹ | ۱۰۴ |
| API/docstring نسخه‌دار | ۱۱۷۲ | ۱۶۴۹ |
| جمع | ۱۲۲۸ | ۱۸۲۷ |

snapshot، SHA خام manifest فیزیکی، allowlist و exclusion با رسید v2 حسن
دقیقاً برابر بودند. این تطبیقِ pinهاست؛ byteهای SQLite/HNSW روی دو سیستم‌عامل
یکسان اعلام نمی‌شوند. rebuild منطقی deterministic بود؛ snapshot تاریخی هر
دو پروفایل ۱۴/۱۸ منبعی هم ثابت ماند. guide آزمایشی answer-linked Enum و
Issue/comment در index نیستند؛ metadata نسخه از متن release note استنباط نمی‌شود.

این build **پیش از freeze و با exclusion تاریخی ۹۰ Issue** است. freeze جدید
PR89، exclusion را به ۹۵ رسانده است؛ برای اجرای نهایی باید Hassan بعد از آن
rebuild با رسید تازه انجام دهد. همان pinهای قدیمی را دوباره نهایی ننامیم.

دو سرچ خنثی محلی ۰٫۳۵۶ و۰٫۳۳۱ ثانیه بودند. این‌ها baseline هم‌دستگاه ندارند؛
بهبود ۴–۵ ثانیه به نیم ثانیه، مشاهدهٔ نویسنده در Windows است. review کد و
تست‌های mutation تأیید می‌کنند cache فقط expected vector را نگه می‌دارد؛ هر
search یک verification کامل قبل و بعد دارد و row برگشتی جدا بررسی می‌شود.
این رفتار transaction بین‌پردازشی یا تضمین relevance نیست.

## ۲. اتصال فیلتر نسخه به اجرای واقعی

پروفایل تازهٔ اختیاری:

```text
AGENT_CORE_PROFILE=grounded_candidate_prefilter_v2
```

[recipe تازه](../config/core-delivery-grounded-prefilter-v2.json) از
`candidate_version_prefilter_v1` استفاده می‌کند: همان candidate۲۵، final۵ و
۱۲۰۰۰بایت با exact USER-version scope، به‌علاوهٔ
`retrieval_version_prefilter=True` قبل از native top-k.
legacy renderer و تمام تنظیم‌های مدل/catalog ثابت‌اند.

`grounded_candidate_v1`، فایل و SHA آن و defaultهای قبلی عیناً حفظ‌اند؛ profile
تازه باید صریحاً انتخاب شود. recipe و binding hash جدا دارند؛ جفت ناسازگارِ
core/retrieval profile، constructor ناسازگار یا metadata دست‌کاری‌شده رد می‌شود.
factory واقعی relevance و پنجرهٔ۲۵ را می‌سازد و descriptor هم همان engine flag
را ثبت می‌کند. انتخاب profile مجوز live یا pin نهایی code/model/config نیست.
یادداشت pendingِ PR89 هنوز v1 را نام می‌برد؛ اجرای نهایی با v2 به ثبت نسخه‌دار
و review مالک evaluation در packet تازه نیاز دارد، نه بازنویسی freeze قبلی.

یک regression مستقل هم رفع شد: Fact نسخهٔ مجاز می‌توانست پس از JSON encoding
از حد filter عبور کند و قبل از retrieval متوقف شود. اکنون فقط optimization
prefilter در آن حالت کنار می‌رود؛ مقدار USER بریده/نرمال نمی‌شود و post-scope
همچنان مرجع اعتبار است. رفتار query نامعتبر یا نسخهٔ canonical شل نشده است.
فیلتر native برای protocolهای ثبت‌شده با applicability تک‌نسخه‌ای طراحی شده؛
آن را تضمین عمومی برای metadata چندنسخه‌ایِ دلخواه معرفی نکنیم.

## ۳. کدام پذیرش عملی پاس شد؟

[دو کنترل واقعی](../tests/test_final_core_profile_http.py) روی build۱۲۲۸منبعیِ
موقت و کپی‌های disposable اجرا می‌شوند. مسیر configured factory، native Chroma،
API/service، SQLite و conditional runner واقعی است؛ provider با MockTransport
جایگزین شده است. ورودی‌ها ساختگی‌اند و از gold dev/test انتخاب نشده‌اند.

- USER نامعلوم، سپس1.50.0 و correction به1.49.0: filter درخواست و where واقعی
  native query، پنجره۲۵، post-scope و evidence مصرف‌شده در mock provider ثبت شدند.
- factory و native client واقعاً به کپی disposable اشاره کردند؛ snapshot و SHA
  manifest معتبر بودند. legacy handoff و binding v2 در observation/runner ماندند.
- approval قدیمی با409 رد شد؛ approval معتبر، بازسازی backend/SQLite و retry
  همان operation فقط یک Action داشت. این بازسازی app در همان interpreter است؛
  restart پردازش/مرورگر تازه در این کنترل ادعا نمی‌شود.
- full conditional runner در phase evaluation سه turn را اجرا کرد؛ engine flag،
  metadata و هزینهٔ ledger موقت با mock usage منطبق بودند. tracker این runner از نوع
  `process_memory_dummy_tracker` است؛ پذیرش SQLite به تست API جدا تعلق دارد.

۹۲۲ تست مرتبط در۲۹فایل روی source `8800786` پاس شدند؛ Ruff/format۴۰۷فایل نیز
پاس‌اند. ۹۶ کنترل تازه در همین مجموعه هستند؛ شمارش‌های author/peer هم‌پوشان‌اند.
این full-suite تازه یا held-out model evaluation نیست. guard parent در اجرای
موفق صفر protected/.env/primaryDB/network ثبت کرد؛ attestation همهٔ subprocessها
یا عملیات داخلی native نیست. دو تلاش اولیهٔ build/replay از CWD مخزن به‌علت
dotenv خودکار dependency با guard متوقف شدند؛ logها حفظ و اجرای موفق از CWD
خنثی انجام شد. bytes بستهٔ seed فقط برای hash custody خوانده شد؛ متن Issue/comment
parse یا وارد query/provider نشد.

## ۴. نتیجهٔ retrieval را درست بخوانیم

بازپخش آفلاین مستقل، نتیجهٔ حسن را روی index واقعی بازتولید کرد: از۱۹requirement،
۱۶مورد با scope سازگارند؛ در۱۶turn از۱۴case آشکار dev، حضور در candidateها
۵→۱۰ و حضور در bundle نهایی۲→۴ است. ورودی دو arm یکسان بود و index اصلی ثابت
ماند. gold و passage فقط در scorer بودند، نه query یا ranking.

نام تاریخی `reached_model` در این benchmark یعنی متن داخل bundle نهاییِ آمادهٔ
reasoning؛ benchmark اصلاً reasoner/model را فراخوانی نمی‌کند. پاسخ مفید،
support معنایی، refinement دور بعد یا کیفیت held-out از آن نتیجه نمی‌شود.
۱۲ requirement سازگار در bundle دور اول مشاهده نشدند؛ این به‌تنهایی برچسب
«ارجاع درست» یا «پرونده غیرقابل پاسخ» نمی‌سازد. کیفیت Enum همچنان باز است.

## ۵. custody و کار باقی‌مانده

PR87، تأیید انسانیِ assistant-informed دو اصلاح dev را ثبت کرده است؛ آن را
داوری تازهٔ کیفیت مدل معرفی نمی‌کنیم. PR88 فقط از نظر مسیر/mode/blobهای Git و
تغییرهای عمومیِ مجاز پذیرفته شد؛ فایل تصمیم held-out باز/parse/hash خام نشد.
PR89 نیز ثبت freeze منابع/metadata است: exposure payload opaque ماند و چهار
تست مصرف‌کنندهٔ آن با مالک evaluation هستند. این review، محتوای آن تصمیم یا
نمرهٔ gold/test را تأیید نمی‌کند. دو کنترل مجاز rubric/split جدا بررسی شدند.

فرمان rebuild در README اکنون receipt تازهٔ v3 می‌خواهد؛ overwrite guard حفظ
است. نسخهٔ جایگزین‌شدهٔ `rag_acceptance_results.json` در مسیر versionedِ PR85
آرشیو و byteهای تاریخی root برگردانده شد. آن فایل همچنان reference-fixture و
`actual_rag_accepted=false` است؛ رسید build واقعی نیست. CRLF تاریخی حفظ شد.

کار بعدی حسن rebuild با exclusion۹۵ و pinهای تازه است؛ محمدحسن native gold و
packet نهایی و انتخاب versioned تنظیم v2 را ثبت می‌کند. بعد از تحویل، core
binding و پذیرش فیزیکی همان build تازه را تأیید می‌کند. C5/سه درخواست نامعلوم،
halt، تمام scopeهای بسته و review انسانی کیفیت باقی‌اند؛ paid API صفر است.
برای تحویل فعلی feature مستقل تازه‌ای سمت core لازم نیست.

بازتولید نرم‌افزاری بدون خواندن dotenv از CWD پروژه:

```bash
project_dir="/Users/sasan/Desktop/Agentic AI/FinalProject/QueraAgenticAI-FinalProject"
cd /tmp
"$project_dir/.venv/bin/python" -m pytest "$project_dir/tests/test_final_core_profile_http.py" -c "$project_dir/pyproject.toml" -q
```

این تست build موقتِ ثبت‌شدهٔ pre-freeze را می‌سازد؛ جای تطبیق pin فیزیکی
rebuild۹۵ یا مجوز اجرای paid را نمی‌گیرد.
