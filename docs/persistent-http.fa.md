# اتصال HTTP به SQLite موجود — C2d

مسیر مستقل HTTP اکنون از `CoreTurnService` و `SQLiteCaseTracker` موجود استفاده
می‌کند. state در `_cases` کپی نمی‌شود. case، history، آخرین intake، proposal،
نتیجهٔ run، review و action همگی از همان database خوانده می‌شوند.
این اتصال **opt-in** است؛ `agent_app.api:app` همچنان demo حافظه‌ای قبلی است.
client و صفحهٔ UI اکنون قرارداد approval پایدار را می‌فرستند؛
[اجرای محلی UI/index و recovery](offline-ui-index-pilot.fa.md) مسیر opt-in دارد.
#30 در `6e719e9` merge و [CI همان main](https://github.com/Iran-110/QueraAgenticAI-FinalProject/actions/runs/38254465683)
با ۲۰۳۵ تست پاس شد.

## نتیجهٔ ثبت‌شده

[protocol v2](../experiments/http_pilot_acceptance/protocol-v2.json) در `6f0e8b5`
پیش از اجرای اتصال ثبت شد. fixture، gold و شواهد همان pilot #12782 باقی ماندند.
[receipt تمیز SQLite](../experiments/http_pilot_acceptance/results-sqlite-b7107c0.json)
روی `b7107c0` **۴۵۷/۴۵۷** check را پاس می‌کند؛ `accepted=true`،
`same_process_accepted=true` و `restart_accepted=true` هستند.
هر پنج checkpoint با interpreter تازه و همان مسیر database اجرا شدند.

| مشاهدهٔ عملیاتی با source یکسان | demo حافظه‌ای | HTTP با SQLite |
| --- | --- | --- |
| حفظ کل state در چهار checkpoint گفتگو | رد | پاس |
| حفظ ورودی/نتیجهٔ توقف در checkpoint setup | رد | پاس |
| retry event قدیمی پس از correction | پس از restart ورودی گم می‌شود | receipt اصلی، state فعلی و صفر port |
| retry review موفق | پس از restart سابقه گم می‌شود | receipt/action اصلی، بدون comment تازه |
| checks همین kit | ۳۶۷/۴۰۴ | ۴۵۷/۴۵۷ |

[receipt حافظه‌ای همان commit](../experiments/http_pilot_acceptance/results-memory-b7107c0.json)
همچنان `accepted=false` دارد. [مقایسه](../experiments/http_pilot_acceptance/comparison-sqlite.json)
hashها و probeهای مشترک مشخص را ثبت می‌کند. v2 شرط‌های review احراز‌شده و
inspection واقعی actionهای SQLite را اضافه می‌کند؛ مخرج‌ها برابر نیستند و از
این اعداد درصد بهبود کیفیت نمی‌سازیم. source/fixture طی هر دو اجرای تمیز ثابت بود.
تعداد check، تعداد case مستقل نیست.

## مرزهای پیاده‌سازی

- `apply_turn` همان event اصلی را deduplicate می‌کند و همراه commit ورودی،
  marker نتیجهٔ ثبت‌نشده را در `run_outcomes` می‌گذارد. این جدول در **همان tracker**
  اضافه شده؛ backend یا state دوم نداریم. constructor هیچ reset انجام نمی‌دهد.
- `CoreTurnService` بعد از commit و read سازگار، portها را می‌سازد. callback
  اختیاری و مورد اعتماد `stage_with_result`، همان `stage_run_proposal` را صدا
  می‌زند؛ handoff و **RunResult اندازه‌گیری‌شده** در یک transaction ثبت می‌شوند.
- `finish_run` نتیجهٔ توقف را یک بار ثبت می‌کند. retry برابر idempotent است؛
  overwrite نتیجهٔ متفاوت/کامل رد می‌شود. crash قبل از نتیجه، وضعیت صریح
  `interrupted` می‌گذارد؛ این marker ممکن است هنگام run در حال اجرا هم دیده شود
  و صرف GET، اثبات crash نیست.
