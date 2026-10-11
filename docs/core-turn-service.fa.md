# C2a — اتصال مستقل core به tracker

`CoreTurnService` در [service.py](../src/agent_app/orchestration/service.py)،
coordinator قابل استفادهٔ core است. از همان `apply_turn`، `read_case` و
`stage_proposal` ماژول SQLite استفاده می‌کند؛ storage، HTTP، review و احراز
هویت را پیاده‌سازی نمی‌کند. مسیر فعلی FastAPI همچنان memory/scripted است.

## مسئله و رفتار جدید

روی `94b60e1`، اتصال سادهٔ commit/read/run می‌توانست receipt مربوط به
revision 1 را بگیرد، بعد از correction state مربوط به revision 2 را بخواند
و پیام قبلی را با facts جدید اجرا و stage کند. callback عدد revision این
فاصله را نمی‌بست. سرویس receipt را به original event و revision بعد از
commit وصل می‌کند؛ replay یا event عقب‌افتاده حتی adapter نمی‌سازد.

| ورودی کنترل‌شده | قبل | بعد |
| --- | --- | --- |
| correction میان commit و read | پیام event در rev 1، روی facts rev 2 با یک model attempt اجرا و stage شد | `superseded_before_run`؛ صفر factory/retrieval/model |
| ورودی از ابتدا pending | یک retrieval و دو attempt گزارش‌شده؛ صفر delegate call و خطای مبهم | صفر port؛ `stale / PendingProposalMismatch` |
| رقیب هنگام retrieval، با همان revision proposal می‌گذارد | یک delegate call و final analysis محلی | صفر delegate call؛ final analysis صادر نمی‌شود |
| reply واقعی `1.50.0` به سؤال نسخه | مسئلهٔ اصلی در query/ورودی reasoner نبود | شرح مسئله، reply و facts فعال در ورودی و handoff حفظ‌اند |
| کد widget در پیام میانی، سپس reply کوتاه | helper اولیهٔ first/latest آن کد را حذف می‌کرد | تمام پیام‌های کاربر در context تاریخی، بدون پاسخ‌های قدیمی دستیار |

سه سطر اول baseline کد واقعی `94b60e1` و اتصال دستی SQLite هستند؛ ادعای
خرابی API حافظه‌ای serialized نیستند. سطر آخر اصلاح دوم helper همین تغییر
است، نه baseline منتشرشدهٔ main. input-preservation و توقف کار اضافه اندازه
گرفته شده‌اند؛ امتیاز معنایی مدل از این جدول به دست نمی‌آید.

مسئلهٔ دوم قابل مشاهده بود: بعد از سؤال تأییدشده، reply کوتاه `1.50.0`
تنها همین متن را به retrieval و reasoner می‌رساند. شرح اصلی مسئله و پیام‌های
کاربر حالا به صورت context تاریخی همراه پیام تازه می‌آیند. facts فعال از
`CaseState` می‌آیند؛ context، fact یا evidence تازه نمی‌سازد. پاسخ‌های قبلی
دستیار evidence محسوب نمی‌شوند و وارد این context نمی‌شوند. فقط سؤال
canonical نسخه که tracker آن را تأیید و به همان reply متصل کرده، نگه داشته
می‌شود. پشتیبانی از binding سؤال دلخواه هنوز قرارداد جدا می‌خواهد.

`SupportEngine.current_case` تغییر کل state را نیز بررسی می‌کند؛ pending
proposal و تغییر محتوا با revision یکسان پیش از ادامهٔ portها متوقف می‌شوند.
ورودی pending از ابتدا retrieval/model ندارد. `current_revision` قبلی همچنان
کار می‌کند، ولی به تنهایی تغییر محتوا یا lifecycle با revision یکسان را نمی‌بیند.

## ورودی و خروجی اتصال

```python
from agent_app.orchestration import CoreAdapters, CoreTurnService

def adapters(case, message, run_id):
    # Fresh ports per accepted turn. No source writes or paid calls at setup.
    return CoreAdapters(retriever, reasoner, snapshot_id)

service = CoreTurnService(tracker, adapters)
outcome = service.submit(original_user_turn)
```

این snippet شکل اتصال است؛ `retriever`، `reasoner`، `snapshot_id` و `tracker`
را caller از تنظیمات معتبر خودش می‌آورد. برای اجرا، از pilot پایین استفاده
کنید. factory فقط state جداشده، context واقعی همان پرونده و run ID معتبر
می‌گیرد؛ gold، expected decision و پاسخ آینده ورودی port نیستند.
`grounded_request_supplier` اختیاری باید request واقعی همان invocation را
برگرداند؛ case/message/آخرین bundle متفاوت، handoff نمی‌سازند.

`UserTurn` اصلی، `reply_to_proposal_id` و `event_context` هویت ingress هستند؛
context ساخته‌شده آن‌ها را عوض نمی‌کند. برای reply نسخه، ID سؤال تأییدشدهٔ
همین پرونده را بدهید. به هر turn تازه run ID تازه بدهید؛ اگر ندهید UUID
تازه ساخته می‌شود. run ID متعلق به caller است؛ مدل آن را انتخاب نمی‌کند.

