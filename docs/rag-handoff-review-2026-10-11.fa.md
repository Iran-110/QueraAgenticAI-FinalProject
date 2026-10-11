# بازبینی تحویل RAG — ۱۱ اکتبر ۲۰۲۶

core در انتشار `37ce74a` برای اتصال آفلاین آماده است: CI انتشار
[موفق است](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38157117534)،
۱۷۹۶ تست و pilot چهار‌نوبتی با ۴۹ check عملیاتی پاس‌اند. بازبینی محدود تازه
ایراد قابل بازتولید دیگری در سهم مستقل core پیدا نکرد. این شواهد، کیفیت مدل،
retrieval واقعی یا test مستقل را اندازه نمی‌گیرند.

حسن backend اولیهٔ Chroma را در
[PR #23](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/23)
با head ثابت `c0d450a57769b4513b6b99f2e75ed506c483363d` تحویل داده.
این بازبینی فقط همین head را توصیف می‌کند؛ commit جدید باید دوباره بررسی شود.
branch از `94b60e1` شروع شده و انتشار #22 را هنوز ندارد.

[probe قابل بازپخش و receiptها](../experiments/retrieval_handoff/README.md)
با hash سورس و seed ثبت شده‌اند. دو script مستقل فقط port با collection ساختگی
و loader/chunker را بررسی می‌کنند؛ متن داده‌ها به‌عنوان کد اجرا نمی‌شود.

## نتیجهٔ بررسی همین head

| بررسی | چیزی که دیدیم | شرط تحویل بعدی |
| --- | --- | --- |
| CI | push و PR در Ruff با ۳۱ finding متوقف شدند؛ [CI همان head](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38157755729) | sync با main، lint/format، تست‌های offline و دستور اجرا |
| port | `search(query: str, n_results=3)` خروجی خام `docs/issues` می‌دهد. core شیء `RetrievalRequest` فرستاد؛ با collection ساختگی، نتیجه `RetrievalResultInvalid` و صفر فراخوانی مدل بود | `search(RetrievalRequest) -> EvidenceBundle`؛ این probe اجرای Chroma واقعی نیست |
| بودجهٔ retrieval | `n_results=3` مستقل برای هر collection است؛ `top_k` درخواست و چند query پردازش نمی‌شوند | dedup و حداکثر `top_k` برای مجموع همهٔ queryها و collectionها |
| provenance | seed دارای `docs_commit` و `file` یا `json_pointer` است؛ chunker فعلی commit/location را نگه نمی‌دارد | ID ثابت، URL قابل بررسی، excerpt و locator دقیق؛ metadata موجود حفظ شود |
| اندازهٔ excerpt | پنج Markdown تولیدشده از سقف ۲۰هزار کاراکتر `EvidenceHit` بزرگ‌ترند؛ بیشینه ۱۱۱۲۵۲ است | ingestion آن‌ها را با span و ID پایدار تقسیم کند؛ core متن را مخفیانه قطع نکند |
| انتخاب Issue | exposure filter چهار Issue موجود را حذف می‌کند و ۲۳۶ از ۲۴۰ می‌ماند؛ #12629 در seed نیست | این filter جای manifest خانواده‌ها و corpus مجاز را نمی‌گیرد؛ R2 باز است |
| commentها | ۹۸۴ comment غیر bot به Issueهای باقی‌مانده متصل‌اند؛ indexer فقط title/body را مصرف می‌کند | انتخاب عمدی منابع مستند شود؛ اگر comment لازم است، chunk مستقل با URL/ID و نقش منبع داشته باشد |

حذف خانوادهٔ شناخته‌شدهٔ #12782/#12629 در Issueهای همین seed رعایت شده؛
از این نتیجه نمی‌توان exclusion کامل همهٔ خانواده‌های ارزیابی را نتیجه گرفت.
یک اشاره به Issue exposed شمارهٔ #8901 در release notes هم candidate بررسی
داده است؛ صرف ارجاع، اثبات duplicate یا نشت پاسخ نیست.

collectionها embedding function صریح ندارند. رفتار offline، مدل embedding،
cache/download و هر هزینه باید قبل از اجرای واقعی مشخص شوند؛ در این بازبینی
هیچ index، embedding یا دانلود مدلی اجرا نشده. پرداختی بودن embedding از این
کد اثبات نمی‌شود. query خام نیز چاپ می‌شود؛ adapter متصل باید از diagnostics
مجاز استفاده کند. مسیر defaultِ `.chroma_db` باید از Git بیرون بماند. import
از `data_scripts` با دست‌کاری `sys.path` هم نیاز به بررسی در package نصب‌شده دارد.

## تحویل کوچک R3/P4 برای pilot

تغییر قرارداد core لازم نیست. backend حسن حفظ شود و adapter کنار همان بخش
اضافه شود. برای شروع، corpus نهایی لازم نیست؛ یک allowlist کوچک از docs مجاز
با snapshot و exclusion خانوادهٔ dev #12782/#12629 ثبت شود. این allowlist
شاهد freeze نهایی E1/R2 نیست و باید قبل از index بررسی شود.

- درخواست یک یا دو query رشته‌ای را مصرف کند و snapshot تنظیم‌شده با درخواست
  برابر باشد. snapshot صرفاً نام دلخواه یک index قابل تغییر نباشد؛ manifest
  نسخهٔ ورودی و exclusion را مشخص کند.
- hitها ID یکتا، `source_id`، URL، excerpt واقعی و نوع معتبر core داشته باشند.
  `source_commit` و `source_span` موجود در seed حفظ شوند. پیشوند ساخته‌شدهٔ
  chunker به‌عنوان نقل‌قول منبع گزارش نشود.
- نسخهٔ API از metadata واقعی بیاید؛ scope نامعلوم Markdown با tuple خالی
  باقی بماند. نامعلوم به معنی سازگار با همهٔ نسخه‌ها نیست. `score_kind` فقط
  وقتی مقدار و معنای score مشخص است ثبت شود.
- `filters` پشتیبانی‌شده مستند و اعمال شوند؛ filter نامعتبر یا پشتیبانی‌نشده
  بی‌صدا نادیده گرفته نشود. `queries_used` queryهای واقعاً مصرف‌شده باشد.
- پس از refinement، bundle نهایی فقط evidence همان پاسخ را داشته باشد؛ منبع
  قبلی اگر هنوز لازم است، داخل همین bundle و همان سقف بازگردد.
- failure backend بدون raw query/error در خروجی، مدل را صدا نزند. ورودی retrieval
  نمی‌تواند fact کاربر، approval یا write به پرونده ایجاد کند.

اول با collection/embedding ساختگی تست شود: دو query، duplicate مشترک docs/issues،
`top_k=1`، snapshot اشتباه، metadata نامعلوم، متن بزرگ، correction نسخه، refinement
و backend failure. سپس همان adapter در
[CoreTurnService](core-turn-service.fa.md) با SQLite موقت و reasoner اسکریپتی
مصرف شود. تحویل، PR، دستور اجرا و receipt باشد. این تست‌ها پذیرش port با
fixture را نشان می‌دهند؛ برای بستن تحویل متصل P4، همان adapter و pilot باید
روی snapshot کوچک docs مجاز هم با receipt قابل تکرار بررسی شوند. corpus و
ارزیابی نهایی همچنان R2/R4 و E1–E5 هستند.
[نمونهٔ executable port](integration.md#a-runnable-offline-adapter-example) و
[pilot موجود](../scripts/core_tracker_pilot.py) نقطهٔ شروع‌اند.

## سهم باقی‌ماندهٔ هر بخش

حسن R1/R2/R3 را با همین backend ادامه می‌دهد. محمدحسن manifest خانواده‌ها و
rubric/branchهای گفتگو را جلو می‌برد و با بهنام API را به SQLite و سرویس core
وصل می‌کند. journal اجرای نیمه‌تمام و CAS اتمیک lifecycle هنوز U3/T4 هستند؛
خواندن state در core جای transaction نهایی را نمی‌گیرد.

ساسان بعد از adapter، همان pilot و correction/refinement را با ورودی واقعی
retrieval می‌گیرد. فعلاً تغییر معماری، agent جدید یا guard عمومی دیگری توجیه
نشده. C5 و halt ledger پابرجاست؛ اجرای مدل واقعی همچنان به reconciliation
وابسته است. نتیجهٔ نهایی کیفیت پس از اتصال و evaluation مستقل گزارش می‌شود.
