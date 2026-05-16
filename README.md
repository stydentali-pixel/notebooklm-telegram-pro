# NotebookLM + Media Telegram Pro

بوت تليجرام واحد يعمل على Railway ويجمع بين:

- قسم NotebookLM: مصادر، ملخص، سؤال وجواب، صوت، فيديو، شرائح، إنفوجرافيك، كويز، بطاقات، خريطة ذهنية، جدول، تقرير.
- قسم التحميل: استخراج الجودات عبر `yt-dlp`، اختيار فيديو/صوت، MP3/M4A/WEBM، وتقطيع الفيديو عبر `ffmpeg`.

## أوامر البوت

### القائمة

```text
/start
/notebooklm
/downloads
/status
/jobs
```

### NotebookLM

```text
/new عنوان الدفتر
/source رابط أو إرسال ملف PDF/DOCX/TXT/صوت/فيديو
/summary
/ask سؤالك
/audio
/video
/slides
/infographic
/quiz
/cards
/mindmap
/table
/report
/auth
/setwebhook
```

### التحميل

```text
/fetch رابط
/download رابط
```

بعد إرسال الرابط، يعرض البوت أزرارًا لاختيار:

- فيديو: 144p / 240p / 360p / 480p / 720p / 1080p / أعلى إن توفر.
- صوت: MP3 64kbps / 128kbps / 192kbps / M4A / WEBM.

### تقطيع الفيديو

```text
/trim رابط 00:00:10 00:00:30
/trim رابط 10 30
```

## متغيرات Railway المطلوبة

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
ADMIN_IDS=224659571
BASE_URL=https://your-app.up.railway.app

NOTEBOOKLM_AUTH_JSON=
NOTEBOOKLM_HL=ar
NOTEBOOKLM_PROFILE=default

DATA_DIR=/app/data
DOWNLOAD_DIR=/app/downloads
UPLOAD_DIR=/app/uploads
JOB_TIMEOUT_SECONDS=900
SOURCE_TIMEOUT_SECONDS=240
MAX_TELEGRAM_FILE_MB=45
DOWNLOAD_MAX_FILE_MB=45
DOWNLOAD_TIMEOUT_SECONDS=900
EXTRACT_TIMEOUT_SECONDS=120

# اختياري لتحسين تحميل YouTube
YTDLP_COOKIES_TXT=
```

لا تحفظ `NOTEBOOKLM_AUTH_JSON` أو `YTDLP_COOKIES_TXT` داخل GitHub.

## نشر Railway

```bash
railway link
railway variable set BASE_URL=https://your-app.up.railway.app
railway variable set TELEGRAM_BOT_TOKEN=xxx
railway variable set TELEGRAM_WEBHOOK_SECRET=secret
railway variable set ADMIN_IDS=224659571
railway redeploy --yes
```

بعد النشر:

```text
https://your-app.up.railway.app/health
```

ثم داخل تليجرام:

```text
/setwebhook
/start
```

## فحص محلي قبل الرفع

```bash
python -m compileall app
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## ملاحظات مهمة

- لا توجد قاعدة بيانات Supabase حاليًا. التخزين المحلي JSON في `/app/data`.
- YouTube قد يطلب تحققًا من الجلسة على سيرفرات مثل Railway. عندها استخدم `YTDLP_COOKIES_TXT` من حساب مخصص للتجربة.
- الملفات الكبيرة قد تتجاوز حد تليجرام. غيّر `DOWNLOAD_MAX_FILE_MB` حسب خطتك وحدود البوت.