- `read_runtime_view` همهٔ اجزای HTTP را در یک snapshot SQLite می‌خواند؛ API
  `read_case`، `comments` و `audit_trace` جدا را برای ساخت view به هم نمی‌چسباند.
  schema قدیمی و shape قرارداد `read_case` حفظ شده‌اند؛ metrics قدیمی که ذخیره
  نشده‌اند `null` می‌مانند.
- reviewer از bearer credential تنظیم‌شدهٔ سمت سرور تعیین می‌شود. tracker
  دوباره credential را کنترل می‌کند و فقط transaction خودش local comment را
  ثبت می‌کند. HTTP هیچ action دوم یا متن assistant مستقل آزاد نمی‌کند.
- staging داخل transaction فقط در وضعیت `open` و پیش از اولین root proposal
  همان revision مجاز است. این شرط مسیر ABA قبلی پس از approve/reject را می‌بندد.
  edit همچنان proposal تازه دارد؛ برای reasoning تازه بعد از بسته‌شدن revision،
  یک UserTurn جدید لازم است. resume خودکار وجود ندارد.

## ورودی و خروجی برای UI/API

factory قابل استفاده در [persistent_api.py](../src/agent_app/persistent_api.py):

```python
from agent_app.persistent_api import create_app
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

def build_backend(database_path, configured_reviewer_tokens):
    tracker = SQLiteCaseTracker(
        database_path, reviewer_tokens=configured_reviewer_tokens
    )
    return create_app(tracker, reviewer_tokens=configured_reviewer_tokens)
```

database path و credential را caller از تنظیم معتبر فراهم می‌کند؛ این factory
`.env`، کلید مدل یا مسیر production ledger را نمی‌خواند. server محلی به loopback
bind شود. portهای پیش‌فرض همان scriptهای آفلاین‌اند؛ adapter مدل واقعی نیاز به
تنظیم/label جدا و رفع C5 دارد. [binding تست](../src/agent_app/testing/sqlite_http_binding.py)
credential **صریحاً synthetic** و database موقت دارد؛ از آن برای credential واقعی
استفاده نکنید.

پیام از همان `MessageRequest` استفاده می‌کند، اما `turn_id` و `expected_revision`
الزامی‌اند. context هویت event شامل `scenario` است؛ تغییر scenario با همان ID
`EventConflict` می‌گیرد. جواب کوتاه نسخه فقط به سؤال approve‌شدهٔ canonical و
همان proposal bind می‌شود. context تاریخی از همان core ساخته می‌شود؛ facts
فعال مرجع‌اند و دادهٔ آینده/gold وارد reasoner نمی‌شود.

برای `POST /cases/{case_id}/decision`، client باید **پیش از ارسال** یک payload
بسازد و برای timeout/retry همان payload را نگه دارد:

```json
{
  "review_id": "client-created-stable-review-id",
  "proposal_id": "id-from-the-displayed-proposal",
  "case_revision": 2,
  "expected_handoff_sha256": "64-hex-digest-from-that-exact-proposal",
  "decision": "approve"
}
```

نمونه بالا شکل قرارداد است؛ digest باید مقدار واقعی
`pending.review_handoff.handoff_sha256` باشد. header برابر
`Authorization: Bearer <configured-maintainer-credential>` است؛ reviewer ID در
JSON یا متن گفتگو پذیرفته نمی‌شود. `edited_draft` فقط برای `edit` فرستاده شود.
هر review مستقل ID تازه دارد؛ retry همان review، ID و hash اصلی را حفظ می‌کند.
سرور hash گم‌شده را از آخرین proposal بازسازی نمی‌کند.

GET همان فیلدهای UI قبلی را با `tracker_backend`، `run_outcome`، `actions` و
آخرین receipt اصلی `review` برمی‌گرداند. POST review علاوه بر view فعلی، receipt
همان عملیات را در `review` می‌دهد. retry کامل آن `replayed=true` دارد؛ حتی بعد
از correction، برگشت receipt قبلی به معنی اجرای approval تازه نیست. review
جدید برای proposal قدیمی 409 می‌گیرد و action تازه نمی‌سازد.

