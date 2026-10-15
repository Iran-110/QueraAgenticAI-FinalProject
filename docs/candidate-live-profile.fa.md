# R4d/C2i — profile بازیابی در مسیر متصل

بستهٔ R4c قبلاً در driver آزمایش مستقیم به engine داده می‌شد. اکنون profile
اختیاری زیر از factory و runner تا engine هر دو مسیر API حافظه‌ای و HTTP/SQLite
منتقل می‌شود؛ backend و UI جدیدی ساخته نشده است.

```bash
export AGENT_RETRIEVAL_PROFILE=candidate_relevance_v1
export AGENT_EVAL_TOP_K=5
export METIS_GROUNDED_DECISION_CONTRACTS=true
export METIS_GROUNDED_COMPACT_PLAN=true
export METIS_GROUNDED_SOURCE_SELECTION_REMINDER=true
export METIS_GROUNDED_SOURCE_GAP_HANDOFF=true
export METIS_GROUNDED_SOURCE_GAP_INVESTIGATION=true
# اختیاری و جدا از retrieval؛ پیش‌فرض false
export AGENT_GROUNDED_ASK_SOURCE_BACKGROUND=true
```

این‌ها علاوه بر تنظیم‌های موجود index/snapshot/manifest، ledger، key خصوصی و
tracker/reviewer هستند؛ [کارخانهٔ live موجود](evaluation-live-routes.fa.md)
و [شرح رفتار R4c](retrieval-relevance.fa.md) مرجع‌اند. نام این profile فقط دو
مقدار معتبر دارد: `native` پیش‌فرض و `candidate_relevance_v1`. حالت candidate
فقط final top-k پنج را می‌پذیرد: adapter تا ۲۵ کاندیدا می‌خواند، policy عمومی
query relevance را اعمال می‌کند و engine پس از scope نسخهٔ فعال USER، حداکثر
پنج رکورد کامل را در ۱۲۰۰۰ byte انتخاب می‌کند. query repair موجود روشن است؛
attempt، query و round اضافه نمی‌شود. policy current-installation این profile
حتی scope مقایسه‌ای `all` را به `exact_user_version` محدود می‌کند.

متادیتای trailing/default-native در `api.RunAdapters` و `CoreAdapters` داخلی
است؛ wrapper runner و تبدیل persistent آن را حفظ می‌کنند. فقط نگاشت ثابت
`orchestration/retrieval_profile.py` kwargs مجاز engine را می‌سازد؛ config دلخواه
از پیام کاربر پذیرفته نمی‌شود. `contracts.py` و `ports.py` عوض نشده‌اند.
حالت native همان call shape و config ID قبلی را نگه می‌دارد؛ profile جدید
شناسهٔ retriever/adapter جدا دارد تا ارزیابی با تنظیم قبلی یکی نشود.

تست متصل با native Chroma واقعی و provider ماک، read ۲۵ کاندیدا، حداکثر پنج
رکورد نسخهٔ جاری و بودجهٔ کامل bundle را کنترل می‌کند. correction از ۱٫۵۰ به
۱٫۴۹، رد approval قدیمی، تأیید hash دقیق متن تازه، restart و retry با یک action
بررسی شده‌اند. مسیر `evaluation.runner.CaseRun` نیز همین metadata را تا API
حفظ می‌کند. کیفیت مدل، مرورگر زنده و corpus نهایی از این کنترل‌ها نتیجه نمی‌شوند.

این تنظیم مجوز مالی یا رفع halt نیست. factory معمولی همان ledger پروژه،
hold/halt و index-before-key را بررسی می‌کند و startup هیچ provider call ندارد.
آزمایش آنلاین فعلی از driver با scopeهای محدود تازه و مجوز صریح ساسان، همان
ledger و حفظ holdهای قبلی استفاده می‌کند؛ ledger جایگزین یا reset ندارد.
تست‌های تازه و receipt پیش از اعلام تغییر پیش‌فرض لازم‌اند؛ پیش‌فرض‌ها فعلاً ثابت‌اند.
