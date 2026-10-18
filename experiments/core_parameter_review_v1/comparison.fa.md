# سه candidate پس از review — C4y

در AI review، هر سه تعریف انتخاب‌شده به سؤال فعلی مرتبط بودند؛ برای همین سؤال‌های محدود، قید ضروریِ جاافتاده‌ای در بقیهٔ source عرضه‌شده پیدا نشد. این نتیجهٔ کیفیِ سه مثال آشکار است، نه تضمین عمومی، نمرهٔ انسانی یا انتخاب تازهٔ مدل.

| مورد | نتیجهٔ محدود review | نیاز به روشن‌کردن کاربر | مسئلهٔ منبع |
| --- | --- | --- | --- |
| B2 `icon` | «next to the button label» به سؤال coexistence جواب می‌دهد؛ قیدهای قالب حفظ‌اند | برای سؤال حاضر ندارد | default همین پارامتر برابر است؛ span و بعضی پارامترهای دیگر نیاز به بررسی دارند |
| C1 `type` | هر سه گزینه و معنایشان موجود است | برای سؤال حاضر ندارد | headerِ `None` با signature/bodyِ `secondary` متفاوت است |
| C2 `disabled` | تعریف True/False، پارامتر را مشخص می‌کند | برای سؤال حاضر ندارد | headerِ `is` قابل مقایسهٔ امن نیست؛ از موقتی‌بودن، زمان‌بندی خودکار نتیجه نمی‌گیریم |

## تفاوت inspection با candidate قبلی

| turn | candidate کوتاه C4x | inspection تازه | default منتخب | span منبع منتخب |
| --- | ---: | ---: | --- | --- |
| B2 | 1357 | 1381 | برابری literal؛ تأیید حقیقت نیست | اختلاف طول با excerpt |
| C1 | 1193 | 1370 | نیازمند بررسی | اختلاف طول با excerpt |
| C2 | 860 | 1029 | نیازمند بررسی | اختلاف طول با excerpt |

متن کمی بلندتر شده، چون آدرس منبع و مسئلهٔ مشخص آن نمایش داده می‌شود. کاهش طول هدف این مرحله نیست. متن کامل منبع و signature در نمای maintainer حفظ‌اند؛ JSON شامل candidate قبلیِ بدون تغییر، observationهای همهٔ unitها و متن کامل review است.

## نمای قابل خواندن هر مورد

بلوک‌های زیر نمایش خروجی آزمایشی هستند؛ فقط فاصله‌های انتهای خط در این Markdown حذف شده‌اند. متن دقیق و hash در [گزارش کامل](replay-result-v1.json) محفوظ‌اند. این خروجی هنوز پاسخ قابل approval یا اجرا نیست.

### B2 — `icon`

```text
Experimental inspection; not an approved response.

### st.button · icon · Streamlit 1.39.0 (USER-reported)

Source checks requiring review:

- Supplied span length differs from excerpt length: 2698 versus 2696 Unicode code points; original-file mapping is unverified.
- Other parameters in this same source have 3 unresolved defaults. This does not disprove the selected quotation; details remain in the maintainer view.

> icon: str or None; default=None
> An optional emoji or icon to display next to the button label. If icon
> is None \(default\), no icon is displayed. If icon is a
> string, the following options are valid:
>
> A single-character emoji. For example, you can set icon="🚨"
> or icon="🔥". Emoji short codes are not supported.
>
> An icon from the Material Symbols library \(rounded style\) in the
> format ":material/icon\_name:" where "icon\_name" is the name
> of the icon in snake case.
>
> For example, icon=":material/thumb\_up:" will display the
> Thumb Up icon. Find additional icons in the Material Symbols
> font library.
>
>

[Supplied documentation](https://github.com/streamlit/docs/blob/695e6ce2fb1b23afc6df66b40420ab0013ad72fd/python/streamlit.json). Quotation offsets [1486,2083) are Unicode code points within the supplied excerpt.

Relevance, external caveats and usefulness remain unscored. Full sources and signatures: maintainer view.
```

### C1 — `type`

```text
Experimental inspection; not an approved response.

### st.button · type · Streamlit 1.49.0 (USER-reported)

Source checks requiring review:

- Header and signature declare different literal defaults; header: None; signature: "secondary". These observations do not choose a corrected or actual runtime default.
- Supplied span length differs from excerpt length: 3754 versus 3752 Unicode code points; original-file mapping is unverified.
- Other parameters in this same source have 3 unresolved defaults. This does not disprove the selected quotation; details remain in the maintainer view.

> type: "primary", "secondary", or "tertiary"; default=None
> An optional string that specifies the button type. This can be one
> of the following:
>
> "primary": The button's background is the app's primary color
> for additional emphasis.
>
> "secondary" \(default\): The button's background coordinates
> with the app's background color for normal emphasis.
>
> "tertiary": The button is plain text without a border or
> background for subtlety.
>
>

[Supplied documentation](https://github.com/streamlit/docs/blob/695e6ce2fb1b23afc6df66b40420ab0013ad72fd/python/streamlit.json). Quotation offsets [1581,2009) are Unicode code points within the supplied excerpt.

Relevance, external caveats and usefulness remain unscored. Full sources and signatures: maintainer view.
```

### C2 — `disabled`

```text
Experimental inspection; not an approved response.

### st.button · disabled · Streamlit 1.49.0 (USER-reported)

Source checks requiring review:

- Header and signature defaults cannot be compared safely; header: is; signature: False. These observations do not choose a corrected or actual runtime default.
- Supplied span length differs from excerpt length: 3754 versus 3752 Unicode code points; original-file mapping is unverified.
- Other parameters in this same source have 3 unresolved defaults. This does not disprove the selected quotation; details remain in the maintainer view.

> disabled: bool; default=is
> An optional boolean that disables the button if set to True.
> The default is False.
>
>

[Supplied documentation](https://github.com/streamlit/docs/blob/695e6ce2fb1b23afc6df66b40420ab0013ad72fd/python/streamlit.json). Quotation offsets [2606,2717) are Unicode code points within the supplied excerpt.

Relevance, external caveats and usefulness remain unscored. Full sources and signatures: maintainer view.
```

## قبل از اتصال واقعی

اختلاف طول span، اثبات خرابی index نیست: trim فاصله‌های مرز در قرارداد فعلی می‌تواند آن را توضیح دهد. بازسازی دو newline با طول و prefix شانزده‌رقمی hash این سه chunk سازگار است؛ raw document، hash کامل و mapping اصلی authenticate نشده‌اند. [مشاهدهٔ normalization](boundary-normalization-observation-v1.json).

review انسانی و سنجش usefulness، بررسی استخراج default/span با مرجع خام، آزمایش واقعی انتخاب مدل و مسیرهای غیرپاسخ، و قرارداد نسخه‌دار تحویل/approval باقی‌اند. این مثال‌ها نیاز به سؤال اضافی کاربر ندارند؛ کمبود source یا provenance را به کاربر واگذار نمی‌کنیم.

AI review در sidecar جداست و وارد payload مدل یا corpus نمی‌شود. تمام هشت attempt و هفت turn قبلی، از جمله شکست‌ها، حفظ‌اند. A3، B1 و Enum با این inspection حل نشده‌اند؛ مسیر زندهٔ جلسه، halt، سه hold، corpus/exclusion و gold ثابت مانده‌اند.

[شرح فارسی](../../docs/core-parameter-review.fa.md)، [AI review با spanهای پشتیبان](ai-review-v1.json)، [روش بازتولید](README.md) و [verification جاری](verification-v2.json).