4xxهای validation/auth/stale/conflict بدون mutation هستند. 503 بعد از commit
می‌تواند ACK نامعلوم باشد؛ آن را rollback فرض نکنید. همان event/review را retry
کنید، state فعلی و receipt اصلی را بخوانید و model را خودکار دوباره اجرا نکنید.
diagnosticها کدهای ثابت‌اند؛ credential و متن exception صادر نمی‌شوند.

## بازتولید و شواهد قطع اجرا

از root، بدون مدل، embedding، index یا production ledger:

```bash
uv sync --locked --group dev
uv run python scripts/http_pilot_acceptance.py \
  --factory agent_app.testing.sqlite_http_binding:sqlite_factory \
  --protocol experiments/http_pilot_acceptance/protocol-v2.json \
  --output /tmp/http-sqlite-new.json
uv run pytest tests/test_sqlite_runtime.py tests/test_persistent_api.py \
  tests/test_persistent_http_crash.py tests/test_sqlite_http_acceptance_binding.py
```

خروجی overwrite نمی‌شود. CI هم اجرای مثبت SQLite و negative control حافظه‌ای
را جدا دارد؛ candidate با `--expect-memory-gap` تأیید نمی‌شود.
harness فقط envelope عملیاتی review را با hash دقیق proposal دیده‌شده و credential
synthetic تکمیل می‌کند؛ fixture/gold تغییر نمی‌کنند. probe approval مستقل ID تازه
می‌گیرد؛ probe retry دقیق، payload قبلی را استفاده می‌کند. actionهای exported در
والد و child با `SQLite.comments()` واقعی هم مقایسه می‌شوند.

kit توقف setup و پنج restart را می‌گیرد؛ tests تکمیلی مرزهای سخت‌تر را پوشش می‌دهند:

- [۴۱ تست HTTP](../tests/test_persistent_api.py): credential، hash، stale/pre-edit،
  correction، retry review، schema، دو app مستقل و درخواست‌های هم‌زمان.
- [۳۲ تست tracker](../tests/test_sqlite_runtime.py): migration بدون reset، snapshot
  هنگام write رقیب، rollback ورودی/نتیجه/stage، metrics واقعی و ABA.
- [۴ تست crash/ACK](../tests/test_persistent_http_crash.py): `os._exit` واقعی بعد از
  commit ingress و بعد از commit stage، rollback بعد از INSERT comment، و recovery
  ACK گم‌شده بدون اجرای port تازه. صرف ساخت TestClient تازه، restart نامیده نمی‌شود.
- [۱۲ تست binding](../tests/test_sqlite_http_acceptance_binding.py): gateهای واقعی
  SQLite و کنترل منفی برای auth envelope، binding ضعیف، action جعلی و ACK نامعلوم.

کل suite **۲۰۳۵ تست**، Ruff و locked sync پاس‌اند. سه demo لازم، pilot مستقل
core/SQLite با **۴۹ check** و adapter واقعی RAG با collection ثابت با **۱۳۲ check**
هم پاس‌اند. هزینهٔ API صفر و C5 halt/ledger دست نخورده‌اند.

## باقی‌مانده

این سهم، HTTP/state/review محلی و restart/retry آفلاین را می‌بندد. UI فعلی باید
به این factory، credential maintainer و payload پایدار review وصل شود؛ نگه‌داشتن
retry review به تفکیک case هنوز کار U3 است. adapterهای واقعی index/model و
configuration/label اجرای live، corpus/exclusion، evaluation و scoring معنایی
همچنان باقی‌اند. action این تست comment محلی SQLite است، نه ابزار بیرونی یا
GitHub. journal outcome برای عدم اجرای دوباره است؛ feature resume ساخته نشده.

این خانوادهٔ Issue exposed و answer-informed است و follow-upها تألیفی‌اند؛
منبع Issue/پاسخ/duplicate خودش وارد corpus نمی‌شود. قبولی عملیات با fixture و
port اسکریپتی، کیفیت تصمیم مدل، entailment ادعاها، RAG واقعی یا test نهایی نیست.
