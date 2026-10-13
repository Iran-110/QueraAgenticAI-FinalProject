# وضعیت کار و مسیر کوتاه تکمیل — ۲۰۲۶-۱۰-۱۳

برآورد بخش الزامی پروژه، بدون bonus، **حدود ۷۰٪ (بازهٔ ۶۵ تا ۷۵٪)** است.
این قضاوت مهندسی از روی خروجی‌های موجود است؛ نمرهٔ مدل، سهم امتیازهای کوئرا
یا نسبت checkboxهای plan نیست. اتصال و کنترل‌های عملیاتی جلوترند؛ مجموعهٔ
ارزیابی مستقل و شواهد کیفیت هنوز عمدهٔ کار باقی‌مانده‌اند.

## آماده و قابل استفاده

- core تک agent، correction و supersession، GroundedPlan و handoff کامل منابع.
- همان tracker SQLite تیم با revision، approval دقیق، restart/retry و منع اجرای تکراری.
- UI و HTTP پایدار، مرورگر pilot، adapter حسن و build تکرارپذیر docs-only:
  ۱۴ source / ۳۰ chunk با Chroma واقعی و vector lexical محلی.
- runner آفلاین و ثبت proposal، config، زمان، تلاش و هزینه؛ passing receipt
  به معنی کیفیت پاسخ نیست. حالت عمومی live هنوز factory نهایی ندارد.

مبنای انتشار این بررسی `main@1c9985a` است. شواهد اصلی در
[PR35](../experiments/retrieval_acceptance/pr35/README.md) و
[pilot پایدار](grounded-persistent-pilot.fa.md) حفظ شده‌اند.

## کار مستقل این مرحله

1. wrapper ارزیابی callback مربوط به cleanup را به API نمی‌داد. همان port
   موجود اکنون حفظ می‌شود؛ cleanup بعد از گرفتن request/handoff و قبل از
   staging اجرا می‌شود. تست شکست retrieval/reasoning/supplier/cleanup و replay
   این مرز را بررسی می‌کند؛ قرارداد مشترک عوض نشده است.
2. [رزرو اولیهٔ خانواده‌ها](../data/evaluation/candidates/reservations-v1.json)
   به شکل metadata-only و قابل تکرار آماده شده: ۱۵ candidate در dev و ۱۵
   در test. **این فایل E1 یا split نهایی نیست**؛ هیچ سؤال، جواب یا gold test
   در آن نیست. خانوادهٔ candidate-12782 همان pilot موجود است و نباید دوباره
   شمرده شود. denylist اولیه ۴۴ ID دارد؛ هنوز به corpus نهایی اعمال نشده است.
3. `evaluation.preflight` بستهٔ جدید `frozen_final_v1` را از نظر hash، origin
   واقعی case، خانواده، exposure، ۱۵/۱۵، ۱۰ چندنوبتی/۵ در test و اظهار بازبینی
   corpus بررسی می‌کند. runner با flagهای final، کل بسته و evidenceهای آن را
   **پیش از ساخت live factory** بررسی می‌کند و فقط subset ثبت‌شده را اجرا می‌کند.
   این تأیید مکانیکی، اصالت بازبینی انسانی، کیفیت پاسخ یا index واقعی را ثابت
   نمی‌کند. runner هنوز مسیر شرطی سؤال‌ها را به‌صورت adaptive اجرا نمی‌کند.
4. [protocol اتصال واقعی](../experiments/grounded_http_acceptance/connected-live-protocol-v1.json)
   پیش از API ثبت می‌شود: همان index واقعی، مدل، HTTP پایدار و SQLite؛ ابتدا
   نسخهٔ معلوم 1.50.0 و سپس correction به 1.49.0. متن‌ها authored و خانواده
   exposed است؛ پاسخ Issue برای شناخت سناریو استفاده شده، ولی داخل evidence
   نیست. هیچ gold یا turn آینده‌ای به مدل فرستاده نمی‌شود.

