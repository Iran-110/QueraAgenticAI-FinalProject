# مقایسهٔ قابل بازبینی — C4x

این برگه برای بررسی candidate آفلاین است؛ پاسخ‌های زیر را مدل تازه انتخاب نکرده و UI فعلی هم آن‌ها را تولید نمی‌کند. ورودی، شواهد همان rehearsal آشکار C4v است. انتخاب‌ها را پس از مشاهدهٔ متن‌های طولانی نوشتیم؛ هشت attempt و هفت turn اصلی، از جمله شکست‌ها، در [گزارش کامل](replay-result-v2.json) مانده‌اند.

## نتیجهٔ نمایش

| turn | پارامتر | draft اصلی | کنترل فقط همان source | candidate | کاهش نسبت به اصلی |
| --- | --- | ---: | ---: | ---: | ---: |
| B2 | `icon` | 9551 | 3434 | 1357 | 85.8% |
| C1 | `type` | 9190 | 4552 | 1193 | 87.0% |
| C2 | `disabled` | 4552 | 4552 | 860 | 81.1% |

تعریف کامل `icon`، هر سه گزینهٔ `type` و تعریف `disabled` عیناً حفظ شده‌اند. معیار این مقایسه کوتاه‌شدن نمایش و حفظ ساختاری متن است؛ نمرهٔ relevance، پشتیبانی معنایی یا usefulness نداریم.

ستون «فقط همان source» یک diagnostic تألیفی و پس از مشاهده است: renderer قبلی روی همان plan با یک source منتخب اصلی اجرا شد. متن qualification دو renderer هم فرق می‌کند؛ این مقایسه اثر خالص یک عامل بر مدل را نشان نمی‌دهد. `C2` از ابتدا یک source داشت، بنابراین کاهش آن حاصل حذف sourceهای دیگر نیست.

## متن دقیق candidateها

متن انگلیسی زیر نمایش خروجی renderer آزمایشی است، بدون خلاصه‌سازی دستی؛ فقط فاصله‌های انتهای خط در این Markdown حذف شده‌اند. متن دقیقِ خروجی و `review_text` کامل در JSON محفوظ‌اند؛ مقدار `semantic_support` تهی و review انسانی الزامی است.

### B2 — `icon`

نسخهٔ USER: `1.39.0`؛ source: `docstring:1.39.0:streamlit.button`؛ span متن خام در chunk: `[1486,2083)`. [منبع ثبت‌شده](https://github.com/streamlit/docs/blob/695e6ce2fb1b23afc6df66b40420ab0013ad72fd/python/streamlit.json).

```text
Selected exact parameter quotations from supplied documentation. The source version metadata matches the current USER-reported Streamlit version 1.39.0; this does not verify relevance, applicability, a diagnosis or a fix. Other parameters and source-wide caveats may matter; complete original records remain in the review view. Human review is required.

API: st.button; parameter: icon; chunk: doc:1.39.0:247abc16624b2e96e3169c26:0:2698:348e29001cbb5d5a; excerpt characters [1486,2083).
Signature supplied by the source (other parameters are not selected):
> st.button\(label, key=None, help=None, on\_click=None, args=None, kwargs=None, \*, type="secondary", icon=None, disabled=False, use\_container\_width=False\)

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
```

### C1 — `type`

نسخهٔ USER: `1.49.0`؛ source: `docstring:1.49.0:streamlit.button`؛ span متن خام در chunk: `[1581,2009)`. [منبع ثبت‌شده](https://github.com/streamlit/docs/blob/695e6ce2fb1b23afc6df66b40420ab0013ad72fd/python/streamlit.json).

```text
Selected exact parameter quotations from supplied documentation. The source version metadata matches the current USER-reported Streamlit version 1.49.0; this does not verify relevance, applicability, a diagnosis or a fix. Other parameters and source-wide caveats may matter; complete original records remain in the review view. Human review is required.

API: st.button; parameter: type; chunk: doc:1.49.0:0e3fc0224f3d3f9fbc9fd032:0:3754:7bd993a4e7d0104f; excerpt characters [1581,2009).
Signature supplied by the source (other parameters are not selected):
> st.button\(label, key=None, help=None, on\_click=None, args=None, kwargs=None, \*, type="secondary", icon=None, disabled=False, use\_container\_width=None, width="content"\)

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
```

### C2 — `disabled`

نسخهٔ USER: `1.49.0`؛ source: `docstring:1.49.0:streamlit.button`؛ span متن خام در chunk: `[2606,2717)`. [منبع ثبت‌شده](https://github.com/streamlit/docs/blob/695e6ce2fb1b23afc6df66b40420ab0013ad72fd/python/streamlit.json).

```text
Selected exact parameter quotations from supplied documentation. The source version metadata matches the current USER-reported Streamlit version 1.49.0; this does not verify relevance, applicability, a diagnosis or a fix. Other parameters and source-wide caveats may matter; complete original records remain in the review view. Human review is required.

API: st.button; parameter: disabled; chunk: doc:1.49.0:0e3fc0224f3d3f9fbc9fd032:0:3754:7bd993a4e7d0104f; excerpt characters [2606,2717).
Signature supplied by the source (other parameters are not selected):
> st.button\(label, key=None, help=None, on\_click=None, args=None, kwargs=None, \*, type="secondary", icon=None, disabled=False, use\_container\_width=None, width="content"\)

> disabled: bool; default=is
> An optional boolean that disables the button if set to True.
> The default is False.
>
>
```

## نکته‌ای دربارهٔ کیفیت خود source

در `type`، headerِ `default=None` با signature و بدنهٔ `secondary` سازگار نیست؛ در `disabled` هم عبارت `default=is` با signature و بدنهٔ `False` تفاوت دارد. candidate این داده‌ها را پنهان یا اصلاح نمی‌کند. کوتاه‌بودن، از منبع ناسازگار یک پاسخ تأییدشده نمی‌سازد؛ استخراج/متن مرجع باید جدا بررسی شود.

CRLF فقط در نمایش به LF تبدیل می‌شود. متن خام، span، source hash و passage hash دست‌نخورده‌اند. caveat بیرون از پارامتر ممکن است لازم باشد؛ کامل‌بودن واحد به معنی کامل‌بودن استدلال نیست.

## چه چیزهایی هنوز بازند؟

- multiselect در A3 همچنان پاسخ کم‌ربط دارد؛ این replay آن را عوض نمی‌کند.
- retrieval miss و escalation مربوط به B1 حفظ شده‌اند.
- برای Enum آزمایش یا fix تازه نداریم.
- انتخاب پارامترها هنوز تألیفی است؛ آزمایش تازهٔ انتخاب مدل، داوری انسانی و اتصال نسخه‌دار جدا لازم‌اند.
- ledger، halt، سه hold، corpus/exclusion، gold و مسیر زندهٔ جلسه تغییر نکرده‌اند؛ هیچ API پرداختی فراخوانی نشده است.

[روش و محدودیت‌ها](README.md)، [پروتکل اصلی](protocol-v1.json)، [اصلاحیهٔ review](protocol-amendment-v1.json)، [کنترل پس از مشاهده](source-only-diagnostic-v1.json) و [verification](verification-v1.json).