| status | معنی برای API |
| --- | --- |
| `proposal_staged` | `handoff` کامل، با read دقیق pending تأیید شده؛ هنوز approval لازم است |
| `replay_only` | فقط receipt ingress قبلی و snapshot فعلی؛ run تازه یا recovery مدل نیست |
| `superseded_before_run` | receipt قدیمی‌تر از state؛ adapter/retrieval/model ساخته نشده |
| `core_stopped` | context/setup/retrieval/reasoning یا handoff متوقف؛ receipt ممکن است قبلاً commit شده باشد |
| `proposal_not_pending` | proposal محلی برای review فعلی قابل استفاده نیست؛ correction/edit/approval دیگری ممکن است رسیده باشد |
| `staging_unknown` | pending دقیق تأیید نشده؛ `candidate_handoff` فقط برای read recovery است، نه نمایش به عنوان proposal قابل approval |
| `ingress_rejected` / `ingress_unknown` | رد صریح یا ACK نامعلوم ingress؛ retry فقط original event، بدون حدس دربارهٔ کامل‌شدن run |

`run_result` تلاش‌ها و trace امن را حتی در خطای handoff/staging نگه می‌دارد.
خطای adapter و exception خام صادر نمی‌شود. ورودی constructed با attribute
اضافی در مدل‌های nested نیز قبل از اعتماد رد می‌شود.

## replay، ACK و race

سرویس هرگز replay را به درخواست دوم مدل تبدیل نمی‌کند. پس از ACK نامعلوم
stage، فقط pending کامل با همان case/revision/ID/hash/content تأیید می‌شود.
برای recovery جداگانه:

```python
saved = service.recover_exact_pending(expected_handoff)
```

این فقط read است؛ نه stage، approval یا اجرای دوباره. receipt ورود اثبات
تمام‌شدن reasoning نیست. اگر بعد از commit و پیش از stage اجرا قطع شود،
resumption خودکار نداریم؛ journal اجرای نیمه‌تمام هنوز با U3/T4 است.

readهای کامل، تغییر lifecycle مشاهده‌شده را هم متوقف می‌کنند، اما lock یا
CAS اتمیک lifecycle نیستند. رقیب می‌تواند بعد از آخرین read، proposal خود را
stage و approve کند و state به همان revision/pending قبلی برگردد؛ stage
فعلی SQLite این ABA را از run جدید تشخیص نمی‌دهد. برای بستن این race، بهنام
و محمدحسن باید run/lifecycle identity را در transaction stage و HTTP recovery
هماهنگ کنند. approval دقیق و جلوگیری از action تکراری فعلی سر جایشان هستند؛
این محدودیت دربارهٔ دو run متفاوت در همان lifecycle است.

history فعلاً حداکثر ۱۰۰۰ entry و context مجموعاً ۲۰هزار کاراکتر دارد؛ داده
بیشتر بدون truncation رد می‌شود. این توقف ممکن است بعد از commit ورود باشد
و replay آن هم run جدید نمی‌سازد. برای گفتگوهای بلند، سیاست حفظ context و
journal جدا لازم است؛ حافظهٔ نامحدود یا فهم معنایی کامل ادعا نمی‌کنیم.

## اجرای قابل بازبینی

از ریشهٔ repo، با مسیر receipt تازه:

```bash
uv run python scripts/core_tracker_pilot.py --output /tmp/core-tracker-pilot-new.json
uv run pytest tests/test_core_turn_service.py tests/test_core_conversation.py tests/test_engine_freshness.py
```

pilot همان fixture dev `12782` را با SQLite موقت و portهای تألیفی اجرا می‌کند:
سؤال، reply کوتاه، correction و refinement، edit/approval، restart/retry،
withdrawal/reject و replay قدیمی. ۴ turn و ۴۹ check عملیاتی ثبت می‌شوند؛
handoff اصلی، ویرایش و متن منتشرشده جدا، با hash fixture/evidence/source و
git commit نگه داشته می‌شوند. هزینه و درخواست واقعی صفرند. این خانواده
answer-informed/exposed است و test مستقل نیست. corpus یا نتیجهٔ RAG ساخته
نشده؛ دستور در CI هم اجرا می‌شود.

baselineهای قبل از تغییر و receipt کامل، بیرون Git در
`output/core-turn-coordinator-2026-10-11/` هستند. مقایسه حفظ ورودی و توقف port
اشتباه را نشان می‌دهد؛ کیفیت تصمیم مدل باید بعد از R3/E1/E2/C5 جدا اندازه
گرفته شود. [packet توقف live](live-reconciliation-2026-10-11.fa.md) blocker
هویت/usage/billing را دقیق‌تر کرده؛ halt و uncertainty دست‌نخورده‌اند.