دو سؤال callback و نمونهٔ واقعاً failing، vocabulary دستی caller هستند؛ core
آن‌ها را فقط برای unknown صریح فعلی و نبود fact معلوم فعال می‌کند. این رفتار
کشف خودکار gap از متن آزاد نیست. برای حفظ excerpt کامل و سقف ورودی، policy
ثبت‌شده `top_k=1` است. این محدودیت باید در تفسیر نتیجه باقی بماند.

## مسیر باقی‌مانده به ترتیب وابستگی

| کار | خروجی لازم | صاحب / کمک مؤثر |
| --- | --- | --- |
| E1/E2: تبدیل candidateها به case | بازبینی خانواده و exposure تمام اعضا؛ ۱۵ dev / ۱۵ test، حداقل ۱۰ مسیر چندنوبتی و ۵ test؛ ورودی/نسخه/gap/تصمیم‌های قابل قبول قبل از اجرا | محمدحسن؛ ساسان قرارداد و runner، حسن duplicate و منابع |
| R1/R2: corpus نهایی | منابع مجاز docs/Issueهای دیگر، provenance، حذف خود case/comment/outcome/duplicate و docs جواب مستقیم؛ manifest و index freezeشده | حسن با manifest محمدحسن؛ builder pilot مبناست |
| E3: مسیر live قابل تکرار | factory عمومی مدل/index با همان ledger، branchهای پاسخ شرطی، pin واقعی config/index/code/prompt/model | ساسان و محمدحسن؛ بودجه و توقف‌ها حفظ شوند |
| C4/E4/R4: dev baseline و یک بهبود | همان caseها/منابع؛ تصمیم در هر stratum، پشتیبانی ادعا، سؤال ضروری/قابل پاسخ، usefulness انسانی، retrieval و هزینه جدا | ساسان و حسن؛ بازبینی مستقل محمدحسن |
| E5: test مستقل | freeze پس از dev، اجرای test بدون tuning، trace و داوری کیفیت/شکست/هزینه؛ تطبیق بخشی از داوری‌ها توسط انسان | محمدحسن؛ کمک اجرای ساسان |
| گزارش و demo | دستور بازتولید، حدود و شکست‌ها، pilot قابل نمایش؛ ارائه پس از این‌ها | مشترک |

منتظر ZIP یا tracker تازه نمی‌مانیم. seed و adapterهای لازم موجودند. کمک انسانی
بیشترین ارزش را در خانواده/chronology، review مستقل claim/source و سؤال‌ها دارد؛
تعداد comment یا پاس شدن pytest جای این قضاوت را نمی‌گیرد. auth محصول و recovery
کامل session مرورگر برای demo محلی اولویت بعدی‌اند؛ bonus و framework تازه در
مسیر کوتاه فعلی نیستند.

## مجوز API و حساب هزینه

کاربر آزمایش واقعی لازم را مجاز کرده است. سقف اصلی تیم همچنان **۵ دلار** است؛
ledger اصلی reset، unhalt یا جایگزین نمی‌شود. C5 قبلی و hold نامعلوم $0.02
حفظ می‌شوند. probe حاضر از continuation توسعهٔ ثبت‌شده استفاده می‌کند:
حداکثر دو send شامل repair/refinement، سقف reservation کل $0.006420480؛ قبل
از ثبت اجرای تازه، remaining برابر $0.007134205 و settled تخمینی $0.121538835 بود.
این‌ها هزینهٔ محاسبه‌شدهٔ ledger هستند؛ شارژ واقعی حساب و درخواست قدیمی disputed
هنوز تطبیق نشده‌اند. شکست یا مصرف دو تلاش، مجوز retry خودکار تازه ایجاد نمی‌کند.

نتیجه و verification اجرای این مرحله پس از اجرا، جدا از protocol اولیه و با
source commit واقعی ثبت می‌شوند. هیچ test نهایی یا کیفیت RAG با این pilot اعلام
نمی‌شود؛ proposalها pending می‌مانند و اقدام خودکار نداریم.
