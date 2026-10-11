# Streamlit RAG Module (Data Ingestion & Retrieval)

این ماژول مسئولیت دریافت، پاک‌سازی، چانک‌بندی و بازیابی اطلاعات (RAG) از مستندات و گزارش‌های گیت‌هاب Streamlit را بر عهده دارد.

## پیش‌نیازها و نصب
این بخش از دیتابیس لوکال ChromaDB استفاده می‌کند. برای نصب وابستگی‌ها:
\\\ash
uv add chromadb
\\\

## ساخت دیتابیس و ایندکس کردن داده‌ها (Data Ingestion)
داده‌های اولیه در پوشه streamlit-data-for-dev-test قرار دارند. برای جلوگیری از Data Leakage، گزارش‌های لو رفته در development_exposure.json و کامنت‌های ربات‌ها فیلتر شده‌اند.
برای ساخت دیتابیس (فقط یک‌بار اجرا شود):
\\\ash
uv run python src/agent_app/retrieval/retriever.py
\\\
این دستور فایل .chroma_db را می‌سازد که شامل متادیتاهای دقیق (ورژن، لینک سورس و...) است.

## اتصال به هسته مرکزی (Integration)
کلاس ChromaRetrieverAdapter در مسیر src/agent_app/retrieval/adapter.py پیاده‌سازی شده است. این کلاس متد search(request: RetrievalRequest) را دقیقاً مطابق با کانتراکت‌های EvidenceBundle و EvidenceHit ایجنت مرکزی (با هندل کردن محدودیت ۲۰ هزار کاراکتر) ارائه می‌دهد و قابلیت Multi-Query Retrieval دارد.
