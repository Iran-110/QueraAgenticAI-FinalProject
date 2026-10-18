# C4z — مقایسهٔ دقیق headerها

این‌ها خروجی یک اصلاح آفلاین‌اند؛ متن مدل یا source داخل build جاری تغییر نکرده.
اصل کامل JSON، متن قبل/بعد، مختصات و hashها در
[رسید source-aware](source-replay-v1.json) باقی است.

| نسخه | پارامتر | مقدار header قبلی | header مشتق‌شده از signature |
|---|---|---|---|
| 1.49.0 | `label` | `default=None` | بدون فیلد default؛ پارامتر required |
| 1.49.0 | `type` | `default=None` | `default="secondary"` |
| 1.49.0 | `disabled` | `default=is` | `default=False` |
| 1.49.0 | `width` | `default=None` | `default="content"` |
| 1.39.0، کنترل | `label` | `default=None` | بدون فیلد default؛ پارامتر required |
| 1.39.0، کنترل | `type` | `default=s` | `default="secondary"` |
| 1.39.0، کنترل | `use_container_width` | `default=None` | `default=False` |

`icon=None` تغییر نمی‌کند؛ این بار `None` در خود signature صریح است. از `null`
در metadata به‌تنهایی نمی‌توان نتیجه گرفت مقدار واقعی پارامتر `None` است.

پیشوند، بدنهٔ همهٔ پارامترها و پسوند متن قدیمی بایت‌به‌بایت برابرند. طول متن
1.49 از۳۷۵۴به۳۷۵۵ و کنترل1.39 از۲۶۹۸به۲۶۹۵کاراکتر تغییر می‌کند؛ کوتاه‌ترشدن
معیار پذیرش این اصلاح نیست. دو LF انتهایی seed بعد از trim دقیقاً excerpt تاریخی
را بازتولید می‌کنند؛ offset منبع قدیمی بازنویسی نشده است.

این خروجی همهٔ اطلاعات خام را در متن ادغام نمی‌کند: مثال‌ها و deprecation در
JSON کامل محفوظ‌اند و prose قدیمی `use_container_width` نسخهٔ1.49 هنوز نیازمند
review است. برای body یا رفع همهٔ تعارض‌ها ادعای اصلاح نداریم.

تأیید AST مستقل کد رسمی برای `type/disabled` نسخهٔ1.49 انجام شده؛ سایر سطرها
اصلاح بر مبنای signature سند هستند. هیچ اجرای runtime یا کیفیت‌سنجی مدل تازه‌ای
صورت نگرفته است. هویت هر مشتق تازه است؛ هیچ approval قبلی به آن منتقل نمی‌شود.
