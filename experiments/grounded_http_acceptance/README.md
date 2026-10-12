# C2f — GroundedPlan در HTTP پایدار، با gateway جعلی

این [protocol](protocol-v1.json) **قبل از اجرای جدید** ثبت می‌شود. همان fixture
چهارمرحله‌ای C3 و oracle کامل قبلی را نگه می‌داریم؛ برای هر مرحله اطلاعات موجود،
کمبود قابل سؤال از کاربر، کمبود source و تصمیم قابل قبول از پیش مشخص‌اند.
caseهای #12782/#12629 exposed و انتخابشان answer-informed بوده؛ ادامهٔ گفتگو
و پاسخ provider authored است. این مسیر کیفیت مدل، RAG واقعی یا test نهایی نیست.

مسیر واقعی gateway و ledger، GroundedReasoner، core، HTTP، client و SQLite اجرا
می‌شود، ولی transport provider فقط MockTransport است. هیچ `.env`، ledger واقعی،
provider، embedding یا source snippet اجرا نمی‌شود. هزینهٔ واقعی API صفر است؛
token usage و settlement داخل ledger موقت فقط شبیه‌سازی‌اند.

baseline از فایل `persistent_api.py` منتشرشده در `3c92b12` بارگذاری می‌شود؛
بقیهٔ ماژول‌های پشتیبان همان checkout فعلی‌اند و hashشان ثبت می‌شود. baseline
با همین ports، GroundedPlan را اجرا می‌کند؛ شکست عملکردی ساختگی به آن نسبت
نمی‌دهیم. دو تفاوت کنترل‌شده، label اشتباه `scripted` و بسته‌نشدن خودکار client
هر run هستند: انتظار baseline ده کنترل از دوازده و نسخهٔ جدید دوازده از دوازده
است. هر دو در cleanup نهایی fixture همهٔ clientها را می‌بندند.

اجرای جدید source/analysis را فقط با JSON یا citation ID نمی‌سنجد: متن کامل
تحلیل با oracle قبلی برابر است؛ نقل منبع کامل، version scope، سؤال canonical
و ضرورت سؤال بررسی می‌شوند. request جدید شامل history است، پس digest آن را
با digest قدیمیِ memory tracker مقایسه نمی‌کنیم. تاریخچه authority نیست؛ نسخهٔ
قدیمی در history، fact فعال یا EvidenceHit تازه نمی‌شود.

اصلاح نسخه و حذف شاهد در round دوم، approval قدیمی، ACK گمشده، retry بعد از
ساخت مجدد backend، edit/reject و replay همان event هم کنترل می‌شوند. proposal
اجرا نیست؛ فقط approval دقیق tracker اقدام محلی ثبت می‌کند. این runner از ASGI
و backend recreation در همان interpreter استفاده می‌کند؛ تست TCP مستقل restart
process و AppTest مستقل rerun صفحه را پوشش می‌دهند.

پس از commit ثبت protocol:

```bash
uv run python scripts/grounded_http_acceptance.py --baseline --output /tmp/grounded-http-baseline-new.json
uv run python scripts/grounded_http_acceptance.py --output /tmp/grounded-http-current-new.json
uv run pytest tests/test_grounded_http_acceptance.py
```

receipt موجود overwrite نمی‌شود. drift در protocol/fixture/oracle، تغییر کد
حین اجرا، assertionهای غیرفعال، baseline غیرمنتظره یا شکست نسخهٔ جدید خروجی
موفق نمی‌گیرد. R2/R4 حسن، E1/E2 محمدحسن و C5 همچنان جدا و بازند.
