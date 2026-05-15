# NotebookLM Telegram Pro for Railway + Cloudflare

بوت تليجرام شخصي لتجربة خدمات NotebookLM عبر `notebooklm-py` على Railway، مع Cloudflare Worker اختياري كبوابة أمامية.

> مهم: لا تضع توكن تليجرام أو جلسة Google داخل GitHub. ضعها فقط في Railway Variables.

## الميزات

- Webhook حقيقي عبر FastAPI.
- تشغيل على Railway مباشرة.
- Cloudflare Worker اختياري كـ gateway.
- جلسة NotebookLM عبر `NOTEBOOKLM_AUTH_JSON`.
- دعم إضافة المصادر:
  - روابط ويب.
  - YouTube.
  - ملفات Telegram مثل PDF, DOCX, TXT, MP3, MP4, صور.
- أوامر NotebookLM:
  - `/summary`
  - `/ask`
  - `/audio`
  - `/video`
  - `/slides`
  - `/infographic`
  - `/quiz`
  - `/cards`
  - `/mindmap`
  - `/table`
  - `/report`
- نظام مهام خفيف بدون Supabase الآن.
- حفظ جلسة المستخدم محليًا في `data/state.json`.

## المتغيرات المطلوبة في Railway

ضعها من Railway Dashboard → Variables:

```env
TELEGRAM_BOT_TOKEN=ضع_توكن_البوت_هنا
TELEGRAM_WEBHOOK_SECRET=ضع_سر_عشوائي_طويل
ADMIN_IDS=224659571
BASE_URL=https://your-app.up.railway.app
NOTEBOOKLM_AUTH_JSON=ضع_جلسة_NotebookLM_كسطر_واحد
NOTEBOOKLM_HL=ar
NOTEBOOKLM_PROFILE=default
APP_NAME=NotebookLM Telegram Pro
DATA_DIR=/app/data
DOWNLOAD_DIR=/app/downloads
UPLOAD_DIR=/app/uploads
JOB_TIMEOUT_SECONDS=900
SOURCE_TIMEOUT_SECONDS=240
AUTO_DELETE_NOTEBOOKS=false
MAX_TELEGRAM_FILE_MB=45
```

لتوليد سر عشوائي:

```bash
python scripts/random_secret.py
```

## تجهيز جلسة NotebookLM

على جهازك المحلي:

```bash
pip install notebooklm-py
notebooklm login
notebooklm auth check --test
```

ابحث عن ملف الجلسة، غالبًا يكون داخل:

```txt
~/.notebooklm/storage_state.json
```

حوّله إلى سطر واحد:

```bash
python scripts/one_line_auth.py ~/.notebooklm/storage_state.json
```

انسخ الناتج إلى Railway Variable باسم:

```env
NOTEBOOKLM_AUTH_JSON
```

## تشغيل محلي

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## النشر على Railway

1. ارفع المشروع إلى GitHub.
2. افتح Railway.
3. New Project → Deploy from GitHub Repo.
4. أضف المتغيرات السابقة.
5. بعد النشر افتح:

```txt
https://your-app.up.railway.app/health
```

6. اضبط الويب هوك:

```txt
https://your-app.up.railway.app/set-telegram-webhook?secret=TELEGRAM_WEBHOOK_SECRET
```

أو من داخل البوت كأدمن:

```txt
/setwebhook
```

## أوامر البوت

```txt
/start
/new عنوان الدفتر
/source https://example.com
ارفع ملف PDF مباشرة للبوت
/summary
/ask ما أهم النقاط؟
/audio
/video
/slides
/infographic
/quiz
/cards
/mindmap
/table
/report
/jobs
/status
/auth
/setwebhook
```

## Cloudflare Worker اختياري

بعد أن يعمل Railway، يمكنك نشر `cloudflare-worker/worker.js`.

متغيرات Cloudflare Worker:

```env
RAILWAY_WEBHOOK_URL=https://your-app.up.railway.app/telegram/webhook
TELEGRAM_WEBHOOK_SECRET=نفس_السر_الموجود_في_Railway
GATEWAY_SECRET=سر_اختياري_لفحص_health
```

ثم اجعل Telegram Webhook يشير إلى رابط Cloudflare Worker بدل Railway:

```txt
https://your-worker.your-subdomain.workers.dev/telegram/webhook
```

## ملاحظات مهمة

- هذه نسخة تجربة شخصية قوية بدون Supabase.
- Railway filesystem قد لا يكون دائمًا حسب إعدادات الخدمة. لاحقًا نضيف Supabase PostgreSQL + Storage.
- الفيديو قد يستغرق وقتًا طويلًا، وبعض ميزاته قد تتطلب توفرها في حساب Google/NotebookLM نفسه.
- `notebooklm-py` يستخدم واجهات غير رسمية وجلسة Google، لذلك قد تحتاج تحديث الجلسة إذا انتهت.
- لا تستخدم حساب Google الشخصي الأساسي. الأفضل حساب مخصص للتجربة.
