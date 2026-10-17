# اصلاح دو شرط ارجاع در native gold — E2ac

در PR81، شرط اولیهٔ ارجاع برای `dev-case-m` و `dev-case-i` هم گزارش fix نسخهٔ
1.38.0 را لازم می‌دانست و هم نبود passage پشتیبان را مجاز می‌شمرد. این دو شرط
با هم سازگار نبودند: کمبود سند نباید مدل را به ادعای بی‌منبع ملزم کند.

## رفتار اصلاح‌شده

| شواهد عرضه‌شده در همان turn | انتظار از review |
| --- | --- |
| شاهد لازم عرضه نشده و جایگزین کافی هم نداریم | ارجاع با نام کمبود واقعی و قدم مشخص برای retrieval یا بررسی maintainer؛ ادعای fix بدون پشتوانه پذیرفته نیست |
| passage هست ولی scope یا کاربردش برای کاربر کافی نیست | راهنمایی پشتیبانی‌شده حفظ شود؛ ارجاع فقط برای ابهام مهمِ باقی‌مانده |
| شواهد مسئله، API و نسخهٔ کاربر را کافی پوشش می‌دهند | پاسخ مستند؛ ارجاع صرفاً به دلیل احتیاط، abstention غیرضروری است |
| anchor ثبت‌شده دیده نشده ولی شاهد معادل کافی داریم | نبود match به‌تنهایی ارجاع را درست نمی‌کند؛ پوشش anchor و support معنایی جدا review می‌شوند |

نسخهٔ USER در هر دو initial برابر 1.37.0 و معلوم است. کمبود سند، مجوز پرسیدن
دوبارهٔ این نسخه نیست. شرایط answer و تمام follow-up پروندهٔ tabs تغییر نکرده‌اند.
این اصلاح **فقط دو شرط escalation** است؛ شرط answer قدیمی هنوز anchor ثبت‌شده
را لازم می‌داند. شاهد معادلِ فاقد anchor به review جدا نیاز دارد؛ این بخش را
پوشش جامع خودکار native gold اعلام نمی‌کنیم.

## نسخه‌ها و hashها

[ثبت فعال dev v2](../data/evaluation/split-e1-v1/native/native-registration-dev-v2.json)
دقیقاً ۱۶ پرونده دارد: ۱۴ fixture قبلی و دو fixture جدید در `native/dev-v2/`.
v1، review انسانی آن و همهٔ hashهای تاریخی عین byte حفظ شده‌اند. هر fixture
جدید `supersedes` با path، hash و شناسهٔ predecessor دارد. `native_of` همچنان
به fixture ثابت قبلی وصل است؛ متن USER، کد، script، route، passage و hash آن‌ها
تغییر نمی‌کنند. manifest ثابت dev/test هم دست‌نخورده است.

[رکورد اصلاح](../data/evaluation/split-e1-v1/native/native-dev-gold-amendment-v2.json)
hash دو نسخهٔ جدید و predecessorها را ثبت می‌کند. این **review دستیار** است؛
تأیید انسانی دو بند جدید هنوز pending است. verdict انسانی v1 به byteهای جدید
منتقل نشده و نمرهٔ انسانی تازه‌ای ساخته نشده است. registration، hash همین
رکورد را هم pin می‌کند؛ چرخهٔ hash نداریم.

## بازتولید آفلاین

از root پروژه، پس از نصب dependencyهای lockشده، این دستور فقط pathهای صریح
registration v2 را انتخاب می‌کند. مسیر خروجی باید تازه و داخل پوشهٔ `offline`
باشد. `native/dev/` را همراه `native/dev-v2/` یا fixed fixtureها glob نکنید؛
یک case نباید دوبار وارد invocation شود.

```bash
.venv/bin/python - <<'PY'
import hashlib
import json
from pathlib import Path
from agent_app.evaluation.runner import main

registration = json.loads(Path(
    "data/evaluation/split-e1-v1/native/native-registration-dev-v2.json"
).read_text())
paths = [entry["path"] for entry in registration["fixtures"]]
for entry in registration["fixtures"]:
    assert hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest() == entry["sha256"]
raise SystemExit(main([
    *paths, "--mode", "offline", "--conditional-routes",
    "--output", "runtime/e2ac/offline/native-dev-v2.json",
]))
PY
```

این registration قرارداد JSON جدیدی برای runner نیست؛ runner موجود pathهای
صریح می‌گیرد. ابزار question coverage فعلی نیز آن را مستقیم به‌عنوان manifest
نمی‌خواند. vocabulary و گزارش projection ثابت تغییر نکرده‌اند.

## شواهد و باقی‌مانده

[رسید بررسی](receipts/native-dev-gold-amendment-2026-10-16.json) source، hashها،
اجرای آفلاین و review مستقل را ثبت می‌کند. اجرای scripted از bundle ثابت
fixture استفاده می‌کند؛ گذشتن آن فقط اتصال و route را تأیید می‌کند، نه کفایت
شواهد index، بهبود کیفیت مدل یا اجرای test نهایی. شرط‌های متنی gold خودکار
امتیاز معنایی نمی‌گیرند؛ observer نیز فقط حضور passage را می‌سنجد.

۲۳۳ تست مرتبط، شامل ۱۰ regression تازه، پاس شدند؛ review مستقل همان ۱۰ تست
را هم پاس کرد و Ruff/format روی ۳۹۱ فایل موفق بود. شمارش‌ها هم‌پوشان‌اند؛
بررسی گستردهٔ قبلی تکرار نشده است. چهار شکست اولیه در helper تست تازه، از
نبودن `Fact.turn_id` بود و با شناسهٔ turn واقعی اصلاح شد؛ log اولیه حفظ است.
guard در parent اجرای نهایی و runner هیچ تلاش open محافظت‌شده یا اتصال شبکه
ثبت نکرد؛ این گواه تمام subprocessها نیست. GitHub CI موفق ادعا نمی‌شود؛
انتشار با تست محلی و مجوز موجود انجام می‌شود.

build pinها همچنان `pending_final_build` هستند. تأیید انسانی دو بند تازه، pin
بیلد نهایی و review معنایی تنظیم منتخب با evaluation/RAG باقی است؛ ثبت این
اصلاح freeze مشترک را نمی‌بندد. runtime، corpus، exclusion، vocabulary، halt و
سه hold عوض نشده‌اند. test باز نشده و هیچ API پرداخت‌شده یا پیام تیمی نداریم.
